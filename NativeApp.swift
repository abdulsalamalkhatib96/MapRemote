import AppKit
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var child: Process?
    var closing = false
    func alert(_ message: String) {
        let a = NSAlert(); a.messageText = "MapRemote"; a.informativeText = message; a.runModal()
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        let main = NSMenu(); let item = NSMenuItem(); main.addItem(item)
        let menu = NSMenu(); menu.addItem(withTitle: "Quit MapRemote", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"); item.submenu = menu; NSApp.mainMenu = main
        let editItem = NSMenuItem(); main.addItem(editItem); let edit = NSMenu(title: "Edit"); editItem.submenu = edit
        for (title, selector, key) in [("Undo", "undo:", "z"), ("Cut", "cut:", "x"), ("Copy", "copy:", "c"), ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")] { edit.addItem(withTitle: title, action: NSSelectorFromString(selector), keyEquivalent: key) }
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1100, height: 790), styleMask: [.titled,.closable,.miniaturizable,.resizable], backing: .buffered, defer: false)
        window.title = "MapRemote"; window.minSize = NSSize(width: 650, height: 480); window.center(); window.delegate = self
        let configuration = WKWebViewConfiguration(); configuration.websiteDataStore = .nonPersistent()
        web = WKWebView(frame: .zero, configuration: configuration); web.navigationDelegate = self; web.uiDelegate = self; window.contentView = web
        window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        guard let resources = Bundle.main.resourceURL else { alert("Missing resources."); NSApp.terminate(nil); return }
        let candidates = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
        guard let python = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0) }) else { alert("Install Python 3 with Homebrew (brew install python)."); NSApp.terminate(nil); return }
        let p = Process(); p.executableURL = URL(fileURLWithPath: python); p.arguments = [resources.appendingPathComponent("app.py").path]
        var env = ProcessInfo.processInfo.environment; env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"; env["MAPREMOTE_NATIVE"] = "1"; env["MAPREMOTE_PARENT_PID"] = String(ProcessInfo.processInfo.processIdentifier); p.environment = env
        let pipe = Pipe(); p.standardOutput = pipe; p.standardError = FileHandle.nullDevice; child = p
        p.terminationHandler = { [weak self] process in DispatchQueue.main.async { guard let self = self, !self.closing else { return }; if process.terminationStatus != 0 { self.alert("The local controller stopped. Close and reopen MapRemote. If network recovery is needed, use Recover network settings.") }; NSApp.terminate(nil) } }
        do { try p.run() } catch { alert(error.localizedDescription); NSApp.terminate(nil); return }
        DispatchQueue.global().async { [weak self] in
            var data = Data(); let handle = pipe.fileHandleForReading
            while data.count < 4096 {
                let b = handle.readData(ofLength: 1); if b.isEmpty || b.first == 10 { break }; data.append(b)
            }
            let line = String(data: data, encoding: .utf8) ?? ""
            DispatchQueue.main.async {
                guard let self = self, !self.closing, line.hasPrefix("MapRemote: "), let url = URL(string: String(line.dropFirst(11))), url.host == "127.0.0.1" else { return }
                self.web.load(URLRequest(url: url))
            }
        }
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if navigationAction.request.url?.host == "127.0.0.1" { decisionHandler(.allow) } else { decisionHandler(.cancel) }
    }
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert(); a.messageText = message; a.addButton(withTitle: "Continue"); a.addButton(withTitle: "Cancel"); completionHandler(a.runModal() == .alertFirstButtonReturn)
    }
    func windowWillClose(_ notification: Notification) { NSApp.terminate(nil) }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if closing { return .terminateLater }; closing = true
        guard let p = child, p.isRunning else { return .terminateNow }
        p.terminate()
        DispatchQueue.global().async { p.waitUntilExit(); DispatchQueue.main.async { sender.reply(toApplicationShouldTerminate: true) } }
        return .terminateLater
    }
}
let app = NSApplication.shared
let delegate = AppDelegate(); app.delegate = delegate; app.setActivationPolicy(.regular); app.run()
