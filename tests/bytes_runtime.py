"""Internal binary primitives: ownership and canonical RFC 4648 codec agreement."""
import base64
import os
from pathlib import Path
import random
import subprocess
import sys
import unittest

PROBE = str(Path(sys.argv.pop(1)).resolve())
NODE = sys.argv.pop(1) if len(sys.argv)>1 and not sys.argv[1].startswith('-') else os.environ.get('NEX_NODE','node')
ROOT = Path(__file__).resolve().parents[1]


class BytesRuntime(unittest.TestCase):
    def compare(self, requests, expected):
        text=''.join(kind+' '+value+'\n' for kind,value in requests)
        for command in ([PROBE,'--stream'],[NODE,'--no-warnings',str(ROOT/'tests/bytes-runtime-runner.mjs')]):
            completed=subprocess.run(command,input=text,text=True,capture_output=True,timeout=60)
            self.assertEqual(completed.returncode,0,completed.stderr)
            self.assertEqual(completed.stdout.splitlines(),expected,command)

    def test_immutable_imports_exports_updates_slices_and_bounds(self):
        for command in ([PROBE],[NODE,'--no-warnings',str(ROOT/'tests/bytes-runtime-runner.mjs'),'--self-test']):
            completed=subprocess.run(command,text=True,capture_output=True,timeout=30)
            self.assertEqual(completed.returncode,0,completed.stderr)
            self.assertEqual(completed.stdout,'8 immutable byte runtime cases passed\n')

    def test_standard_vectors_arbitrary_octets_and_random_reference_roundtrips(self):
        examples=[(b'',''),(b'f','Zg=='),(b'fo','Zm8='),(b'foo','Zm9v'),(b'foob','Zm9vYg=='),(b'fooba','Zm9vYmE='),(b'foobar','Zm9vYmFy')]
        rng=random.Random(0x31B);values=[v for v,_ in examples]+[bytes(range(256)),b'\0\xff\x80\xc3\x28']
        values += [bytes(rng.randrange(256) for _ in range(length)) for length in [*range(64),255,256,257,1023,1024,1025,16384]]
        requests=[];expected=[]
        for value in values:
            encoded=base64.b64encode(value).decode();requests += [('E',value.hex()),('D',encoded)];expected += [encoded,value.hex()]
        for value,encoded in examples:self.assertEqual(base64.b64encode(value).decode(),encoded)
        self.compare(requests,expected)

    def test_rejects_noncanonical_padding_alphabets_and_nonzero_unused_bits(self):
        invalid=['Zg','Zg=','Zg===','====','A===','Zm=8','Zg== ',' Zg==','Zg==\t','AA-_','Zh==','Zm9=','Zg==AAAA','ЯAAA','🧠AA','Zm9v====']
        # The line protocol cannot carry embedded newlines; test other whitespace
        # here and cover newline rejection directly in the native self-test.
        self.compare([('D',value) for value in invalid],['ERR:E_BASE64']*len(invalid))
        self.assertEqual(base64.b64decode('Zh==',validate=True),b'f')
        self.assertNotEqual(base64.b64encode(b'f').decode(),'Zh==')


if __name__=='__main__':unittest.main()
