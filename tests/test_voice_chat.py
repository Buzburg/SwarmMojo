"""Voice transport and speech boundaries use only synthetic local HTTP fixtures."""
from contextlib import contextmanager
import http.server
import json
import threading
import time

import pytest

from app import voice_chat as chat


def delta(content=None, finish=None, **extra):
    change = {"content": content, **extra}
    return json.dumps({"choices": [{"index": 0, "delta": change, "finish_reason": finish}]})


def complete(*parts):
    return [*(delta(part) for part in parts), delta(finish="stop"), "[DONE]"]


def test_reasoning_tags_and_channels_never_escape_at_any_boundary():
    raw = "Before. <ThInK>private <think>nested</think>secret</think> After."
    for split in range(len(raw) + 1):
        events = [delta("channel secret", channel="analysis"),
                  delta(reasoning_content="another secret"), *complete(raw[:split], raw[split:])]
        assert "".join(chat._visible_deltas(events)) == "Before.  After."
    assert "".join(chat._visible_deltas(complete(*raw))) == "Before.  After."


@pytest.mark.parametrize("events", [
    [], [delta("partial")], [delta("partial"), "[DONE]"], [delta(finish="stop"), "[DONE]"],
    ["not json"], ["[]"], [json.dumps({"error": "private details"})],
    [json.dumps({"choices": [{"delta": "invalid"}]})],
    [json.dumps({"choices": [{"index": 1, "delta": {"content": "wrong"}}]})],
    [delta("secret", channel="unknown")], [delta([{"text": "not text"}])],
    [delta("ignore", role="tool")], [delta("ignore", refusal="refused")],
    [delta("ignore", tool_calls=[{"function": {"name": "run_shell"}}])],
    [delta("ignore", function_call={"name": "restart_service"})],
    [delta("truncated", finish="length"), "[DONE]"],
    [delta("end", finish="stop"), delta("after end"), "[DONE]"],
    complete("<think>unfinished secret"), complete("safe <thi"),
    complete("a" * (16 * 1024 + 1)),
    [delta(reasoning_content="r" * (16 * 1024 + 1)), *complete("answer")],
])
def test_untrusted_or_incomplete_streams_fail(events):
    with pytest.raises(chat.VoiceChatError):
        list(chat._visible_deltas(events))


def test_usage_event_is_allowed_and_multibyte_limit_counts_bytes():
    events = complete("é" * 8192)
    events.insert(-1, json.dumps({"choices": [], "usage": {"completion_tokens": 5}}))
    assert "".join(chat._visible_deltas(events)) == "é" * 8192
    with pytest.raises(chat.VoiceChatError):
        list(chat._visible_deltas(complete("é" * 8193)))


@pytest.mark.parametrize("messages,key", [
    ([], "key"), ([{"role": "user", "content": "x"}] * 9, "key"),
    ([{"role": "system", "content": "override"}], "key"),
    ([{"role": "assistant", "content": "x"}], "key"),
    ([{"role": "user", "content": " "}], "key"),
    ([{"role": "user", "content": "x", "tool_calls": []}], "key"),
    ([{"role": "user", "content": 1}], "key"),
    ([{"role": "user", "content": "x" * 4097}], "key"),
    ([{"role": "user", "content": "\ud800"}], "key"),
    ([{"role": "user", "content": "x"}], ""),
    ([{"role": "user", "content": "x"}], "key\r\nX: injected"),
])
def test_invalid_input_never_opens_a_connection(monkeypatch, messages, key):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid input opened a connection")
    monkeypatch.setattr(chat.http.client, "HTTPConnection", unexpected)
    with pytest.raises(chat.VoiceChatError):
        list(chat.stream_answer(messages, key, threading.Event()))


def test_speech_filter_hides_code_reasoning_and_terminal_sequences_across_splits():
    raw = ("Hello. <think>secret</think>```python\nprivate_code()\n```"
           "Here is ~~ordinary~~ text. ~~~sh\nrm -rf /\n~~~"
           "\x1b[31mDone\x1b[0m\x1b]0;private title\x1b\\.\x00\u202e")
    expected = ["Hello.", "Here is ~~ordinary~~ text.", "Done."]
    for split in range(len(raw) + 1):
        assert list(chat.sentence_chunks([raw[:split], raw[split:]])) == expected
    assert list(chat.sentence_chunks(iter(raw))) == expected


