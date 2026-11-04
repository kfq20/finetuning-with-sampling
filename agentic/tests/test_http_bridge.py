"""Actual HTTP forwarding tests; no provider or model requests."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from append_rewrite.terminus.http_bridge import make_handler


class BridgeTests(unittest.TestCase):
    def test_preserves_stream_errors_and_single_attempt(self):
        calls=[]
        class Provider(BaseHTTPRequestHandler):
            def log_message(self,*_):pass
            def do_POST(self):
                body=self.rfile.read(int(self.headers['Content-Length']));calls.append((self.headers['Authorization'],body))
                self.send_response(401 if body==b'error' else 200);self.end_headers()
                for chunk in [b'data: {"text":"4"}\n\n',b'data: [DONE]\n\n']:
                    self.wfile.write(chunk);self.wfile.flush()
        provider=ThreadingHTTPServer(('127.0.0.1',0),Provider)
        threading.Thread(target=provider.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                journal=Path(folder)/'requests.jsonl'
                handler=make_handler({'base_url':f'http://127.0.0.1:{provider.server_port}/v1','api_key':'provider-test-key','user_authorized':True},journal)
                bridge=ThreadingHTTPServer(('127.0.0.1',0),handler)
                threading.Thread(target=bridge.serve_forever,daemon=True).start()
                try:
                    for body,status in [(b'normal',200),(b'error',401)]:
                        c=http.client.HTTPConnection('127.0.0.1',bridge.server_port)
                        c.request('POST','/generate',body,{'Authorization':'Bearer local'})
                        response=c.getresponse();self.assertEqual(response.status,status)
                        self.assertEqual(response.read(),b'data: {"text":"4"}\n\ndata: [DONE]\n\n');c.close()
                    c=http.client.HTTPConnection('127.0.0.1',bridge.server_port)
                    c.request('GET','/v1/models');response=c.getresponse();self.assertEqual(response.status,401);response.read();c.close()
                finally:bridge.shutdown();bridge.server_close()
                self.assertEqual(calls,[('Bearer provider-test-key',b'normal'),('Bearer provider-test-key',b'error')])
                text=journal.read_text();self.assertNotIn('provider-test-key',text)
                self.assertTrue(all(x['upstream_attempts']==1 for x in map(json.loads,text.splitlines())))
        finally:provider.shutdown();provider.server_close()


if __name__=='__main__':unittest.main()
