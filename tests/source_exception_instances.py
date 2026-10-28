"""Checked consumer specializations, trait witnesses and physical code ownership."""
import hashlib
import json
import os
import shutil
from pathlib import Path
import source_exception_frontiers as frontiers

VALUE = r'''module leaf;
pub trait Readable {fn value(v:Self)->i64 !{task,throw};}
pub fn anchor()->i64 !{task}{return 0;}
pub fn read<T:Readable>(v:T)->i64 !{task,throw}{task_yield();return Readable<T>::value(v);}
'''


def app_case(leaf, app, requests, **extra):
    return {"sources": {"leaf": leaf, "app": app}, "entries": {"leaf": "anchor", "app": "main"},
            "instantiations": {"app": requests},
            "topologies": {"static-template": {"leaf": "static"}, "shared-template": {"leaf": "shared"}}, **extra}


def request(template, *arguments):
    return {"template": "leaf::" + template, "arguments": list(arguments)}


CASES = {
    "trait-basic": app_case(VALUE, r'''module app;import "../leaf/main.nex" as leaf;
struct Number {value:i64;}
fn number(v:Number)->i64 !{task,throw}{task_yield();return v.value;}
impl numbers:leaf::Readable for Number {value=number;}
fn main()->i64 !{task,throw}{return leaf::read(Number(42));}''', [request("read", "app::Number")], typescript=True),
    "associated-types": app_case(r'''module leaf;
pub trait Content {type Item;fn get(v:Self)->Content::Item<Self> !{task,throw};}
pub fn anchor()->i64 !{task}{return 0;}
pub fn read<T:Content>(v:T)->Content::Item<T> !{task,throw}{task_yield();return Content<T>::get(v);}''', r'''module app;import "../leaf/main.nex" as leaf;
struct Box<T>{value:T;}
fn extract<T>(v:Box<T>)->T !{task,throw}{task_yield();return v.value;}
impl boxes<T>:leaf::Content for Box<T>{type Item=T;get=extract<T>;}
fn main()->i64 !{task,throw}{let n:i64=leaf::read(Box<i64>(42));let s:str=leaf::read(Box<str>("λ\u0000🙂"));assert(len(s)==3);return n;}''', [request("read", "app::Box<i64>"), request("read", "app::Box<str>")], typescript=True),
    "captured-instance": app_case(VALUE.replace('pub fn read<T:Readable>(v:T)->i64 !{task,throw}{task_yield();return Readable<T>::value(v);}', 'pub fn make<T:Readable>(v:T)->fn()->i64 !{task,throw}{return fn()->i64 !{task,throw}{task_yield();return Readable<T>::value(v);};}'), r'''module app;import "../leaf/main.nex" as leaf;
struct Number {values:list<str>;}
fn number(v:Number)->i64 !{task,throw}{task_yield();throw("CAPTURE",v.values[0]);}
impl numbers:leaf::Readable for Number {value=number;}
fn main()->i64 !{task}{let cb:fn()->i64 !{task,throw}=leaf::make(Number(["λ\u0000🙂"]));try{return cb();}catch(code,message){assert(code=="CAPTURE"&&len(message)==3);return 42;}}''', [request("make", "app::Number")], typescript=True),
}

