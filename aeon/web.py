"""Loopback-only assistant interface. All actions use the existing harness."""

from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from urllib.parse import urlsplit, parse_qs

from .audit import report as audit
from .conversations import Conversations, chat
from .engine import Harness
from .memory import Memory
from .workflows import Workflows


class AssistantServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, config, state_dir, workspace, offline=False):
        if address[0] != '127.0.0.1':
            raise ValueError('Assistant interface binds only to 127.0.0.1')
        super().__init__(address, Handler)
        self.config, self.state_dir = config, state_dir
        self.workspace, self.offline = Path(workspace).resolve(), offline
        self.token = secrets.token_urlsafe(32)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.lock, self.jobs = threading.Lock(), {}

    def submit(self, fn):
        with self.lock:
            if any(not future.done() for future in self.jobs.values()):
                raise ValueError('A task is already running; wait for its result')
            key = secrets.token_hex(12)
            self.jobs = {k:v for k,v in list(self.jobs.items())[-19:]}
            self.jobs[key] = self.executor.submit(fn)
            return {'job': key}

    def server_close(self):
        super().server_close()
        self.executor.shutdown(wait=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, value, html=False):
        raw = value.encode() if html else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'nonce-"+self.server.token+"'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers(); self.wfile.write(raw)

    def trusted(self):
        host = f'127.0.0.1:{self.server.server_port}'
        return self.headers.get('Host') == host and self.headers.get('Origin', 'http://'+host) == 'http://'+host

    def do_GET(self):
        if not self.trusted():
            return self.respond(403, {'error': 'Use the local assistant URL'})
        path = urlsplit(self.path)
        if path.path == '/':
            return self.respond(200, Path(__file__).with_name('assistant.html').read_text(encoding='utf-8').replace('__TOKEN__', self.server.token), True)
        if self.headers.get('X-Aeon-Token') != self.server.token:
            return self.respond(403, {'error': 'Missing session token'})
        try:
            if path.path == '/api/job':
                key = parse_qs(path.query).get('id', [''])[0]
                with self.server.lock:
                    future = self.server.jobs.get(key)
                if future is None:
                    raise ValueError('Unknown job')
                return self.respond(200, {'done': future.done(), 'result': future.result() if future.done() else None})
            if path.path not in {'/api/state', '/api/memory', '/api/entry'}:
                return self.respond(404, {'error': 'Not found'})
            memory = Memory(self.server.state_dir)
            try:
                conversations = Conversations(memory, self.server.workspace)
                query = parse_qs(path.query)
                cid = query.get('conversation', [''])[0]
                if path.path == '/api/memory':
                    return self.respond(200, conversations.search(cid, query.get('query', [''])[0]))
                if path.path == '/api/entry':
                    return self.respond(200, conversations.entry(cid, int(query.get('entry', ['0'])[0])))
                entries = conversations.entries(cid) if cid else []
                sessions = {}
                for entry in entries:
                    sid = entry['session']
                    if sid and sid not in sessions:
                        sessions[sid] = {'session': memory.session(sid), 'audit': audit(memory, sid)}
                self.respond(200, {'workspace': str(self.server.workspace), 'offline': self.server.offline,
                                  'conversations': conversations.list(), 'entries': entries,
                                  'sessions': sessions, 'workflows': Workflows(memory, self.server.workspace).list()})
            finally:
                memory.close()
        except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
            self.respond(400, {'error': str(exc)})

    def do_POST(self):
        if not self.trusted() or self.headers.get('X-Aeon-Token') != self.server.token:
            return self.respond(403, {'error': 'Invalid assistant session or origin'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 160000 or self.headers.get('Content-Type') != 'application/json':
                raise ValueError('Expected bounded JSON request')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Expected object')
            route = urlsplit(self.path).path
            if route == '/api/swarm':
                from .swarm import repo_map, review
                operation = body.get('operation')
                if operation not in ('map', 'prepare'):
                    raise ValueError('Code review operation must be map or prepare')
                allowed = {'operation', 'path'} if operation == 'map' else {'operation', 'path', 'goal', 'mode'}
                if set(body) - allowed or (operation == 'prepare' and 'goal' not in body):
                    raise ValueError('Unexpected or missing code review fields; model calls and execution are unavailable')
                if operation == 'map':
                    task = lambda: repo_map(self.server.workspace, path=body.get('path', '.'))
                else:
                    task = lambda: review(self.server.workspace, body['goal'], path=body.get('path', '.'),
                                          mode=body.get('mode', 'low'), profile=None)
                return self.respond(202, self.server.submit(task))
            if route not in {'/api/conversation', '/api/chat', '/api/note', '/api/approve', '/api/workflow', '/api/plan'}:
                return self.respond(404, {'error': 'Not found'})
            def operation():
                memory = Memory(self.server.state_dir)
                try:
                    store = Conversations(memory, self.server.workspace)
                    if route == '/api/plan':
                        from .planner import preview
                        return preview(self.server.config, memory, self.server.workspace, body['text'])
                    if route == '/api/conversation':
                        return {'conversation': store.create(body.get('title', 'New conversation'))}
                    cid = body.get('conversation')
                    if route == '/api/note':
                        replacement = body.get('replaces')
                        return {'entry': store.append(cid, 'correction' if replacement is not None else 'note', body['text'], replaces=replacement)}
                    if route == '/api/chat':
                        return chat(self.server.config, memory, self.server.workspace, cid, body['text'], self.server.offline)
                    if route == '/api/approve':
                        sid = body['session']
                        if not any(e['session'] == sid for e in store.entries(cid)):
                            raise ValueError('Task is not in this conversation')
                        result = Harness(self.server.config, memory, self.server.workspace).run(
                            sid=sid, approve=body['ticket'], offline=self.server.offline)
                        store.append(cid, 'assistant', result['answer'], session=sid)
                        return result
                    workflows = Workflows(memory, self.server.workspace)
                    op = body['operation']
                    if op == 'propose':
                        return workflows.propose(body['plan'], body.get('source_session') or None)
                    if op == 'learn':
                        return workflows.learn(body['session'], body['name'])
                    if op == 'test':
                        return workflows.regress(body['id'], body['fixtures'], self.server.config)
                    if op == 'approve':
                        return workflows.review(body['id'])
                    if op == 'run':
                        store.get(cid)
                        plan = workflows.approved(body['id'])
                        store.append(cid, 'user', 'Run reviewed workflow: '+plan['name'])
                        result = Harness(self.server.config, memory, self.server.workspace).run(
                            'Run workflow: '+plan['name'], workflow=plan, offline=self.server.offline)
                        store.append(cid, 'assistant', result['answer'], session=result['session'])
                        return result
                    raise ValueError('Unknown workflow operation')
                finally:
                    memory.close()
            self.respond(202, self.server.submit(operation))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.respond(400, {'error': str(exc)})


def serve(config, state_dir, workspace, port=7878, offline=False, open_browser=False):
    with AssistantServer(('127.0.0.1', port), config, state_dir, workspace, offline) as server:
        print(f'Swarm Mojo assistant: http://127.0.0.1:{server.server_port}', flush=True)
        if open_browser:
            import webbrowser
            webbrowser.open(f'http://127.0.0.1:{server.server_port}')
        server.serve_forever()
