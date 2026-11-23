"""Execute the published 0.30 SDK example corpus against two compiler installations."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


# Reviewed entry points from the published examples. Named checks belong to the
# application, so adding an unrelated test to an installed library is compatible.
# Java FIFO and the insertion-ordered map first appeared after the 0.280.1 distribution.
PROGRAMS = {
    "insertion-ordered-map": {
        "main.nex": ("east\nwest\n", ("insertion_order_example::reinsertion_appends",)),
    },
    "hash-containers": {
        "main.nex": ("hash-containers-ok\n", ("hash_inventory::retained_values",)),
        "tasks.nex": ("42\n", ("hash_tasks::snapshots_across_tasks",)),
    },
    "java-circular-fifo": {
        "main.nex": ("java-circular-fifo-ok\n", ("java_circular_fifo_example::overwrite_and_iterator_alias",)),
    },
    "java-long": {"main.nex": ("java-long-ok\n", ("java_long_example::exact_long_wrap",))},
    "native-host-session": {"app/main.nex": ("42\n", ())},
    "persistent-ui": {"main.nex": ("41\n42\n43\n", ("persistent_ui::shared_state_after_suspension",))},
    "reference-provider-debugging": {"app/main.nex": ("42\n", ())},
    "reference-task-profiling": {"app/main.nex": ("42\n", ())},
    "reference-task-providers": {"app/main.nex": ("42\n", ("provider_app::aliases",))},
    "references": {
        "main.nex": ("42\n", ("references::aliases_and_captures",)),
        "tasks.nex": ("42\n", ("reference_tasks::shared_background_counter",)),
    },
    "sequence-containers": {
        "main.nex": ("sequence-containers-ok\n", ("work_containers::retained_versions",)),
        "tasks.nex": ("42\n", ("task_containers::snapshots_across_tasks",)),
    },
}
WORKBOARD = {
    "client.nex": ("web", ("workboard::client_app::persistent_requests_and_worker_values",)),
    "server.nex": ("native", ("workboard::server_app::principal_export_names",)),
    "model.nex": ("native", ("workboard::model::snapshot_contract", "workboard::model::Unicode_summary")),
}


PUBLISHED_02801 = (set(PROGRAMS) - {"java-circular-fifo", "insertion-ordered-map"}) | {"workboard"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def invoke(nex, project, *args):
    env = os.environ.copy()
    env.pop("NEX_RESOURCE_DIR", None)
    proc = subprocess.run([str(nex), *args, "--json"], cwd=project, env=env,
                          capture_output=True, timeout=300)
    if proc.returncode:
        message = (proc.stdout + proc.stderr).decode("utf-8", "replace")[:1500]
        raise ValueError(f"{project.name}: {' '.join(args)} exited {proc.returncode}: {message}")
    report = json.loads(proc.stdout)
    if report.get("ok") is not True:
        raise ValueError(f"{project.name}: {' '.join(args)} did not return a positive report")
    return report


def named_tests(nex, project, entry, backend, names, build_dir):
    records = []
    for name in names:
        options = ["--target", "web"] if backend == "web" else []
        result = invoke(nex, project, "test", entry, "--symbol", name, "--build-directory", str(build_dir), *options)
        rows = result["tests"]
        if (len(rows) != 1 or rows[0].get("name") != name or rows[0].get("ok") is not True
                or rows[0].get("native") is not (backend == "native")
                or rows[0].get("web") is not (backend == "web")):
            raise ValueError(f"{entry}: missing reference/{backend} agreement for {name}")
        records.append({"name": name, "backend": backend, "reference_agreement": True})
    return records


def check_entry(nex, project, entry):
    revision = invoke(nex, project, "check", entry).get("revision")
    if not isinstance(revision, str) or len(revision) != 64:
        raise ValueError(f"No checked revision for {entry}")
    return revision


def observe(nex, project, name, build_dir):
    entries = []
    if name == "workboard":
        for entry, (backend, tests) in WORKBOARD.items():
            entries.append({"entry": entry, "revision": check_entry(nex, project, entry),
                            "tests": named_tests(nex, project, entry, backend, tests, build_dir)})
    else:
        for entry, (expected, tests) in PROGRAMS[name].items():
            revision = check_entry(nex, project, entry)
            reference = invoke(nex, project, "eval", entry)
            native = invoke(nex, project, "run", entry, "--profile", "release", "--build-directory", str(build_dir))
            if (reference.get("stdout") != native.get("stdout") or native.get("exit_code") != 0
                    or native.get("stderr") != "" or "value" not in reference or reference["value"] is not None
                    or not isinstance(reference.get("stdout"), str)
                    or (expected is not None and expected != native["stdout"])):
                raise ValueError(f"{name}/{entry}: wrong reference or native result")
            entries.append({"entry": entry, "revision": revision, "stdout": native["stdout"],
                            "reference_value": reference["value"], "native_exit": native["exit_code"],
                            "tests": named_tests(nex, project, entry, "native", tests, build_dir)})
    return entries


def check_examples(baseline_nex: Path, candidate_nex: Path, examples: Path, root: Path) -> dict:
    """Check original installed project bytes in independent copies for each SDK."""
    examples, root = Path(examples).resolve(strict=True), Path(root).resolve()
    if root.is_relative_to(examples):
        raise ValueError("example work directory must be outside the supplied examples tree")
    root.mkdir(parents=True, exist_ok=True)
    roles = {"baseline": Path(baseline_nex).absolute(), "candidate": Path(candidate_nex).absolute()}
    projects, other_languages = [], {}
    for manifest in sorted(examples.rglob("nex.json")):
        if ".nex" in manifest.relative_to(examples).parts:
            continue
        spec = json.loads(manifest.read_bytes())
        language = spec.get("language", "compiler-default")
        if language != "0.30":
            other_languages[language] = other_languages.get(language, 0) + 1
            continue
        src = manifest.parent
        name = src.relative_to(examples).as_posix()
        data = {"name": name, "manifest_entry": spec["entry"], "manifest_sha256": digest(manifest.read_bytes())}
        projects.append(data)
        inputs = {p.relative_to(src).as_posix(): digest(p.read_bytes()) for p in sorted(src.rglob("*"))
                  if p.is_file() and p.suffix in (".json", ".nex") and ".nex" not in p.relative_to(src).parts}
        data["inputs_sha256"] = inputs
        entries = WORKBOARD if name == "workboard" else PROGRAMS.get(name, {})
        if spec["entry"] not in entries:
            data.update(ok=False, reason="published 0.30 project has no reviewed executable entry plan")
            continue
        observed, errors = {}, {}
        for role, nex in roles.items():
            work = root / role / name
            shutil.copytree(src, work, ignore=shutil.ignore_patterns(".nex", "node_modules", ".build"))
            try:
                observed[role] = observe(nex, work, name, root / "build" / role)
            except ValueError as error:
                errors[role] = str(error)
            except subprocess.TimeoutExpired as error:
                errors[role] = f"{error.cmd[1]} exceeded {error.timeout} seconds"
        if errors:
            data.update(ok=False, observed=observed, errors=errors)
            continue
        # A compiler's new bundled stdlib can change a physical program's hash.
        # Preserve both identities and compare its observed behavior.
        def behavior(rows):
            return [{k: v for k, v in row.items() if k != "revision"} for row in rows]
        data.update(observed=observed, ok=behavior(observed["candidate"]) == behavior(observed["baseline"]))
    missing = sorted(PUBLISHED_02801 - {p["name"] for p in projects})
    return {"schema": "nex.sdk-compat-examples/1", "ok": not missing and all(p["ok"] for p in projects),
            "language": "0.30", "projects": projects, "other_manifest_counts": other_languages,
            "missing_published_02801_projects": missing,
            "scope": "Published projects explicitly selecting 0.30: source checks, reference/native Release mains, "
                     "named reference/native tests and the Workboard reference/generated TypeScript client test.",
            "outside_scope": ["Examples without an explicit 0.30 manifest", "Browser interaction and deployed HTTP traffic",
                              "External C++ hosts, separate library linkage, debugger and profiler sessions",
                              "Device and mobile execution"]}