NUMBER = r'''module app;import "../leaf/main.nex" as leaf;
struct Number {value:i64;}
fn number(v:Number)->i64 !{task,throw}{task_yield();return v.value;}
impl numbers:leaf::Readable for Number {value=number;}
'''
CASES["private-template-support"] = app_case(VALUE.replace('task_yield();return Readable<T>::value(v);', 'return helper(v)+offset();') + r'''
fn helper<T:Readable>(v:T)->i64 !{task,throw}{let cb:fn(T)->i64 !{task,throw}=Readable<T>::value;return cb(v);}
fn offset()->i64{return 1;}
''', NUMBER + 'fn main()->i64 !{task,throw}{return leaf::read(Number(41));}', [request("read", "app::Number")], typescript=True)
CASES["recursive-specialization"] = app_case(VALUE.replace('pub fn read<T:Readable>(v:T)->i64 !{task,throw}{task_yield();return Readable<T>::value(v);}', 'pub fn repeat<T:Readable>(v:T,n:i64)->i64 !{task,throw}{task_yield();if n==0{return 0;}return Readable<T>::value(v)+repeat(v,n-1);}'), NUMBER + 'fn main()->i64 !{task,throw}{return leaf::repeat(Number(21),2);}', [request("repeat", "app::Number")], typescript=True)
CASES["constructor-trait-method"] = app_case(r'''module leaf;
pub trait Mapper<Self<_>>{fn map<A,B>(v:Self<A>,apply:fn(A)->B)->Self<B>;}
pub fn anchor()->i64 !{task}{return 0;}
pub fn convert<F<_>:Mapper,A,B>(v:F<A>,apply:fn(A)->B)->F<B>{return Mapper<F>::map<A,B>(v,apply);}''', r'''module app;import "../leaf/main.nex" as leaf;
struct Box<T>{value:T;}
fn map_box<A,B>(v:Box<A>,apply:fn(A)->B)->Box<B>{return Box<B>(apply(v.value));}
impl boxes:leaf::Mapper for Box{map=map_box;}
fn main()->i64 !{task}{let b:Box<i64>=leaf::convert<Box,i64,i64>(Box<i64>(41),fn(v:i64)->i64{return v+1;});return b.value;}''', [request("convert", "app::Box", "i64", "i64")], typescript=True)
THROWING = NUMBER.replace('task_yield();return v.value;', 'task_yield();throw("ORIGINAL","λ\\u0000🙂");')
CASES["caught-specialization-error"] = app_case(VALUE, THROWING + r'''fn main()->i64 !{task}{try{return leaf::read(Number(42));}catch(code,message){assert(code=="ORIGINAL"&&len(message)==3);return 42;}}''', [request("read", "app::Number")], typescript=True)
CASES["uncaught-specialization-error"] = app_case(VALUE, THROWING + 'fn main()->i64 !{task,throw}{return leaf::read(Number(42));}', [request("read", "app::Number")], expected="exception")
CASES["origin-template-error"] = app_case(VALUE.replace('task_yield();return Readable<T>::value(v);', r'let n:i64=Readable<T>::value(v);task_yield();throw("TEMPLATE","λ\u0000🙂");'), NUMBER + 'fn main()->i64 !{task,throw}{return leaf::read(Number(42));}', [request("read", "app::Number")], expected="exception")
CASES["specialized-runtime-trap"] = app_case(VALUE, NUMBER.replace('task_yield();return v.value;', 'task_yield();assert(false);return v.value;') + 'fn main()->i64 !{task}{try{return leaf::read(Number(42));}catch(code,message){return 0;}}', [request("read", "app::Number")], expected="trap")
CASES["owned-resource-specialization"] = app_case(r'''module leaf;
DECL
pub server trait Readable {server fn value(v:Self)->i64 !{task,ffi,throw};}
pub server fn anchor()->i64 !{task}{return 0;}
pub server fn make(v:i64)->Counter !{task,ffi}{return create(v);}
pub server fn peek(v:Counter)->i64 !{task,ffi}{return read(v);}
pub server fn apply<T:Readable>(v:T)->i64 !{task,ffi,throw}{task_yield();return Readable<T>::value(v);}'''.replace('pub server trait', 'pub trait'), r'''module app;import "../leaf/main.nex" as leaf;
struct Holder {counter:leaf::Counter;}
server fn held(v:Holder)->i64 !{task,ffi,throw}{let n:i64=leaf::peek(v.counter);task_yield();throw("RESOURCE",str(n));}
impl holders:leaf::Readable for Holder{value=held;}
server fn main()->i64 !{task,ffi}{let c:leaf::Counter=leaf::make(42);try{return leaf::apply(Holder(c));}catch(code,message){assert(code=="RESOURCE"&&message=="42");return 42;}}''', [request("apply", "app::Holder")], foreign=True, exports={"leaf": ["make", "peek"]})


def library_case(leaf, mid, app, requests, **extra):
    return {"sources": {"leaf": leaf, "mid": mid, "app": app},
            "entries": {"leaf": "anchor", "mid": "run", "app": "main"},
            "instantiations": {"mid": requests},
            "topologies": {"static-in-shared": {"leaf": "static", "mid": "shared"},
                           "shared-under-static": {"leaf": "shared", "mid": "static"}}, **extra}


