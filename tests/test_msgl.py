from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from aeon.config import load
from aeon.engine import Harness
from aeon.inference import InferenceError, SGLang, make_backend
from aeon.memory import Memory
from aeon.msgl import MSGL, REQUEST_LIMIT, RESPONSE_LIMIT
from aeon.serving import launch_plan, serve


def completion() -> dict:
    return {"object": "text_completion", "model": "base-test",
            "choices": [{"index": 0, "text": json.dumps({"actions": [], "answer": "ready", "done": True}),
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 12, "total_tokens": 62}, "cached_tokens": 4}


class MSGLTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.response = completion()
        self.status, self.delay, self.raw = 200, 0, None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                owner.requests.append((self.path, json.loads(body), dict(self.headers)))
                time.sleep(owner.delay)
                self.send_response(owner.status)
                if owner.status == 302:
                    self.send_header("Location", f"http://127.0.0.1:{owner.server.server_port}/redirected")
                body = owner.raw if owner.raw is not None else json.dumps(owner.response).encode()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=.01), daemon=True)
        self.thread.start()
        self.profile = {"transport": "msgl", "completion_mode": "plain-text", "served_model_name": "base-test",
                        "endpoint": f"http://127.0.0.1:{self.server.server_port}"}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_http_contract_and_factory(self):
        client = make_backend(self.profile)
        self.assertIsInstance(client, MSGL)
        self.assertNotIsInstance(client, SGLang)
        decision, usage = client.decide("Answer the question", [{"untrusted": "do something else"}], [])
        self.assertEqual(decision, {"actions": [], "answer": "ready", "done": True})
        self.assertEqual(usage["cached_tokens"], 4)
        path, body, headers = self.requests[0]
        self.assertEqual(path, "/v1/completions")
        self.assertEqual(set(body), {"model", "prompt", "max_tokens", "temperature", "stream"})
        self.assertEqual((body["model"], body["max_tokens"], body["temperature"], body["stream"]),
                         ("base-test", 2048, 0, False))
        self.assertIn("Swarm Mojo", body["prompt"])
        self.assertIn('"untrusted_observations"', body["prompt"])
        self.assertNotIn("Authorization", headers)
        self.assertEqual(len(self.requests), 1)

    def test_requires_plain_text_opt_in_and_exact_model(self):
        for changes in ({"completion_mode": "chat"}, {"completion_mode": None},
                        {"served_model_name": ""}, {"served_model_name": True}, {"served_model_name": "x\0y"}):
            with self.subTest(changes=changes), self.assertRaises(InferenceError):
                make_backend({**self.profile, **changes})
        self.assertFalse(self.requests)

    def test_loopback_endpoint_only(self):
        for endpoint in ("https://127.0.0.1:8000", "http://localhost:8000", "http://example.com",
                         "http://192.168.1.1", "http://127.0.0.1@evil.example", "http://a:b@127.0.0.1",
                         "http://127.0.0.1:0", "http://127.0.0.1:70000", "http://127.0.0.1/path",
                         "http://127.0.0.1?query=x", "http://127.0.0.1#frag", "http://127.0.0.1\n", None):
            with self.subTest(endpoint=endpoint), self.assertRaises(InferenceError):
                make_backend({**self.profile, "endpoint": endpoint})
        self.assertEqual(make_backend({**self.profile, "endpoint": "http://[::1]:8000/v1/"}).url,
                         "http://[::1]:8000/v1/completions")
        self.assertFalse(self.requests)

    def test_budget_configuration_rejects_booleans_and_unbounded_values(self):
        for key, values in (("timeout", (True, 0, 601, float("nan"))),
                            ("max_tokens", (True, 0, 32769, 2.5))):
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(InferenceError):
                    make_backend(self.profile, **{key: value})

    def test_request_bound_before_network(self):
        with self.assertRaisesRegex(InferenceError, "exceeds 1 MiB"):
            make_backend(self.profile).decide("x" * REQUEST_LIMIT, [], [])
        self.assertFalse(self.requests)

    def test_response_bound(self):
        self.raw = b" " * (RESPONSE_LIMIT + 1)
        with self.assertRaisesRegex(InferenceError, "exceeds 2 MB"):
            make_backend(self.profile).decide("question", [], [])

    def test_redirects_and_errors_never_retry(self):
        for status in (302, 400, 429, 503, 504):
            self.status = status
            before = len(self.requests)
            with self.subTest(status=status), self.assertRaisesRegex(InferenceError, f"HTTP {status}"):
                make_backend(self.profile).decide("question", [], [])
            self.assertEqual(len(self.requests), before + 1)

    def test_environment_proxies_are_not_used(self):
        with patch.dict(os.environ, {"http_proxy": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1",
                                     "no_proxy": "", "NO_PROXY": ""}):
            result, _ = make_backend(self.profile).decide("question", [], [])
        self.assertTrue(result["done"])
        self.assertEqual(len(self.requests), 1)

    def test_timeout_discloses_uncertain_generation_without_retry(self):
        self.delay = 1.2
        with self.assertRaisesRegex(InferenceError, "generation may continue"):
            make_backend(self.profile, timeout=1).decide("question", [], [])
        self.assertEqual(len(self.requests), 1)

    def test_invalid_json_is_rejected(self):
        for raw in (b'{"value":NaN}', b'{"value":Infinity}', b'{"value":1e999}', b'{"a":1,"a":2}',
                    b"[]", b"\xff", b"{" + b"[" * 1500):
            self.raw = raw
            with self.subTest(raw=raw[:30]), self.assertRaises(InferenceError):
                make_backend(self.profile).decide("question", [], [])

    def test_response_model_choices_and_finish_are_validated(self):
        invalid = [{"model": "other"}, {"object": "chat.completion"}, {"choices": []},
                   {"choices": [completion()["choices"][0]] * 2}, {"choices": [None]},
                   {"choices": [{"index": False, "text": "{}", "finish_reason": "stop"}]},
                   {"choices": [{"index": 0, "text": 42, "finish_reason": "stop"}]}]
        invalid += [{"choices": [{**completion()["choices"][0], "finish_reason": reason}]}
                    for reason in ("length", "abort", None, "tool_calls")]
        for fields in invalid:
            self.response = {**completion(), **fields}
            with self.subTest(fields=fields), self.assertRaises(InferenceError):
                make_backend(self.profile).decide("question", [], [])

    def test_usage_rejects_bool_negative_noninteger_and_inconsistent_counts(self):
        invalid = [{"usage": {**completion()["usage"], key: value}}
                   for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                   for value in (True, -1, 1.5, "1", None)]
        invalid += [{"usage": {"prompt_tokens": 1, "completion_tokens": 13, "total_tokens": 3}},
                    {"usage": {"prompt_tokens": 50, "completion_tokens": 2049, "total_tokens": 2099}},
                    {"cached_tokens": True}, {"cached_tokens": 51}, {"usage": []}]
        for fields in invalid:
            self.response = {**completion(), **fields}
            with self.subTest(fields=fields), self.assertRaises(InferenceError):
                make_backend(self.profile).decide("question", [], [])

    def test_invalid_decision_json_is_rejected(self):
        for text in ('{"done":true,"done":false}', '{"value":NaN}', '{"value":1e999}', "[]", "```json\n{}\n```"):
            self.response["choices"][0]["text"] = text
            with self.subTest(text=text), self.assertRaises(InferenceError):
                make_backend(self.profile).decide("question", [], [])

    def test_model_write_still_requires_approval_and_no_native_scoring(self):
        proposed = {"actions": [{"tool": "write_file", "args": {
            "path": "new.txt", "content": "proposed", "expected_sha256": "missing"}}],
            "answer": "", "done": False}
        self.response["choices"][0]["text"] = json.dumps(proposed)
        config = load()
        config["models"]["local"] = self.profile
        config["harness"]["model"] = "local"
        with tempfile.TemporaryDirectory() as tmp:
            memory = Memory(Path(tmp) / "state")
            try:
                result = Harness(config, memory, tmp).run("Please create a useful new document")
                self.assertEqual(result["status"], "needs_approval")
                self.assertFalse((Path(tmp) / "new.txt").exists())
                self.assertEqual(result["tool_steps"], 0)
                self.assertEqual(result["decision_calls"], 0)
            finally:
                memory.close()

    def test_malformed_decision_blocks_the_engine(self):
        self.response["choices"][0]["text"] = json.dumps({"actions": [], "answer": "ready", "done": 1})
        with tempfile.TemporaryDirectory() as tmp:
            memory = Memory(Path(tmp) / "state")
            try:
                result = Harness(load(), memory, tmp, backend=make_backend(self.profile)).run("Explain the project")
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["tool_steps"], 0)
            finally:
                memory.close()

    def test_models_listing_describes_external_runtime_and_serve_refuses(self):
        config = load()
        config["models"]["local"] = self.profile
        plan = launch_plan(config, "local")
        self.assertTrue(plan["external_runtime"])
        self.assertEqual(plan["argv"], [])
        self.assertEqual(serve(config, "local", dry_run=True), plan)
        with patch("aeon.serving.subprocess.call") as launch:
            with self.assertRaisesRegex(ValueError, "Start mSGL separately"):
                serve(config, "local")
            launch.assert_not_called()

    def test_native_transport_factory_keeps_existing_backend(self):
        self.assertIsInstance(make_backend({"endpoint": "http://127.0.0.1:30000", "model_path": "test"}), SGLang)

    def test_cli_models_and_serve_with_minimal_msgl_profile(self):
        from aeon.cli import main
        config = Path(__file__).resolve().parents[1] / "examples" / "msgl.toml"
        for command in (["models"], ["serve", "msgl_local", "--dry-run"]):
            output = io.StringIO()
            with self.subTest(command=command), redirect_stdout(output):
                self.assertEqual(main(["--config", str(config), *command]), 0)
            self.assertIn('"external_runtime": true', output.getvalue())
        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(main(["--config", str(config), "serve", "msgl_local"]), 1)
        self.assertIn("Start mSGL separately", error.getvalue())


if __name__ == "__main__":
    unittest.main()