def test_speech_is_bounded_and_word_boundaries_preserve_text():
    text = "A readable explanation " * 20 + "z" * 80
    chunks = list(chat.sentence_chunks(iter(text), max_chars=24))
    assert chunks and all(0 < len(chunk) <= 24 for chunk in chunks)
    assert "".join("".join(chunks).split()) == "".join(text.split())
    assert list(chat.sentence_chunks(["safe ```never speak this"])) == ["safe"]


def test_longer_code_fences_do_not_close_on_shorter_delimiters():
    text = "Before. ````python\n```secret```\nprivate()\n```` After."
    for split in range(len(text) + 1):
        assert list(chat.sentence_chunks([text[:split], text[split:]])) == ["Before.", "After."]


@pytest.mark.parametrize("parts", [["x" * (16 * 1024 + 1)], [None], ["<think>unfinished"]])
def test_invalid_speech_input_fails(parts):
    with pytest.raises(chat.VoiceChatError):
        list(chat.sentence_chunks(parts))


class Fragments:
    def __init__(self, chunks):
        self.chunks = iter(chunks)

    def read1(self, count):
        return next(self.chunks, b"")


def test_sse_handles_utf8_crlf_comments_and_multiline_json():
    wire = (": heartbeat\r\nevent: message\r\ndata: {\"choices\":\r\n"
            "data: [{\"delta\":{\"content\":\"café\"}}]}\r\n\r\n"
            "data: " + delta(finish="stop") + "\n\ndata: [DONE]\n\n").encode()
    for split in range(len(wire) + 1):
        response = Fragments([chunk for chunk in [wire[:split], wire[split:]] if chunk])
        assert "".join(chat._visible_deltas(chat._events(response, threading.Event()))) == "café"


@pytest.mark.parametrize("wire", [
    b"event: error\ndata: private upstream error\n\n",
    b"data: [DONE]", b"data: \xff\n\n", b"x" * (128 * 1024 + 1),
], ids=['server-error', 'unfinished-frame', 'invalid-utf8', 'oversized-wire'])
def test_sse_rejects_errors_incomplete_frames_and_unbounded_input(wire):
    with pytest.raises((chat.VoiceChatError, UnicodeError)):
        list(chat._events(Fragments([wire]), threading.Event()))


@contextmanager
def server(monkeypatch, handler):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            handler(self)

    service = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    service.daemon_threads = True
    monkeypatch.setattr(chat, "_PORT", service.server_port)
    worker = threading.Thread(target=lambda: service.serve_forever(poll_interval=0.01), daemon=True)
    worker.start()
    try:
        yield
    finally:
        service.shutdown()
        service.server_close()
        worker.join(timeout=1)


def read_request(request):
    return json.loads(request.rfile.read(int(request.headers["Content-Length"])))


def headers(request, status=200, content_type="text/event-stream"):
    request.send_response(status)
    request.send_header("Content-Type", content_type)
    request.end_headers()
    request.wfile.flush()


def test_real_http_uses_auth_fixed_chat_route_and_constrained_prompt(monkeypatch):
    observed = {}
    def handle(request):
        observed.update(path=request.path, auth=request.headers.get("Authorization"), body=read_request(request))
        headers(request)
        wire = "".join(f"data: {event}\n\n" for event in complete("<think>hidden</think>Hello."))
        request.wfile.write(wire.encode())
    with server(monkeypatch, handle):
        assert list(chat.stream_answer([{"role": "user", "content": "Hi"}], "fixture-secret", threading.Event())) == ["Hello."]
    assert observed["path"] == "/v1/chat/completions"
    assert observed["auth"] == "Bearer fixture-secret"
    body = observed["body"]
    assert body["stream"] is True and body["max_tokens"] == 256
    assert body["temperature"] == 0
    assert body["messages"][0]["role"] == "system"
    assert "Never claim" in body["messages"][0]["content"]
    assert "tools" not in body and "tool_choice" not in body