MID = NUMBER.replace('module app;', 'module mid;').replace('struct Number', 'pub struct Number') + 'pub fn run()->i64 !{task,throw}{return leaf::read(Number(42));}'
APP_MID = 'module app;import "../mid/main.nex" as mid;fn main()->i64 !{task,throw}{return mid::run();}'
CASES["library-consumer"] = library_case(VALUE, MID, APP_MID, [request("read", "mid::Number")], typescript=True)
CASES["exported-consumer-instance"] = library_case(VALUE, MID, 'module app;import "../mid/main.nex" as mid;import "../leaf/main.nex" as leaf;fn main()->i64 !{task,throw}{return leaf::read(mid::Number(42));}', [request("read", "mid::Number")], instance_exports={"mid": ["leaf::read"]}, typescript=True)
CASES["exported-consumer-instance"]["topologies"] = {"shared-consumer": {"leaf": "shared", "mid": "shared"}, "static-consumer": {"leaf": "shared", "mid": "static"}}
CASES["two-consumer-types"] = library_case(VALUE, MID.replace('Number(42)', 'Number(21)'), NUMBER.replace('import "../leaf/main.nex" as leaf;', 'import "../leaf/main.nex" as leaf;import "../mid/main.nex" as mid;') + 'fn main()->i64 !{task,throw}{return mid::run()+leaf::read(Number(21));}', [request("read", "mid::Number")], typescript=True)
CASES["two-consumer-types"]["instantiations"]["app"] = [request("read", "app::Number")]
CASES["two-consumer-types"]["topologies"] = CASES["exported-consumer-instance"]["topologies"]
CASES["shared-private-generic-support"] = {
    **CASES["two-consumer-types"],
    "sources": {**CASES["two-consumer-types"]["sources"], "leaf": VALUE.replace('task_yield();return Readable<T>::value(v);', 'task_yield();return Readable<T>::value(v)+helper<i64>(0);') + '\nfn helper<U:integer>(v:U)->U !{task}{task_yield();return v;}\n'},
    "instantiations": {**CASES["two-consumer-types"]["instantiations"], "leaf": [request("helper", "i64")]}}
CASES["associated-file-future"] = library_case(r'''module leaf;
pub trait Open {type Item;server fn open(v:Self)->Open::Item<Self> !{task,fs,throw};}
pub server fn anchor()->i64 !{task}{return 0;}
pub server fn open<T:Open>(v:T)->Open::Item<T> !{task,fs,throw}{return Open<T>::open(v);}''', r'''module mid;import "../leaf/main.nex" as leaf;
struct Path {value:str;}
server fn open_path(v:Path)->file !{task,fs,throw}{task_yield();return unwrap(file_open_read(v.value));}
impl paths:leaf::Open for Path{type Item=file;open=open_path;}
pub server fn run(s:task_scope,q:channel<file>)->i64 !{task,fs,throw}{
 let t:task<file>=task_spawn(s,server fn()->file !{task,fs,throw}{return leaf::open(Path("input"));});
 let f:file=task_wait(t);assert(unwrap(file_size(f))==6);assert(task_send(q,f));return 42;}''', r'''module app;import "../mid/main.nex" as mid;
server fn main()->i64 !{task,fs,throw}{return with_tasks(2,server fn(s:task_scope)->i64 !{task,fs,throw}{
 let q:channel<file>=channel_new<file>(s,1);let n:i64=mid::run(s,q);let f:file=unwrap(task_recv(q));
 assert(unwrap(file_read(f,3))==utf8_bytes("abc"));file_close(f);return n;});}''', [request("open", "mid::Path")])


