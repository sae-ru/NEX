---
status: current
applies_to: "toolchain 0.247.0; language 0.28 and 0.29"
owner: repository
---

# Persistent ordered map and set

`std/ordered_map.nex` and `std/ordered_set.nex` implement persistent AVL trees in
ordinary NEX source. Lookup and update follow a logarithmic search path. Each
update returns a new collection; saved versions retain their original values.
The existing [list-backed map/set](containers.md) retain insertion order and
their existing APIs. No language migration is required.

```nex
import "std/ordered_map.nex" as maps;
fn compare(a:i64,b:i64)->i64 {
  if a<b{return -1;}if a>b{return 1;}return 0;
}
fn example()->unit {
  let old:maps::Map<i64,str>=maps::put(maps::empty(compare),2,"two");
  let next:maps::Map<i64,str>=maps::put(old,1,"one");
  assert(maps::keys(next)==[1,2] && maps::keys(old)==[2]);
  assert(unwrap(maps::get(next,2))=="two");
}
```

The [complete example](../examples/ordered-containers/main.nex) has an explicit
0.29 project manifest and dependency lock. The same modules also compile in
0.28 projects. Discover the actual installed APIs and source pins with
`nex describe --field standard_library --json`, then use `nex lock --json` to
record a project's checked dependencies.

Updating standard-library source can change a project's dependency pins. Review
the library changes before explicitly updating its lock; checking never silently
rewrites an existing dependency lock.

## Comparator contract

`empty` takes a pure `fn(K,K)->i64`. Negative means before, positive means after,
and zero defines equivalent keys. The comparator must define a stable strict
weak ordering, including transitive equivalence. It can capture immutable
values, but cannot perform `io` or other effects. Avoid subtracting arbitrary
i64 keys: subtraction can overflow; compare with `<` and `>` as above.

`put` on an equivalent key replaces its value and retains the first key
representative. `get`, `has`, and `remove` use the same equivalence, even if two
keys differ according to `==`. No locale, case folding or ordering for custom
types is invented by the library. Define the required rule in the comparator.

## Map API

| Function | Result |
|---|---|
| `empty<K,V>(compare)` | empty `Map<K,V>` |
| `put(map,key,value)` | new map with an inserted or replaced value |
| `remove(map,key)` | new map without the equivalent key; absent key has no effect |
| `get(map,key)` | `result<V>`; missing key returns `E_NOT_FOUND` |
| `has(map,key)` | bool |
| `entries(map)` | ordered `list<Entry<K,V>>`; each entry has `key` and `value` |
| `keys(map)` / `values(map)` | lists in comparator order |
| `size(map)` / `is_empty(map)` | cached count / bool |
| `height(map)` | cached tree height; empty is 0 |
| `validate(map)` | whether the public representation satisfies tree invariants |

## Set API

`Set<T>` wraps `Map<T,bool>`. It provides `empty(compare)`, `add`, `remove`,
`has`, `items`, `size`, `is_empty`, `height`, `validate`, `union`, `intersection`
and `difference`. Enumeration is in comparator order; equivalent additions
retain the existing representative.

Binary set operations use the **left** comparator and retain left
representatives. The right set can have another comparator; intersection and
difference first normalize its items under the left rule. Thus an equivalent
right item matches even when its original comparator would distinguish it.

## Representation and complexity

`Node<K,V>` exposes `key`, `value`, `left`, `right`, `height`, and `count`.
Children and `Map.root` are lists of zero or one node; `Map.compare` is the
comparator. `Set.tree` is its backing map. Only rebuild the path being changed:
records and lists contain shared immutable values, so retaining a subtree does
not deep-copy its descendants. AVL rotations keep height O(log(n+1)). The
runtime's `Value` shared payloads and `nex_record_init_heap` retain these values;
TypeScript also shares unchanged immutable child objects. Enumeration uses a
linked traversal stack and a linear list builder, without repeated concatenation.

For valid API-produced trees with n entries, lookup, insertion and removal take
O(log(n+1)) comparator calls and insertion/removal allocate O(log(n+1)) path
nodes. `size`, `is_empty`, and `height` take O(1); enumeration takes O(n) time
and output space with O(log(n+1)) traversal state. `validate` takes O(n) time
and O(log(n+1)) stack space. Exclude comparator/value construction and reclamation
of unreachable saved versions from these bounds; dropping the last owner of an
entire tree can release O(n) nodes.

For left/right sizes n/m, union takes O(m log(n+m+1)); intersection and difference
take O((n+m) log(n+m+1)), including normalization. Output versions remain immutable.

Public fields allow manually assembled representations. `validate` checks child
cardinality, strict key bounds, cached counts/heights and AVL balance before
trusting child metadata. It rejects depth above 90: no AVL tree with a positive
i64 entry count can be taller. It cannot prove comparator laws. Other operations
expect valid representations and do not run an O(n) validation before each call.
The comparator field prevents serializing the entire map as a wire value; export
`entries` instead when its key/value types support the wire protocol.

These modules are not hash tables. Efficient queue/deque/heap implementations
and matching installed SDK/platform qualification remain separate work.

[0.247 focused acceptance](evidence/containers-0.247.0-2026-11-15.json) records
272 deterministic trace operations, four insertion rotation orders, ascending
and descending 512-entry trees, native Debug/Release/reference/strict TypeScript
agreement, rejected comparator signatures and a relocated local installation.
The record also preserves the exploratory step-budget failure and the corrected
diagnostic-code test expectation. It does not claim full SDK/platform acceptance.
