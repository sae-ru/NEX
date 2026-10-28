"""Execute checked private mixed images and verify actual code/data ownership."""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from source_exception_modules import CASES as OLD_CASES, DECL
from source_exception_host import MODULE
from source_exception_profile_support import FLAGS as PROFILE_FLAGS,EXTRA_RUNTIME,host_identity
import source_exception_module_debug_support as debug_support


def chain(leaf, mid, app, entry="run", foreign=False, budget=1000000, exports=None):
    return {"sources": {"leaf": leaf, "mid": mid, "app": app},
            "entries": {"leaf": entry, "mid": "run", "app": "main"},
            "exports": exports or {}, "foreign": foreign, "budget": budget,
            "topologies": {"static-in-shared": {"leaf": "static", "mid": "shared"},
                           "shared-under-static": {"leaf": "shared", "mid": "static"}}}


CASES = {}
for name, entry in [("direct-catch", "fail"), ("uncaught-rethrow", "fail"), ("runtime-trap", "fail")]:
    c = OLD_CASES[name]
    CASES[name] = chain(c["leaf"], c["mid"], c["app"], entry)
for name, result, effects, realm, foreign in [
        ("returned-pure-callback", "fn(i64)->i64 !{throw}", "", "", False),
        ("returned-resource-callback", "server fn()->i64 !{task,ffi}", "!{task,ffi}", "server ", True)]:
    c = OLD_CASES[name]
    mid = 'module mid;import "../leaf/main.nex" as leaf;pub ' + realm + 'fn run()->' + result + ' ' + effects + '{return leaf::make();}'
    app = c["app"].replace('../leaf/main.nex', '../mid/main.nex').replace('as leaf;', 'as mid;').replace('leaf::make()', 'mid::run()')
    CASES[name] = chain(c["leaf"], mid, app, "make", foreign)
c = OLD_CASES["caller-callback"]
CASES["caller-callback"] = chain(c["leaf"], 'module mid;import "../leaf/main.nex" as leaf;pub fn run(cb:fn(i64)->i64 !{throw},v:i64)->i64 !{throw}{return leaf::apply(cb,v);}', c["app"].replace('../leaf/main.nex', '../mid/main.nex').replace('as leaf;', 'as mid;').replace('leaf::apply', 'mid::run'), "apply")
c = OLD_CASES["concrete-generic"]
CASES["concrete-generic"] = chain(c["leaf"], 'module mid;import "../leaf/main.nex" as leaf;pub fn run()->i64 !{task,throw}{return leaf::generic(7);}', c["app"].replace('../leaf/main.nex', '../mid/main.nex').replace('as leaf;', 'as mid;').replace('leaf::generic(7)', 'mid::run()'), "generic")
c = OLD_CASES["owned-file-resource"]
CASES["owned-file-resource"] = chain(c["leaf"], r'''module mid;import "../leaf/main.nex" as leaf;
pub server fn run(s:task_scope,q:channel<file>)->i64 !{task,fs,ffi,throw}{
 let c:leaf::Counter=leaf::make(42);let t:task<file>=task_spawn(s,leaf::open);
 let f:file=task_wait(t);assert(task_send(q,f));
 try{return leaf::use(c,f);}catch(code,message){assert(code=="OWNER"&&len(message)==3);return 42;}}''', r'''module app;import "../mid/main.nex" as mid;
server fn main()->i64 !{task,fs,ffi,throw}{return with_tasks(2,server fn(s:task_scope)->i64 !{task,fs,ffi,throw}{
 let q:channel<file>=channel_new<file>(s,1);let n:i64=mid::run(s,q);
 let f:file=unwrap(task_recv(q));assert(unwrap(file_read(f,2))==utf8_bytes("cd"));file_close(f);return n;});}''', "open", True, exports={"leaf": ["make", "use"]})
c = OLD_CASES["future-resource"]
CASES["future-resource"] = chain(c["leaf"], r'''module mid;import "../leaf/main.nex" as leaf;
pub server fn run(s:task_scope)->i64 !{task,ffi,throw}{let t:task<leaf::Counter>=leaf::launch(s);
let c:leaf::Counter=task_wait(t);assert(resource_is_open(c));resource_close(c);return 42;}''', r'''module app;import "../mid/main.nex" as mid;
server fn main()->i64 !{task,ffi,throw}{return with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi,throw}{return mid::run(s);});}''', "launch", True)
c = OLD_CASES["budget-owned-cleanup"]
CASES["budget-owned-cleanup"] = chain(c["leaf"], 'module mid;import "../leaf/main.nex" as leaf;pub server fn run()->i64 !{task,fs,ffi}{return leaf::spin();}', c["app"].replace('../leaf/main.nex', '../mid/main.nex').replace('as leaf;', 'as mid;').replace('leaf::spin()', 'mid::run()'), "spin", True, 10000)
CASES["drain-source-error"] = chain('module leaf;pub fn fail()->i64 !{task,throw}{task_yield();throw("DRAIN","λ\\u0000🙂");}', 'module mid;import "../leaf/main.nex" as leaf;pub fn run(s:task_scope)->unit !{task}{let t:task<i64>=task_spawn(s,leaf::fail);return;}', r'''module app;import "../mid/main.nex" as mid;fn main()->i64 !{task}{try{return with_tasks(1,fn(s:task_scope)->i64 !{task}{mid::run(s);return 0;});}catch(code,message){assert(code=="DRAIN"&&len(message)==3);return 42;}}''', "fail")
diamond = {"leaf": 'module leaf;pub fn value()->i64 !{task,throw}{task_yield();throw("DIAMOND","same owner");}',
           "left": 'module left;import "../leaf/main.nex" as leaf;pub fn run()->i64 !{task}{try{return leaf::value();}catch(code,message){return 20;}}',
           "right": 'module right;import "../leaf/main.nex" as leaf;pub fn run()->i64 !{task}{try{return leaf::value();}catch(code,message){return 22;}}',
           "app": 'module app;import "../left/main.nex" as left;import "../right/main.nex" as right;fn main()->i64 !{task}{return left::run()+right::run();}'}
