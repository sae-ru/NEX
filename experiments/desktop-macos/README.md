# NEX desktop macOS host (experimental)

Minimal AppKit `WKWebView` host for a checked NEX browser build. It proves the
same NEX state/update/view application renders in a native macOS window; it is
not a full desktop UI toolkit or a packaging/signing workflow.

```sh
# build the browser dist and serve it locally
nex build path/to/main.nex --target web -o /tmp/nex-desktop-web --profile release --json
python3 -m http.server 8765 --directory /tmp/nex-desktop-web
# build and run the host
mkdir -p build/App.app/Contents/MacOS
cp experiments/desktop-macos/Info.plist build/App.app/Contents/Info.plist
xcrun swiftc -O -framework Cocoa -framework WebKit experiments/desktop-macos/main.swift \
  -o build/App.app/Contents/MacOS/NEXDesktop
NEX_DESKTOP_SNAPSHOT=/tmp/desktop.png build/App.app/Contents/MacOS/NEXDesktop
```

`NEX_DESKTOP_URL` selects another local URL. The snapshot hook waits for the
WebView navigation and writes the rendered UI; it exists for evidence only.
Native menus, packaging, notarization, signing, distribution and a bundled HTTP
server remain pending.
