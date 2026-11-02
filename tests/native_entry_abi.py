"""Physical LLVM discovery exercised by matching-runtime native host calls."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import unittest

import support as harness


SOURCE = r'''module entry_abi;
struct Fault { values:list<str>; }
fn step(x:i64)->i64 !{throw}
  requires(x>=0) ensures(value=>x!=9 && value==x+1) {
  if(x==7){throw(Fault(["Я\u0000🧠"]));}
  return x+1;
}
fn empty(x:i64)->unit !{throw} {
  if(x==7){throw("unit-error");}
  assert(x>=0);
}
fn mixed(flag:bool,x:f64)->f64 {if(flag){return x+0.5;}return x-0.5;}
fn echo(value:str)->str {return value+"🧠";}
fn work()->i64 !{task} {return 42;}
fn generic<T>(x:T)->T {return x;}
fn main()->i64 {return 42;}
'''

HOST = r'''
#include "nex_host.h"
#include <cassert>
#include <cstdint>
#include <iostream>
#include <limits>
extern "C" int64_t STEP(int64_t,nexrt::Handle **);
extern "C" void EMPTY(int64_t,nexrt::Handle **);
extern "C" double MIXED(bool,double);
extern "C" nexrt::Handle *ECHO(nexrt::Handle *);
extern "C" [[noreturn]] void nex_source_error_unhandled(nexrt::Handle *);
int main(){
  for(int repeat=0;repeat<100;++repeat){
    for(int64_t input:{int64_t(41),int64_t(7),int64_t(-1),int64_t(9),std::numeric_limits<int64_t>::max()}){
      try{
        nexrt::RequestScope scope;nexrt::Handle *error=nullptr;
        auto result=STEP(input,&error);if(error)nex_source_error_unhandled(error);
        assert(input==41 && result==42);
      }catch(const nexrt::NativeSourceException &error){
        assert(input==7 && error.code=="entry_abi::Fault" && error.payload);
        auto text=error.payload->value.object->values.at(0).object->values.at(0).object->text;
        assert(text==std::string("\xd0\xaf\0\xf0\x9f\xa7\xa0",7));
      }catch(const nexrt::Trap &error){
        assert(error.code==(input==std::numeric_limits<int64_t>::max()?"E_OVERFLOW":"E_ASSERT"));
        assert(input==-1 || input==9 || input==std::numeric_limits<int64_t>::max());
      }
      nex_runtime_finish();
    }
    for(int64_t input:{int64_t(0),int64_t(7)}){
      try{nexrt::RequestScope scope;nexrt::Handle *error=nullptr;EMPTY(input,&error);
        if(error)nex_source_error_unhandled(error);assert(input==0);
      }catch(const nexrt::NativeSourceException &error){
        assert(input==7 && error.code=="str" && error.payload);
        assert(error.payload->value.object->text=="unit-error");
      }
      nex_runtime_finish();
    }
    for(bool flag:{false,true}){
      {nexrt::RequestScope scope;assert(MIXED(flag,41.5)==(flag?42.0:41.0));}
      nex_runtime_finish();
    }
    {nexrt::RequestScope scope;
      auto *input=nexrt::makeHandle(nexrt::Value(nexrt::string(std::string("\xd0\xaf\0",3))));
      auto result=nexrt::readHandle(ECHO(input));
      assert(result.object->text==std::string("\xd0\xaf\0\xf0\x9f\xa7\xa0",7));
    }
    nex_runtime_finish();
  }
  std::cout<<"1000 calls and cleanup checks passed\n";
}
'''


class NativeEntryABI(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        if os.environ.get('NEX_NATIVE_ENTRY_ABI_OUTPUT'):
            self.root = Path(os.environ['NEX_NATIVE_ENTRY_ABI_OUTPUT']).resolve()/self._testMethodName
            self.root.mkdir(parents=True)
            self.file = self.root/'main.nex'
        self.source(SOURCE)

    def build(self, entry='step', profile='debug', *args):
        return self.cli('build', '--library', '--entry', entry, '--profile', profile,
                        *args, timeout=240)

    def abi(self, built):
        abi = built['native_entry_abi']
        metadata = json.loads(Path(built['metadata']).read_text())
        self.assertEqual(abi, metadata['native_entry_abi'])
        self.assertEqual(abi['schema'], 'nex.native-entry-abi/1')
        self.assertFalse(abi['stable_public_abi'])
        self.assertEqual(abi['build_key'], built['build_key'])
        self.assertEqual(abi['compiler_target'], built['compiler_target'])
        self.assertEqual(abi['data_layout'], metadata['data_layout'])
        ir = Path(built['llvm']).read_bytes()
        self.assertEqual(abi['llvm_sha256'], hashlib.sha256(ir).hexdigest())
        self.assertEqual(len(abi['entries']), 1)
        entry = abi['entries'][0]
        # Use the emitted definition, independently of the source-to-type map.
        match = re.search(r'^define\s+([^@\n]+)@'+re.escape(entry['native_symbol'])+r'\(([^\n]*)\)',
                          ir.decode(), re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match[1].strip(), entry['return']['llvm_type'])
        physical = re.findall(r'(?:^|, )([^ ]+) %[^,]+', match[2])
        self.assertEqual(physical, [p['llvm_type'] for p in entry['parameters']])
        return entry

    def test_real_host_debug_release_scalars_errors_heap_and_cleanup(self):
        evidence = {'compiler_sha256':hashlib.sha256(Path(harness.NEX).read_bytes()).hexdigest(),
                    'profiles':[],'ok':False}
        for profile in ('debug', 'release'):
            with self.subTest(profile=profile):
                builds = {name:self.build(name, profile) for name in ('step','empty','mixed','echo')}
                entries = {name:self.abi(built) for name,built in builds.items()}
                for entry in entries.values():
                    self.assertTrue(entry['direct_host_call'])
                    self.assertEqual(entry['mode'], 'synchronous')
                    self.assertEqual(entry['calling_convention'], 0)
                self.assertEqual(entries['step']['llvm_function_type'], 'i64 (i64, ptr)')
                self.assertEqual(entries['empty']['llvm_function_type'], 'void (i64, ptr)')
                self.assertEqual(entries['mixed']['llvm_function_type'], 'double (i1, double)')
                self.assertEqual(entries['echo']['llvm_function_type'], 'ptr (ptr)')
                error = entries['step']['parameters'][-1]
                self.assertEqual(error['role'], 'source_error_out')
                self.assertEqual(error['initialize'], 'null_handle')
                self.assertEqual(entries['echo']['parameters'][0]['source_type'], 'str')
                text = HOST
                for name,entry in entries.items():
                    text = text.replace(name.upper(), entry['native_symbol'])
                host = self.root/('host-'+profile+'.cpp');host.write_text(text, newline='\n')
                metadata = json.loads(Path(builds['step']['metadata']).read_text())
                driver = json.loads(metadata['toolchain_inputs'])['driver']
                image = self.root/('host-'+profile+('.exe' if os.name=='nt' else ''))
                command = [*driver,'-std=c++20','-I'+metadata['runtime_source_projection'],str(host),
                           *(b['executable'] for b in builds.values()),'-o',str(image)]
                result = subprocess.run(command,capture_output=True,text=True,timeout=180)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                result = subprocess.run([image],capture_output=True,text=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertEqual(result.stdout,'1000 calls and cleanup checks passed\n')
                evidence['profiles'].append({'profile':profile,'native_calls':1000,
                    'owned_cleanup_checks':1000,'stdout':result.stdout,
                    'host_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
                    'library_entries':{name:built['native_entry_abi'] for name,built in builds.items()}})
        evidence['ok'] = True
        (self.root/'host-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n',newline='\n')

    def test_warm_cache_tampered_metadata_repair_and_archived_source(self):
        first = self.build();self.abi(first)
        warm = self.build();self.assertTrue(warm['cached'])
        self.assertEqual(first['native_entry_abi'],warm['native_entry_abi'])
        metadata = Path(first['metadata']);changed = json.loads(metadata.read_text())
        changed['native_entry_abi']['entries'][0]['parameters'].pop()
        metadata.write_text(json.dumps(changed),newline='\n')
        repaired = self.build();self.assertFalse(repaired['cached'])
        self.assertEqual(repaired['compiled_functions'],0)
        self.assertEqual(first['native_entry_abi'],repaired['native_entry_abi'])
        self.file.unlink()
        restored = self.build('step','debug','--revision',first['revision'])
        self.assertTrue(restored['cached'])
        self.assertEqual(first['native_entry_abi'],restored['native_entry_abi'])

    def test_task_entry_is_explicitly_not_a_synchronous_host_call(self):
        # Ordinary --library cannot create a task executor/provider cohort.
        rejected = self.cli('build','--library','--entry','work',ok=False)
        self.assertEqual(rejected['code'],'E_TASK_PROVIDER')
        for name in ('leaf','app'):
            (self.root/name).mkdir()
        (self.root/'leaf/main.nex').write_text(
            'module leaf;pub fn work()->i64 !{task}{task_yield();return 42;}',newline='\n')
        (self.root/'app/main.nex').write_text(
            'module app;import "../leaf/main.nex" as leaf;'
            'fn main()->unit !{task,io}{print(leaf::work());}',newline='\n')
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1',
            'language':harness.CURRENT_LANGUAGE,'entry':'app/main.nex'}),newline='\n')
        (self.root/'nex.build.json').write_text(json.dumps({
            'schema':'nex.project-build/1','default_configuration':'debug',
            'configurations':{'debug':{'profile':'debug'}},'components':{
                'leaf':{'kind':'static_library','root':'leaf','entry':'leaf/main.nex',
                        'entry_function':'work','exports':['work']},
                'app':{'kind':'executable','root':'app','entry':'app/main.nex',
                       'dependencies':{'leaf':'static'}}}}),newline='\n')
        result = self.cli('project','--kind','run','--component','app',timeout=240)
        self.assertEqual(result['observation']['exit_code'],0)
        self.assertEqual(result['observation']['stdout'],'42\n')
        leaf = next(row for row in result['artifacts'] if row.get('component',row.get('name'))=='leaf')
        folder = Path(leaf['artifact']).parent
        meta = json.loads((folder/'build.json').read_text())
        entry = self.abi({'native_entry_abi':meta['native_entry_abi'],
            'metadata':str(folder/'build.json'),'build_key':meta['key'],
            'compiler_target':meta['compiler_target'],'llvm':str(folder/'program.ll')})
        self.assertFalse(entry['direct_host_call'])
        self.assertEqual(entry['mode'],'task_executor')
        self.assertTrue(entry['native_symbol'].endswith('__task_step'))
        self.assertTrue(entry['parameters'])
        self.assertEqual({p['role'] for p in entry['parameters']},{'task_executor_argument'})

    def test_discovery_executable_boundary_and_generic_rejection(self):
        field = self.cli('describe','--field','native_entry_abi')['value']
        pack = json.loads((harness.REPO/'llm/language-pack.json').read_text())
        self.assertEqual(field,pack['native_entry_abi'])
        guide = self.cli('guide','--kind','native-entry-abi')
        self.assertIn('source-error output',guide['text'])
        built = self.cli('build',timeout=240)
        self.assertNotIn('native_entry_abi',built)
        self.assertNotIn('native_entry_abi',json.loads(Path(built['metadata']).read_text()))
        rejected = self.cli('build','--library','--entry','generic',ok=False)
        self.assertEqual(rejected['code'],'E_GENERIC_ENTRY')


if __name__ == '__main__':
    unittest.main()
