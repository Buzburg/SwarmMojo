import copy

import pytest

from app.goose_response import decode_completed_response


def reply(content, *, model='goose-2.9b', finish='stop'):
    return {'model': model, 'choices': [{'finish_reason': finish, 'message': {'role': 'assistant', 'content': content}}]}


@pytest.mark.parametrize('content,answer,thought', [
    ('<think>\n</think>\nURGENT', 'URGENT', None),
    ('<answer>URGENT</answer>', 'URGENT', None),
    ('<thinking>Fixture reasoning</thinking><answer>56</answer>', '56', 'Fixture reasoning'),
    ('<think>First</think><think>Second</think>56', '56', 'First\n\nSecond'),
])
def test_complete_envelopes_are_decoded_without_losing_raw_output(content, answer, thought):
    response = decode_completed_response(reply(content))
    assert response['choices'][0]['message']['content'] == answer
    assert response['choices'][0]['message'].get('reasoning_content') == thought
    assert response['roms_response_format']['originals'][0]['content'] == content
    assert response['choices'][0]['finish_reason'] == 'stop'


@pytest.mark.parametrize('content', ['56', 'Example: <answer>56</answer>', '```xml\n<answer>56</answer>\n```',
    '<answer>unfinished', '<think>unfinished', '<think>only reasoning</think>',
    '<answer>outer<answer>inner</answer></answer>', '<answer>56</answer>extra',
    '<think>outer<think>inner</think></think>56',
    '<think></think>' * 5 + '56'])
def test_incomplete_ambiguous_and_quoted_text_is_preserved(content):
    response = reply(content)
    assert decode_completed_response(copy.deepcopy(response)) == response


@pytest.mark.parametrize('model,finish', [('other-model', 'stop'), ('goose-2.9b', 'length')])
def test_other_models_and_incomplete_generations_are_not_rewritten(model, finish):
    response = reply('<answer>56</answer>', model=model, finish=finish)
    assert decode_completed_response(copy.deepcopy(response)) == response


def test_existing_native_reasoning_is_preserved():
    response = reply('<think>Additional</think><answer>56</answer>')
    response['choices'][0]['message']['reasoning_content'] = 'Native'
    decoded = decode_completed_response(response)
    assert decoded['choices'][0]['message']['reasoning_content'] == 'Native\n\nAdditional'
