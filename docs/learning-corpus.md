# Current learning corpus

`llm/corpus-spec.json` authors current examples and expected outcomes.
`llm/corpus.json` contains observed labels generated only after complete validation
with the selected compiler. The specification and labels share
[the corpus schema](../llm/corpus.schema.json); they have distinct schema tags and
path-base semantics. Repository-relative label paths also resolve within a
matching SDK resource tree. Labels bind source and project/import files, compiler bytes,
compiler/descriptor identities, the language-pack manifest and validation report.

The current finite corpus covers functions, typed source errors/finally, ordered
CPU mapping, source contracts/loop rankings, generics/enums/Results, finite f64,
Unicode/bytes/codecs, traits/associated types, structured tasks and module imports.
It is teaching material, not complete language/platform/SDK qualification or a
measurement of LLM task cost. Provider grants, server/UI/mobile and device execution
retain their separate guides and acceptance boundaries.

## Validate and publish labels

From a source checkout, or the matching SDK resource root:

```sh
python3 tools/llm/language_pack.py --compiler /absolute/path/to/nex \
  --resources /absolute/path/to/resources --check
NEX_NODE=/absolute/path/to/node NEX_TSC=/absolute/path/to/typescript/bin/tsc \
python3 tools/llm/learning_corpus.py --compiler /absolute/path/to/nex \
  --resources /absolute/path/to/resources --output /new/learning-validation \
  --publish /absolute/path/to/resources/llm/corpus.json
```

Node22.18+ and the resource cohort's locked TypeScript compiler are required.
The validator does not install dependencies or call a model. It checks every
source first, then runs reference main/tests, native Release main/tests,
TypeScript tests and emitted TypeScript main for each valid project. Assertions
must actually execute: missing, skipped or wrongly selected backend tests fail.
Rejected sources must produce exactly the labelled frontend diagnostic and exit1;
a crash is not accepted as a rejection.

Commands, raw stdout/stderr, hashes and copied inputs are retained in the new
output directory. Programs run in isolated temporary projects, outside existing
NEX projects. No source examples or existing graphs are modified. A failed
workspace stays available for reproduction; successful native/build workspaces
are removed. TypeScript tasks must report completed cleanup with no active calls
or retained frames. These Node checks do not establish browser UI execution.

Without `--publish`, validation writes only the new report directory. Publication
requires the complete accepted case/backend set, unchanged input/manifest/spec
pins and the original historical-record digest. It atomically replaces labels
only after success. Do not manually change a failed record to `passed`.

## Historical record

[The retained0.27/0.152.1 corpus](../llm/history/learning-0.27-0.152.1/README.md)
keeps its original JSON bytes and Git-recovered input snapshot. Its compiler was
not rerun and its result is not relabelled as0.28. The canonical example manifests
had already advanced to0.28; this validation supplies new evidence rather than
pretending that the earlier receipt validates those changed inputs.
