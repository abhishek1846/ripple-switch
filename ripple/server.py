import importlib.util
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .core import RippleError


def validate_files(app, data):
    if app.example != 'parcel':
        raise RippleError('Selection validation belongs to the included Parcel example')
    files = data.get('files')
    if not isinstance(files, list) or len(files) > 200 or not all(isinstance(f, str) and len(f) < 1000 for f in files):
        raise RippleError('Provide a list of at most 200 filenames')
    path = app.area_path('application') / 'limits.py'
    if not path.is_file():
        raise RippleError('Selection validation is available for the included application with limits.py')
    spec = importlib.util.spec_from_file_location('parcel_live_limits', path)
    module = importlib.util.module_from_spec(spec)
    # Read source explicitly to avoid same-second .pyc cache staleness after an edit.
    exec(compile(path.read_text(), str(path), 'exec'), module.__dict__)
    return module.validate(data.get('plan', 'basic'), files, path.parent)


def mutate(app, path, data):
    from .switch import Switch
    if path == '/api/switch/configure':
        return Switch(app).configure(data)
    if path == '/api/switch/test':
        return Switch(app).test()
    if path == '/api/changes':
        return app.start(data.get('request'), data.get('plan'), data.get('limit'), data.get('draft', False))
    if path == '/api/validate':
        return validate_files(app, data)
    pieces = path.strip('/').split('/')
    if len(pieces) == 4 and pieces[:2] == ['api', 'changes']:
        change, action = pieces[2:]
        if action == 'publish':
            return app.publish(change, data.get('remote', 'origin'), data.get('base'), data.get('push_only', False))
        if action == 'check':
            return app.check(change)
        if action == 'approve':
            return app.approve(change)
        if action == 'cancel':
            return app.cancel(change)
        if action == 'draft':
            return app.draft(change)
        if action == 'resume':
            return app.resume(change)
        if action == 'dispatch':
            return Switch(app).dispatch(change, data.get('phase', 'request'))
    raise RippleError('Unknown action')


def serve(app, port=8790):
    token = secrets.token_urlsafe(32)
    web = Path(__file__).resolve().parents[1] / 'web'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def respond(self, status, content, mime='application/json; charset=utf-8'):
            body = content if isinstance(content, bytes) else content.encode()
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            self.wfile.write(body)

        def trusted_host(self):
            host = self.headers.get('Host', '')
            return host in (f'127.0.0.1:{port}', f'localhost:{port}')

        def do_GET(self):
            if not self.trusted_host():
                return self.respond(403, '{"error":"Local access only"}')
            path = urlparse(self.path).path
            try:
                if path == '/api/state':
                    return self.respond(200, json.dumps(app.status(parse_qs(urlparse(self.path).query).get('change', [None])[0])))
                assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/styles.css': ('styles.css', 'text/css; charset=utf-8'), '/favicon.svg': ('favicon.svg', 'image/svg+xml')}
                if path not in assets:
                    return self.respond(404, '{"error":"Not found"}')
                filename, mime = assets[path]
                text = (web / filename).read_text()
                if filename == 'index.html':
                    text = text.replace('__RIPPLE_TOKEN__', token)
                self.respond(200, text, mime)
            except (ValueError, OSError, KeyError) as exc:
                self.respond(500, json.dumps({'error': str(exc)}))

        def do_POST(self):
            origin = self.headers.get('Origin')
            if not self.trusted_host() or self.headers.get('X-Ripple-Token') != token or (origin and origin not in (f'http://127.0.0.1:{port}', f'http://localhost:{port}')):
                return self.respond(403, '{"error":"Open the local Ripple page before making changes"}')
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 100000:
                    raise RippleError('Invalid request size')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise RippleError('Expected a JSON object')
                result = mutate(app, urlparse(self.path).path, data)
                self.respond(200, json.dumps(result))
            except (RippleError, ValueError, KeyError, TypeError, OSError) as exc:
                self.respond(400, json.dumps({'error': str(exc)}))

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'Ripple is running at http://127.0.0.1:{port}', flush=True)
    print('Keep this Terminal open. Press Ctrl+C to stop.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
