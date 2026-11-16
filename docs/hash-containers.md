---
status: current
applies_to: "toolchain 0.273.0; language 0.28; language 0.29; language 0.30"
owner: repository
---

# Persistent hash map and set

`std/hash_map.nex`, `std/hash_set.nex` and `std/hash.nex` are ordinary checked
source libraries. They use existing generics, immutable aggregates, recursive
values and callable snapshots. No source type, operator, grammar, source-version
migration or runtime ABI is added. Discover
`standard_library.modules.hash_map`, `hash_set` and `hash` in the selected
compiler; its descriptor pins the installed source bytes with SHA256.

```nex
module inventory;
import "std/hash.nex" as hash;
import "std/hash_map.nex" as maps;
fn main() -> unit {
  let original: maps::Map<str, i64> = maps::empty(hash::text, hash::equal<str>);
  let stock: maps::Map<str, i64> = maps::put(original, "bolts", 12);
  assert(unwrap(maps::get(stock, "bolts")) == 12);
  assert(maps::is_empty(original));
}
```

## Keys, hashes and order

Construction takes pure `hash: fn(K)->i64` and `equal: fn(K,K)->bool` callbacks.
Equality must be a stable equivalence relation, and equivalent keys must have
exactly equal hashes. Keys and callable captures are ordinary NEX snapshots;
cells retain their documented identity. A callback failure follows ordinary
source control rules. The container cannot prove arbitrary callback laws.

The trie consumes all64 bits of the signed-i64 hash, four at a time, starting
with the low nibble. Arithmetic quotient/remainder implements the equivalent
signed bit decomposition without changing checked NEX arithmetic. Child slots
are0–15 in ascending order. Distinct keys with the same complete hash share a
leaf bucket. Equality checks apply to that bucket; unequal complete hashes do
not require key comparison. Updating an equivalent key retains its first key
representative and replaces the value.

Enumeration is ascending lexicographic low-nibble-first hash order, with
insertion order within each full-hash collision bucket. It is neither global
insertion order nor sorted key order. Existing `std/map.nex` and `std/set.nex`
retain their list-backed insertion-order API; use the separate
[ordered containers](ordered-containers.md) for comparator order.

## API

`Map<K,V>` has `empty(hash,equal)`, `put`, `remove`, `get`, `has`, `size`,
`is_empty`, `entries`, `keys`, `values`, `height` and `validate`.
`get` returns `result<V>` with `E_NOT_FOUND` for an absent key. `Entry<K,V>`
contains `key` and `value`. Updates preserve all retained old maps and values.

`Set<T>` has `empty(hash,equal)`, `add`, `remove`, `has`, `items`, `size`,
`is_empty`, `height`, `validate`, `union`, `intersection` and `difference`.
Set algebra uses the left operand's hash/equality callbacks. Union retains left
representatives; intersection/difference first normalize the right values under
those callbacks. The right set may use a different valid equivalence relation.

The public source representation contains `Item<K,V>`, `Node<K,V>` and a map
root plus its two callbacks. Operations assume an API-produced valid trie.
`validate` checks shape, bounded depth, sorted child slots, cached counts,
complete-hash buckets, hash-path correspondence, recomputed hashes and equal
duplicates within a bucket. It rejects malformed representations; it does not
prove equality laws or detect inconsistent equivalence across different hashes.

Map/set values contain their hash/equality callbacks. For a wire/API response,
serialize `entries`/`items` or an application DTO whose key/value types satisfy
the ordinary wire contract. The internal callback-bearing map is not a JSON
wire value.

## Costs

Let n be the entry count, d the number of trie nodes on the selected path and
c the size of its complete-hash bucket. API-produced tries have d≤17. Branches
hold at most16 children. Lookup/update/removal use O(d+c) work, excluding hash,
equality and value costs. Updates rebuild the changed path and at most one
bucket, sharing unchanged subtrees. Colliding hashes may make c=n.

Size/empty are O(1). Enumeration and `height` are O(n); enumeration uses a
bounded cursor stack and the linear list constructor. Validation costs
O(n+sum(c²)) because it also checks bucket duplicates. Set algebra performs
insertions/lookups under the left callbacks and can be quadratic with collisions.
Reclamation of unreachable versions and payload/callback work are additional.
These are structural bounds, not a general throughput or token-saving claim.

A [local0.273 workload](evidence/hash-container-workload-0.273.0-2026-11-17.json)
on Apple M5 Max inserted, read and removed4096 integer keys. Five alternating
Release-process trials measured medians4.602724s for the existing list-backed
`std/map` and0.102064s for `std/hash_map` (45.10×). Both produced the same checked
checksum. Timing includes process startup/cleanup and excludes compilation. This
is one integer-key workload; it does not measure arbitrary applications, other
languages, string hashing or LLM token costs.

## Hash helpers

`std/hash.nex` supplies `integer(i64)`, `boolean(bool)`, `binary(bytes)`,
`text(str)` and generic `equal<T>(T,T)`. Integer hashing is the identity across
the full i64 range; booleans map to0/1. Binary hashing starts at0 and applies
`h=(h*257+octet+1)%4294967296` per byte. Text hashes its strict UTF-8 bytes;
NUL, BOM and combining sequences keep their ordinary exact-byte meaning. There
is no normalization or case folding. Binary/text hashing is O(bytes); text
materializes the UTF-8 buffer. These are stable bucket helpers, with no
cryptographic contract. Applications may supply their own consistent functions.

## Use and qualification

The [example](../examples/hash-containers/README.md) has a source0.30 project,
reviewed dependency pins and a separate cell/task example. These pure modules
also run in retained028/029 projects without relabeling their graphs.

`tests/hash_containers.py` compares a deterministic Python dict/set oracle with
reference execution, native Debug/Release and executed strict TypeScript. It
covers signed hash boundaries, the full17-node path, collisions, retained
versions, custom equality, differing set callbacks, byte hashing, malformed
representations, pin rejection and source0.30 cells/tasks. Full matching source,
platform and portable SDK qualification remain separate. The
[focused0.273 receipt](evidence/hash-containers-0.273.0-2026-11-17.json) retains
matching identities, source observations and the actual moved installation proof. Published SDK0.246.1
is immutable and predates these modules. [Sequence/FIFO/LIFO/heap libraries](sequence-containers.md) have separate
focused acceptance. Complete delivery and the remaining original PLAN stay open.