CASES["diamond"] = {"sources": diamond, "entries": {"leaf": "value", "left": "run", "right": "run", "app": "main"},
                    "topologies": {"same-image": {k: "static" for k in ["leaf", "left", "right"]}, "shared-diamond": {k: "shared" for k in ["leaf", "left", "right"]}}}
bridge = {**diamond, "bridge": diamond["app"].replace('module app;', 'module bridge;').replace('fn main()', 'pub fn run()'), "app": 'module app;import "../bridge/main.nex" as bridge;fn main()->i64 !{task}{return bridge::run();}'}
CASES["diamond-shared-frontier"] = {"sources": bridge, "entries": {"leaf": "value", "left": "run", "right": "run", "bridge": "run", "app": "main"},
                                    "topologies": {"one-shared-frontier": {"leaf": "static", "left": "static", "right": "static", "bridge": "shared"}}}
CASES["uncalled-shared-export"] = {"sources": {
    "leaf": 'module leaf;pub server fn unused()->file !{task,fs}{return unwrap(file_open_read("input"));}',
    "mid": 'module mid;pub fn run()->i64 !{task}{return 42;}',
    "app": 'module app;import "../leaf/main.nex" as leaf;import "../mid/main.nex" as mid;fn main()->i64 !{task}{return mid::run();}'},
    "entries": {"leaf": "unused", "mid": "run", "app": "main"}, "native_no_file_configuration": True,
    "topologies": {"uncalled-shared-with-static": {"leaf": "shared", "mid": "static"},
                   "uncalled-shared-with-shared": {"leaf": "shared", "mid": "shared"}}}


