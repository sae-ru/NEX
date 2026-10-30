# Project task example

Toolchain 0.151.1 / language 0.27. Requires `project_architecture_tasks` and
`project_task_packages` from the selected compiler.
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

The checked-in contract pins this example's current source revision and test
content. After a source change, generate a fresh scaffold with
`nex task nex.build.json --kind init --component app --configuration debug --json`
and review its pins together with the existing acceptance requirements. This
example has no persisted graph. An existing project's language/history requires
the explicit migration workflow; editing the task version is not a migration.
