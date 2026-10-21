"""Actual iOS target archives/linkage; no device or simulator execution claim."""
import json
from pathlib import Path
import platform
import shutil
import subprocess
import unittest

import support as harness


@unittest.skipUnless(platform.system() == 'Darwin', 'iOS cross compilation requires a macOS host')
class IOSTargets(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        self.sdks = {}
        for name in ('iphoneos', 'iphonesimulator', 'macosx'):
            result = subprocess.run(['xcrun', '--sdk', name, '--show-sdk-path'], capture_output=True, text=True, timeout=20)
            if result.returncode:
                self.skipTest('Xcode SDK unavailable: ' + name)
            self.sdks[name] = Path(result.stdout.strip()).resolve()
        self.doctor = self.cli('doctor')
        self.config = self.root / 'toolchain.json'
        (self.root / 'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.18','entry':'main.nex'}))
        self.source('''module ios_logic;
trait Read {type Item;fn get(value:Self)->Read::Item<Self>;}
struct Box<T> {value:T;}
fn extract<T>(value:Box<T>)->T {return value.value;}
impl boxes<T>:Read for Box<T> {type Item=T;get=extract<T>;}
fn read<T:Read>(value:T)->Read::Item<T> {return Read<T>::get(value);}
pub fn answer()->i64 {
 let original:list<str>=["Я🧠2","tail"];
 let changed:list<str>=push(original,"extra");
 let captured:i64=read(Box<i64>(40));
 let add:fn(i64)->i64=fn(value:i64)->i64{return captured+value;};
 assert(len(original)==2 && len(changed)==3 && len(original[0])==3);
 assert(unwrap(decode_json<Box<str>>(encode_json(Box<str>(original[0])))).value=="Я🧠2");
 assert((false && 1 / 0 == 0)==false);
 return add(2);
}
test fn semantics()->unit {assert(answer()==42);}
''')

    def configure(self, target='arm64-apple-ios17.0', sdk=None, **fields):
        name = 'iphonesimulator' if target.endswith('-simulator') else 'iphoneos'
        value = {'schema':'nex.toolchain/1','target':target,'compiler':self.doctor['native_compiler'],
                 'sysroot':str(self.sdks[name] if sdk is None else sdk), **fields}
        self.config.write_text(json.dumps(value))
        return value

    def build(self, *args, **kwargs):
        return self.cli('build', '--toolchain', self.config, '--library', '--entry', 'answer', *args, **kwargs)

    def command(self, args, timeout=40):
        result = subprocess.run(list(map(str,args)), capture_output=True, text=True, timeout=timeout)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return result.stdout

    def test_device_simulator_archives_link_and_cache_with_distinct_platforms(self):
        self.cli('test')
        self.cli('test','--target','web')
        keys = set()
        symbol = self.cli('context','--symbol','answer')['native_symbol']
        bridge = self.root / 'bridge.cpp'
        bridge.write_text('extern "C" long long '+symbol+'();\nextern "C" long long nex_ios_answer(){return '+symbol+'();}\n')
        for target, sdk, arch, apple_platform in (
            ('arm64-apple-ios17.0','iphoneos','arm64','IOS'),
            ('arm64-apple-ios17.0-simulator','iphonesimulator','arm64','IOSSIMULATOR'),
            ('x86_64-apple-ios17.0-simulator','iphonesimulator','x86_64','IOSSIMULATOR')):
            self.configure(target)
            inspected = self.cli('toolchain',self.config)
            self.assertFalse(inspected['host_compatible'])
            for profile in ('debug','release'):
                with self.subTest(target=target,profile=profile):
                    built = self.build('--profile',profile,timeout=120)
                    self.assertEqual(built['kind'],'static_library')
                    self.assertFalse(built['host_compatible'])
                    self.assertNotIn(built['build_key'],keys);keys.add(built['build_key'])
                    self.assertTrue(self.build('--profile',profile)['cached'])
                    meta = json.loads(Path(built['metadata']).read_text())
                    inputs = json.loads(meta['toolchain_inputs'])
                    self.assertEqual(inputs['sqlite_library'],'')
                    self.assertEqual(inputs['openssl_ssl'],'')
                    self.assertIn('--sysroot='+str(self.sdks[sdk]),inputs['driver'])
                    self.assertIn('target triple = "'+built['compiler_target']+'"',Path(built['llvm']).read_text())
                    folder = Path(built['executable']).parent
                    for obj in folder.rglob('*.o'):
                        info=self.command(['xcrun','vtool','-show-build',obj])
                        self.assertRegex(info,r'platform\s+'+apple_platform+r'\b')
                        self.assertRegex(info,r'minos\s+17\.0\b')
                        self.assertEqual(self.command(['xcrun','lipo','-archs',obj]).strip(),arch)
                    image=self.root/(target+'-'+profile+'.dylib')
                    self.command([self.doctor['native_compiler'],'--target='+target,'--sysroot='+str(self.sdks[sdk]),
                                  '-std=c++20','-dynamiclib',bridge,built['executable'],'-o',image],timeout=60)
                    info=self.command(['xcrun','vtool','-show-build',image])
                    self.assertRegex(info,r'platform\s+'+apple_platform+r'\b')
                    self.assertRegex(info,r'minos\s+17\.0\b')
                    # A linked target image proves ABI linkage, not target execution.
                    self.assertEqual(self.command(['xcrun','lipo','-archs',image]).strip(),arch)
        self.assertEqual(len(keys),6)
        self.file.unlink()
        shutil.rmtree(folder)
        restored=self.build('--revision',built['revision'],'--profile','release',timeout=120)
        self.assertEqual(restored['build_key'],built['build_key'])
        self.assertEqual(restored['compiled_functions'],0)
        self.assertGreater(restored['reused_functions'],0)

    def test_wrong_sdk_deployment_architecture_and_environment_are_rejected(self):
        for target,sdk in (
            ('arm64-apple-ios17.0',self.sdks['iphonesimulator']),
            ('arm64-apple-ios17.0-simulator',self.sdks['iphoneos']),
            ('arm64-apple-ios17.0',self.sdks['macosx']),
            ('arm64-apple-ios1.0',self.sdks['iphoneos']),
            ('arm64-apple-ios99.0',self.sdks['iphoneos']),
            ('x86_64-apple-ios17.0',self.sdks['iphoneos']),
            ('arm64-apple-ios17.0-macabi',self.sdks['iphoneos']),
            ('arm64-apple-tvos17.0',self.sdks['iphoneos']),
            ('arm64e-apple-ios17.0',self.sdks['iphoneos'])):
            with self.subTest(target=target,sdk=sdk.name):
                self.configure(target,sdk)
                self.assertEqual(self.build(ok=False)['code'],'E_TARGET')
        self.configure();value=json.loads(self.config.read_text());del value['sysroot'];self.config.write_text(json.dumps(value))
        self.assertEqual(self.build(ok=False)['code'],'E_TARGET')
        self.assertEqual(self.cli('build','--target','arm64-apple-ios17.0','--library','--entry','answer',ok=False)['code'],'E_TARGET')

    def test_ios_is_never_local_host_execution_or_an_application_package(self):
        for target in ('arm64-apple-ios17.0','arm64-apple-ios17.0-simulator'):
            self.configure(target)
            for command in ('run','test','debug','profile'):
                self.assertEqual(self.cli(command,'--toolchain',self.config,ok=False)['code'],'E_TARGET_RUN')
            self.assertEqual(self.cli('build','--entry','answer','--toolchain',self.config,ok=False)['code'],'E_TARGET')
            self.assertEqual(self.build('--profile','profile',ok=False)['code'],'E_TARGET')
            self.assertEqual(self.cli('package','--entry','answer','--toolchain',self.config,'--directory',self.root/'package',ok=False)['code'],'E_TARGET')
            self.assertFalse((self.root/'package').exists())
        self.source('module needs_store; server fn answer()->i64 !{db} {return len(unwrap(store_keys("")));}')
        self.assertEqual(self.build(ok=False)['code'],'E_TARGET_LIBRARY')

    def test_actual_driver_must_preserve_deployment_version(self):
        self.configure()
        script=self.root/'wrong-version-driver';log=self.root/'driver-log.jsonl'
        script.write_text('''#!/usr/bin/env python3
import json,os,subprocess,sys
with open(LOG,'a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')
args=[x.replace('ios17.0','ios18.0') if x.startswith('--target=') else x for x in sys.argv[1:]]
os.execv(REAL,[REAL,*args])
'''.replace('LOG',repr(str(log))).replace('REAL',repr(self.doctor['native_compiler'])))
        script.chmod(0o755)
        self.configure(compiler=str(script))
        self.assertEqual(self.build(ok=False)['code'],'E_TARGET')
        calls=[json.loads(line) for line in log.read_text().splitlines()]
        self.assertTrue(any('-emit-llvm' in call for call in calls))
        self.assertFalse(any('-c' in call for call in calls))


if __name__ == '__main__':
    unittest.main(verbosity=2)
