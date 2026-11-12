"""Observable CLI help/completion/quiet behavior with real shell callbacks."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import support as h

PUBLIC=set('analyze api apply build changes check context contract core cost debug declarations describe diagnose doctor emit eval explain export ffi fmt foreign graph guide help fix bench history identities import init inspect lock lsp migrate operations package profile project recover restore run search snapshot subgraph task test token toolchain verify web completion'.split())


class CLI(h.ToolchainCase):
    def raw(self,*args,ok=True,env=None):
        result=subprocess.run([h.NEX,*map(str,args)],cwd=self.root,capture_output=True,
            text=True,timeout=120,env=None if env is None else {**os.environ,**env})
        self.assertEqual(result.returncode==0,ok,result.stdout+result.stderr)
        return result

    def candidates(self,*words):
        return json.loads(self.raw('complete','--json','--',*words).stdout)['candidates']

    def test_every_command_has_bounded_compiled_help(self):
        # Deliberately invalid metadata must remain unopened by help/query.
        (self.root/'nex.json').write_text('not a project manifest')
        index=self.cli('help');self.assertEqual(index['schema'],'nex.cli-help/1')
        self.assertEqual({c['name'] for c in index['commands']},PUBLIC)
        for command in sorted(PUBLIC|{'complete','inspect-private-task'}):
            with self.subTest(command=command):
                a=self.cli('help',command);b=self.cli(command,'--help')
                self.assertEqual(a,b);self.assertEqual(a['kind'],'command')
                self.assertFalse(a['project_opened']);self.assertFalse(a['command_executed'])
                raw=self.raw(command,'--help','--json')
                self.assertLessEqual(len(raw.stdout.encode()),32768)
                self.assertLessEqual(len(self.raw('help',command).stdout.encode()),16384)
                names=[x['name'] for x in a['options']]
                self.assertEqual(len(names),len(set(names)))
        self.assertEqual(self.raw('--help').stdout,self.raw('help').stdout)
        self.assertEqual(self.raw('-h').stdout,self.raw('help').stdout)
        self.assertEqual(self.cli('build','-h'),self.cli('help','build'))
        self.cli('build','does-not-exist.nex','--help')
        self.raw('help','build',env={'PATH':'','NEX_RESOURCE_DIR':str(self.root/'missing-resources')})
        self.assertFalse((self.root/'.nex').exists())
        self.assertEqual((self.root/'nex.json').read_text(),'not a project manifest')

    def test_diagnostics_and_original_option_types(self):
        for args,code in [(['help','unknown'],'E_COMMAND'),(['unknown','--help'],'E_COMMAND'),
            (['build','--unknown','--help'],'E_OPTION'),
            (['build','--overlay','file','--help'],'E_OPTION'),(['fmt','--write','--write'],'E_OPTION'),
            (['describe','--quiet','--quiet'],'E_OPTION'),(['completion','--kind','unknown'],'E_OPTION')]:
            with self.subTest(args=args):self.assertEqual(self.cli(*args,ok=False)['code'],code)
        missing=self.raw('build','--json','--output',ok=False)
        self.assertEqual(json.loads(missing.stdout)['code'],'E_OPTION')
        build=self.cli('help','build')
        options={x['name']:x for x in build['options']}
        for name in ['--profile','--entry','--output','--target','--toolchain','--task-workers']:
            self.assertTrue(options[name]['takes_value'])
        self.assertEqual(options['--output']['aliases'],['-o'])
        for name in ['--help','--json','--quiet','--library']:
            self.assertFalse(options[name]['takes_value'])
        self.assertNotIn('--interpreter-only',options)
        test_options={x['name']:x for x in self.cli('help','test')['options']}
        self.assertFalse(test_options['--interpreter-only']['takes_value'])
        self.assertNotIn('--entry',test_options)
        self.assertFalse(self.cli('help','profile')['application_arguments'])
        bad_guide=self.cli('guide','--kind','not-a-guide',ok=False)
        self.assertEqual(bad_guide['code'],'E_OPTION');self.assertIn('nex help guide',bad_guide['message'])
        self.source('module cli;fn main()->i64{return 3;}')
        self.raw('emit','--kind','llvm','-o',self.root/'program.ll')
        self.assertTrue((self.root/'program.ll').is_file())
        self.assertEqual(self.cli('eval','--steps','100')['value'],3)

    def test_contextual_completion_and_literal_passthrough(self):
        self.assertEqual(set(self.candidates('')),PUBLIC)
        self.assertEqual(self.candidates('b'),['bench','build'])
        self.assertEqual(self.candidates('help','b'),['bench','build'])
        self.assertEqual(self.candidates('build','--pr'),['--profile'])
        self.assertEqual(self.candidates('project','--profile'),['--profile-output'])
        self.assertEqual(self.candidates('build','--profile',''),['debug','profile','release'])
        self.assertEqual(self.candidates('profile','--profile',''),['profile'])
        self.assertEqual(self.candidates('run','--interpreter'),[])
        self.assertEqual(self.candidates('emit','--kind','c'),['cuda'])
        self.assertEqual(self.candidates('guide','--kind','cl'),['cli'])
        self.assertEqual(set(self.candidates('subgraph','--entity','')),
            {'module','type','trait','impl','function','endpoint'})
        self.assertEqual(self.candidates('build','-o','file.nex','--pr'),['--profile'])
        self.assertEqual(self.candidates('build','--profile','release','--pr'),[])
        self.assertEqual(self.candidates('run','--','--pr'),[])
        self.assertEqual(self.candidates('build',''),[])
        self.assertEqual(self.candidates('build','path with spaces/'),[])
        self.assertEqual(self.candidates('unknown','--pr'),[])
        self.assertEqual(self.raw('complete','--','build','--pr').stdout,'--profile\n')
        result=json.loads(self.raw('complete','--json','--','run','--','--pr').stdout)
        self.assertEqual(result['expects'],'application')
        self.assertFalse(result['command_executed']);self.assertFalse(result['filesystem_read'])
        self.assertFalse((self.root/'.nex').exists())

    def test_quiet_retains_results_json_errors_and_program_stdout(self):
        self.source('module cli;fn main()->unit!{io}{print("Я🌍");}')
        ordinary=self.raw('check');quiet=self.raw('check','--quiet')
        self.assertIn('Checked',ordinary.stdout);self.assertEqual(quiet.stdout,'')
        self.assertEqual(self.cli('check'),self.cli('check','--quiet'))
        self.assertEqual(self.raw('eval').stdout,self.raw('eval','--quiet').stdout)
        self.assertEqual(self.cli('eval'),self.cli('eval','--quiet'))
        self.assertEqual(self.cli('run','--profile','release','--quiet')['stdout'],'Я🌍\n')
        self.assertEqual(self.raw('run','--profile','release','--quiet').stdout,'Я🌍\n')
        preview=self.raw('fmt',self.file).stdout
        self.assertEqual(self.raw('fmt',self.file,'--quiet').stdout,preview)
        self.assertEqual(self.cli('fmt',self.file),self.cli('fmt',self.file,'--quiet'))
        failed=self.raw('fmt',self.file,'--check','--quiet',ok=False)
        self.assertIn('Needs formatting',failed.stderr)
        self.source('module cli;fn main()->i64{return missing;}')
        failed=self.raw('check','--quiet',ok=False)
        self.assertIn('E_NAME',failed.stderr)
        self.assertEqual(self.cli('check',ok=False),self.cli('check','--quiet',ok=False))
        created=self.root/'new'
        self.assertEqual(self.raw('init',created,'--quiet').stdout,'')
        self.assertTrue((created/'nex.json').is_file())
        self.assertEqual(self.cli('init',created,'--quiet',ok=False)['code'],'E_EXISTS')
        selected=self.root/'init-029'
        self.assertEqual(self.raw('init',selected,'--quiet','--language-version','0.29').returncode,0)
        self.assertEqual(json.loads((selected/'nex.json').read_text())['language'],'0.29')
        self.assertEqual(self.cli('check',cwd=selected)['ok'],True)
        self.assertEqual(self.raw('init',self.root/'init-bad','--quiet','--language-version','0.30',ok=False).returncode,1)

    def test_shell_scripts_and_actual_bash_zsh_callbacks(self):
        scripts={shell:self.cli('completion','--kind',shell)['script']
            for shell in ['bash','zsh','fish','powershell']}
        for shell,script in scripts.items():
            path=self.root/('completion.'+shell);path.write_text(script)
            self.assertIn('nex complete --',script)
            self.assertEqual(self.raw('completion','--kind',shell).stdout,script)
        bindir=self.root/'bin';bindir.mkdir()
        if os.name=='nt':
            # The callback's selected executable is the actual compiler.
            bindir=Path(h.NEX).parent
        else:(bindir/'nex').symlink_to(h.NEX)
        env={**os.environ,'PATH':str(bindir)+os.pathsep+os.environ.get('PATH','')}
        observed=[]
        for shell in dict.fromkeys([shutil.which('bash'),'/bin/bash' if os.name!='nt' else None,shutil.which('zsh')]):
            if not shell or not Path(shell).is_file():continue
            kind='zsh' if Path(shell).name=='zsh' else 'bash';script=self.root/('completion.'+kind)
            syntax=subprocess.run([shell,'-n',script],capture_output=True,text=True)
            self.assertEqual(syntax.returncode,0,syntax.stderr)
            if kind=='bash':
                body='source "$1"; COMP_WORDS=(nex build --pr); COMP_CWORD=2; _nex_complete; printf "%s\\n" "${COMPREPLY[@]}"'
            else:
                body='compdef(){ :; }; compadd(){ print -rl -- "${candidates[@]}"; }; _files(){ :; }; source "$1"; words=(nex build --pr); CURRENT=3; PREFIX=--pr; _nex_complete'
            run=subprocess.run([shell,'-f','-c',body,'nex-test',str(script)],env=env,
                cwd=self.root,capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr);self.assertEqual(run.stdout,'--profile\n')
            observed.append(shell)
        self.assertTrue(observed or os.name=='nt','Bash or zsh is required for Unix shell qualification')
        print(json.dumps({'executed_shell_callbacks':observed,'fish_or_PowerShell_execution_claimed':False}))

    def test_descriptor_and_language_pack_contract(self):
        cap=self.cli('describe','--field','cli_interface')['value']
        pack=json.loads((h.REPO/'llm/language-pack.json').read_text())
        self.assertEqual(cap,pack['cli_interface'])
        self.assertIn('nex help',json.dumps(self.cli('guide','--kind','cli')))


if __name__=='__main__':unittest.main()
