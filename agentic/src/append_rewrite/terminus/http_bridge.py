"""Loopback-only native HTTP bridge for an in-flight endpoint handoff.

One upstream POST per downstream POST. Forward bytes unchanged, preserve HTTP
errors, never retry or fall back, and journal metadata without auth or bodies.
Existing clients keep their frozen loopback endpoint and action protocol.
"""
import argparse
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit
import uuid


HOP = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
       'te', 'trailer', 'transfer-encoding', 'upgrade', 'content-length'}


def make_handler(config, journal):
    target = urlsplit(config['base_url'])
    if target.scheme not in {'http', 'https'} or target.path != '/v1' or target.username or target.query or target.fragment:
        raise ValueError('Explicit provider origin with /v1 base required')
    if config.get('user_authorized') is not True:
        raise ValueError('User-authorized provider required')
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_):
            pass  # Never expose auth, request bodies, or query strings.

        def do_GET(self):
            self.forward()

        def do_POST(self):
            self.forward()

        def forward(self):
            if self.path not in {'/generate', '/v1/models'} or (self.command == 'POST') != (self.path == '/generate'):
                self.send_error(404);return
            if self.headers.get('Authorization') != 'Bearer local':
                self.send_error(401);return
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 <= size <= 8 * 1024 * 1024:
                self.send_error(413);return
            body = self.rfile.read(size) if size else None
            record = {'id': uuid.uuid4().hex, 'started_at': time.time(), 'path': self.path,
                      'body_sha256': hashlib.sha256(body or b'').hexdigest(),
                      'upstream_attempts': 0, 'bytes_forwarded': 0, 'complete_http': False}
            connection = None;sent_headers = False;started = time.monotonic()
            try:
                cls = http.client.HTTPSConnection if target.scheme == 'https' else http.client.HTTPConnection
                connection = cls(target.hostname, target.port, timeout=900)
                record['upstream_attempts'] = 1
                connection.request(self.command, self.path, body=body, headers={
                    'Authorization': 'Bearer ' + config['api_key'], 'Content-Type': 'application/json'})
                response = connection.getresponse()
                record.update(status=response.status, headers_sec=time.monotonic()-started)
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in HOP:
                        self.send_header(key, value)
                self.send_header('Connection', 'close')
                self.send_header('X-Bridge-Request-ID', record['id'])
                self.end_headers();sent_headers = True
                while chunk := response.read1(65536):
                    self.wfile.write(chunk);self.wfile.flush()
                    record['bytes_forwarded'] += len(chunk)
                record['complete_http'] = True
            except Exception as exc:
                record['error_type'] = type(exc).__name__
                if not sent_headers:
                    self.send_error(502)
            finally:
                if connection is not None:connection.close()
                self.close_connection = True
                record.update(elapsed_sec=time.monotonic()-started, finished_at=time.time())
                with lock:
                    with Path(journal).open('a') as output:
                        output.write(json.dumps(record)+'\n')

    return Handler


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--journal', type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    if args.config.stat().st_mode & 0o077:
        raise PermissionError('Private credential file required')
    config = json.loads(args.config.read_text())
    handler = make_handler(config, args.journal)
    ThreadingHTTPServer(('127.0.0.1', args.port), handler).serve_forever()


if __name__ == '__main__':main()
