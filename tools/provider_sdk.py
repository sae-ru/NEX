"""Check provider source templates against an actual SDK without running a device."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile


def source_language(descriptor, kind=None):
    if not isinstance(descriptor,dict):
        raise RuntimeError('provider preparation needs a checked source descriptor')
    language=descriptor.get('version','')
    parts=language.split('.') if isinstance(language,str) else []
    foreign=descriptor.get('foreign_boundary',{})
    if (descriptor.get('schema')!='nex.language/1' or len(parts)!=2 or parts[0]!='0' or
            not 1<=len(parts[1])<=8 or not parts[1].isascii() or not parts[1].isdigit() or
            str(int(parts[1]))!=parts[1] or int(parts[1])<20 or not isinstance(foreign,dict) or
            foreign.get('source_support') is not True):
        raise RuntimeError('provider preparation requires a checked language0.20+ source FFI descriptor')
    if kind in ('model','compute') and kind in descriptor:
        feature=descriptor[kind]
        if (not isinstance(feature,dict) or feature.get('source_support') is not True or
                feature.get('import')!='std/'+kind+'.nex' or
                type(feature.get('contract_version')) is not int or feature['contract_version']!=1):
            raise RuntimeError('provider preparation requires checked '+kind+' contract1')
    return language


def sdk_compiler(sdk):
    root=Path(sdk);native=root/'bin/nex.exe'
    return native if os.name=='nt' and native.is_file() else root/'bin/nex'



def native_compile(arguments, **kwargs):
    """Compile a provider while preserving its requested Unicode output path.

    The selected Windows LLVM-MinGW22 linker cannot open some Unicode/percent
    output paths. Inputs stay in the recorded project; link in a private ASCII
    workspace and copy the completed artifact with Python's wide file APIs.
    """
    command=list(map(str,arguments))
    if os.name!='nt':
        return subprocess.run(command,**kwargs)
    index=command.index('-o')+1
    requested=Path(command[index]).absolute()
    directory=Path(os.environ.get('NEX_PROVIDER_BUILD_ROOT',tempfile.gettempdir()))
    if not directory.is_absolute() or not str(directory).isascii() or '%' in str(directory) or not directory.is_dir():
        raise RuntimeError('Windows provider linking requires an absolute ASCII directory; select NEX_PROVIDER_BUILD_ROOT')
    # Python's Windows mkdir0700 descriptor omits the AppContainer principal.
    # Create the private descriptor atomically, using the same effective
    # user/container pair as native runtime snapshots and private tool files.
    import importlib.util
    import uuid
    spec=importlib.util.spec_from_file_location('_nex_provider_windows_files',Path(__file__).with_name('windows_files.py'))
    files=importlib.util.module_from_spec(spec);spec.loader.exec_module(files)
    for attempt in range(10):
        staging=directory/('nex-provider-'+uuid.uuid4().hex)
        try:files.create_private_directory(staging)
        except FileExistsError:continue
        break
    else:raise RuntimeError('cannot create a unique private provider workspace')
    artifact=staging/('provider'+requested.suffix)
    command[index]=str(artifact)
    try:
        result=subprocess.run(command,**kwargs)
        result.nex_link_staging=str(staging)
        result.nex_requested_output=str(requested)
        if result.returncode==0:
            if not artifact.is_file():
                raise RuntimeError('provider compiler did not produce its declared artifact: '+str(artifact))
            shutil.copy2(artifact,requested)
            shutil.rmtree(staging)
        return result
    except BaseException as error:
        raise RuntimeError('provider compilation failed; retained native link workspace '+str(staging)) from error


def check_sdk(sdk, source, libraries, symbols, kind=None):
    sdk=Path(sdk).resolve(strict=True);compiler=sdk_compiler(sdk);resources=sdk/'share/nex'
    if not compiler.is_file() or not resources.is_dir():
        raise RuntimeError('provider SDK needs bin/nex and share/nex')
    environment={**os.environ,'NEX_RESOURCE_DIR':str(resources),'PYTHONDONTWRITEBYTECODE':'1'}
    commands=[]
    with tempfile.TemporaryDirectory(prefix='nex-provider-sdk-') as temporary:
        root=Path(temporary)
        def cli(*arguments):
            argv=[str(compiler),*arguments,'--json']
            result=subprocess.run(argv,cwd=root,env=environment,capture_output=True,text=True,timeout=120)
            commands.append({'argv':argv,'exit_code':result.returncode,
                'stdout_sha256':hashlib.sha256(result.stdout.encode()).hexdigest(),
                'stderr':result.stderr})
            if result.returncode:
                raise RuntimeError('provider source SDK check failed: '+result.stderr[-2048:]+' '+result.stdout[-4096:])
            return json.loads(result.stdout)
        descriptor=cli('describe');language=source_language(descriptor,kind)
        project={'schema':'nex.project/1','language':language,'entry':'main.nex'}
        hashes={}
        if libraries:
            (root/'stdlib').mkdir();project['libraries']={'std':'./stdlib'}
            for name,path in libraries.items():
                shutil.copyfile(path,root/'stdlib'/name)
                hashes[name]=hashlib.sha256(Path(path).read_bytes()).hexdigest()
        (root/'nex.json').write_text(json.dumps(project)+'\n');(root/'main.nex').write_text(source)
        checked=cli('check');signatures={};signature_values={}
        for symbol in symbols:
            signature=cli('ffi','--symbol',symbol)
            if signature.get('schema')!='nex.foreign-signature/1' or not isinstance(signature.get('types'),list) or not signature['types']:
                raise RuntimeError('provider SDK returned an unsupported foreign signature')
            signature_values[symbol]=signature
            signatures[symbol]=hashlib.sha256(json.dumps(signature,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        report={'schema':'nex.provider-sdk-check/1','ok':True,'source_language':language,
            'source_checked':True,'checked_revision':checked['revision'],
            'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),
            'probe_source':source,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'library_sha256':hashes,'signature_sha256':signatures,'signatures':signature_values,'commands':commands,
            'native_host_supported':platform.system()=='Linux' and platform.machine() in ('aarch64','arm64'),
            'native_worker_built':False,'hardware_executed':False}
    report['temporary_project_removed']=True
    return report
