"""Compile checked scalar NEX graph definitions to an experimental Metal kernel."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


class Unsupported(ValueError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def msl_type(value):
    if value not in {"i64", "bool", "unit"}:
        raise Unsupported("GPU scalar backend does not support type " + value)
    return {"i64": "long", "bool": "bool", "unit": "void"}[value]


class Generator:
    def __init__(self, graph, root, input_layout="rows"):
        if graph.get("schema") != "nex.graph/2" or graph.get("language") != "0.28":
            raise Unsupported("expected a compiler-checked language0.28 graph")
        self.nodes = {row["name"]: row for row in graph["nodes"]}
        self.root = root
        if input_layout not in {"rows", "columns"}:
            raise Unsupported("unknown generated-kernel input layout")
        self.input_layout = input_layout
        self.order = []
        self.visiting = set()
        self.visited = set()
        self.discover(root)
        self.names = {name: "nex_fn_" + str(i) for i, name in enumerate(self.order)}
        self.lines = []
        self.indent = 0
        self.serial = 0
        self.result = "unit"

    def discover(self, name):
        if name in self.visiting:
            raise Unsupported("recursive GPU call graph: " + name)
        if name in self.visited:
            return
        if len(self.visiting) >= 128:
            raise Unsupported("GPU call depth exceeds128 functions")
        if name not in self.nodes:
            raise Unsupported("unavailable GPU callee: " + name)
        function = self.nodes[name]["definition"]
        if function.get("format") not in {"nex.function/13", "nex.function/14"}:
            raise Unsupported("unrecognized checked function format")
        if function["effects"] or function["realm"] != "shared":
            raise Unsupported("GPU functions must be shared and pure: " + name)
        if function.get("foreign") or "captures" in function or function.get("type_parameters"):
            raise Unsupported("GPU function must be concrete, without captures or foreign authority")
        msl_type(function["result"])
        for parameter in function["parameters"]:
            if parameter["type"] == "unit":
                raise Unsupported("unit is not a GPU argument")
            msl_type(parameter["type"])
        self.visiting.add(name)

        def walk(value):
            if isinstance(value, list):
                for child in value:
                    walk(child)
            elif isinstance(value, dict):
                if "operator" in value and value.get("kind") == 5:
                    callee = value["operator"]
                    if callee != "assert":
                        self.discover(callee)
                for key, child in value.items():
                    if key != "operator":
                        walk(child)

        walk(function["body"])
        self.visiting.remove(name)
        self.visited.add(name)
        self.order.append(name)
        if len(self.order) > 128:
            raise Unsupported("GPU call graph exceeds128 functions")

    def line(self, value):
        self.lines.append("  " * self.indent + value)

    def temporary(self):
        self.serial += 1
        return "nex_v_" + str(self.serial)

    def stop(self):
        return "return;" if self.result == "unit" else "return " + ("false" if self.result == "bool" else "0L") + ";"

    def guard(self):
        self.line("if (nex_s.code) { " + self.stop() + " }")

    def tick(self):
        self.line("if (!nex_tick(nex_s)) { " + self.stop() + " }")

    def expression(self, node, scope):
        if node is None:
            raise Unsupported("missing checked GPU expression")
        self.tick()
        kind, operator, value_type = node["kind"], node["operator"], node["type"]
        msl_type(value_type)
        arguments = node["args"]
        if kind == 0 and value_type == "i64":
            value = node["value"]
            if type(value) is not int or not -(1 << 63) <= value < (1 << 63):
                raise Unsupported("invalid checked integer")
            text = "nex_bits(0x" + format(value & ((1 << 64) - 1), "016x") + "UL)"
        elif kind == 1 and value_type == "bool":
            text = "true" if node["value"] else "false"
        elif kind == 2:
            if operator not in scope:
                raise Unsupported("unbound checked GPU local: " + operator)
            text = scope[operator]
        elif kind == 3 and len(arguments) == 1 and operator in {"-", "!"}:
            child = self.expression(arguments[0], scope)
            text = "nex_neg(" + child + ", nex_s)" if operator == "-" else "!" + child
        elif kind == 4 and len(arguments) == 2:
            left = self.expression(arguments[0], scope)
            if operator in {"&&", "||"}:
                result = self.temporary()
                self.line("bool " + result + " = " + left + ";")
                self.line("if (" + ("!" if operator == "||" else "") + result + ") {")
                self.indent += 1
                right = self.expression(arguments[1], scope)
                self.line(result + " = " + right + ";")
                self.indent -= 1
                self.line("}")
                return result
            right = self.expression(arguments[1], scope)
            if operator in {"+", "-", "*", "/", "%"}:
                helper = {"+": "add", "-": "sub", "*": "mul", "/": "div", "%": "mod"}[operator]
                text = "nex_" + helper + "(" + left + ", " + right + ", nex_s)"
            elif operator in {"==", "!=", "<", "<=", ">", ">="}:
                text = left + " " + operator + " " + right
            else:
                raise Unsupported("unsupported GPU binary operator: " + operator)
        elif kind == 5:
            values = [self.expression(argument, scope) for argument in arguments]
            if operator == "assert" and len(values) == 1 and value_type == "unit":
                self.line("if (!" + values[0] + ") { nex_s.code = 3; " + self.stop() + " }")
                return None
            if operator not in self.names:
                raise Unsupported("unrecognized checked GPU call: " + operator)
            text = self.names[operator] + "(" + ", ".join(values + ["nex_s"]) + ")"
        else:
            raise Unsupported("unsupported GPU expression kind " + str(kind))
        if value_type == "unit":
            self.line(text + ";")
            self.guard()
            return None
        temporary = self.temporary()
        self.line(msl_type(value_type) + " " + temporary + " = " + text + ";")
        self.guard()
        return temporary

    def block(self, statements, inherited):
        scope = dict(inherited)
        for statement in statements:
            self.tick()
            kind = statement["kind"]
            if kind in {0, 1}:
                value = self.expression(statement["expression"], scope)
                name = self.temporary()
                self.line(msl_type(statement["type"]) + " " + name + " = " + value + ";")
                scope[statement["name"]] = name
            elif kind == 2:
                value = self.expression(statement["expression"], scope)
                if statement["name"] not in scope:
                    raise Unsupported("unbound checked GPU assignment")
                self.line(scope[statement["name"]] + " = " + value + ";")
            elif kind == 3:
                self.expression(statement["expression"], scope)
            elif kind == 4:
                value = self.expression(statement["expression"], scope) if statement["expression"] else None
                self.line("return" + (" " + value if value is not None else "") + ";")
            elif kind == 5:
                condition = self.expression(statement["expression"], scope)
                self.line("if (" + condition + ") {")
                self.indent += 1
                self.block(statement["body"], scope)
                self.indent -= 1
                self.line("} else {")
                self.indent += 1
                self.block(statement["else"], scope)
                self.indent -= 1
                self.line("}")
            elif kind == 6:
                self.line("while (true) {")
                self.indent += 1
                condition = self.expression(statement["expression"], scope)
                self.line("if (!" + condition + ") break;")
                self.block(statement["body"], scope)
                self.indent -= 1
                self.line("}")
            else:
                raise Unsupported("unsupported GPU statement kind " + str(kind))

    def generate(self):
        root = self.nodes[self.root]["definition"]
        if len(root["parameters"]) > 8:
            raise Unsupported("GPU root has more than8 scalar arguments")
        for name in self.order:
            function = self.nodes[name]["definition"]
            self.result = function["result"]
            parameters = function["parameters"]
            scope = {p["name"]: "nex_p_" + str(i) for i, p in enumerate(parameters)}
            signature = [msl_type(p["type"]) + " " + scope[p["name"]] for p in parameters]
            signature.append("thread NexState &nex_s")
            self.line(msl_type(self.result) + " " + self.names[name] + "(" + ", ".join(signature) + ") {")
            self.indent += 1
            self.block(function["body"], scope)
            if self.result == "unit":
                self.line("return;")
            else:
                self.line("nex_s.code = 5; " + self.stop())
            self.indent -= 1
            self.line("}")
        if self.input_layout == "rows":
            self.line("kernel void nex_generated_map(device const long *input [[buffer(0)]],")
            self.line("  device long *output [[buffer(1)]], device uint *errors [[buffer(2)]],")
            self.line("  constant uint2 &parameters [[buffer(3)]], uint lane [[thread_position_in_grid]]) {")
        else:
            self.line("kernel void nex_generated_map(")
            for i in range(len(root["parameters"])):
                self.line("  device const long *input_" + str(i) + " [[buffer(" + str(i) + ")]],")
            self.line("  device long *output [[buffer(8)]], device uint *errors [[buffer(9)]],")
            self.line("  constant uint2 &parameters [[buffer(10)]], uint lane [[thread_position_in_grid]]) {")
        self.indent += 1
        self.line("if (lane >= parameters.x) return;")
        self.line("NexState nex_s = {0, parameters.y};")
        arguments = []
        for i, parameter in enumerate(root["parameters"]):
            name = "nex_input_" + str(i)
            address = "input[lane * " + str(len(root["parameters"])) + "u + " + str(i) + "u]" if self.input_layout == "rows" else "input_" + str(i) + "[lane]"
            self.line("long " + name + " = " + address + ";")
            if parameter["type"] == "bool":
                self.line("if (" + name + " != 0L && " + name + " != 1L) nex_s.code = 6;")
                arguments.append("(" + name + " != 0L)")
            else:
                arguments.append(name)
        self.line("long nex_result = 0L;")
        call = self.names[self.root] + "(" + ", ".join(arguments + ["nex_s"]) + ")"
        self.line("if (!nex_s.code) {")
        self.indent += 1
        self.line(("nex_result = " if root["result"] != "unit" else "") + call + ";")
        self.indent -= 1
        self.line("}")
        self.line("output[lane] = nex_s.code ? 0L : nex_result;")
        self.line("errors[lane] = nex_s.code;")
        self.indent -= 1
        self.line("}")
        return "\n".join(self.lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ["sdk", "project", "output"]:
        parser.add_argument("--" + key, required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--input-layout", choices=["rows", "columns"], default="rows")
    args = parser.parse_args()
    sdk, project = args.sdk.resolve(strict=True), args.project.resolve(strict=True)
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    compiler = sdk / "bin" / ("nex.exe" if os.name == "nt" else "nex")
    env = {**os.environ, "NEX_RESOURCE_DIR": str(sdk / "share/nex")}
    start = time.monotonic()
    report = {"schema": "nex.experimental-Metal-codegen/1", "ok": False, "commands": [],
              "compiler_sha256": sha(compiler), "driver_initialized": False,
              "installed_SDK_accepted": False, "general_GPU_backend_complete": False}

    def save():
        report["seconds"] = time.monotonic() - start
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(label, arguments):
        argv = [str(compiler), *arguments]
        with (out / (label + ".stdout")).open("wb") as stdout, (out / (label + ".stderr")).open("wb") as stderr:
            result = subprocess.run(argv, cwd=project, env=env, stdout=stdout, stderr=stderr, timeout=120)
        report["commands"].append({"label": label, "argv": argv, "exit_code": result.returncode})
        save()
        if result.returncode:
            raise Unsupported("actual compiler rejected " + label + "; inspect retained diagnostics")
        path = out / (label + ".stdout")
        if path.stat().st_size > 16777216:
            raise Unsupported("checked GPU graph output exceeds16MiB")
        return json.loads(path.read_bytes())

    try:
        index = run("index", ["describe", "--kind", "index", "--json"])
        if index["language"] != "0.28":
            raise Unsupported("select an actual language0.28 compiler")
        checked = run("check", ["check", "--json"])
        context = run("context", ["context", "--symbol", args.symbol, "--revision", checked["revision"], "--json"])
        graph = run("graph", ["graph", "--revision", checked["revision"], "--json"])
        if context["revision"] != checked["revision"] or graph["revision"] != checked["revision"]:
            raise Unsupported("checked graph revision changed")
        generator = Generator(graph, context["symbol"], args.input_layout)
        generated = generator.generate()
        runtime = Path(__file__).with_name("runtime.metal")
        (out / "kernel.metal").write_text(runtime.read_text() + "\n" + generated)
        root = generator.nodes[context["symbol"]]["definition"]
        report.update(ok=True, state="checked-source-generated", toolchain=index["toolchain"], language="0.28",
                      compiler_build=index["compiler_build"], descriptor_hash=index["descriptor_hash"],
                      revision=graph["revision"], root=context["symbol"], graph_sha256=sha(out / "graph.stdout"),
                      parameter_types=[p["type"] for p in root["parameters"]], result_type=root["result"], input_layout=args.input_layout,
                      functions={name: generator.nodes[name]["hash"] for name in generator.order},
                      kernel_sha256=sha(out / "kernel.metal"), runtime_sha256=sha(runtime),
                      generator_sha256=sha(__file__), error_codes={"1": "E_OVERFLOW", "2": "E_DIV_ZERO", "3": "E_ASSERT",
                      "4": "E_GPU_STEP_LIMIT", "5": "E_GPU_INTERNAL", "6": "E_GPU_INPUT"})
        if sha(compiler) != report["compiler_sha256"]:
            raise Unsupported("compiler bytes changed during code generation")
    except BaseException as error:
        report.update(ok=False, state="rejected", error=repr(error))
        raise
    finally:
        save()
    print(json.dumps({"ok": True, "output": str(out), "functions": len(report["functions"]), "driver_initialized": False}))


if __name__ == "__main__":
    main()
