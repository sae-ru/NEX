"""C fixture signatures pinned independently of the loader being tested."""
import hashlib
import json
from pathlib import Path
import sys

resource={'kind':'resource','name':'fixture::Session','identity':'a'*64}
integer={'kind':'i64'}
def signature(parameters,result,types):return {'schema':'nex.foreign-signature/1','parameters':parameters,'result':result,'types':types}
create=signature([0],1,[integer,resource])
read=signature([0],1,[resource,integer])
forward=signature([0],0,[resource])
result=signature([0],2,[integer,resource,{'kind':'result','item':1}])
signatures={'create':create,'read':read,'forward':forward,'close_borrow':read,'status':read,
            'input_constructor':read,'bad_callback':create,'hold_poll':read,
            'result_create':result,'tokens':read,'wrong_thread':read}

if __name__=='__main__':
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
    (out/'signatures.json').write_text(json.dumps(signatures,sort_keys=True,indent=2)+'\n', newline="\n")
    lines=['/* Independently computed canonical signature SHA256 pins. */']
    for name,value in signatures.items():
        digest=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        lines.append('#define PIN_'+name.upper()+' "'+digest+'"')
    (out/'typed-resource-signatures.h').write_text('\n'.join(lines)+'\n', newline="\n")
