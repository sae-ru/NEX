# Native desktop host

The experimental macOS host in `experiments/desktop-macos` wraps a checked NEX
browser build in an AppKit `WKWebView`. It renders the same state/update/view
application as the browser and mobile hosts without a second UI language.

Current 0.244.0 receipt: the web dist is embedded under
`Contents/Resources/web`, served to `WKWebView` through an application-local
`nex://app/` scheme handler, and the standalone `.app` renders the actual NEX
Tasks UI without an external HTTP server
([receipt](evidence/desktop-macos-bundle-0.244.0-2026-11-13.json)). The host
builds with `experiments/desktop-macos/build.sh`.

A local [signed bundle receipt](evidence/desktop-macos-signed-0.244.0-2026-11-13.json)
ad-hoc signs, verifies and zips the app and renders the actual UI. `codesign`
verification passes, but `spctl` rejects it for distribution because it has no
Developer ID signature or notarization. This is not a complete desktop UI
toolkit: native menus, a native widget toolkit, Developer ID signing,
notarization and external distribution remain pending. A
[desktop interaction receipt](evidence/desktop-macos-interaction-0.244.0-2026-11-13.json)
drives the live text input and Add task button in the standalone app, changing
the actual UI from 1 to 2 active tasks.
