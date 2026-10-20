# Explicit HTTPS API hosting — toolchain0.63 candidate

NEX commands retain bounded relative `/api/` paths. The deployment operator
selects one HTTPS API origin when generating a mobile project:

```sh
python3 /sdk/share/nex/tools/mobile_project.py /project/client.nex \
  --nex /sdk/bin/nex --directory /new/mobile --platform both \
  --app-id dev.example.app --name "Example" --artifact-cache /cache/frameworks \
  --api-origin https://api.example.test
```

The origin must be canonical lowercase `https://HOST[:PORT]`, without a slash,
path, query, fragment, credentials, default port443 or leading-zero port. ASCII
DNS labels and canonical IPv4 are supported; international hostnames must use
their ASCII form. IPv6 literals are pending. Local origins require an explicitly
trusted TLS certificate too. No insecure TLS override is added.

The helper adds one escaped `meta[name=nex-api-origin]` to the built index and
records its original and configured SHA256 in `host_configuration`. Every final
web asset is hashed and byte-checked against both native projects. The original
compiler build result remains the identity before this recorded host derivation.
Without the option the index is unchanged. The browser adapter rejects duplicate
or invalid metadata before dispatching commands; checked View values cannot
construct meta/script elements. Host metadata and assets are trusted deployment
inputs, never an application-supplied request destination or credential store.

The adapter resolves commands against the configured origin and uses ordinary
browser fetch with `mode:cors`. It retains omitted cookie credentials, rejected
redirects, a 1MiB streaming response limit, strict UTF-8, endpoint schema checks,
AbortController, timeout and at-most-once response delivery. Runtime tokens stay
in memory in the example. Never put a token in NEX source, a meta tag, a build
argument or static assets. Browser CORS failures have the same bounded generic
`E_NETWORK` outcome as other transport failures. Cancellation/timeouts do not
prove that a mutation was rolled back; refresh durable state before retrying.

Start the matching native NEX server with its TLS key/certificate, private auth
file and database, granting only the mobile application origins:

```sh
SERVER --auth /private/auth.json --database /private/data.sqlite \
  --cert /private/server.pem --key /private/server-key.pem \
  --cors-origin capacitor://localhost --cors-origin https://localhost
```

Capacitor's default iOS application origin is `capacitor://localhost`; Android
uses `https://localhost`. These defaults come from the pinned host configuration,
not unique application identities. CORS does not identify an installed app or
user. Bearer authentication and server-injected principal partitions remain
mandatory; possession of an allowed Origin alone grants no data access.

The repeated server option allows at most16 distinct exact origins: the local
Capacitor origin or lowercase HTTP(S) origins with ASCII host labels and optional
nondefault port. No wildcards, `null`, credentials, paths, trailing slash or IPv6
literals are accepted. Explicit HTTP origins may support a local browser during
development; the mobile API destination still requires HTTPS. Same-origin calls
remain usable when the remote allowlist is enabled. Requests without Origin
retain normal authentication. Approved preflight accepts only the seven request
methods and Authorization/Content-Type headers, returns204 without entering NEX
or storage, and grants no cookie credentials. Denied origins cannot reach a NEX
handler. Allowed-origin authentication and application errors retain CORS headers.

Native compilation, network execution and mobile UI execution are separate
checks. The0.62 state-only mobile UI evidence does not establish0.63 remote API
support. This candidate's full acceptance remains pending until recorded with
its exact source, compiler, native application and server identities.

From a source checkout, the opt-in `tests/mobile_api_browser.py COMPILER
GENERATED_FULLSTACK_PROJECT --output NEW_DIRECTORY --browsers-path CACHE`
checks the separately hosted production client against a real HTTPS native API
in Chromium, Firefox and WebKit. Its temporary certificate is accepted only in
the owned test browser contexts; it checks fetch/CORS and application semantics,
not production certificate deployment. Output contains private ephemeral test
credentials and TLS keys and must not be published as a source artifact.
