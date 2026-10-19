# Native iOS library example

`main.nex` exposes a pure scalar `answer() -> i64` returning42 and exercises
Unicode scalar length. Run its source tests on the current host:

```sh
nex test main.nex --json
nex test main.nex --target web --json
```

Read `docs/ios.md` for explicit SDK/target configuration, then build:

```sh
nex build main.nex --library --entry answer --profile release \
  --toolchain /actual/path/ios-device.json --json
nex context --symbol answer --json
```

Use the reported library and native symbol in a host with the same target and
SDK. The example produces a static library; the app wrapper, installation and
execution on iPhone/iPad or a simulator are still pending.
