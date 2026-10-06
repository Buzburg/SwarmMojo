"""Decode complete Goose response envelopes while retaining the original text."""
import re

THOUGHT = re.compile(r'\A\s*<(think|thinking)>(.*?)</\1>\s*', re.DOTALL)
ANSWER = re.compile(r'\A\s*<answer>(.*?)</answer>\s*\Z', re.DOTALL)


def decode_completed_response(response: dict) -> dict:
    if response.get('model') != 'goose-2.9b' or type(response.get('choices')) is not list:
        return response
    originals = []
    for index, choice in enumerate(response['choices']):
        if type(choice) is not dict or choice.get('finish_reason') != 'stop':
            continue
        message = choice.get('message')
        if type(message) is not dict or type(message.get('content')) is not str:
            continue
        original = text = message['content']
        if len(text) > 16384:
            continue
        thoughts = []
        for _ in range(4):
            match = THOUGHT.match(text)
            if not match:
                break
            if '<think>' in match[2] or '<thinking>' in match[2]:
                text = original
                break
            if match[2].strip():
                thoughts.append(match[2])
            text = text[match.end():]
        answer = ANSWER.fullmatch(text)
        if answer and '<answer>' not in answer[1] and '</answer>' not in answer[1]:
            text = answer[1]
        if text == original or not text.strip():
            continue
        # A remaining envelope is malformed/ambiguous; preserve it rather than guessing.
        if text.lstrip().startswith(('<think>', '<thinking>', '<answer>')):
            continue
        previous = message.get('reasoning_content')
        if previous is not None and type(previous) is not str:
            continue
        message['content'] = text
        if thoughts:
            message['reasoning_content'] = '\n\n'.join(([previous] if previous else []) + thoughts)
        originals.append({'choice': index, 'content': original})
    if originals:
        response['roms_response_format'] = {'version': 1, 'originals': originals}
    return response