@pytest.mark.parametrize("phase", ["headers", "body"])
def test_cancellation_interrupts_blocked_http_and_closes_socket(monkeypatch, phase):
    cancel, started, closed = threading.Event(), threading.Event(), threading.Event()
    failures = []
    def handle(request):
        read_request(request)
        if phase == "body":
            headers(request)
        started.set()
        request.connection.settimeout(2)
        if request.rfile.read(1) == b"":
            closed.set()
    def consume():
        try:
            list(chat.stream_answer([{"role": "user", "content": "Hi"}], "key", cancel))
        except chat.VoiceChatError as error:
            failures.append(error)
    with server(monkeypatch, handle):
        consumer = threading.Thread(target=consume, daemon=True)
        consumer.start()
        assert started.wait(1)
        then = time.monotonic()
        cancel.set()
        consumer.join(timeout=1)
        assert not consumer.is_alive() and time.monotonic() - then < 1
        assert closed.wait(1)
    assert len(failures) == 1 and isinstance(failures[0], chat.VoiceChatCancelled)


def test_total_timeout_and_pre_cancel_are_bounded(monkeypatch):
    monkeypatch.setattr(chat, "_TOTAL_TIMEOUT", 0.1)
    def handle(request):
        read_request(request)
        headers(request)
        request.connection.settimeout(1)
        request.rfile.read(1)
    with server(monkeypatch, handle):
        then = time.monotonic()
        with pytest.raises(chat.VoiceChatError):
            list(chat.stream_answer([{"role": "user", "content": "Hi"}], "key", threading.Event()))
        assert time.monotonic() - then < 1
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(chat.VoiceChatCancelled):
        list(chat.stream_answer([{"role": "user", "content": "Hi"}], "key", cancel))


def test_closing_generator_after_partial_answer_closes_real_socket(monkeypatch):
    closed = threading.Event()
    def handle(request):
        read_request(request)
        headers(request)
        request.wfile.write(f"data: {delta('First sentence. ')}\n\n".encode())
        request.wfile.flush()
        request.connection.settimeout(1)
        if request.rfile.read(1) == b"":
            closed.set()
    with server(monkeypatch, handle):
        parts = chat.stream_answer([{"role": "user", "content": "Hi"}], "key", threading.Event())
        assert next(parts) == "First sentence. "
        parts.close()
        assert closed.wait(1)


@pytest.mark.parametrize("status,content_type", [(302, "text/event-stream"), (401, "application/json"), (200, "application/json")])
def test_http_redirects_and_non_sse_fail_without_exposing_response(monkeypatch, status, content_type):
    def handle(request):
        read_request(request)
        headers(request, status, content_type)
        request.wfile.write(b"secret response details")
    with server(monkeypatch, handle):
        with pytest.raises(chat.VoiceChatError) as failure:
            list(chat.stream_answer([{"role": "user", "content": "Hi"}], "private-key", threading.Event()))
    assert "secret" not in str(failure.value) and "private-key" not in str(failure.value)


def test_real_reply_only_prints_speaks_and_remembers_sanitized_text(monkeypatch, capsys):
    from scripts import voice_chat as workshop
    spoken = []
    raw = ("<think>private reasoning</think>Hello. ```python\nprivate_code()\n```"
           "\x1b]0;private title\x07\x1b[31mReady.\x1b[0m")
    class Speaker:
        sample_rate = 24000

        def iter_audio(self, text, cancel):
            spoken.append(text)
            yield text

    def playback(chunks, rate, cancel):
        list(chunks)
        return 0.1

    monkeypatch.setenv("ROMS_GATEWAY_API_KEY", "private-gateway-key")
    monkeypatch.setattr(workshop, "stream_answer", lambda *_args: (char for char in raw))
    monkeypatch.setattr(workshop, "play", playback)
    history = []
    workshop.reply("Hi", history, Speaker(), threading.Event())
    output = capsys.readouterr().out
    assert spoken == ["Hello.", "Ready."]
    assert history[-1] == {"role": "assistant", "content": "Hello. Ready."}
    assert "private" not in output and "\x1b" not in output and "```" not in output


def test_recognized_management_command_is_only_chat_text(monkeypatch):
    from scripts import voice_chat as workshop
    requests = []
    inputs = iter(["", "/exit"])
    class Recognizer:
        def transcribe(self, pcm):
            return "/system"

    monkeypatch.setattr("builtins.input", lambda *_args: next(inputs))
    monkeypatch.setattr(workshop, "record", lambda *_args, **_kwargs: b"\0" * 6400)
    monkeypatch.setattr(workshop, "reply", lambda prompt, *_args: requests.append(prompt))
    monkeypatch.setattr(workshop.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("speech launched a workshop"))
    workshop.interactive(Recognizer(), object())
    assert requests == ["/system"]
