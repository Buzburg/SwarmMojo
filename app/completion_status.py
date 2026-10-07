"""Bounded completion accounting for a transparent OpenAI-compatible proxy.

This observes protocol completion, never tool execution or answer correctness.
Unrecognized or incomplete responses remain proxy data, but cannot count as success.
"""
from __future__ import annotations

import codecs
import json

from app.json_protocol import unique_object

_SUCCESS = {'stop', 'tool_calls', 'function_call'}
_TERMINAL = _SUCCESS | {'length', 'content_filter'}
_MAX_EVENT_CHARS = 262144
_MAX_CHOICES = 128


def _reject_constant(value: str) -> None:
    raise ValueError('Nonfinite JSON value: ' + value)


def _message_valid(message: object) -> bool:
    if type(message) is not dict or message.get('role', 'assistant') != 'assistant':
        return False
    if message.get('content') is not None and type(message['content']) is not str:
        return False
    calls = message.get('tool_calls')
    if calls is not None:
        if type(calls) is not list or not calls:
            return False
        for call in calls:
            if (type(call) is not dict or call.get('type', 'function') != 'function'
                    or type(call.get('id')) is not str or not call['id']):
                return False
            function = call.get('function')
            if (type(function) is not dict or type(function.get('name')) is not str
                    or not function['name'] or type(function.get('arguments')) is not str):
                return False
    function = message.get('function_call')
    if function is not None and (type(function) is not dict or type(function.get('name')) is not str
            or not function['name'] or type(function.get('arguments')) is not str):
        return False
    return type(message.get('content')) is str or calls is not None or function is not None


def response_complete(response: object, expected_choices: int | None = None) -> bool:
    """Whether every choice completed; tool requests are valid proxy responses."""
    if type(response) is not dict or 'error' in response:
        return False
    choices = response.get('choices')
    if type(choices) is not list or not 1 <= len(choices) <= _MAX_CHOICES:
        return False
    if expected_choices is not None and (type(expected_choices) is not int or len(choices) != expected_choices):
        return False
    indices: set[int] = set()
    for position, choice in enumerate(choices):
        if type(choice) is not dict:
            return False
        index = choice.get('index', position)
        if type(index) is not int or index < 0 or index in indices:
            return False
        indices.add(index)
        reason = choice.get('finish_reason')
        message = choice.get('message')
        if type(reason) is not str or reason not in _SUCCESS or not _message_valid(message):
            return False
        if reason in {'tool_calls', 'function_call'} and not message.get(reason):
            return False
    return indices == set(range(len(choices)))


