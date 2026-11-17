# A manual Java queue port

This language0.30 program manually adapts the ring queue operations of Apache
Commons Collections4.6.0 `CircularFifoQueue`. It exercises an existing Java
library's observable behavior with ordinary NEX generics, cells, typed errors
and cooperative tasks. It introduces no compiler feature or converter.

Run with a source-built NEX0.280.1 or a compatible later compiler:

```sh
cd examples/java-circular-fifo
/absolute/path/to/nex check --json
/absolute/path/to/nex eval --json
/absolute/path/to/nex run --profile release --json
/absolute/path/to/nex test --target web --json
```

The example prints `java-circular-fifo-ok`. It imports the ordinary
`std/java_int.nex` module; keep its dependency lock with the source project.
This directory was added after the published0.280.1 SDK snapshot. Its source
can be used with that compiler; it is not already inside that frozen archive.

## Preserved behavior

- A positive fixed capacity, default32; insertion evicts the oldest item when
  the ring is full. `is_at_full_capacity` and `is_full` are distinct: the
  latter is always false because insertion remains possible.
- Queue and iterator aliases retain identity through cells. Copies made with
  `from_items(items(queue))` have independent queue storage. A saved list is an
  immutable snapshot.
- Empty `peek`/`poll` return `Maybe::None`. `remove`/`element` throw `EmptyError`.
  `get` checks the logical index. The explicit `add_maybe`/`offer_maybe` and
  `from_maybe_items` adapters represent Java's null rejection.
- Iterator traversal and removal preserve the head, contiguous-shift and
  wrapped-shift paths, including repeated removal and iterator aliases.
- Generic elements can contain genuine cells. Cooperative child tasks can use
  the same queue within one owner context.

Construct queues and iterators through the factory functions. Their NEX record
representations are visible; this example does not reproduce Java private-field
access control. It does not implement the entire inherited `Collection` API,
JVM serialization, reflection, class dispatch, Java monitors or the Java memory
model. Concurrent mutation during traversal has no additional compatibility
promise. This is a bounded manual port, not Commons Collections as a whole.

## Comparison with the original Java

`tests/fixtures/java-circular-fifo` retains two unmodified Java source files,
their Apache license/notice and a source-archive hash record. `Oracle.java`
calls those original classes. Its frozen995 observations cover48 deterministic
command traces: invalid construction, null/empty/index errors, overflow
eviction, queue/iterator aliases, snapshots/copies and iterator removal over
capacities1..6 in contiguous and wrapped states. Native, reference and executed
strict TypeScript must match the same original observations. This is functional
agreement for the selected corpus; no throughput or whole-Java compatibility
claim follows from it.

Run the maintained group after building:

```sh
ctest --test-dir build -R '^java_circular_fifo$' --output-on-failure
```

Set `NEX_JAVA_HOME` to a JDK21+ directory to compile and execute the original
Java again during the test. A JDK is optional for ordinary regression: the
checked-in frozen oracle retains the original observations and source hashes.
TypeScript validation uses the repository's pinned web dependencies, as described
in the [testing guide](../../docs/testing.md).

The adapted queue and retained upstream files use Apache-2.0, with
[LICENSE.txt](LICENSE.txt) and [NOTICE.txt](NOTICE.txt). NEX-authored test adapters
retain the repository's MIT license.
