---
status: current
applies_to: "toolchain 0.274.0; language 0.28; language 0.29; language 0.30"
owner: repository
---

# Persistent sequences, queues, stacks and heaps

`std/sequence.nex`, `std/fifo.nex`, `std/lifo.nex` and `std/heap.nex` are ordinary
checked source modules. They use existing recursive values, generics, immutable
sharing and callable snapshots. There is no new primitive, syntax, source-version
migration or task/C ABI. Discover the matching `standard_library.modules` entry;
compiled SHA256 pins identify the actual installed sources.

The retained `std/queue`, `std/stack`, `std/deque` and `std/priority_queue`
keep their public flat-list fields and behavior. Select the new representation
explicitly when its performance/ordering contract fits the application.

## Operations and structural costs

| Module | Type and operations | Bound for valid API-produced values |
|---|---|---|
| `sequence` | `Sequence<T>`: both-end push/pop/peek, indexed `get`/`replace` | O(log(n+1)) worst case |
| `fifo` | `Queue<T>`: `enqueue`, `dequeue`, `peek` | O(log(n+1)) worst case |
| `lifo` | `Stack<T>`: `push_value`, `pop`, `peek` | O(1) |
| `heap` | `Heap<T>`: `push_value`, `pop` | O(log(n+1)) comparator calls/work |

All four have `empty`, `size`, `is_empty`, `items` and `validate`.
Size/empty are O(1). Sequence/FIFO expose cached O(1) `height`; heap exposes cached
O(1) `rank` and O(1) `peek`. Enumeration/validation are O(n), except heap `sorted`
is O(n log(n+1)). Heap `items` is preorder tree traversal, not priority order.
LIFO `items` returns the top first. Sequence/FIFO preserve logical sequence order.

Payload work, callbacks and retirement of unreachable old versions are additional.
Discarding the last owner of a whole structure can retire O(n) nodes. Retaining
an old version shares unchanged subtrees/links, rather than copying descendants.
The queue's logarithmic bound holds when histories branch; it does not rely on
an amortized two-list rotation being paid for only once.

## Sequence and FIFO

```nex
module work;
import "std/sequence.nex" as seq;
import "std/fifo.nex" as fifo;
fn main() -> unit {
  let before: seq::Sequence<str> = seq::push_back(seq::empty<str>(), "first");
  let after: seq::Sequence<str> = unwrap(seq::replace(before, 0, "new"));
  assert(unwrap(seq::get(before, 0)) == "first");
  assert(unwrap(seq::get(after, 0)) == "new");
  let queue: fifo::Queue<i64> = fifo::enqueue(fifo::empty<i64>(), 42);
  assert(unwrap(fifo::dequeue(queue)).value == 42);
}
```

Sequence provides `push_front`, `push_back`, `pop_front`, `pop_back`,
`peek_front`, `peek_back`, `get`, `replace`, `items` and `validate`.
`get` returns `result<T>`; `replace` returns `result<Sequence<T>>`. Negative or
out-of-range indices yield `E_BOUNDS`. Empty end operations yield `E_EMPTY`.
Pop returns `Popped<T>{sequence,value}`. FIFO pop returns `{queue,value}`.

The sequence is an indexed AVL tree. Cached subtree counts select positions;
rotations preserve inorder values. End updates and replacement copy one bounded
path. FIFO wraps that sequence. Public nodes expose value/children/count/height;
validation checks child cardinality, cached metadata and balance, with a90-level
limit valid for positive-i64 AVL counts. It does not repair manually forged trees.

## Linked stack

`lifo::Stack<T>` uses zero-or-one root/next lists and cached counts. Push makes
one head; pop returns `Popped<T>{stack,value}` sharing the tail. Empty pop/peek
returns `E_EMPTY`. Traversal and validation are iterative; they do not use one
source recursion frame per link. The shared runtime's iterative retirement
handles deep value teardown. Other operations assume an API-produced stack.

## Priority heap

Construct with `heap::empty(compare)`, where pure `fn(T,T)->i64` uses its sign
to define a stable strict weak ordering. `ascending<T:ordered>()` and
`descending<T:ordered>()` supply numeric i64/f64 order. For records, provide a
comparator; include a serial field when equal-priority stability is required.
Ties otherwise have no stability guarantee. Captured comparator values retain
ordinary NEX snapshot semantics. Empty `peek`/`pop` yields `E_EMPTY`; pop returns
`Popped<T>{heap,value}`.

The rank-biased leftist invariant keeps the right path short. Rank is its node
count and satisfies left-rank≥right-rank; push/pop meld along right paths. With
a positive-i64 count, rank cannot exceed63. The
[CMU rank-bound discussion](https://www.cs.cmu.edu/afs/cs/academic/class/15210-s13/www/recitations/rec15.pdf)
gives the underlying logarithmic argument. This NEX implementation additionally
caches counts and uses explicit stack traversal/validation, including long left
chains. Validation checks shape, counts, ranks and local heap order; arbitrary
comparator laws remain a caller contract.

`merge(left,right)` produces a heap under the **left** comparator. It enumerates
and inserts the right values, supporting different valid comparison policies at
O(m log(n+m+1)) work for n/m input sizes. Both input versions remain intact.
`sorted` repeatedly removes the current minimum; `items` simply traverses the
heap. The callback-bearing heap is not a wire value; export `items`/`sorted` or
a DTO with wire-compatible fields. For other containers, exporting `items` also
avoids serializing internal tree/link metadata and its wire-depth limits.

## Delivery and qualification

The [example](../examples/sequence-containers/README.md) contains source030
cell/task and caught-error composition. Pure library consumers also run in
retained028/029 projects. Dependency locks keep reviewed source hashes; changing
a pin requires an explicit review/update, without rewriting old graph history.
The retained list modules have corrected complexity comments/pins, with unchanged
function bodies and layouts. Their repeated flat-list `push` loops can copy
quadratic prefixes; source discovery now reports those bounds explicitly.

`tests/sequence_containers.py` compares independent Python list/deque/heapq
observations with reference, native Debug/Release and executed strict TypeScript.
Cases include branching snapshots, indexed bounds, double rotations, numeric
extremes, duplicate priorities, comparator normalization, malformed values,
16384 stack links and a4096-node left heap chain. SDK source-library acceptance
also consumes both example programs after installation. Full current source,
platform and portable SDK gates remain separate from focused checks.
Published SDK0.246.1 is immutable and predates these modules.

The [focused0.274 receipt](evidence/sequence-containers-0.274.0-2026-11-17.json)
records24 distinct core/affected CTest groups, the direct new-container harness
and32 commands using the actual relocated normal installation. The source
standard-library SDK subworkflow runs five examples and19 rejection controls.

A [local combined workload](evidence/sequence-container-workload-0.274.0-2026-11-17.json)
inserts and removes256 integers from each of FIFO, LIFO, deque and priority
containers, verifying every result and a shared checksum. Five alternating
Release-process trials on Apple M5 Max measured medians0.062722s for the retained
list modules and0.014221s for the new modules (4.41× for this combined workload).
Wall time includes process startup and cleanup; compilation is excluded. This
does not measure each container independently, arbitrary applications, other
languages or token savings.