class StreamCompletion:
    """Observe fragmented SSE without altering bytes or retaining response text."""

    def __init__(self, expected_choices: int = 1) -> None:
        self._decoder = codecs.getincrementaldecoder('utf-8')('strict')
        self._pending = ''
        self._data: list[str] = []
        self._event = ''
        self._event_chars = 0
        self._choices: dict[int, str | None] = {}
        self._tools: dict[int, dict[int, set[str]]] = {}
        self._functions: dict[int, set[str]] = {}
        self._valid = type(expected_choices) is int and 1 <= expected_choices <= _MAX_CHOICES
        self._expected_choices = expected_choices
        self._done = False

    def feed(self, chunk: bytes) -> None:
        if not self._valid:
            return
        try:
            self._pending += self._decoder.decode(chunk)
            while '\n' in self._pending:
                line, self._pending = self._pending.split('\n', 1)
                self._line(line.removesuffix('\r'))
            if len(self._pending) + self._event_chars > _MAX_EVENT_CHARS:
                raise ValueError('Oversized SSE event')
        except (ValueError, TypeError, RecursionError):
            self._valid = False
            self._pending, self._data = '', []

    def _line(self, line: str) -> None:
        self._event_chars += len(line)
        if self._event_chars > _MAX_EVENT_CHARS:
            raise ValueError('Oversized SSE event')
        if not line:
            if self._event == 'error':
                raise ValueError('Upstream stream error')
            if self._data:
                self._payload('\n'.join(self._data))
            self._data, self._event, self._event_chars = [], '', 0
        elif line.startswith('data:'):
            self._data.append(line[5:].removeprefix(' '))
        elif line.startswith('event:'):
            self._event = line[6:].strip()

    def _payload(self, data: str) -> None:
        if self._done:
            raise ValueError('Data followed completion marker')
        if data == '[DONE]':
            self._done = True
            return
        value = json.loads(data, object_pairs_hook=unique_object, parse_constant=_reject_constant)
        if type(value) is not dict or 'error' in value or type(value.get('choices')) is not list:
            raise ValueError('Invalid completion event')
        if not value['choices']:
            if type(value.get('usage')) is not dict:
                raise ValueError('Empty completion event')
            return
        event_indices: set[int] = set()
        for choice in value['choices']:
            if type(choice) is not dict:
                raise ValueError('Invalid choice')
            index = choice.get('index', 0)
            if (type(index) is not int or index < 0 or index in event_indices
                    or self._choices.get(index) is not None):
                raise ValueError('Invalid or finished choice')
            event_indices.add(index)
            delta = choice.get('delta')
            if type(delta) is not dict:
                raise ValueError('Invalid delta')
            if delta.get('role', 'assistant') != 'assistant':
                raise ValueError('Invalid response role')
            for field in ('content', 'reasoning_content', 'reasoning', 'refusal'):
                if delta.get(field) is not None and type(delta[field]) is not str:
                    raise ValueError('Invalid text delta')
            if delta.get('tool_calls') is not None and type(delta['tool_calls']) is not list:
                raise ValueError('Invalid tool delta')
            for call in delta.get('tool_calls') or []:
                if (type(call) is not dict or type(call.get('index')) is not int
                        or not 0 <= call['index'] < _MAX_CHOICES
                        or call.get('type', 'function') != 'function'
                        or ('id' in call and type(call['id']) is not str)):
                    raise ValueError('Invalid tool delta')
                function = call.get('function', {})
                if type(function) is not dict or any(type(part) is not str for part in function.values()):
                    raise ValueError('Invalid function delta')
                fields = self._tools.setdefault(index, {}).setdefault(call['index'], set())
                if call.get('id'):
                    fields.add('id')
                self._function_fields(fields, function)
            if delta.get('function_call') is not None and type(delta['function_call']) is not dict:
                raise ValueError('Invalid function delta')
            if any(type(part) is not str for part in (delta.get('function_call') or {}).values()):
                raise ValueError('Invalid function delta')
            if delta.get('function_call') is not None:
                self._function_fields(self._functions.setdefault(index, set()), delta['function_call'])
            reason = choice.get('finish_reason')
            if reason is not None and (type(reason) is not str or reason not in _TERMINAL):
                raise ValueError('Unknown completion reason')
            tools = self._tools.get(index, {})
            if reason == 'tool_calls' and (not tools or any(fields != {'id', 'name', 'arguments'}
                                                           for fields in tools.values())):
                raise ValueError('Incomplete tool metadata')
            if reason == 'function_call' and self._functions.get(index) != {'name', 'arguments'}:
                raise ValueError('Incomplete function metadata')
            self._choices[index] = reason
            if len(self._choices) > _MAX_CHOICES:
                raise ValueError('Too many choices')

    @staticmethod
    def _function_fields(fields: set[str], function: dict) -> None:
        if function.get('name'):
            fields.add('name')
        if 'arguments' in function:
            fields.add('arguments')

    def complete(self) -> bool:
        try:
            self._decoder.decode(b'', final=True)
        except UnicodeError:
            self._valid = False
        return (self._valid and self._done and not self._pending.strip() and not self._data and not self._event
                and len(self._choices) == self._expected_choices
                and set(self._choices) == set(range(len(self._choices)))
                and all(fields == {'id', 'name', 'arguments'} for tools in self._tools.values()
                        for fields in tools.values())
                and all(fields == {'name', 'arguments'} for fields in self._functions.values())
                and all(reason in _SUCCESS for reason in self._choices.values()))
