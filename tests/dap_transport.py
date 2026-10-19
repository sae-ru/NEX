"""DAP framing, reference separation and ownership on client disconnect."""
import base64
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from types import SimpleNamespace
import support as harness

spec=importlib.util.spec_from_file_location('nex_dap',harness.REPO/'debug/nex_dap.py')
adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)


class Transport(harness.ToolchainCase):
    def bridge(self):
        self.output=io.BytesIO();self.backend=SimpleNamespace(stdin=io.BytesIO())
        return adapter.Bridge(self.backend,self.output)

    def messages(self,stream):
        stream.seek(0);messages=[]
        while True:
            value=adapter.read_packet(stream)
            if value is None:return messages
            messages.append(value)

    def test_utf8_framing_and_rejected_ambiguous_or_oversized_packets(self):
        stream=io.BytesIO();value={'type':'event','event':'output','body':{'output':'\u0410\x00\U0001f98a'}}
        adapter.write_packet(stream,value);stream.seek(0)
        self.assertEqual(adapter.read_packet(stream),value)
        for invalid in [b'Content-Length: 0\r\nContent-Length: 0\r\n\r\n',b'Content-Length: 999999999\r\n\r\n',b'Content-Length: 5\r\n\r\n{}',b'x'*8193]:
            with self.subTest(packet=invalid[:40]),self.assertRaises(ValueError):adapter.read_packet(io.BytesIO(invalid))

    def test_expressions_are_encoded_and_reverse_requests_keep_backend_identity(self):
        bridge=self.bridge();bridge.frames[99]={'thread_id':'500','frame_index':2}
        expression='total\n+ 2 // `continue\n'
        bridge.client({'seq':1,'type':'request','command':'evaluate','arguments':{'expression':expression,'frameId':99,'context':'watch'}})
        sent=self.messages(self.backend.stdin)[0]
        raw=sent['arguments']['expression'];self.assertTrue(raw.startswith('`nex-eval-encoded '));self.assertNotIn('\n',raw)
        payload=json.loads(base64.b64decode(raw.split(' ',1)[1]))
        self.assertEqual(payload,{'expression':expression,'thread_id':'500','frame_index':2})
        bridge.server({'seq':900,'type':'request','command':'runInTerminal','arguments':{'args':['owned-backend']}})
        reverse=self.messages(self.output)[0]
        bridge.client({'seq':2,'type':'response','request_seq':reverse['seq'],'command':'runInTerminal','success':True,'body':{'processId':123}})
        self.assertEqual(self.messages(self.backend.stdin)[-1]['request_seq'],900)

    def test_client_eof_sends_terminate_disconnect_to_owned_backend(self):
        marker=self.root/'disconnected.json';backend=self.root/'backend'
        backend.write_text('#!/usr/bin/env python3\nimport sys,json\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(harness.REPO/'debug'))+')\nfrom nex_dap import read_packet,write_packet\nwhile True:\n    r=read_packet(sys.stdin.buffer)\n    if r is None:break\n    if r["type"]=="response":\n        assert r["request_seq"]==900;continue\n    if r["command"]=="disconnect":\n        Path('+repr(str(marker))+').write_text(json.dumps(r));break\n    write_packet(sys.stdout.buffer,{"seq":1,"type":"response","command":r["command"],"request_seq":r["seq"],"success":True,"body":{}})\n    write_packet(sys.stdout.buffer,{"seq":900,"type":"request","command":"runInTerminal","arguments":{"args":["owned-backend"]}})\n')
        backend.chmod(0o755)
        process=subprocess.Popen([sys.executable,str(harness.REPO/'debug/nex_dap.py'),'--backend',str(backend)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        timer=threading.Timer(10,process.terminate);timer.start()
        try:
            adapter.write_packet(process.stdin,{'seq':1,'type':'request','command':'initialize','arguments':{}})
            reply=adapter.read_packet(process.stdout);self.assertTrue(reply['success'])
            reverse=adapter.read_packet(process.stdout);self.assertEqual(reverse['command'],'runInTerminal')
            adapter.write_packet(process.stdin,{'seq':42,'type':'response','command':'runInTerminal','request_seq':reverse['seq'],'success':True,'body':{'processId':123}})
            process.stdin.close();process.stdin=None
            stdout,stderr=process.communicate(timeout=15)
            self.assertEqual(process.returncode,0,stderr)
            message=json.loads(marker.read_text());self.assertEqual(message['command'],'disconnect')
            self.assertTrue(message['arguments']['terminateDebuggee'])
            self.assertGreater(message['seq'],42)
        finally:
            timer.cancel()
            if process.poll() is None:process.terminate();process.communicate(timeout=10)

    def test_native_pages_bound_work_keep_requested_offsets_and_expire_on_resume(self):
        bridge=self.bridge()
        bridge.server({'seq':1,'type':'response','command':'variables','request_seq':0,'success':True,'body':{'variables':[{'name':'large','type':'bytes','variablesReference':900,'indexedVariables':4194304}]}})
        reference=self.messages(self.output)[0]['body']['variables'][0]['variablesReference']
        self.assertNotEqual(reference,900)
        bridge.client({'seq':99,'type':'request','command':'variables','arguments':{'variablesReference':reference,'filter':'named','count':2}})
        self.assertEqual(self.messages(self.output)[-1]['body']['variables'],[])
        self.assertEqual(self.backend.stdin.getvalue(),b'')
        for sequence,count in enumerate([0,2,1000000],1):
            bridge.client({'seq':sequence,'type':'request','command':'variables','arguments':{'variablesReference':reference,'start':4194302,'count':count}})
            forwarded=self.messages(self.backend.stdin)[-1]
            self.assertEqual(forwarded['arguments']['start'],4194302)
            self.assertEqual(forwarded['arguments']['variablesReference'],900)
            self.assertEqual(forwarded['arguments']['count'],2 if count==2 else 1000)
            bridge.server({'seq':sequence+10,'type':'response','command':'variables','request_seq':sequence,'success':True,'body':{'variables':[{'name':'[4194303]','value':'255','variablesReference':0}]}})
            response=self.messages(self.output)[-1]
            self.assertEqual(response['body']['nex']['native_page'],{'start':4194302,'requested_count':count,'returned_count':1,'limit':1000})
        bridge.server({'seq':100,'type':'event','event':'continued','body':{'threadId':1}})
        bridge.client({'seq':4,'type':'request','command':'variables','arguments':{'variablesReference':reference}})
        self.assertFalse(self.messages(self.output)[-1]['success'])

    def test_native_page_rejects_invalid_bounds_and_backend_overflow(self):
        bridge=self.bridge();reference=bridge.allocate({'backend':77})
        for sequence,change in enumerate([{'start':True},{'count':False},{'start':-1},{'count':-1},{'start':2147483648},{'count':2147483648},{'variablesReference':True},{'filter':'invalid'}],1):
            bridge.client({'seq':sequence,'type':'request','command':'variables','arguments':{'variablesReference':reference,**change}})
            self.assertFalse(self.messages(self.output)[-1]['success'])
        self.assertEqual(self.backend.stdin.getvalue(),b'')
        bridge.client({'seq':50,'type':'request','command':'variables','arguments':{'variablesReference':reference}})
        bridge.server({'seq':99,'type':'response','request_seq':50,'command':'variables','success':True,'body':{'variables':[{'variablesReference':0}]*1001}})
        response=self.messages(self.output)[-1];self.assertFalse(response['success']);self.assertIn('page limit',response['message'])


if __name__=='__main__':unittest.main(verbosity=2)
