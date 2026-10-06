import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from app.workbench.qualification import probe_endpoint


@pytest.mark.parametrize('channel', ['content', 'reasoning_content'])
def test_real_http_probe_distinguishes_streaming_and_observed_idle_slot(channel):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'[{"is_processing": false}]')
        def do_POST(self):
            value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.send_response(200)
            self.end_headers()
            if value.get('stream'):
                chunk = {'choices': [{'delta': {channel: 'one'}}]}
                self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
            else:
                text = '4' if '2 + 2' in value['messages'][0]['content'] else 'READY'
                self.wfile.write(json.dumps({'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}]}).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = probe_endpoint(f'http://127.0.0.1:{server.server_port}', 'fixture', checkpoint_sha256='a' * 64)
        assert result['task_success'] == 1
        assert result['streaming'] and result['cancellation'] and result['recovery']
        assert not result['recurrent_checkpoint']
        assert result['representative_tasks'] == 0
        assert not result['environment']['target_qualified']
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
