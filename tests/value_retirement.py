"""Execute bounded-stack retirement cases separately; keep the actual outcomes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

SCENARIOS=("ordinary","closed_snapshot","shared_tail","duplicate_edges",
           "wide_branches","host_destructor","owned_file","unwind","concurrent")


def no_core():
    import resource
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("probe",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for name in SCENARIOS:
        started=time.monotonic()
        result=subprocess.run([str(args.probe.absolute()),name],capture_output=True,
                              text=True,timeout=60,preexec_fn=no_core if os.name=="posix" else None)
        row={"scenario":name,"returncode":result.returncode,"stdout":result.stdout,
             "stderr":result.stderr,"wall_seconds":time.monotonic()-started}
        if result.returncode==0:
            try:
                receipt=json.loads(result.stdout)
                row["receipt"]=receipt
                row["ok"]=(receipt["ok"] is True and receipt["scenario"]==name
                           and receipt["depth"]==65536 and receipt["stack_bytes"]==262144
                           and receipt["live_value_delta"]==0)
            except (ValueError,KeyError,TypeError):row["ok"]=False
        else:row["ok"]=False
        rows.append(row)
        print(("PASS " if row["ok"] else "FAIL ")+name,flush=True)
    evidence={"schema":"nex.value-retirement-tests/1","ok":all(r["ok"] for r in rows),
              "probe_sha256":hashlib.sha256(args.probe.read_bytes()).hexdigest(),"results":rows}
    (args.output/"results.json").write_text(json.dumps(evidence,indent=2)+"\n")
    if not evidence["ok"]:raise SystemExit(json.dumps(evidence,indent=2))


if __name__=="__main__":main()
