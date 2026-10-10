"""Opt-in, loopback-only client for mSGL's plain-text completion protocol."""

import ipaddress
import json
import math
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from .inference import InferenceError, NoRedirect, SYSTEM, prompt_payload


REQUEST_LIMIT = 1024 * 1024
RESPONSE_LIMIT = 2_000_000


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON property")
        result[key] = value
    return result


def _number(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("Nonfinite JSON number")
    return value


def _constant(text: str) -> object:
    raise ValueError("Nonstandard JSON constant")


def _json(text: str) -> object:
    return json.loads(text, parse_constant=_constant, parse_float=_number, object_pairs_hook=_pairs)


def _endpoint(value: object) -> str:
    if not isinstance(value, str) or any(ord(c) <= 32 for c in value):
        raise InferenceError("mSGL endpoint must be a literal loopback HTTP URL")
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == "http" and parsed.hostname is not None
                 and ipaddress.ip_address(parsed.hostname).is_loopback
                 and parsed.username is None and parsed.password is None
                 and parsed.path in {"", "/", "/v1", "/v1/"}
                 and not parsed.query and not parsed.fragment
                 and (parsed.port is None or 1 <= parsed.port <= 65535))
    except ValueError:
        valid = False
    if not valid:
        raise InferenceError("mSGL endpoint must be a literal loopback HTTP URL without credentials, query, or extra path")
    return f"http://{parsed.netloc}/v1/completions"


class MSGL:
    """No templates, credentials, retries, streaming, or automatic server launch."""

    def __init__(self, profile: dict, timeout: int = 120, max_tokens: int = 2048):
        if profile.get("completion_mode") != "plain-text":
            raise InferenceError("mSGL requires completion_mode='plain-text'; chat templates are unsupported")
        model = profile.get("served_model_name")
        if not isinstance(model, str) or not model.strip() or "\0" in model or len(model) > 512:
            raise InferenceError("mSGL requires an exact served_model_name (the loaded GGUF filename stem)")
        if type(timeout) is not int or not 1 <= timeout <= 600:
            raise InferenceError("mSGL timeout must be an integer from 1 to 600 seconds")
        if type(max_tokens) is not int or not 1 <= max_tokens <= 32768:
            raise InferenceError("mSGL max_tokens must be an integer from 1 to 32768")
        self.profile = dict(profile)
        self.url = _endpoint(profile.get("endpoint"))
        self.model, self.timeout, self.max_tokens = model, timeout, max_tokens

    def _complete(self, prompt: str) -> dict:
        if "\0" in prompt:
            raise InferenceError("mSGL prompt cannot contain NUL")
        try:
            body = json.dumps({"model": self.model, "prompt": prompt, "max_tokens": self.max_tokens,
                               "temperature": 0, "stream": False}, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (ValueError, UnicodeError):
            raise InferenceError("mSGL prompt must be valid UTF-8 text") from None
        if len(body) > REQUEST_LIMIT:
            raise InferenceError("mSGL request exceeds 1 MiB; no request sent")
        request = Request(self.url, data=body, headers={"Content-Type": "application/json"})
        try:
            # Empty proxy configuration keeps loopback data off environment-configured proxies.
            with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise InferenceError(f"mSGL returned HTTP {response.status}; no action executed")
                data = response.read(RESPONSE_LIMIT + 1)
            if len(data) > RESPONSE_LIMIT:
                raise InferenceError("mSGL response exceeds 2 MB; no action executed")
            result = _json(data.decode("utf-8"))
            if not isinstance(result, dict):
                raise InferenceError("mSGL returned a non-object response; no action executed")
            return result
        except HTTPError as exc:
            code = exc.code
            exc.close()
            raise InferenceError(f"mSGL returned HTTP {code}; no retry or action executed") from None
        except (URLError, TimeoutError, OSError, HTTPException) as exc:
            raise InferenceError(f"mSGL request failed ({type(exc).__name__}); generation may continue on the server. No retry or action executed") from None
        except (ValueError, UnicodeError, RecursionError):
            raise InferenceError("mSGL returned invalid JSON; no action executed") from None

    def decide(self, goal: str, events: list[dict], hints: list[dict]) -> tuple[dict, dict]:
        prompt = (SYSTEM + "\nTask data:\n" + prompt_payload(goal, events, hints)
                  + "\nReturn only the JSON decision:\n")
        result = self._complete(prompt)
        try:
            choices, usage = result["choices"], result["usage"]
            if (result.get("object") != "text_completion" or result.get("model") != self.model
                    or not isinstance(choices, list) or len(choices) != 1
                    or not isinstance(choices[0], dict) or type(choices[0].get("index")) is not int
                    or choices[0]["index"] != 0 or not isinstance(choices[0].get("text"), str)
                    or not isinstance(usage, dict)):
                raise ValueError("Invalid completion envelope")
            if choices[0].get("finish_reason") != "stop":
                raise InferenceError("mSGL generation did not finish normally; no action executed")
            counts = {key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
            counts["cached_tokens"] = result["cached_tokens"]
            if (any(type(n) is not int or n < 0 for n in counts.values())
                    or counts["total_tokens"] != counts["prompt_tokens"] + counts["completion_tokens"]
                    or counts["completion_tokens"] > self.max_tokens
                    or counts["cached_tokens"] > counts["prompt_tokens"]):
                raise ValueError("Invalid token usage")
            decision = _json(choices[0]["text"])
            if not isinstance(decision, dict):
                raise ValueError("Decision must be an object")
            return decision, counts
        except (KeyError, ValueError, TypeError, RecursionError):
            raise InferenceError("Malformed mSGL completion or JSON decision; no action executed") from None