def main():
    state = frontiers.main(CASES, architecture_version=3, output_env="NEX_EXCEPTION_INSTANCES_OUTPUT", finalize=False)
    report, out, run = state["report"], state["output"], state["run"]
    report.update(consumer_owned_specializations=True, trait_witnesses_checked=True, typescript_cases=[])
    programs = []
    for name, case in CASES.items():
        d = out / name
        if not d.is_dir():
            continue
        catalog = json.loads((out / (name + "-instances.stdout")).read_text())
        assert catalog["instances"] and catalog["archived"] is False and "revision" not in catalog
        for topology in case["topologies"]:
            plan = json.loads((out / (name + "-" + topology + "-plan.stdout")).read_text())
            assert plan["schema"] == "nex.private-task-modules/3"
            for root, owner in plan["instantiation_roots"].items():
                assert plan["specialization_owners"][root] == owner
                row = plan["components"][owner]
                assert root in row["template_instances"] and root in row["instantiation_descriptors"]
                assert row["template_instances"][root] == catalog["instances"][root]
                assert row["definitions"][root]["machine_component"] == owner
                assert row["definitions"][root]["source_component"] == "leaf"
                assert plan["definition_owners"][root] == plan["component_images"][owner]
                witnesses = [w for f in row["trait_witnesses"].values() for w in f.values()]
                if owner != "leaf":
                    assert witnesses and all(w["implementation_unit"] == owner + "/main.nex" for w in witnesses)
            if name == "private-template-support":
                assert "leaf::offset" in plan["components"]["leaf"]["support_exports"]
                assert "leaf::offset" not in plan["components"]["leaf"]["exports"]
                assert plan["components"]["app"]["import_kinds"]["leaf::offset"] == "instantiation-support"
                assert "leaf::helper<app::Number>" in plan["components"]["app"]["template_instances"]
            if name == "captured-instance":
                captured = [k for k in plan["specialization_owners"] if "::$lambda_" in k]
                assert captured and all(plan["specialization_owners"][k] == "app" for k in captured)
            if name == "origin-template-error":
                root = next(iter(plan["instantiation_roots"]))
                for optimization in ["0", "2"]:
                    stderr = (out / (name + "-" + topology + "-O" + optimization + "-execute.stderr")).read_text()
                    error = next(json.loads(v.split(" ", 1)[1]) for v in stderr.splitlines() if v.startswith("NEX_SOURCE_EXCEPTION "))
                    assert error["source"]["function_hash"] == plan["components"]["app"]["definitions"][root]["function_hash"]
                    assert error["source"]["function_source_hash"] == plan["components"]["app"]["template_instances"][root]["template_source_hash"]
            if name == "shared-private-generic-support":
                helper = "leaf::helper<i64>"
                assert plan["specialization_owners"][helper] == "leaf"
                assert helper in plan["components"]["leaf"]["support_exports"]
                assert helper not in plan["components"]["leaf"]["exports"]
                assert all(plan["components"][c]["import_kinds"][helper] == "instantiation-support" for c in ["app", "mid"])
        if case.get("typescript"):
            ts = d / "typescript"
            run(name + "-typescript-emit", [state["reference"], "typescript-context", d / "context.json", ts])
            runner = ts / "run.mjs"
            runner.write_text(r'''import * as program from './program.ts';import * as task from './nex-task-runtime.ts';import * as source from './nex-source-exception-runtime.ts';
let statistics;const value=await task.runSourceExceptionPrototype(task.call(()=>program.main()),e=>source.details(e)!==undefined,{steps:1000000,timeoutMs:10000,workers:2,complete:s=>statistics=s});
if(value!==42n||!statistics?.completed||statistics.retainedFrames||statistics.activeCalls||statistics.externalPending||statistics.externalReservedBytes||statistics.externalMailbox)throw new Error('wrong result or retained task state');process.stdout.write(JSON.stringify({ok:true,value:String(value)})+'\n');
''')
            actual = json.loads(run(name + "-typescript-run", [os.environ.get("NEX_NODE", "node"), "--experimental-strip-types", "--disable-warning=ExperimentalWarning", runner]).stdout)
            assert actual == {"ok": True, "value": "42"}
            programs.append(ts / "program.ts")
            report["typescript_cases"].append({"name": name, "value": "42", "passed": True})
    if programs:
        tsc = Path(os.environ["NEX_TSC"]).resolve()
        actual_version = json.loads((tsc.parent.parent / "package.json").read_text())["version"]
        expected_version = json.loads((Path(__file__).resolve().parents[1] / "web/package.json").read_text())["devDependencies"]["typescript"]
        assert actual_version == expected_version
        run("strict-typescript", [os.environ.get("NEX_NODE", "node"), tsc, "--noEmit", "--strict", "--target", "ES2022", "--module", "ESNext", "--moduleResolution", "bundler", "--allowImportingTsExtensions", "--lib", "ES2022,DOM", *programs])
        report.update(strict_typecheck=True, typescript_version=actual_version)
    extra_checks(state)
    report["ok"] = True
    state["save"]()
    print(json.dumps({k: report[k] for k in ["ok", "source_programs", "native_comparisons"]}))


