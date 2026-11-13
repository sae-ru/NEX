# Native desktop host

The experimental macOS host in `experiments/desktop-macos` wraps a checked NEX
browser build in an AppKit `WKWebView`. It renders the same state/update/view
application as the browser and mobile hosts without a second UI language.

Current 0.243.0 receipt: the NEX Tasks web build was served locally, the Swift
host built with `swiftc`, and its `WKWebView` snapshot shows the actual UI
([receipt](evidence/desktop-macos-0.243.0-2026-11-13.json)).

This is not a complete desktop UI toolkit: native menus, application packaging,
a bundled HTTP server, notarization/signing and distribution remain pending.
