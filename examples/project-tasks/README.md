# Project task example

Requires project_architecture_tasks and project_task_packages (toolchain0.79 candidate).
The app consumes a real shared core library and one shared runtime.

```sh
nex task task.json --kind check --json
nex task task.json --kind run --json
nex task /absolute/run/receipt.json --kind replay --json
```

The reviewed example task pins the architecture and test body, checks output
42 🧠, builds actual images, measures one call to core::make and captures a
deployment package without executing it. It is an example
acceptance contract, not a claim that natural-language goals can be proven from
placeholders. Use the current operator catalogues if configuring custom native
compilers or FFI. Inspect the package check's relative `package` directory in
the receipt for deployable output. Package generation does not verify target
execution; task/editor debugger commands remain separate. See the project task guide.
