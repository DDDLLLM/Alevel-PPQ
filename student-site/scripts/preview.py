#!/usr/bin/env python3
"""Local-only preview; serves public exports without starting the teacher app."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / ('student-publish' if (ROOT / 'student-publish').exists() else 'student-data')
class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        p = unquote(urlsplit(path).path)
        root = DATA if p.startswith('/library/') else ROOT / 'student-site' / 'dist'
        rel = p.removeprefix('/library/') if p.startswith('/library/') else p.lstrip('/')
        target = (root / rel).resolve()
        if not target.is_relative_to(root.resolve()):
            return str(root / '_invalid')
        return str(target)
    def do_GET(self):
        if urlsplit(self.path).path == '/config.js':
            data = b"window.LIBRARY_CONFIG = Object.freeze({ dataBase: '/library/' });"
            self.send_response(200); self.send_header('Content-Type', 'application/javascript'); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        else:
            super().do_GET()

if __name__ == '__main__':
    print('Local: http://127.0.0.1:9780', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 9780), Handler).serve_forever()
