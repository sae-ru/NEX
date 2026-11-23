---
status: current
applies_to: "toolchain 0.281.0; language 0.30"
owner: repository
---

# Insertion-ordered hash map

Import `std/insertion_ordered_map.nex` to use a persistent key/value map whose
entries iterate in first-insertion order. This order is useful when porting
Python dictionaries or Java insertion-order maps with stable hashable keys.
It uses standard NEX types, immutable return values and explicit callbacks.

Construct a map with `empty<K,V>(hash, equal)`. Both callbacks are pure.
Equality must be a stable equivalence relation, and equivalent keys must have
the same hash. `put` retains the first representative of an equivalent key
and its original position when changing its value. `remove` on a missing key
returns the input. Removing an existing key and inserting it again puts the
new representative at the end. Prior versions retain their keys, order and
values. A value containing a cell retains the ordinary NEX cell identity.

`has`, `get`, `size` and `is_empty` inspect a map. Missing `get` returns
`err("E_NOT_FOUND", ...)`. `entries`, `keys` and `values` enumerate in the
same insertion order. Maps contain callbacks. Use the ordered `entries`
list for interchange when its keys and values are wire-compatible.
[Runnable example](../examples/insertion-ordered-map/README.md)

The implementation maintains a persistent hash trie for lookup and a persistent
AVL tree keyed by insertion position. Ordinary changes rebuild only affected
paths and the affected hash-collision bucket, sharing the remaining subtrees.
For `n` retained keys, hash depth `d <= 17` and collision-bucket size `c`,
lookup costs O(d+c). Ordinary insertion, replacement and deletion cost
O(d+c+log(n+1)). Size and emptiness are O(1). Materializing ordered entries,
keys or values costs O(n). These bounds exclude callbacks, payload construction
and disposal of unreachable versions. A constant hash makes its bucket linear.

If removals over the lifetime of one branch exhaust its checked i64 position
counter, the next new insertion densely renumbers its live entries in order.
This exceptional rebuild costs O(n log(n+1) + sum of squared collision-bucket
sizes) and preserves prior versions. Overwriting an existing key never
requires renumbering. Element counts remain subject to checked i64 arithmetic.
The public operations assume maps constructed by this API. They do not implement
Python's dynamic hashing or Java access-order semantics.

On macOS ARM64, an installed development SDK produced the same 476 lines as
a Python dictionary across 26 observations of maps with up to eight entries.
The reference interpreter, native Debug and Release, and TypeScript checked
with `tsc --strict` and run by Node.js agreed. The checker rejected an effectful hash
callback. The trace covers an exhausted position counter by constructing a map
at that boundary. [Source hashes and focused results](evidence/insertion-ordered-map-0.281.0-2026-11-23.json)
