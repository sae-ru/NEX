import Cocoa
import WebKit

final class Delegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var web: WKWebView!
    func applicationDidFinishLaunching(_ note: Notification) {
        let rect = NSRect(x: 0, y: 0, width: 1100, height: 820)
        window = NSWindow(contentRect: rect, styleMask: [.titled, .closable, .resizable, .miniaturizable],
                          backing: .buffered, defer: false)
        window.title = "NEX Desktop 0.243"
        window.center()
        web = WKWebView(frame: rect)
        web.navigationDelegate = self
        window.contentView = web
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        let url = ProcessInfo.processInfo.environment["NEX_DESKTOP_URL"] ?? "http://127.0.0.1:8765/"
        web.load(URLRequest(url: URL(string: url)!))
    }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard let path = ProcessInfo.processInfo.environment["NEX_DESKTOP_SNAPSHOT"] else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
        webView.takeSnapshot(with: nil) { image, error in
            if let image = image, let data = image.tiffRepresentation,
               let rep = NSBitmapImageRep(data: data), let png = rep.representation(using: .png, properties: [:]) {
                try? png.write(to: URL(fileURLWithPath: path))
            }
            NSApp.terminate(nil)
        }
        }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

let app = NSApplication.shared
let delegate = Delegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
