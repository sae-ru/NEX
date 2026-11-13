import Cocoa
import UniformTypeIdentifiers
import WebKit

final class BundleHandler: NSObject, WKURLSchemeHandler {
    let root: URL
    init(root: URL) { self.root = root.standardizedFileURL; super.init() }
    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        func finish(_ code: Int, _ data: Data = Data(), _ mime: String = "text/plain") {
            let response = HTTPURLResponse(url: task.request.url!, statusCode: code, httpVersion: "HTTP/1.1",
                                           headerFields: ["Content-Type": mime])!
            task.didReceive(response); task.didReceive(data); task.didFinish()
        }
        guard let url = task.request.url, let decoded = url.path.removingPercentEncoding else { return finish(400) }
        let relative = decoded == "/" ? "index.html" : String(decoded.dropFirst())
        let file = root.appendingPathComponent(relative).standardizedFileURL
        guard file.path == root.path || file.path.hasPrefix(root.path + "/") else { return finish(403) }
        guard let data = try? Data(contentsOf: file) else { return finish(404) }
        let type = UTType(filenameExtension: file.pathExtension)?.preferredMIMEType ?? "application/octet-stream"
        finish(200, data, type)
    }
    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {}
}

final class Delegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var web: WKWebView!
    func applicationDidFinishLaunching(_ note: Notification) {
        let rect = NSRect(x: 0, y: 0, width: 1100, height: 820)
        window = NSWindow(contentRect: rect, styleMask: [.titled, .closable, .resizable, .miniaturizable],
                          backing: .buffered, defer: false)
        window.title = "NEX Desktop 0.243"
        window.center()
        let config = WKWebViewConfiguration()
        let root = Bundle.main.resourceURL!.appendingPathComponent("web")
        config.setURLSchemeHandler(BundleHandler(root: root), forURLScheme: "nex")
        web = WKWebView(frame: rect, configuration: config)
        web.navigationDelegate = self
        window.contentView = web
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        web.load(URLRequest(url: URL(string: "nex://app/index.html")!))
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
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        fputs("navigation failed: \(error)\n", stderr)
    }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        fputs("provisional navigation failed: \(error)\n", stderr)
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

let app = NSApplication.shared
let delegate = Delegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
