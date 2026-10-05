"""Local Goose chat client; no command execution."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser(description='Local Omarchy Goose assistant')
    parser.add_argument('--status', action='store_true')
    intake = parser.add_mutually_exclusive_group()
    intake.add_argument('--add-file')
    intake.add_argument('--add-repo')
    intake.add_argument('--add-folder')
    intake.add_argument('--sources', action='store_true')
    intake.add_argument('--library', action='store_true', help='Open the knowledge library menu')
    intake.add_argument('--remove-source')
    intake.add_argument('--refresh-source')
    intake.add_argument('--cleanup-worker', help='Retry container cleanup for a retained task ID')
    intake.add_argument('--register-project')
    intake.add_argument('--stage-patch', help='Prepare a proposal JSON file in an isolated worktree')
    intake.add_argument('--validate-patch')
    intake.add_argument('--show-patch')
    intake.add_argument('--patch-tasks', action='store_true')
    parser.add_argument('--preview', action='store_true', help='List eligible files without importing')
    parser.add_argument('prompt', nargs='*')
    args = parser.parse_args()
    operation = next(((name, value) for name, value in [
        ('file', args.add_file), ('repo', args.add_repo), ('folder', args.add_folder),
        ('list', args.sources), ('menu', args.library), ('remove', args.remove_source),
        ('refresh', args.refresh_source), ('cleanup', args.cleanup_worker),
        ('register', args.register_project), ('propose', args.stage_patch),
        ('validate', args.validate_patch), ('show', args.show_patch), ('tasks', args.patch_tasks)] if value), None)
    if operation:
        if args.status or args.prompt:
            parser.error('Management actions cannot be combined with chat or --status')
        action, value = operation
        command = ['/usr/bin/python', str(Path(__file__).with_name('run_linux_env.py')), 'python', '-m']
        if action == 'cleanup':
            if args.preview:
                parser.error('--preview does not apply to worker cleanup')
            command.append('scripts.cleanup_worker')
        elif action in {'register', 'propose', 'validate', 'show', 'tasks'}:
            if args.preview:
                parser.error('Staging never changes the source checkout; --preview is for knowledge imports')
            command.extend(['scripts.patch_tasks_cli', 'list' if action == 'tasks' else action])
        else:
            command.extend(['app.source_library', action])
        if action not in {'list', 'menu', 'tasks'}:
            command.append(value)
        if args.preview:
            command.append('--preview')
        environment = {key: value for key, value in os.environ.items() if key not in {'PYTHONHOME', 'PYTHONPATH'}}
        raise SystemExit(subprocess.run(command, env=environment).returncode)
    if args.preview:
        parser.error('--preview requires a source operation')
    if args.status:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(10)
            client.connect('/run/omarchy-broker/broker.sock')
            client.sendall(b'STATUS\n')
            data = bytearray()
            while not data.endswith(b'\n'):
                chunk = client.recv(4096)
                if not chunk:
                    raise RuntimeError('Broker disconnected')
                data.extend(chunk)
            print(json.dumps(json.loads(data), indent=2))
        return
    messages: list[dict[str, str]] = []
    print('Goose — local Omarchy test build. Type /exit to leave, /reset to clear this chat.')
    headers = {'Content-Type': 'application/json',
               'Authorization': 'Bearer ' + os.environ['ROMS_GATEWAY_API_KEY']}
    deadline = time.monotonic() + 90
    announced = False
    while True:
        try:
            health = urllib.request.Request('http://127.0.0.1:8844/health', headers=headers)
            with urllib.request.urlopen(health, timeout=4) as response:
                if json.load(response).get('upstream_ready'):
                    break
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            raise SystemExit('Goose did not become ready. Check the model and ROMS service logs.')
        if not announced:
            print('Waiting for the local model to start...', flush=True)
            announced = True
        time.sleep(1)
    while True:
        try:
            prompt = ' '.join(args.prompt) if args.prompt else input('\nYou: ').strip()
        except EOFError:
            break
        if prompt == '/exit':
            break
        if prompt == '/reset':
            messages.clear()
            continue
        if not prompt:
            continue
        messages.append({'role': 'user', 'content': prompt})
        payload = {'messages': messages[-8:], 'max_tokens': 256, 'temperature': 0.3}
        request = urllib.request.Request('http://127.0.0.1:8844/v1/chat/completions',
            json.dumps(payload).encode(), headers)
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                text = json.load(response)['choices'][0]['message']['content']
            print('\nGoose:', text)
            messages.append({'role': 'assistant', 'content': text})
        except (OSError, ValueError, KeyError) as error:
            messages.pop()
            print(f'Goose unavailable: {error}', file=sys.stderr)
            if args.prompt:
                raise SystemExit(1)
        if args.prompt:
            break


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nChat closed.')
