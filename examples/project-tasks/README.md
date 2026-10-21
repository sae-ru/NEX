# Project task example

Requires the project_architecture_tasks capability (toolchain0.78 candidate).
The app consumes a real shared core library and one shared runtime.

```sh
nex task task.json --kind check --json
nex task task.json --kind run --json
nex task /absolute/run/receipt.json --kind replay --json
```

The reviewed example task pins the architecture and test body, checks output
42 🧠, builds actual images and measures one call to core::make. It is an example
acceptance contract, not a claim that natural-language goals can be proven from
placeholders. Use the current operator catalogues if configuring custom native
compilers or FFI. Deployment packages and task/editor debugger commands remain
separate workflows. See the project task guide.
