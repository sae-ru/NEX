# Traits in a generated API client

Run these commands from this example directory with a matching NEX SDK:

```sh
nex check --json
nex test --json
nex api --directory generated --json
cp client.nex generated/client/consumer.nex
cd generated/client
nex test consumer.nex --json
nex test consumer.nex --target web --json
```

Use the generated client's manifest and frozen dependency roots. `client.nex` is
a consumer template to copy after generation, not the service entry point.
The public library contract supplies an associated wire type and a real shared
getter. The generated client retains the getter and its private implementation;
the server-only audit member, binding and sentinel body are excluded. Its typed
request preserves `Envelope<Box<i64>>` identity and exact i64 wire encoding.
The example constructs request commands; it performs no browser network request
or server authorization. Supply credentials through runtime configuration.
