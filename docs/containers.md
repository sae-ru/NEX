---
status: current
applies_to: "toolchain 0.178; language 0.28"
owner: repository
---

# Map and set containers

`std/map.nex` and `std/set.nex` are checked source modules. They are immutable,
insertion-ordered, and backed by a list: lookup and update are **O(n)**, not a
hash table or a balanced tree. They do not add a language primitive or change
language semantics.

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
`remove(set,value)`, `has(set,value)`, `items(set)`, and `size(set)`. `add` of
an existing value is a no-op. Removal preserves order and removes matching
values; duplicates are not produced by `add`.

## Limits

Operations scan the backing list and allocate a new list, so `put`, `remove`,
`get`, and `has` are O(n). This is suitable for checked small and medium
collections, not a replacement for a hash or balanced-tree container. Those,
generic ordering constraints, and effect-polymorphic named signatures remain
pending. Import aliases such as `maps`/`sets` avoid the reserved `list` name and
the `std/list` `map` helper.


## Queue and stack

`std/queue.nex` (`std::queue`) provides immutable FIFO `Queue<T>` with
`empty`, `enqueue`, `dequeue`, `peek`, `size` and `is_empty`; `dequeue`/`peek`
return `result` and empty operations use `E_EMPTY`. `std/stack.nex`
(`std::stack`) provides immutable LIFO `Stack<T>` with `empty`, `push_value`,
`pop`, `peek`, `size` and `is_empty`. Both are list-backed and therefore O(n)
per element operation; neither is a ring buffer, hash table or language
primitive.
