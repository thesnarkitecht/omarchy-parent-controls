import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'kids'))
from remote_http import Handler

class Socket:
    def __init__(self, raw): self.input=io.BytesIO(raw);self.output=bytearray()
    def makefile(self,*args): return self.input
    def settimeout(self,*args): pass
    def sendall(self, value): self.output.extend(value)

class HTTPTests(unittest.TestCase):
    def call(self,body=None,headers=None,path='/v1/parent',method='POST'):
        data=json.dumps(body or {'id':'a'*32,'issued':1000,'operation':'status','fields':{}}).encode()
        values={'Authorization':'Bearer '+'t'*43,'Content-Type':'application/json','Content-Length':str(len(data))}
        values.update(headers or {})
        raw=(f'{method} {path} HTTP/1.1\r\nHost: school.example.ts.net\r\n'+''.join(k+': '+v+'\r\n' for k,v in values.items())+'\r\n').encode()+data
        connection=Socket(raw)
        with patch('remote_http.request',return_value={'ok':True,'name':'School'}) as broker:
            Handler(connection,('127.0.0.1',1234),object())
        return bytes(connection.output),broker
    def test_relay_transfers_only_authenticated_envelope(self):
        output,broker=self.call()
        self.assertIn(b'200 OK',output)
        args,kwargs=broker.call_args
        self.assertEqual(args,('remote-parent',));self.assertEqual(kwargs['envelope']['token'],'t'*43)
        self.assertNotIn(b't'*43,output)
    def test_no_browser_origin_redirect_or_get_endpoint(self):
        for kwargs in [dict(headers={'Origin':'https://evil.org'}),dict(path='/'),dict(method='GET')]:
            output,broker=self.call(**kwargs);self.assertNotIn(b'200 OK',output);broker.assert_not_called()
    def test_missing_token_chunked_body_and_extra_fields_rejected(self):
        for kwargs in [dict(headers={'Authorization':''}),dict(headers={'Transfer-Encoding':'chunked'}),dict(body={'token':'x','id':'a'*32,'issued':1000,'operation':'status','fields':{}}),dict(headers={'Content-Length':'9000'})]:
            output,broker=self.call(**kwargs);self.assertNotIn(b'200 OK',output);broker.assert_not_called()

if __name__=='__main__':unittest.main()
