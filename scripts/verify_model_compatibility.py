"""Inspect the actual local runtime, tokenizer, prompt and bounded stop behavior."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import httpx
from jinja2 import Environment, StrictUndefined
from scripts.download_rwkv7 import MANIFEST, verify_file
from app.goose_response import decode_completed_response

ROOT = Path(__file__).resolve().parents[1]
TEXTS = ['', 'Hello, world!', '  leading\tand trailing  \n', 'def f():\n\treturn "a\\b"\n\n',
         'café e\u0301 — 日本語 中文 العربية', '👩🏽‍💻 🚀', '<s> <think> literal </think>', 'before\x00after']


def verify(client: httpx.Client) -> dict:
    def call(path: str, body: dict | None = None) -> dict:
        response = client.get(path) if body is None else client.post(path, json=body)
        response.raise_for_status()
        return response.json()
    props = call('/props')
    report = {key: props[key] for key in ('model_alias', 'model_path', 'model_ftype', 'build_info', 'total_slots', 'bos_token', 'eos_token')}
    report['context'] = props['default_generation_settings']['n_ctx']
    report['round_trips'] = []
    for index, text in enumerate(TEXTS):
        tokens = call('/tokenize', {'content': text, 'add_special': False, 'parse_special': False})['tokens']
        assert all(type(token) is int for token in tokens)
        restored = call('/detokenize', {'tokens': tokens})['content']
        report['round_trips'].append({'fixture': index, 'tokens': len(tokens), 'passed': restored == text})
    messages = [{'role': 'system', 'content': 'Preserve code and whitespace.'},
                {'role': 'user', 'content': TEXTS[3]}, {'role': 'assistant', 'content': 'Acknowledged.'},
                {'role': 'user', 'content': 'Next request'}]
    template = (ROOT / 'config/rwkv-user-assistant.jinja').read_text()
    expected = Environment(undefined=StrictUndefined).from_string(template).render(messages=messages, add_generation_prompt=True)
    report['template_matches'] = call('/apply-template', {'messages': messages})['prompt'] == expected
    report['template_sha256'] = hashlib.sha256(template.encode()).hexdigest()
    question = [{'role': 'user', 'content': 'What is 7 times 8? Reply with only the number.'}]
    prompt = call('/apply-template', {'messages': question})['prompt']
    bounded = {'prompt': prompt, 'n_predict': 1, 'ignore_eos': True, 'temperature': 0,
               'seed': 17, 'cache_prompt': False, 'stream': False}
    limited = call('/completion', bounded)
    report['token_limit'] = {'stop_type': limited['stop_type'], 'tokens': limited['tokens_predicted'],
                             'passed': limited['stop_type'] == 'limit' and limited['tokens_predicted'] == 1}
    word = limited['content']
    assert word, 'A one-token text completion is required to inspect stop-string behavior'
    stopped = call('/completion', dict(bounded, n_predict=16, stop=[word]))
    report['stop_string'] = {'stop_type': stopped['stop_type'], 'stopping_word': stopped['stopping_word'],
                            'passed': stopped['stop_type'] == 'word' and stopped['stopping_word'] == word and stopped['content'] == ''}
    response = call('/v1/chat/completions', {'messages': question, 'max_tokens': 256, 'temperature': 0,
                                             'seed': 17, 'cache_prompt': False, 'stream': False})
    decode_completed_response(response)
    choice = response['choices'][0]
    report['answer'] = {'text': choice['message']['content'], 'finish_reason': choice['finish_reason'],
                        'usage': response.get('usage'), 'passed': choice['finish_reason'] == 'stop' and choice['message']['content'].strip() == '56'}
    report['passed'] = (all(item['passed'] for item in report['round_trips']) and report['template_matches'] and
                        all(report[name]['passed'] for name in ('token_limit', 'stop_string', 'answer')))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18080)
    parser.add_argument('--key-file', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    key = os.getenv('ROMS_UPSTREAM_API_KEY', '')
    if args.key_file:
        settings = dict(line.split('=', 1) for line in args.key_file.read_text().splitlines() if '=' in line)
        key = settings['ROMS_UPSTREAM_API_KEY']
    with httpx.Client(base_url=f'http://127.0.0.1:{args.port}', headers={'Authorization': 'Bearer ' + key} if key else {},
                      trust_env=False, timeout=90) as client:
        report = verify(client)
    inputs = json.loads(MANIFEST.read_text())
    report['model_identity'] = verify_file(Path(report['model_path']), inputs['models']['2.9b'])
    report['installed_service_memory'] = subprocess.check_output(['systemctl', 'show', 'goose-model.service',
        '-p', 'MemoryCurrent', '-p', 'MemoryPeak'], text=True).splitlines()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'round_trips': report['round_trips'],
                      'answer': report['answer'], 'output': str(args.output)}, ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
