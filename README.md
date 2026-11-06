# Historical NEX backup snapshots / Исторические резервные снимки NEX

This archive branch consolidates 293 old backup branch tips. `refs.json` preserves
each original name and commit. Every mapped commit remains reachable through this
archive commit's parents. These snapshots were not merged into the active language.

Fetch the archive, then create a local branch at a selected commit from `refs.json`:

```sh
git fetch origin codex/archive-history-20261106
git switch -c restored-snapshot COMMIT_FROM_REFS_JSON
```

В `refs.json` сохранены исходные имена и хеши 293 старых резервных веток.
Все снимки доступны через родителей архивного коммита. Для восстановления
используйте команды выше, подставив выбранный хеш. Архив не является рабочей
версией языка; он сохраняет историю при очистке списка веток.