def main(cases=None, architecture_version=2, output_env="NEX_EXCEPTION_FRONTIERS_OUTPUT", finalize=True, instrumentation=None):
    p = argparse.ArgumentParser()
    for name in ["probe", "reference", "signatures", "compiler"]:
        p.add_argument(name)
    p.add_argument("--output", default=os.environ.get(output_env))
    p.add_argument("--runtime-cache")
    p.add_argument("--crypto-library")
    p.add_argument("--debug-compiler")
    p.add_argument("--debug-native-only",action="store_true")
    p.add_argument("--case", action="append")
    a = p.parse_args()
    source = Path(__file__).resolve().parents[1]
    runtime = source / "runtime"
    out = Path(a.output or tempfile.mkdtemp(prefix="nex-frontiers-")).resolve()
    out.mkdir(parents=True, exist_ok=True)
    compiler = Path(a.compiler).absolute()
    probe, reference, signatures = [Path(getattr(a, n)).resolve() for n in ["probe", "reference", "signatures"]]
    mac = platform.system() == "Darwin"
    suffix = ".dylib" if mac else ".so"
    crypto = a.crypto_library or ("/opt/homebrew/opt/openssl@3/lib/libcrypto.dylib" if mac else "-lcrypto")
    cache = Path(a.runtime_cache).resolve() if a.runtime_cache else out / "runtime"
    cache.mkdir(parents=True, exist_ok=True)
    report = {"ok": False, "commands": [], "cases": [], "rejections": [], "incremental": [], "relocated": [],
              "ordinary_functional_only": True, "security_checks_deferred_by_user": True,
              "private_identity": "0.25-prototype", "public_language": "0.24", "full_objective_complete": False,
              "public_source_support": False, "descriptor_abi": "0x4e45585400002502"}

    def save():
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    def run(label, argv, env=None, allowed=(0,), timeout=300):
        result = subprocess.run(list(map(str, argv)), cwd=out, env=env, text=True, capture_output=True, timeout=timeout)
        for channel in ["stdout", "stderr"]:
            (out / (label + "." + channel)).write_text(getattr(result, channel))
        report["commands"].append({"label": label, "argv": list(map(str, argv)), "exit": result.returncode})
        save()
        assert result.returncode in allowed, (label, result.returncode, result.stdout[-1200:], result.stderr[-3000:])
        return result

    run("target", [compiler, "-x", "c", "-S", "-emit-llvm", "/dev/null", "-o", out / "target.ll"])
    target = (out / "target.ll").read_text()
    triple = re.search(r'target triple = "([^"]+)"', target)[1]
    layout = re.search(r'target datalayout = "([^"]+)"', target)[1]
    flags = ["-std=c++20", "-O1", "-g", "-fPIC", "-DNEX_STRUCTURED_WORKERS", "-DNEX_ASYNC_TASKS", "-DNEX_FOREIGN_ENABLED", "-I" + str(runtime)]
    profiled = instrumentation == 'profile'
    debugged = instrumentation == 'debug'
    assert instrumentation is None or (profiled and architecture_version == 5) or (debugged and architecture_version == 6)
    if debugged:flags += debug_support.FLAGS
    if profiled:
        flags += PROFILE_FLAGS
    headers = {str(f.relative_to(runtime)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(runtime.rglob("*")) if f.is_file() and f.suffix in [".h", ".hpp"]}
    compiler_hash = hashlib.sha256(compiler.read_bytes()).hexdigest()
    objects = []
    runtime_names = ["runtime.cpp", "nex_files.cpp", "files_runtime.cpp", "nex_task_frame.cpp", "nex_task_external.cpp", "nex_task_application.cpp", "foreign_runtime.cpp", "nex_foreign.cpp", "nex_ffi_loader.cpp", "nex_ffi.cpp", "nex_ffi_types.cpp", "nex_ffi_resources.cpp", "nex_external_resource.cpp", "nex_resource_region.cpp", "nex_resource_executor.cpp", "nex_json.cpp"]
    if profiled:runtime_names += EXTRA_RUNTIME
    if debugged:runtime_names += debug_support.EXTRA_RUNTIME
    for name in runtime_names:
        obj = cache / (name + ".o")
        obj.parent.mkdir(parents=True, exist_ok=True)
        stamp = obj.with_suffix(".recipe.json")
        recipe = {"compiler": compiler_hash, "source": hashlib.sha256((runtime / name).read_bytes()).hexdigest(), "headers": headers, "flags": flags}
        if not (obj.is_file() and stamp.is_file() and json.loads(stamp.read_text()) == recipe):
            run("compile-" + name.replace('/','_'), [compiler, *flags, "-c", runtime / name, "-o", obj])
            stamp.write_text(json.dumps(recipe, sort_keys=True) + "\n")
        objects.append(obj)
    shared_runtime = cache / ("libnex-private-runtime" + suffix)
    run("runtime-shared", [compiler, "-dynamiclib" if mac else "-shared", *objects, crypto, "-pthread", *(["-Wl,-install_name,@rpath/" + shared_runtime.name] if mac else ["-ldl", "-Wl,-soname," + shared_runtime.name]), "-o", shared_runtime])

    def materialize(directory, case, pin):
        directory.mkdir()
        sources = {k + "/main.nex": v.replace("DECL", DECL.replace("@PIN@", pin)) for k, v in case["sources"].items()}
        for name, text in sources.items():
            f = directory / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text)
        (directory / "nex.json").write_text(json.dumps({"schema": "nex.project/1", "language": "0.24", "entry": "app/main.nex"}))
        context = directory / "context.json"
        context.write_text(json.dumps({"schema": "nex.private-task-source/2", "file": str(directory / "app/main.nex"), "source": sources["app/main.nex"], "entry_unit": "app/main.nex", "units": [{"unit": k, "file": str(directory / k), "source": v} for k, v in sorted(sources.items())]}, ensure_ascii=False))
        return context, sources

    ctx, _ = materialize(out / "signatures", CASES["owned-file-resource"], "0" * 64)
    sigs = json.loads(run("signatures", [signatures, "signatures-context", ctx]).stdout)
    bundle = out / "bundle"
    bundle.mkdir()
    rows = []
    for name, op in [("create", 1), ("read", 2), ("add", 3), ("ordinary", 4), ("bad", 5)]:
        sha = hashlib.sha256(json.dumps(sigs[name], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        rows.append('{sizeof(nex_ffi_export_v1),0,' + json.dumps(name) + ',' + json.dumps(sha) + ',callback,(void*)' + str(op) + '}')
    (out / "module.c").write_text(MODULE.replace("EXPORTS", ",".join(rows)))
    run("foreign-module", [compiler, "-x", "c", "-std=c11", "-shared", "-fPIC", "-fvisibility=hidden", "-I" + str(runtime), out / "module.c", "-o", bundle / "module"])
    (bundle / "NOTICE").write_text("NEX ordinary mixed-image fixture\n")
    manifest = {"schema": "nex.foreign-bundle/1", "platform": ("macos" if mac else "linux") + "-" + {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x86_64"}[platform.machine()], "entry": "module", "files": [{"path": name, "sha256": hashlib.sha256((bundle / name).read_bytes()).hexdigest()} for name in ["module", "NOTICE"]], "exports": {k: hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest() for k, v in sigs.items()}, "notices": ["NOTICE"]}
    (bundle / "manifest.json").write_text(json.dumps(manifest) + "\n")
    pin = hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()
    catalog = out / "host.json"
    catalog.write_text(json.dumps({"schema": "nex.foreign-host/1", "module_limit": 64, "libraries": {"host": {"directory": "bundle", "manifest_sha256": pin, "exports": list(sigs)}}}))

    host_template = r'''#include "nex_host.h"
#include "nex_task_frame.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <dlfcn.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#else
#include <link.h>
#endif
DECLARATIONS
extern "C" int nex_private_modules_entry(int,const char *const *);
static const char *base(const char *p){auto *s=std::strrchr(p,'/');return s?s+1:p;}
static const nexrt::TaskCodeDescriptor *find(const char *symbol){using Accessor=const nexrt::TaskCodeDescriptor *(*)();auto f=reinterpret_cast<Accessor>(dlsym(RTLD_DEFAULT,symbol));return f?f():nullptr;}
static long files(){auto *d=opendir("/dev/fd");if(!d)std::abort();long n=0;while(auto *e=readdir(d))if(e->d_name[0]!='.')++n;closedir(d);return n;}
static bool inspect(const nexrt::TaskCodeDescriptor *code,const char *function,const char *expected){
 Dl_info data{},step{};bool ok=code&&code->abi==nexrt::taskCodeExceptionHostPrototypeABI&&dladdr(code,&data)&&dladdr(reinterpret_cast<const void*>(code->step),&step)&&!std::strcmp(base(data.dli_fname),expected)&&!std::strcmp(base(step.dli_fname),expected);
 std::fprintf(stderr,"NEX_PRIVATE_FRONTIER_ADDRESS {\"function\":\"%s\",\"expected\":\"%s\",\"data\":\"%s\",\"step\":\"%s\",\"ok\":%s}\n",function,expected,data.dli_fname?base(data.dli_fname):"",step.dli_fname?base(step.dli_fname):"",ok?"true":"false");return ok;}
static void images(unsigned &runtime,unsigned &code){
#ifdef __APPLE__
 for(uint32_t i=0;i<_dyld_image_count();++i){auto *name=base(_dyld_get_image_name(i));if(std::strstr(name,"libnex-private-runtime.dylib"))++runtime;if(!std::strncmp(name,"libimage-",9))++code;}
#else
 struct Counts{unsigned &runtime,&code;} counts{runtime,code};dl_iterate_phdr([](struct dl_phdr_info *image,size_t,void *p){auto &c=*static_cast<Counts*>(p);auto *name=base(image->dlpi_name);if(std::strstr(name,"libnex-private-runtime.so"))++c.runtime;if(!std::strncmp(name,"libimage-",9))++c.code;return 0;},&counts);
#endif
}
int main(int argc,const char *const *argv){bool addresses=true;CHECKS
 auto before=nexrt::liveObjects.load();auto descriptors=files();auto result=nex_private_modules_entry(argc,argv);nex_runtime_finish();unsigned runtime=0,code=0;images(runtime,code);
 bool clean=addresses&&nexrt::liveObjects.load()==before&&files()==descriptors&&runtime==EXPECT_RUNTIME&&code==EXPECT_CODE;
 std::fprintf(stderr,"NEX_PRIVATE_MODULE_CLEANUP {\"ok\":%s,\"managed_live\":%llu,\"runtime_finish\":true,\"file_delta\":%ld,\"runtime_images\":%u,\"code_images\":%u}\n",clean?"true":"false",(unsigned long long)(nexrt::liveObjects.load()-before),files()-descriptors,runtime,code);return clean?result:71;}
'''

    def image_file(image, plan):
        return "program" if image == plan["application"] else "libimage-" + image + suffix

    def link_image(label, directory, image, plan, records, host=None, app_object=None):
        row = plan["images"][image]
        own = app_object or directory / image / "module.o"
        statics = []
        for component in row["static_components"]:
            archive = directory / ("lib" + component + ".a")
            statics += ["-Wl,-force_load," + str(archive)] if mac else ["-Wl,--whole-archive," + str(archive) + ",--no-whole-archive"]
        libraries = (["-Wl,-needed_library," + str(directory / image_file(name, plan)) for name in row["dependencies"]]
                     if mac else ["-Wl,--no-as-needed", "-L" + str(directory), *["-limage-" + name for name in row["dependencies"]]])
        shared = plan["runtime_linkage"] == "shared"
        output = directory / image_file(image, plan)
        args = [compiler, *([] if image == "app" else ["-dynamiclib" if mac else "-shared"]), own, *([host] if host else []), *statics, *libraries]
        if image == "app":
            args += ["-Wl,-export_dynamic" if mac else "-Wl,--export-dynamic"]
        if shared and mac:
            args += ["-L" + str(directory)]
        args += ["-lnex-private-runtime"] if shared else [*objects, crypto, "-pthread", *([] if mac else ["-ldl"])]
        if image != "app":
            args += ["-Wl,-install_name,@rpath/" + output.name] if mac else ["-Wl,-soname," + output.name]
        if shared:
            args += ["-Wl,-rpath,@loader_path" if mac else "-Wl,-rpath,$ORIGIN", *([] if mac else ["-Wl,-z,defs"])]
        run(label + "-link-" + image, [*args, "-o", output])
        return output

    selected = {k: v for k, v in (CASES if cases is None else cases).items() if not a.case or k in a.case}
    for name, case in selected.items():
        directory = out / name
        ctx, sources = materialize(directory, case, pin)
        oracle = None
        budget = case.get("budget", 1000000)
        for mode in ["host-reference-context", "host-task-ir-context"]:
            files = directory / mode
            files.mkdir()
            (files / "input").write_text("abcdef")
            events = files / "events"
            env = {**os.environ, "NEX_FILES_ROOT": str(files), "NEX_FILES_WRITE": "1", "NEX_PRIVATE_HOST_EVENTS": str(events)}
            value = json.loads(run(name + "-" + mode, [reference, mode, ctx, str(budget), catalog if case.get("foreign") else "-"], env).stdout)
            assert value["managed_live"] == value["external_capacity"] == 0
            observed = events.read_text() if events.exists() else ""
            assert observed.count("F") == observed.count("X")
            outcome = {k: value[k] for k in ["kind", "value", "code", "message", "line", "column", "output"] if k in value}
            if oracle is None:
                oracle = outcome
            elif name == "budget-owned-cleanup":
                assert oracle["kind"] == outcome["kind"] == "trap" and oracle["code"] == outcome["code"] == "E_LIMIT"
            else:
                assert oracle == outcome, (name, oracle, outcome)
        expected = case.get("expected", "exception" if name == "uncaught-rethrow" else "trap" if name in ["runtime-trap", "budget-owned-cleanup"] else "return")
        assert oracle["kind"] == expected and (expected != "return" or oracle["value"] == 42), (name, oracle)
        catalog_instances = None
        if architecture_version >= 3:
            catalog_instances = json.loads(run(name + "-instances", [probe, "instances", ctx]).stdout)
            assert catalog_instances["schema"] == "nex.private-task-instances/1" and catalog_instances["archived"] is False
        for topology, linkages in case["topologies"].items():
            model = directory / topology
            model.mkdir()
            components = {k: {"entry": k + "::" + case["entries"][k], "units": [k + "/main.nex"], "exports": [k + "::" + v for v in case.get("exports", {}).get(k, [])], "dependencies": re.findall(r'import "\.\./([^/]+)/main\.nex"', text), "linkage": "application" if k == "app" else linkages[k]} for k, text in case["sources"].items()}
            if architecture_version >= 3:
                for component, row in components.items():
                    row["instantiations"] = []
                    for request in case.get("instantiations", {}).get(component, []):
                        matches = [k for k, v in catalog_instances["instances"].items() if v["template"] == request["template"] and v["arguments"] == request["arguments"]]
                        assert len(matches) == 1, (name, request, catalog_instances)
                        row["instantiations"].append(matches[0])
                for component, functions in case.get("instance_exports", {}).items():
                    components[component]["exports"] += [v for v in components[component]["instantiations"] if any(catalog_instances["instances"][v]["template"] == wanted for wanted in functions)]
            if case.get('component_names'):
                aliases=case['component_names'];components={aliases.get(key,key):{**value,'dependencies':[aliases.get(dep,dep) for dep in value['dependencies']]} for key,value in components.items()}
            architecture = {"schema": "nex.private-task-architecture/" + str(architecture_version), "mode": "mixed-fixed", "application": "app", "components": components}
            if architecture_version >= 4:architecture['host'] = 'application'
            if profiled:architecture['instrumentation'] = 'profile'
            if debugged:architecture.update(instrumentation='debug',debug_timeout_ms=60000)
            arch = model / "architecture.json"
            arch.write_text(json.dumps(architecture))
            plan = json.loads(run(name + "-" + topology + "-plan", [probe, "plan", ctx, arch]).stdout)
            assert plan["schema"] == "nex.private-task-modules/" + str(architecture_version) and plan["archived"] is False and "revision" not in plan
            assert set(plan["component_images"]) == set(components)
            for optimization in ["0", "2"]:
                label = name + "-" + topology + "-O" + optimization
                e = model / ("O" + optimization)
                e.mkdir()
                records, metadata, accessors, compiled_symbols = {}, [], {}, {}
                shared = plan["runtime_linkage"] == "shared"
                if shared:
                    shutil.copyfile(shared_runtime, e / shared_runtime.name)
                for component in plan["load_order"]:
                    module = e / component
                    run(label + "-" + component + "-emit", [probe, "emit", ctx, arch, component, module, triple, layout, str(optimization == "2").lower()])
                    record = json.loads((module / "module-record.json").read_text())
                    assert record == plan["components"][component] and record["schema"] == "nex.private-task-module/" + str(architecture_version)
                    run(label + "-" + component + "-validate", [probe, "validate", ctx, arch, component, module / "module-record.json"])
                    records[component] = record
                    ir = (module / "module.ll").read_text()
                    compiled_symbols[component] = re.findall(r'^define[^\n]*@([^\s(]+__task_step)\(', ir, re.M)
                    assert len(compiled_symbols[component]) == len(record["definitions"])
                    code = module / "module.ll"
                    if component == "app":
                        assert ir.count("@main(") == 1
                        code = module / "linked.ll"
                        code.write_text(ir.replace("@main(", "@nex_private_modules_entry("))
                    run(label + "-" + component + "-object", [compiler, "-c", "-fPIC", "-O" + optimization, code, "-o", module / "module.o"])
                    meta = json.loads((module / "metadata.json").read_text())
                    metadata += meta["operations"]
                    accessors[record["entry"]] = meta["descriptor_symbol"]
                    accessors.update({k: v["accessor"] for k, v in record["exports"].items()})
                    accessors.update({k: v["accessor"] for k, v in record.get("support_exports", {}).items()})
                    accessors.update({k: v["accessor"] for k, v in record.get("instantiation_descriptors", {}).items()})
                    if record["linkage"] == "static":
                        run(label + "-" + component + "-archive", [compiler.parent / "llvm-ar", "rcs", e / ("lib" + component + ".a"), module / "module.o"])
                declarations, checks = [], []
                if profiled:
                    declarations += [host_identity(plan)]
                if debugged:
                    declarations += [debug_support.host_identity(plan)]
                for function, accessor in sorted(accessors.items()):
                    checks.append('addresses=inspect(find(' + json.dumps(accessor) + '),' + json.dumps(function) + ',' + json.dumps(image_file(plan["definition_owners"][function], plan)) + ')&&addresses;')
                host = host_template.replace("DECLARATIONS", "\n".join(declarations)).replace("CHECKS", "\n".join(checks)).replace("EXPECT_RUNTIME", str(int(shared))).replace("EXPECT_CODE", str(len(plan["images"]) - 1))
                if debugged:host=host.replace('auto before=nexrt::liveObjects.load();','nex_private_module_debug_start();auto before=nexrt::liveObjects.load();').replace('bool clean=addresses&&','bool clean=nex_private_module_debug_finish()&&addresses&&')
                (e / "host.cpp").write_text(host)
                run(label + "-host", [compiler, *flags, "-c", e / "host.cpp", "-o", e / "host.o"])
                images, symbols = {}, {}
                for image in plan["image_load_order"]:
                    binary = link_image(label, e, image, plan, records, e / "host.o" if image == "app" else None)
                    images[image] = {"file": binary.name, "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}
                    text = run(label + "-symbols-" + image, [compiler.parent / "llvm-nm", "--defined-only", "--format=posix", binary]).stdout
                    symbols[image] = [v.lstrip("_") for v in re.findall(r'^([^ ]+__task_step) ', text, re.M)]
                    expected_symbols = {v for component, row in records.items() if row["machine_image"] == image for v in compiled_symbols[component]}
                    assert len(symbols[image]) == len(plan["images"][image]["definitions"]) and set(symbols[image]) == expected_symbols, (name, image, symbols[image], expected_symbols)
                    for function in plan["images"][image]["definitions"]:
                        descriptor = accessors.get(function)
                        if descriptor:
                            assert descriptor.replace("__task_code_address", "__task_step") in symbols[image]
                assert len(set(v for row in symbols.values() for v in row)) == sum(map(len, symbols.values()))
                files = e / "files"
                files.mkdir()
                (files / "input").write_text("abcdef")
                events = files / "events"
                env = {**os.environ, "PATH": "/usr/bin:/bin", "NEX_FILES_ROOT": str(files), "NEX_FILES_WRITE": "1", "NEX_PRIVATE_HOST_EVENTS": str(events), "NEX_RESOURCE_DIR": str(out / "absent-sdk")}
                if profiled:env['NEX_PROFILE_OUTPUT'] = str(e / 'profile.json')
                if case.get("native_no_file_configuration"):
                    env.pop("NEX_FILES_ROOT", None)
                    env.pop("NEX_FILES_WRITE", None)
                hidden = []
                try:
                    for path in [ctx, *[directory / k for k in sources]]:
                        saved = path.with_name(path.name + ".hidden")
                        path.rename(saved)
                        hidden.append((path, saved))
                    executed = run(label + "-execute", [e / "program", "--nex-task-workers", "4", "--nex-task-steps", str(budget), *(["--nex-foreign", catalog] if case.get("foreign") else [])], env, (42, 70))
                finally:
                    for path, saved in hidden:
                        if saved.exists():
                            saved.rename(path)
                cleanup = next(json.loads(line.split(" ", 1)[1]) for line in executed.stderr.splitlines() if line.startswith("NEX_PRIVATE_MODULE_CLEANUP "))
                assert cleanup == {"ok": True, "managed_live": 0, "runtime_finish": True, "file_delta": 0, "runtime_images": int(shared), "code_images": len(plan["images"]) - 1}
                addresses = [json.loads(line.split(" ", 1)[1]) for line in executed.stderr.splitlines() if line.startswith("NEX_PRIVATE_FRONTIER_ADDRESS ")]
                assert len(addresses) == len(accessors) and all(v["ok"] and v["data"] == v["step"] == v["expected"] for v in addresses)
                if expected == "return":
                    assert executed.returncode == 42 and executed.stdout == oracle["output"]
                elif expected == "exception":
                    error = next(json.loads(line.split(" ", 1)[1]) for line in executed.stderr.splitlines() if line.startswith("NEX_SOURCE_EXCEPTION "))
                    assert executed.returncode == 70 and all(error[k] == oracle[k] for k in ["code", "message", "line"])
                    site = next(v for v in metadata if v["site"] == error["source"]["operation_site"] and v["function_hash"] == error["source"]["function_hash"])
                    assert site["kind"] == "statement.throw" and site["function_source_hash"] == error["source"]["function_source_hash"]
                else:
                    assert executed.returncode == 70 and oracle["code"] in executed.stderr and "NEX_SOURCE_EXCEPTION " not in executed.stderr
                observed = events.read_text() if events.exists() else ""
                assert observed.count("F") == observed.count("X") and (not case.get("foreign") or observed.count("F") > 0)
                report["cases"].append({"name": name, "topology": topology, "optimization": optimization, "oracle": oracle, "native_exit": executed.returncode, "source_hashes": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in sources.items()}, "module_records": {k: hashlib.sha256((e / k / "module-record.json").read_bytes()).hexdigest() for k in records}, "images": images, "physical_symbols": symbols, "addresses": addresses, "source_files_absent": True, "cleanup": cleanup, "resource_factories": observed.count("F"), "resource_finalizers": observed.count("X"), "passed": True})
                save()
    if "direct-catch" in selected:
        base = out / "direct-catch"
        ctx = base / "context.json"
        original_context = json.loads(ctx.read_text())
        arch = base / "static-in-shared/architecture.json"
        original_architecture = json.loads(arch.read_text())
        negative = out / "negative"
        negative.mkdir()

        def clone(value):
            return json.loads(json.dumps(value))

        bad = {}
        changed = clone(original_architecture)
        changed["components"]["app"]["dependencies"].append("leaf")
        bad["static-component-in-two-images"] = changed
        changed = clone(original_architecture)
        changed["components"]["app"]["linkage"] = "static"
        bad["application-is-not-static-provider"] = changed
        changed = clone(original_architecture)
        changed["components"]["leaf"]["linkage"] = "application"
        bad["provider-is-not-application"] = changed
        changed = clone(original_architecture)
        changed["components"]["leaf"].pop("linkage")
        bad["missing-explicit-linkage"] = changed
        changed = clone(original_architecture)
        changed["components"]["leaf"]["linkage"] = "dynamic"
        bad["unknown-linkage"] = changed
        changed = clone(original_architecture)
        changed["schema"] = "nex.private-task-architecture/1"
        bad["legacy-schema-preserves-old-meaning"] = changed
        changed = clone(original_architecture)
        changed["mode"] = "shared-fixed"
        bad["mixed-schema-requires-mixed-mode"] = changed
        changed = clone(original_architecture)
        changed["schema"] = "nex.private-task-architecture/99"
        bad["unknown-architecture-schema"] = changed
        for name, value in bad.items():
            file = negative / (name + ".json")
            file.write_text(json.dumps(value))
            result = run("reject-" + name, [probe, "plan", ctx, file], allowed=(1,))
            assert "E_EXCEPTION_MODULE" in result.stderr
            report["rejections"].append({"name": name, "code": "E_EXCEPTION_MODULE", "passed": True})
        record = json.loads((base / "static-in-shared/O0/leaf/module-record.json").read_text())
        for field, value in [("machine_image", "app"), ("linkage", "shared"), ("schema", "nex.private-task-module/1"), ("descriptor_abi", 0x4e45585400000005)]:
            changed = clone(record)
            changed[field] = value
            file = negative / ("record-" + field + ".json")
            file.write_text(json.dumps(changed))
            result = run("reject-record-" + field, [probe, "validate", ctx, arch, "leaf", file], allowed=(1,))
            assert "E_EXCEPTION_MODULE" in result.stderr
            report["rejections"].append({"name": "record-" + field, "code": "E_EXCEPTION_MODULE", "passed": True})
        changed = clone(original_context)
        entry = next(v for v in changed["units"] if v["unit"] == "app/main.nex")
        entry["source"] = entry["source"].replace("return mid::run();", "let n:i64=mid::run();return n;")
        changed["source"] = entry["source"]
        ctx_changed = base / "changed-context.json"
        ctx_changed.write_text(json.dumps(changed))
        for topology in CASES["direct-catch"]["topologies"]:
            arch = base / topology / "architecture.json"
            prior = json.loads((out / ("direct-catch-" + topology + "-plan.stdout")).read_text())
            plan = json.loads(run("incremental-" + topology + "-plan", [probe, "plan", ctx_changed, arch]).stdout)
            assert all(plan["components"][k] == prior["components"][k] for k in ["leaf", "mid"])
            assert plan["components"]["app"] != prior["components"]["app"]
            old = base / topology / "O0"
            module = old / "changed-app"
            run("incremental-" + topology + "-emit", [probe, "emit", ctx_changed, arch, "app", module, triple, layout, "false"])
            code = module / "linked.ll"
            code.write_text((module / "module.ll").read_text().replace("@main(", "@nex_private_modules_entry("))
            run("incremental-" + topology + "-object", [compiler, "-c", "-fPIC", code, "-o", module / "module.o"])
            # Use a new application filename while retaining the exact old
            # provider archives/shared images and the host's image expectations.
            original_binary = old / "program"
            saved_binary = old / "original-program"
            original_binary.rename(saved_binary)
            try:
                binary = link_image("incremental-" + topology, old, "app", plan, {}, old / "host.o", module / "module.o")
                result = run("incremental-" + topology + "-execute", [binary], allowed=(42,))
                cleanup = next(json.loads(s.split(" ", 1)[1]) for s in result.stderr.splitlines() if s.startswith("NEX_PRIVATE_MODULE_CLEANUP "))
                assert cleanup["ok"]
                binary.rename(old / "changed-program")
            finally:
                if saved_binary.exists():
                    saved_binary.rename(original_binary)
            report["incremental"].append({"topology": topology, "provider_records_identical": True, "provider_binaries_reused": True, "exit": 42, "passed": True})
    if "diamond" in selected:
        base = out / "diamond"
        architecture = json.loads((base / "shared-diamond/architecture.json").read_text())
        architecture["components"]["leaf"]["linkage"] = "static"
        file = base / "duplicate-shared-frontiers.json"
        file.write_text(json.dumps(architecture))
        result = run("reject-two-shared-frontiers", [probe, "plan", base / "context.json", file], allowed=(1,))
        assert "E_EXCEPTION_MODULE" in result.stderr and "multiple loaded machine images" in result.stderr
        report["rejections"].append({"name": "same-static-in-two-shared-frontiers", "code": "E_EXCEPTION_MODULE", "passed": True})
    if "owned-file-resource" in selected:
        base = out / "owned-file-resource"
        for topology in CASES["owned-file-resource"]["topologies"]:
            original = base / topology / "O2"
            moved = out / ("relocated-" + topology)
            moved.mkdir()
            for file in original.iterdir():
                if file.is_file() and (file.name == "program" or file.name.endswith(suffix)):
                    shutil.copy2(file, moved / file.name)
            shutil.copytree(bundle, moved / "bundle")
            shutil.copyfile(catalog, moved / "host.json")
            files = moved / "files"
            files.mkdir()
            (files / "input").write_text("abcdef")
            events = files / "events"
            hidden = []
            try:
                for path in [original, base / "context.json", *[base / (k + "/main.nex") for k in CASES["owned-file-resource"]["sources"]]]:
                    saved = path.with_name(path.name + ".hidden")
                    path.rename(saved)
                    hidden.append((path, saved))
                result = run("relocated-" + topology + "-execute", [moved / "program", "--nex-foreign", moved / "host.json"], {**os.environ, "PATH": "/usr/bin:/bin", "NEX_RESOURCE_DIR": str(out / "missing-sdk"), "NEX_FILES_ROOT": str(files), "NEX_FILES_WRITE": "1", "NEX_PRIVATE_HOST_EVENTS": str(events)}, allowed=(42,))
            finally:
                for path, saved in reversed(hidden):
                    if saved.exists():
                        saved.rename(path)
            cleanup = next(json.loads(s.split(" ", 1)[1]) for s in result.stderr.splitlines() if s.startswith("NEX_PRIVATE_MODULE_CLEANUP "))
            assert cleanup["ok"] and cleanup["runtime_images"] == cleanup["code_images"] == 1
            observed = events.read_text()
            assert observed.count("F") == observed.count("X") == 1
            report["relocated"].append({"topology": topology, "original_images_and_sources_absent": True, "common_runtime_images": 1, "exit": 42, "passed": True})
    report.update(ok=finalize, source_programs=len(selected), native_comparisons=len(report["cases"]), actual_compiled_native=True, physical_image_ownership_checked=True, architecture_version=architecture_version)
    save()
    if finalize:
        print(json.dumps({k: report[k] for k in ["ok", "source_programs", "native_comparisons"]}))
    return {"report": report, "output": out, "run": run, "save": save, "compiler": compiler, "probe": probe, "reference": reference, "triple": triple, "layout": layout, "link_image": link_image, "materialize": materialize, "pin": pin, "catalog": catalog, "suffix": suffix, "flags": flags, "debug_compiler":a.debug_compiler,"debug_native_only":a.debug_native_only}


if __name__ == "__main__":
    main()
