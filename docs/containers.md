---
status: current
applies_to: "toolchain 0.247.0; language 0.28 and 0.29"
owner: repository
---

# Map and set containers

`std/map.nex` and `std/set.nex` are checked source modules. They are immutable,
insertion-ordered, and backed by a list: lookup and update are **O(n)**, not a
hash table or a balanced tree. They do not add a language primitive or change
language semantics.

For a persistent hash trie with explicit stable hash/equality callbacks, use
[hash map/set](hash-containers.md). Hash order differs from global insertion
order. For logarithmic lookup/update with explicit comparator order, use the separate
[persistent AVL map/set](ordered-containers.md) modules introduced in 0.247.

```nex
module inventory;
import "std/map.nex" as maps;
import "std/set.nex" as sets;

fn main() -> unit !{io} {
  let stock: maps::Map<str, i64> = maps::put(maps::empty(), "bolts", 12);
  assert(unwrap(maps::get(stock, "bolts")) == 12);
  assert(!maps::has(stock, "nuts"));
  assert(maps::keys(stock) == ["bolts"]);

  let tags: sets::Set<str> = sets::add(sets::add(sets::empty(), "metal"), "metal");
  assert(sets::size(tags) == 1);
  print("containers-ok");
}
```

## Map

`Map<K,V>` exposes `entries: list<Entry<K,V>>`; `Entry<K,V>` has `key` and
`value`. Functions:

| Function | Result |
|---|---|
| `empty<K,V>()` | empty map |
| `put(map,key,value)` | copy with the key inserted at the end, or replaced in place |
| `remove(map,key)` | copy without every matching key |
| `get(map,key)` | `result<V>`; missing key is `E_NOT_FOUND` |
| `has(map,key)` | bool |
| `keys(map)` / `values(map)` | insertion-order lists |
| `size(map)` | number of entries |

`put` and `remove` are immutable: an existing binding is not changed. Keys are
compared with `==`; the key type must support it.

## Set

`Set<T>` exposes `items: list<T>`. Functions `empty<T>()`, `add(set,value)`,
`remove(set,value)`, `has(set,value)`, `union(left,right)`,
`intersection(left,right)`, `difference(left,right)`, `items(set)`, and
`size(set)`. `add` of an existing value is a no-op. Removal preserves order and
removes matching values; duplicates are not produced by `add`. Set operations
preserve the left insertion order. For left/right sizes n/m, union is
O(m(n+m)); intersection/difference are O(n(n+m)), including duplicate checks
and output construction. `items` and `size` are O(1).

## Limits

Operations scan the backing list. In 0.247, map updates/enumeration and set
removal use the linear bulk constructor instead of repeatedly copying a growing
list; `put`, `remove`, `get`, and `has` are O(n), excluding key/value comparison
and construction. This is suitable for checked small and medium
collections. Hash containers use the separate persistent trie modules; balanced-tree collections are
available through the separate ordered modules. Generic numeric ordering and
[inferred effect parameters](effect-parameters.md) are implemented features.
Import aliases such as `maps`/`sets` avoid the reserved `list` name and
the `std/list` `map` helper.


## Queue, stack and deque

`std/queue.nex` (`std::queue`) provides immutable FIFO `Queue<T>` with
`empty`, `enqueue`, `dequeue`, `peek`, `size` and `is_empty`; `dequeue`/`peek`
return `result` and empty operations use `E_EMPTY`. `std/stack.nex`
(`std::stack`) provides immutable LIFO `Stack<T>` with `empty`, `push_value`,
`pop`, `peek`, `size` and `is_empty`. `std/deque.nex` (`std::deque`) provides
`Deque<T>` with `push_back`/`push_front`, `pop_front`/`pop_back` and
`peek_front`/`peek_back`. `std/priority_queue.nex` (`std::priority_queue`)
provides an immutable ascending minimum `PriorityQueue<T: ordered>` with
`empty`, `push_value`, `pop`, `peek`, `size` and `is_empty`. All four are
list-backed and therefore O(n) per element operation; none is a ring buffer,
binary heap, hash table or language primitive.
