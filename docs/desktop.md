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

This is not a complete desktop UI toolkit: native menus, a native widget
toolkit, notarization/signing and distribution remain pending.
