"""Read-only marker provenance when an instrumented prologue hides its argument."""
import ast,types,unittest
from pathlib import Path
source=Path(__file__).resolve().parents[1]/'debug/lldb_nex.py'
node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='_task_stop_record')
namespace={'lldb':types.SimpleNamespace(eDynamicDontRunTarget=0),'_integer':lambda value:value.pointer}
exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),namespace)
record=namespace['_task_stop_record']
class Value:
 def __init__(self,valid=True,pointer=100,address=200,name='nexrt::TaskDebugStop',size=64):self.valid,self.pointer,self.address,self.name,self.size=valid,pointer,address,name,size
 def IsValid(self):return self.valid
 def GetType(self):return self
 def GetCanonicalType(self):return self
 def GetName(self):return self.name
 def GetByteSize(self):return self.size
 def GetLoadAddress(self):return self.address
class Caller:
 def __init__(self,name='nexrt::taskDebugPublish(std::span<const X>, bool)',pc=300,value=None,valid=True):self.name,self.pc,self.value,self.valid=name,pc,value or Value(),valid
 def IsValid(self):return self.valid
 def GetFunctionName(self):return self.name
 def GetPC(self):return self.pc
 def FindVariable(self,*_):return self.value
class Frame:
 def __init__(self,argument=None,caller=None):self.argument,self.caller=argument or Value(),caller or Caller()
 def FindVariable(self,*_):return self.argument
 def GetThread(self):return self
 def GetFrameID(self):return 0
 def GetFrameAtIndex(self,index):assert index==1;return self.caller
class View:
 address=9;runtime_image=object()
 def __init__(self,words=None):self.memory=words or {100:[9,1,2,3,4,5,6,7],200:[9,1,2,3,4,5,6,7]};self.checked=[]
 def words(self,address,count):
  if address not in self.memory:raise ValueError('unreadable marker')
  assert count==8;return self.memory[address]
 def image_address(self,pc,size,image):
  self.checked.append((pc,size,image))
  if pc!=300 or image is not self.runtime_image:raise ValueError('foreign runtime image')
class Marker(unittest.TestCase):
 def test_live_argument_needs_no_fallback(self):
  view=View();self.assertEqual(record(view,Frame()),view.memory[100]);self.assertEqual(view.checked,[])
 def test_missing_argument_uses_verified_local(self):
  view=View();self.assertEqual(record(view,Frame(Value(valid=False))),view.memory[200]);self.assertEqual(len(view.checked),1)
 def test_instrumented_argument_foreign_catalog_uses_publisher(self):
  view=View({100:[77]*8,200:[9,1,2,3,4,5,6,7]});self.assertEqual(record(view,Frame()),view.memory[200])
 def test_unreadable_argument_uses_publisher(self):
  view=View();self.assertEqual(record(view,Frame(Value(pointer=999))),view.memory[200])
 def test_wrong_caller_name_rejected(self):
  with self.assertRaises(ValueError):record(View(),Frame(Value(valid=False),Caller(name='attacker::taskDebugPublish()')))
 def test_wrong_runtime_image_rejected(self):
  with self.assertRaises(ValueError):record(View(),Frame(Value(valid=False),Caller(pc=999)))
 def test_wrong_local_type_rejected(self):
  with self.assertRaises(ValueError):record(View(),Frame(Value(valid=False),Caller(value=Value(name='untrusted::Record'))))
 def test_wrong_local_size_rejected(self):
  with self.assertRaises(ValueError):record(View(),Frame(Value(valid=False),Caller(value=Value(size=56))))
 def test_missing_publisher_rejected(self):
  with self.assertRaises(ValueError):record(View(),Frame(Value(valid=False),Caller(valid=False)))
 def test_foreign_local_catalog_rejected(self):
  with self.assertRaises(ValueError):record(View({100:[77]*8,200:[88]*8}),Frame())
if __name__=='__main__':unittest.main()
