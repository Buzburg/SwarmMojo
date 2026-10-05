"""Local Goose chat client; no command execution."""
import argparse
import json
import os
import socket
import sys
import time
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser(description='Local Omarchy Goose assistant')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('prompt', nargs='*')
    args = parser.parse_args()
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
