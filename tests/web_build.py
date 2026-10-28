"""Opt-in real npm/TypeScript/Vite build, isolation, cache and snapshot checks."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("compiler", type=Path)
parser.add_argument("--npm-cache", type=Path)
args = parser.parse_args()
compiler = args.compiler.resolve()
repo = Path(__file__).resolve().parents[1]
env = dict(os.environ)
if args.npm_cache:
    env["NEX_NPM_CACHE"] = str(args.npm_cache.resolve())
with tempfile.TemporaryDirectory(prefix='nex real web build "quoted" \\ % 🧠 ') as temporary:
    root = Path(temporary)
    (root / "nex.json").write_text(json.dumps({"entry": "main.nex", "language": "0.16"}))
    source = root / "main.nex"
    secret = "SERVER_ONLY_NEVER_IN_BROWSER_ASSETS"
    source.write_text((repo / "examples/web/main.nex").read_text() + '\nserver fn secret() -> str { return "' + secret + '"; }\n')
    def call(*options):
        result = subprocess.run([str(compiler), *map(str, options), "--json"], cwd=root, env=env, capture_output=True, text=True, timeout=240)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)
    built = call("build", "--target", "web", "--profile", "release")
    assert not built["cached"], built
    dist = Path(built["dist"])
    assert (dist / "index.html").is_file()
    assert (dist / "THIRD_PARTY_NOTICES.txt").is_file()
    for file in dist.rglob("*"):
        if file.is_file():
            assert secret not in file.read_text(), file
    assert call("build", "--target", "web", "--profile", "release")["cached"]
    (dist / "index.html").write_text("corrupted cached browser output")
    repaired = call("build", "--target", "web", "--profile", "release")
    assert not repaired["cached"]
    assert "corrupted" not in (dist / "index.html").read_text()
    copied = root / "standalone web assets"
    call("build", "--target", "web", "--profile", "release", "-o", copied)
    assert (copied / "index.html").read_bytes() == (dist / "index.html").read_bytes()
    assert len(list(copied.rglob("*"))) == len(list(dist.rglob("*")))
    source.unlink()
    archived = call("build", "--target", "web", "--profile", "release", "--revision", built["revision"])
    assert archived["cached"] and archived["build_key"] == built["build_key"]
    print(json.dumps({"real_build": True, "secret_excluded_from_assets_and_source_maps": True,
                      "cache_hit_and_corruption_repair": True, "standalone_asset_copy": True,
                      "archived_source_build": True, "revision": built["revision"]}))
