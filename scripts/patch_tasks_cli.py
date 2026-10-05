"""Stage, validate, review and explicitly approve local project changes."""
import argparse
import asyncio
import json
import sys

from app import patch_tasks, patch_promotion
from app.source_library import local_path


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['register', 'propose', 'validate', 'show', 'list', 'review', 'apply', 'rollback'])
    parser.add_argument('value', nargs='?')
    args = parser.parse_args()
    if args.action != 'list' and not args.value:
        parser.error('A path or task ID is required')
    if args.action == 'register':
        result = await patch_tasks.register_project(args.value)
    elif args.action == 'propose':
        path = local_path(args.value)
        if not path.is_file() or path.stat().st_size > 512 * 1024:
            raise ValueError('Select a proposal JSON file up to 512 KiB')
        request = json.loads(path.read_text(encoding='utf-8'))
        if type(request) is not dict or set(request) != {'project_id', 'base_commit', 'changes', 'checks'}:
            raise ValueError('Proposal fields must be project_id, base_commit, changes and checks')
        result = await patch_tasks.propose(**request)
    elif args.action == 'validate':
        result = await patch_tasks.validate_task(args.value)
    elif args.action in {'review', 'apply', 'rollback'}:
        rollback = args.action == 'rollback'
        result = patch_promotion.review(args.value, rollback=rollback)
        if args.action != 'review':
            # JSON escapes terminal controls in untrusted filenames and patch text.
            print(json.dumps(result, indent=2), flush=True)
            if not sys.stdin.isatty():
                raise ValueError('Apply and rollback require an interactive operator review')
            confirmation = args.action + ' ' + result['patch_sha256'][:12]
            print('This changes the listed files in ' + json.dumps(result['source']) + '.', flush=True)
            if input('Type "' + confirmation + '" to confirm: ').strip() != confirmation:
                raise ValueError('No matching approval; source files were not changed')
            token = patch_promotion.authorize(args.value, result['patch_sha256'], args.action)
            result = await patch_promotion.promote(args.value, token, rollback=rollback)
    elif args.action == 'show':
        control, metadata, patch = patch_tasks.load_task(args.value)
        result = {'task': metadata, 'patch': patch, 'record_directory': str(control)}
    else:
        result = []
        for path in sorted((patch_tasks.STORE / 'tasks').glob('*/task.json'),
                           key=lambda item: item.stat().st_mtime, reverse=True)[:100]:
            task = json.loads(path.read_text())
            result.append({key: task[key] for key in ('id', 'state', 'source', 'patch_sha256')})
    if args.action in {'propose', 'validate', 'apply', 'rollback'}:
        result = {key: result[key] for key in ('id', 'state', 'source', 'base_commit', 'patch_sha256')}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (OSError, ValueError, RuntimeError, EOFError) as error:
        raise SystemExit(f'Patch operation failed: {error}') from error
