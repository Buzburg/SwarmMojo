"""Fetch only pinned MiniLM data files; verify the safetensors LFS digest."""
import hashlib
import json
from pathlib import Path
import urllib.request

MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
REVISION = '1110a243fdf4706b3f48f1d95db1a4f5529b4d41'


def main() -> None:
    root = Path('/opt/omarchy-embedding')
    root.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(f'https://huggingface.co/api/models/{MODEL}/revision/{REVISION}?blobs=true', timeout=30) as response:
        metadata = json.load(response)
    weights = next(item for item in metadata['siblings'] if item['rfilename'] == 'model.safetensors')
    expected = weights['lfs']['sha256']
    files = ['1_Pooling/config.json', 'README.md', 'config.json', 'config_sentence_transformers.json',
             'modules.json', 'sentence_bert_config.json', 'special_tokens_map.json',
             'tokenizer.json', 'tokenizer_config.json', 'vocab.txt', 'model.safetensors']
    for name in files:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + '.partial')
        digest = hashlib.sha256()
        with urllib.request.urlopen(f'https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}', timeout=120) as response:
            with temporary.open('wb') as output:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    output.write(chunk)
        if name == 'model.safetensors' and digest.hexdigest() != expected:
            raise RuntimeError('Embedding weights checksum mismatch')
        temporary.replace(target)
    (root / 'provenance.json').write_text(json.dumps({'model': MODEL, 'revision': REVISION,
                                                   'weights_sha256': expected}, indent=2))
    print(f'Embedding model verified: {root}, revision {REVISION}')


if __name__ == '__main__':
    main()
