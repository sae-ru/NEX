# Preserve the order of stock updates

`main.nex` records two warehouses. Updating the western warehouse's count keeps
it in first place. Removing it and adding it again places it after the eastern
warehouse. The saved version still has its original order and counts.

Run `nex test --json` and `nex run --json` from this directory. The program
prints `east` followed by `west`. [Map operations and costs](../../docs/insertion-ordered-map.md)