def extra_checks(state):
    out, run, probe = state["output"], state["run"], state["probe"]
    report = state["report"]
    report["incremental"] = []
    report["relocated"] = []
    report["catalogue_checks"] = []

    def clone(value):
        return json.loads(json.dumps(value))

    def sha(file):
        return hashlib.sha256(file.read_bytes()).hexdigest()

    if (out / "trait-basic").is_dir():
        base = out / "trait-basic"
        context = base / "context.json"
        arch = base / "static-template/architecture.json"
        original = json.loads(arch.read_text())
        root = original["components"]["app"]["instantiations"][0]
        negative = out / "negative"
        negative.mkdir()
        bad = {}
        for name, value in [("unknown-concrete-instance", "leaf::read<app::Missing>"), ("abstract-template-selector", "leaf::read"), ("nongeneric-selector", "app::number")]:
            changed = clone(original)
            changed["components"]["app"]["instantiations"] = [value]
            bad[name] = changed
        changed = clone(original)
        changed["components"]["leaf"]["instantiations"] = [root]
        bad["duplicate-concrete-owner"] = changed
        changed = clone(original)
        changed["components"]["app"]["instantiations"] = []
        bad["missing-consumer-instantiation"] = changed
        changed = clone(original)
        changed["components"]["app"]["instantiations"] = []
        changed["components"]["leaf"]["instantiations"] = [root]
        bad["provider-cannot-call-consumer-implementation"] = changed
        changed = clone(original)
        changed["components"]["leaf"]["exports"].append(root)
        bad["provider-cannot-also-export-moved-instance"] = changed
        changed = clone(original)
        changed["schema"] = "nex.private-task-architecture/2"
        bad["legacy-schema-does-not-reinterpret-placements"] = changed
        changed = clone(original)
        changed["components"]["app"].pop("instantiations")
        bad["missing-explicit-instantiation-list"] = changed
        for name, value in bad.items():
            file = negative / (name + ".json")
            file.write_text(json.dumps(value))
            result = run("reject-" + name, [probe, "plan", context, file], allowed=(1,))
            assert "E_EXCEPTION_MODULE" in result.stderr
            report["rejections"].append({"name": name, "code": "E_EXCEPTION_MODULE", "passed": True})
        record = json.loads((base / "static-template/O0/app/module-record.json").read_text())
        bad_records = {}
        for field, value in [("source_component", "app"), ("machine_component", "leaf")]:
            changed = clone(record)
            changed["definitions"][root][field] = value
            bad_records["definition-" + field] = changed
        changed = clone(record)
        changed["template_instances"][root]["template_hash"] = "0" * 64
        bad_records["template-identity"] = changed
        changed = clone(record)
        next(iter(changed["template_instances"][root]["trait_witnesses"].values()))["implementation_hash"] = "0" * 64
        bad_records["selected-implementation"] = changed
        changed = clone(record)
        changed["instantiation_descriptors"][root]["signature"] = "0" * 64
        bad_records["instantiation-descriptor"] = changed
        changed = clone(record)
        changed["instantiation_families"][root] = []
        bad_records["missing-instance-family"] = changed
        changed = clone(record)
        changed["schema"] = "nex.private-task-module/2"
        bad_records["legacy-record"] = changed
        for name, value in bad_records.items():
            file = negative / ("record-" + name + ".json")
            file.write_text(json.dumps(value))
            result = run("reject-record-" + name, [probe, "validate", context, arch, "app", file], allowed=(1,))
            assert "E_EXCEPTION_MODULE" in result.stderr
            report["rejections"].append({"name": "record-" + name, "code": "E_EXCEPTION_MODULE", "passed": True})
        original_context = json.loads(context.read_text())
        for name, source, code in [("method-effect-mismatch", CASES["trait-basic"]["sources"]["app"].replace('fn number(v:Number)->i64 !{task,throw}', 'fn number(v:Number)->i64 !{task}'), "E_TRAIT_METHOD"), ("missing-trait-witness", CASES["trait-basic"]["sources"]["app"].replace('impl numbers:leaf::Readable for Number {value=number;}', ''), "E_GENERIC_BOUND")]:
            changed = clone(original_context)
            changed["source"] = source
            next(v for v in changed["units"] if v["unit"] == "app/main.nex")["source"] = source
            file = negative / (name + ".json")
            file.write_text(json.dumps(changed))
            result = run("reject-" + name, [probe, "instances", file], allowed=(1,))
            assert code in result.stderr
            report["rejections"].append({"name": name, "code": code, "passed": True})
    if (out / "private-template-support").is_dir():
        base = out / "private-template-support"
        context = json.loads((base / "context.json").read_text())
        arch = base / "static-template/architecture.json"
        architecture = json.loads(arch.read_text())
        changed = clone(architecture)
        changed["components"]["app"]["instantiations"] = ["leaf::helper<app::Number>"]
        file = base / "private-selector.json"
        file.write_text(json.dumps(changed))
        result = run("reject-private-template-selector", [probe, "plan", base / "context.json", file], allowed=(1,))
        assert "E_EXCEPTION_MODULE" in result.stderr
        report["rejections"].append({"name": "private-template-selector", "code": "E_EXCEPTION_MODULE", "passed": True})
        changed = clone(context)
        changed["source"] = 'module app;import "../leaf/main.nex" as leaf;fn main()->i64 !{task}{return leaf::offset();}'
        next(v for v in changed["units"] if v["unit"] == "app/main.nex")["source"] = changed["source"]
        file = base / "private-source-call.json"
        file.write_text(json.dumps(changed))
        result = run("reject-direct-private-support-call", [probe, "instances", file], allowed=(1,))
        assert "E_VISIBILITY" in result.stderr
        report["rejections"].append({"name": "direct-private-support-call", "code": "E_VISIBILITY", "passed": True})
        record = json.loads((base / "static-template/O0/leaf/module-record.json").read_text())
        record["support_exports"]["leaf::offset"]["signature"] = "0" * 64
        file = base / "bad-support-record.json"
        file.write_text(json.dumps(record))
        result = run("reject-support-contract", [probe, "validate", base / "context.json", arch, "leaf", file], allowed=(1,))
        assert "E_EXCEPTION_MODULE" in result.stderr
        report["rejections"].append({"name": "support-contract", "code": "E_EXCEPTION_MODULE", "passed": True})
        for change in ["method-body", "method-binding"]:
            current = clone(context)
            source = current["source"].replace("Number(41)", "Number(40)")
            if change == "method-body":
                source = source.replace("return v.value;", "return v.value+1;")
            else:
                source = source.replace("value=number;", "value=selected;") + '\nfn selected(v:Number)->i64 !{task,throw}{task_yield();return v.value+1;}\n'
            current["source"] = source
            next(v for v in current["units"] if v["unit"] == "app/main.nex")["source"] = source
            ctx = base / (change + "-context.json")
            ctx.write_text(json.dumps(current))
            for topology in CASES["private-template-support"]["topologies"]:
                label = "incremental-" + change + "-" + topology
                arch = base / topology / "architecture.json"
                plan = json.loads(run(label + "-plan", [probe, "plan", ctx, arch]).stdout)
                prior = json.loads((out / ("private-template-support-" + topology + "-plan.stdout")).read_text())
                assert plan["components"]["leaf"] == prior["components"]["leaf"] and plan["components"]["app"] != prior["components"]["app"]
                if change == "method-binding":
                    assert plan["components"]["app"]["trait_witnesses"] != prior["components"]["app"]["trait_witnesses"]
                old = base / topology / "O0"
                provider = old / ("libleaf.a" if topology == "static-template" else "libimage-leaf" + state["suffix"])
                before = sha(provider)
                module = old / ("changed-" + change)
                run(label + "-emit", [probe, "emit", ctx, arch, "app", module, state["triple"], state["layout"], "false"])
                run(label + "-validate", [probe, "validate", ctx, arch, "app", module / "module-record.json"])
                code = module / "linked.ll"
                code.write_text((module / "module.ll").read_text().replace("@main(", "@nex_private_modules_entry("))
                run(label + "-object", [state["compiler"], "-c", "-fPIC", code, "-o", module / "module.o"])
                saved = old / "original-program"
                (old / "program").rename(saved)
                try:
                    binary = state["link_image"](label, old, "app", plan, {}, old / "host.o", module / "module.o")
                    result = run(label + "-execute", [binary], allowed=(42,))
                    cleanup = next(json.loads(v.split(" ", 1)[1]) for v in result.stderr.splitlines() if v.startswith("NEX_PRIVATE_MODULE_CLEANUP "))
                    assert cleanup["ok"]
                    binary.rename(old / ("program-" + change))
                finally:
                    if saved.exists():
                        saved.rename(old / "program")
                assert sha(provider) == before
                report["incremental"].append({"change": change, "topology": topology, "provider_record_identical": True, "provider_artifact_sha256": before, "provider_artifact_unchanged": True, "consumer_record_changed": True, "binding_witness_changed": change == "method-binding", "native_exit": 42, "passed": True})
    if (out / "associated-file-future").is_dir():
        base = out / "associated-file-future"
        for topology in CASES["associated-file-future"]["topologies"]:
            original = base / topology / "O2"
            moved = out / ("relocated-file-" + topology)
            moved.mkdir()
            images = {}
            for file in original.iterdir():
                if file.is_file() and (file.name == "program" or file.name.endswith(state["suffix"])):
                    shutil.copy2(file, moved / file.name)
                    images[file.name] = sha(file)
            files = moved / "files"
            files.mkdir()
            (files / "input").write_text("abcdef")
            hidden = []
            try:
                for path in [original, base / "context.json", *[base / (k + "/main.nex") for k in CASES["associated-file-future"]["sources"]]]:
                    saved = path.with_name(path.name + ".hidden")
                    path.rename(saved)
                    hidden.append((path, saved))
                result = run("relocated-file-" + topology, [moved / "program"], {**os.environ, "PATH": "/usr/bin:/bin", "NEX_RESOURCE_DIR": str(out / "missing-sdk"), "NEX_FILES_ROOT": str(files), "NEX_FILES_WRITE": "1"}, allowed=(42,))
            finally:
                for path, saved in reversed(hidden):
                    if saved.exists():
                        saved.rename(path)
            cleanup = next(json.loads(v.split(" ", 1)[1]) for v in result.stderr.splitlines() if v.startswith("NEX_PRIVATE_MODULE_CLEANUP "))
            assert cleanup["ok"] and cleanup["runtime_images"] == cleanup["code_images"] == 1
            report["relocated"].append({"topology": topology, "images": images, "original_images_and_sources_absent": True, "cleanup": cleanup, "native_exit": 42, "passed": True})
    if (out / "shared-private-generic-support").is_dir():
        base = out / "shared-private-generic-support"
        arch = json.loads((base / "shared-consumer/architecture.json").read_text())
        arch["components"]["leaf"]["instantiations"] = []
        file = base / "ambiguous-helper-owner.json"
        file.write_text(json.dumps(arch))
        result = run("reject-ambiguous-private-family-owner", [probe, "plan", base / "context.json", file], allowed=(1,))
        assert "E_EXCEPTION_MODULE" in result.stderr and "different owners" in result.stderr
        report["rejections"].append({"name": "ambiguous-private-family-owner", "code": "E_EXCEPTION_MODULE", "passed": True})
    if (out / "associated-types").is_dir():
        context = out / "associated-types/context.json"
        pages = []
        for name, offset, limit in [("filtered-complete", 0, 256), ("first-page", 0, 1), ("second-page", 1, 1), ("past-last-page", 2, 1)]:
            value = json.loads(run("catalogue-" + name, [probe, "instances", context, "leaf::read", str(offset), str(limit)]).stdout)
            assert value["template_filter"] == "leaf::read" and value["total"] == 2 and value["offset"] == offset and value["limit"] == limit
            assert all(v["template"] == "leaf::read" and v["template_public"] for v in value["instances"].values())
            pages.append(value)
            report["catalogue_checks"].append({"name": name, "count": len(value["instances"]), "next_offset": value["next_offset"], "passed": True})
        assert list(pages[0]["instances"]) == [*pages[1]["instances"], *pages[2]["instances"]]
        assert pages[1]["truncated"] is True and pages[1]["next_offset"] == 1
        assert pages[2]["truncated"] is False and pages[2]["next_offset"] is None
        assert not pages[3]["instances"] and pages[3]["truncated"] is False and pages[3]["next_offset"] is None
        for name, template, offset, limit, message in [("zero-limit", "leaf::read", "0", "0", "E_EXCEPTION_MODULE"), ("excess-limit", "leaf::read", "0", "257", "E_EXCEPTION_MODULE"), ("unknown-template", "leaf::missing", "0", "1", "E_EXCEPTION_MODULE"), ("malformed-offset", "leaf::read", "1x", "1", "expected unsigned catalogue")]:
            value = run("catalogue-reject-" + name, [probe, "instances", context, template, offset, limit], allowed=(1,))
            assert message in value.stderr
            report["catalogue_checks"].append({"name": name, "diagnostic": message, "passed": True})


if __name__ == "__main__":
    main()
