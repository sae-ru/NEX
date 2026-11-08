"""Native host operations shared by the installed SDK acceptance workflow."""
from contextlib import contextmanager
import importlib.util
import os
import platform
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
from types import SimpleNamespace

WINDOWS = os.name == 'nt'

def executable_name(name):
    return name + '.exe' if WINDOWS else name

def same_existing_path(recorded, expected):
    """Match a host path's namespace and physical identity, not its spelling.

    Windows producers may combine native separators with portable suffixes.
    Path equality handles those spellings; samefile also checks the actual
    filesystem, including directories with case-sensitive name lookup. Neither
    an outside hard link nor an unresolved historical path satisfies this check.
    Portable relative inventory names are validated separately by their callers.
    """
    if type(recorded) is not str or '\0' in recorded:
        return False
    try:
        actual, expected = Path(recorded), Path(expected)
        return (actual.is_absolute() and expected.is_absolute() and
                actual == expected and actual.samefile(expected))
    except (OSError, ValueError):
        return False

def shared_name(name):
    return name + ('.dll' if WINDOWS else '.dylib' if platform.system() == 'Darwin' else '.so')

def owned_image_relative_path(image):
    """Use the compiler's adjacent PE DLL / nested Unix image layout."""
    image = Path(image)
    return image.name if image.suffix == '.dll' else 'images/' + image.name

def platform_name():
    machine = {'aarch64':'arm64','arm64':'arm64','AMD64':'x86_64','x86_64':'x86_64'}[platform.machine()]
    return ('windows' if WINDOWS else 'macos' if platform.system() == 'Darwin' else 'linux') + '-' + machine

def host_root(directory):
    return Path(directory).anchor if WINDOWS else '/'

@contextmanager
def connection(*args, **kwargs):
    # Connection.__exit__ commits/rolls back without closing the physical file.
    database = sqlite3.connect(*args, **kwargs)
    try:
        with database:
            yield database
    finally:
        database.close()

_fixture_cache = {}
def fixture(name):
    if name not in _fixture_cache:
        path = Path(__file__).resolve().parents[1]/'tests'/(name+'.py')
        spec = importlib.util.spec_from_file_location('nex_sdk_'+name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _fixture_cache[name] = module
    return _fixture_cache[name]

def deployed_environment(**extra):
    return fixture('host_fixture').deployed_environment(**extra)

def debugger_crash_diagnostic(command, stderr):
    return fixture('host_fixture').debugger_crash_diagnostic(command, stderr)

def compiler_command(arguments):
    values = list(map(str, arguments))
    return ('-o' in values and (any(value.startswith('-std=') for value in values) or
        any(value.lower().endswith(('.c','.cpp','.o','.obj','.ll')) for value in values[1:])))

def compile_fixture(arguments, *, doctor=None, **kwargs):
    command=list(map(str,arguments))
    selected=Path(doctor['native_compiler']) if doctor and doctor.get('native_compiler') else None
    selected_drivers={selected, selected.with_name(executable_name('clang'))} if selected else set()
    if WINDOWS and doctor and Path(command[0]) in selected_drivers:
        # A portable SDK keeps its sysroot separately from the relocated driver.
        # Direct C/C++ fixtures need the same selected target/headers as NEX builds.
        target = doctor.get('host')
        sysroot = doctor.get('native_sysroot')
        if not target or not sysroot:
            raise ValueError('Windows native fixture requires the selected target and sysroot')
        for option, value, aliases in (('--target', target, ('-target', '--target')),
                                       ('--sysroot', sysroot, ('--sysroot', '-isysroot'))):
            if not any(arg in aliases or arg.startswith(option + '=') for arg in command[1:]):
                command.insert(1, option + '=' + str(value))
        if isinstance(arguments, list):
            arguments[:] = command
    requested=Path(command[command.index('-o')+1]) if '-o' in command else None
    result=fixture('host_fixture').run_native(command, **kwargs)
    if isinstance(arguments, list):
        arguments[:] = command
    if WINDOWS and result.returncode==0 and requested is not None:
        # MinGW appends .exe to an extension-free -o. Keep the fixture's exact
        # requested filename for its subsequent inventory/hash checks. It is
        # still a real PE executable launched directly by CreateProcessW.
        actual=requested.with_name(requested.name+'.exe')
        if not requested.is_file() and actual.is_file():
            actual.replace(requested)
    return result

def source(text):
    return fixture('host_fixture').host_cpp(text) if WINDOWS else text

def request_server_stop(process):
    if WINDOWS:
        fixture('host_fixture').stop_server(process if hasattr(process,'pid') else SimpleNamespace(pid=process))
    elif hasattr(process, 'send_signal'):
        process.send_signal(signal.SIGTERM)
    else:
        os.kill(process, signal.SIGTERM)

def interrupt(process):
    if WINDOWS:
        try:
            fixture('host_fixture').interrupt_task(process)
        except OSError:
            process.terminate()
    else:
        os.killpg(process.pid, signal.SIGTERM)

def kill(process):
    if WINDOWS:
        subprocess.run(['taskkill.exe','/PID',str(process.pid),'/T','/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    else:
        os.killpg(process.pid, signal.SIGKILL)

def inspect_loaded(arguments, **kwargs):
    return fixture('windows_loader_fixture').run(arguments, **kwargs)

def selected_tool(sdk, doctor, name):
    if not WINDOWS:
        return name
    if name in ('nm', 'llvm-readobj'):
        return str(Path(doctor['native_compiler']).parent/
                   ('llvm-nm.exe' if name == 'nm' else 'llvm-readobj.exe'))
    if name == 'openssl':
        packaged = Path(sdk)/'libexec/nex/host-tools/openssl.exe'
        return str(packaged if packaged.is_file() else Path(doctor['wasm_compiler']).parent/'openssl.exe')
    return name

def global_symbols(image, run):
    """Distinguish global definitions from actual PE imports, including thunks."""
    symbols = {}
    for line in run(['nm', '-g', image]).splitlines():
        words = line.split()
        if len(words) >= 2 and len(words[-2]) == 1:
            name = words[-1]
            if platform.system() == 'Darwin' and name.startswith('_'):
                name = name[1:]
            symbols.setdefault(name, set()).add(words[-2])
    if WINDOWS and Path(image).suffix.lower() == '.dll':
        # A COFF import library can add a local T jump thunk. Only the actual
        # PE import directory establishes that this name belongs to a dependency;
        # ordinary T/W definitions must still fail provider ownership checks.
        imports = run(['llvm-readobj', '--coff-imports', image])
        for name in re.findall(r'^\s*Symbol: (\S+) \(\d+\)\s*$', imports, re.M):
            symbols[name] = {'U'}
    return symbols
