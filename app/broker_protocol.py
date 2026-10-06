"""Versioned broker framing contract; no request can grant execution authority."""
import json
import re

from app.json_protocol import unique_object

MAX_FRAME = 65536
MAX_DEPTH = 16


class ProtocolError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def error_response(code: str, message: str, request_id: str | None = None) -> dict:
    return {'v': 1, 'id': request_id, 'ok': False, 'error': {'code': code, 'message': message}}


def parse(frame: bytes) -> dict:
    if len(frame) > MAX_FRAME:
        raise ProtocolError('REQUEST_TOO_LARGE', 'Request exceeds the 65536-byte frame limit')
    try:
        text = frame.decode('utf-8', errors='strict')
    except UnicodeError as error:
        raise ProtocolError('INVALID_REQUEST', 'Request must be valid UTF-8') from error
    # Count container nesting without interpreting braces inside JSON strings.
    depth, quoted, escaped = 0, False, False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == '\\':
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in '{[':
            depth += 1
            if depth > MAX_DEPTH:
                raise ProtocolError('INVALID_REQUEST', 'JSON nesting exceeds 16 containers')
        elif character in '}]':
            depth -= 1
    def invalid_constant(value: str) -> None:
        raise ValueError('Non-finite JSON number')
    try:
        value = json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    except (ValueError, RecursionError) as error:
        raise ProtocolError('INVALID_REQUEST', 'Request must be one unambiguous JSON object') from error
    if type(value) is not dict or set(value) != {'v', 'id', 'action', 'args'}:
        raise ProtocolError('INVALID_REQUEST', 'Expected exactly v, id, action and args')
    if type(value['v']) is not int or value['v'] != 1:
        raise ProtocolError('UNSUPPORTED_VERSION', 'Only integer protocol version 1 is supported')
    if type(value['id']) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}', value['id']):
        raise ProtocolError('INVALID_REQUEST', 'Request id must be 1–64 ASCII letters, digits, underscores or hyphens')
    if type(value['action']) is not str or type(value['args']) is not dict:
        raise ProtocolError('INVALID_REQUEST', 'Action must be text and args must be an object')
    return value


def encode(result: dict) -> str:
    try:
        encoded = json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(',', ':')) + '\n'
    except (TypeError, ValueError):
        return json.dumps(error_response('SERVICE_FAILURE', 'Local service returned invalid response data', result.get('id'))) + '\n'
    if len(encoded.encode('utf-8')) > MAX_FRAME:
        encoded = json.dumps(error_response('RESPONSE_TOO_LARGE', 'Response exceeds the broker limit', result.get('id'))) + '\n'
    return encoded
