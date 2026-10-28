# Private source exceptions with files and foreign resources

Toolchain0.135.21 extends the separate `0.25-prototype` task experiment.
Discover `source_exception_prototype` and its `private_task_native_host_*`
fields. Ordinary `nex.json` projects still select public language0.24 and
reject private025. Publication requires an explicit history-preserving migration.

`parseSourceExceptionTasksPrototype` can check server functions combining
`task`, `fs`, `ffi` and `throw`. It retains the existing realm and callable
signature rules. The sequential private parser retains its pure/io/throw scope.
Private task TypeScript still rejects host effects.

```nex
module file_exception;
server fn load()->i64 !{task,fs,throw} {
  let f:file=unwrap(file_open_read("input"));
  let data:bytes=unwrap(file_read(f,6));
  if len(data)!=6 { throw("SHORT","expected six bytes"); }
  return len(data);
}
server fn main()->i64 !{task,fs} {
  try { return load(); }
  catch(code,message) { return 0; }
}
```

Whole-file operations, opened files and pinned C FFI callbacks use the same
host bridges as public024. The operator supplies filesystem roots and write
access explicitly. Native foreign calls require `--nex-foreign HOST.json` and
the existing exact bundle/signature declarations. Source effects describe
requirements; they do not configure the host.

Lexical unwinding retires values created within the exited scopes. An outer
file or opaque resource remains usable after a catch; a closed alias remains
closed. File cursors and completed writes preserve their observable effects.
Resources returned from a task scope or future retain the existing region
promotion rules. A failed child releases its local values before delivery.

`task_spawn` retains a child's source-error effect in its future. `task_wait`
and `with_tasks` require a lexical try or a declared `throw` effect. A callback
may combine server task/fs/ffi with throw; its caller still declares the host
effects. A source exception remains distinct from `Result`: a foreign or file
error becomes a source exception only through an explicit `throw`.
Runtime assertion failures, cancellation and deadlines bypass source catches.

Private native images requiring file/foreign operations or file carriers use
`0x4e45585400002502`. Pure private images retain2501. The public ABI3/4/5
formats and masks retain their existing interpretation. An image uses one
private ABI across its linked task descriptors. Existing private source-site,
profile and debug metadata carry the selected descriptor ABI.

`source_exception_host` compares independent AST and TaskIR execution with
actual native O0/O2 execution. Fixtures exercise recovery, rethrow, file
cursor preservation, repeated cleanup, resource factories/finalizers, future
delivery and returned owners. Reports identify the compiler/platform and
their exact functional scope. The LLDB conformance pauses with both a file and
a foreign resource alive, then checks catch values after unwinding. File identity
expressions can be captured and inspected offline. External resource previews
remain available, but evaluating a resource proxy still reports
`E_DEBUG_UNAVAILABLE`, as in the public debugger. Security-specific checks are
user-deferred.

HTTP request hosting, source binary providers, installed SDK acceptance,
complete platform delivery, browser host effects and public025 migration
remain pending. This experiment does not complete the language/toolchain.
