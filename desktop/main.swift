// 每日一卦 · 原生 macOS 外壳
// 用 WKWebView 承载本地网页，Python 只做本地数据服务；关窗即退出并停止服务。
import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    private let appName = "每日一卦"
    private let preferredPort = 5288

    private var window: NSWindow!
    private var container: NSView!
    private var webView: WKWebView!
    private var overlay: NSView?
    private var server: Process?
    private var stdoutPipe: Pipe?
    private var stderrPipe: Pipe?
    private var logHandle: FileHandle?
    private var outBuffer = ""
    private var appURL: URL?
    private var hasFailed = false
    private var terminating = false

    private var resources: URL { Bundle.main.resourceURL! }
    private var serverScript: URL { resources.appendingPathComponent("app/server.py") }
    private var engineRoot: URL { resources.appendingPathComponent("自动化任务", isDirectory: true) }
    private var dataDir: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        return base.appendingPathComponent(appName, isDirectory: true)
    }
    private var logURL: URL { dataDir.appendingPathComponent("desktop.log") }

    // MARK: - 生命周期 -------------------------------------------------------
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        buildMenu()
        setupWindow()
        seedProfile()
        startServer()
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        terminating = true
        stopServer()
        try? logHandle?.close()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { window?.makeKeyAndOrderFront(nil) }
        return true
    }

    // MARK: - 窗口与网页 -----------------------------------------------------
    private func setupWindow() {
        let bg = NSColor(srgbRed: 0.043, green: 0.050, blue: 0.047, alpha: 1)

        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        config.applicationNameForUserAgent = "YiguaDesktop/1.0"
        webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.translatesAutoresizingMaskIntoConstraints = false
        webView.setValue(false, forKey: "drawsBackground")
        if #available(macOS 12.0, *) { webView.underPageBackgroundColor = bg }
        if #available(macOS 13.3, *) { webView.isInspectable = true }

        container = NSView(frame: NSRect(x: 0, y: 0, width: 1280, height: 860))
        container.wantsLayer = true
        container.layer?.backgroundColor = bg.cgColor
        container.addSubview(webView)
        NSLayoutConstraint.activate([
            webView.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            webView.topAnchor.constraint(equalTo: container.topAnchor),
            webView.bottomAnchor.constraint(equalTo: container.bottomAnchor),
        ])

        let style: NSWindow.StyleMask = [.titled, .closable, .miniaturizable, .resizable]
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 860),
                          styleMask: style, backing: .buffered, defer: false)
        window.contentView = container
        window.title = appName
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.backgroundColor = bg
        window.appearance = NSAppearance(named: .darkAqua)
        window.minSize = NSSize(width: 960, height: 640)
        window.isReleasedWhenClosed = false

        let visible = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        window.setContentSize(NSSize(width: min(1280, visible.width - 40),
                                     height: min(900, visible.height - 40)))
        window.center()
        window.setFrameAutosaveName("YiguaDesktopWindowV2")
        window.makeKeyAndOrderFront(nil)

        addLoadingOverlay()
    }

    private func addLoadingOverlay() {
        let bg = NSColor(srgbRed: 0.043, green: 0.050, blue: 0.047, alpha: 1)
        let view = NSView()
        view.translatesAutoresizingMaskIntoConstraints = false
        view.wantsLayer = true
        view.layer?.backgroundColor = bg.cgColor

        let title = NSTextField(labelWithString: appName)
        title.font = NSFont(name: "Songti SC", size: 34) ?? NSFont.systemFont(ofSize: 34, weight: .medium)
        title.textColor = NSColor(srgbRed: 0.90, green: 0.87, blue: 0.79, alpha: 1)

        let spinner = NSProgressIndicator()
        spinner.style = .spinning
        spinner.controlSize = .small
        spinner.startAnimation(nil)

        let sub = NSTextField(labelWithString: "正在起卦…")
        sub.font = NSFont(name: "Kaiti SC", size: 13) ?? NSFont.systemFont(ofSize: 13)
        sub.textColor = NSColor(srgbRed: 0.72, green: 0.64, blue: 0.40, alpha: 0.9)

        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .centerX
        stack.spacing = 12
        stack.addArrangedSubview(title)
        stack.addArrangedSubview(spinner)
        stack.addArrangedSubview(sub)
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: view.centerYAnchor),
        ])
        container.addSubview(view)
        NSLayoutConstraint.activate([
            view.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            view.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            view.topAnchor.constraint(equalTo: container.topAnchor),
            view.bottomAnchor.constraint(equalTo: container.bottomAnchor),
        ])
        overlay = view
    }

    private func removeOverlay() {
        guard let overlay else { return }
        self.overlay = nil
        NSAnimationContext.runAnimationGroup({ ctx in
            ctx.duration = 0.25
            overlay.animator().alphaValue = 0
        }, completionHandler: {
            overlay.removeFromSuperview()
        })
    }

    private func seedProfile() {
        try? FileManager.default.createDirectory(at: dataDir, withIntermediateDirectories: true)
        let dest = dataDir.appendingPathComponent("profile.json")
        guard !FileManager.default.fileExists(atPath: dest.path) else { return }
        guard let seed = Bundle.main.url(forResource: "seed-profile", withExtension: "json") else { return }
        try? FileManager.default.copyItem(at: seed, to: dest)
    }

    // MARK: - 本地服务 -------------------------------------------------------
    private func resolvePython() -> URL? {
        var candidates: [String] = []
        let cfg = resources.appendingPathComponent("python-path.txt")
        if let raw = try? String(contentsOf: cfg, encoding: .utf8) {
            let path = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            if !path.isEmpty { candidates.append(path) }
        }
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        candidates += [
            "\(home)/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3",
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python3",
        ]
        for path in candidates where FileManager.default.isExecutableFile(atPath: path) {
            return URL(fileURLWithPath: path)
        }
        return nil
    }

    private func prepareLog() {
        try? FileManager.default.createDirectory(at: dataDir, withIntermediateDirectories: true)
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        logHandle = try? FileHandle(forWritingTo: logURL)
    }

    private func appendLog(_ data: Data) {
        try? logHandle?.write(contentsOf: data)
    }

    private func startServer() {
        guard server == nil, !hasFailed else { return }
        guard FileManager.default.fileExists(atPath: serverScript.path) else {
            fail("应用资源不完整：找不到 \(serverScript.path)。")
            return
        }
        guard FileManager.default.fileExists(atPath: engineRoot.appendingPathComponent("engine/report.py").path) else {
            fail("应用资源不完整：找不到运势引擎。")
            return
        }
        guard let python = resolvePython() else {
            fail("找不到可用的 Python 3。请重新构建桌面版，或安装 Python 3.10+。")
            return
        }
        prepareLog()

        let proc = Process()
        proc.executableURL = python
        proc.arguments = [serverScript.path, "--port", String(preferredPort), "--no-open"]
        proc.currentDirectoryURL = resources
        var env = ProcessInfo.processInfo.environment
        env["FORTUNE_ENGINE_ROOT"] = engineRoot.path
        env["FORTUNE_DATA_DIR"] = dataDir.path
        env["FORTUNE_PARENT_PID"] = String(ProcessInfo.processInfo.processIdentifier)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        proc.environment = env

        let out = Pipe()
        let err = Pipe()
        proc.standardOutput = out
        proc.standardError = err
        proc.standardInput = FileHandle.nullDevice

        out.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            self?.appendLog(data)
            if let text = String(data: data, encoding: .utf8) {
                DispatchQueue.main.async { self?.consumeStdout(text) }
            }
        }
        err.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            self?.appendLog(data)
        }
        proc.terminationHandler = { [weak self] process in
            DispatchQueue.main.async { self?.serverExited(process) }
        }

        do {
            try proc.run()
        } catch {
            fail("无法启动本地服务：\(error.localizedDescription)")
            return
        }
        server = proc
        stdoutPipe = out
        stderrPipe = err

        DispatchQueue.main.asyncAfter(deadline: .now() + 15) { [weak self] in
            guard let self, self.appURL == nil, !self.hasFailed, !self.terminating else { return }
            self.fail("本地服务启动超时。请查看运行日志了解原因。")
        }
    }

    private func consumeStdout(_ text: String) {
        outBuffer += text
        if outBuffer.count > 12000 { outBuffer = String(outBuffer.suffix(6000)) }
        guard appURL == nil else { return }
        guard let range = outBuffer.range(of: #"http://127\.0\.0\.1:\d+/"#, options: .regularExpression) else { return }
        let address = String(outBuffer[range])
        guard let url = URL(string: address) else { return }
        appURL = url
        waitForHealth(url)
    }

    private func waitForHealth(_ base: URL, attempt: Int = 0) {
        var request = URLRequest(url: base.appendingPathComponent("api/health"))
        request.timeoutInterval = 1.5
        request.cachePolicy = .reloadIgnoringLocalCacheData
        URLSession.shared.dataTask(with: request) { [weak self] _, response, _ in
            guard let self else { return }
            if let http = response as? HTTPURLResponse, http.statusCode == 200 {
                DispatchQueue.main.async {
                    self.appendLog(Data("desktop: loading \(base.absoluteString)\n".utf8))
                    self.webView.load(URLRequest(url: base))
                }
            } else if attempt < 40 {
                DispatchQueue.global().asyncAfter(deadline: .now() + 0.25) {
                    self.waitForHealth(base, attempt: attempt + 1)
                }
            } else {
                DispatchQueue.main.async { self.fail("本地服务已启动，但健康检查没有通过。") }
            }
        }.resume()
    }

    private func serverExited(_ process: Process) {
        stdoutPipe?.fileHandleForReading.readabilityHandler = nil
        stderrPipe?.fileHandleForReading.readabilityHandler = nil
        server = nil
        if terminating { return }
        if appURL == nil {
            fail("本地服务没有启动成功。")
        } else if !hasFailed {
            fail("本地服务已退出。重新打开应用即可恢复。")
        }
    }

    private func stopServer() {
        guard let proc = server else { return }
        proc.terminationHandler = nil
        if proc.isRunning { proc.terminate() }
        server = nil
    }

    private func fail(_ message: String) {
        guard !hasFailed else { return }
        hasFailed = true
        let tail: String
        if let text = try? String(contentsOf: logURL, encoding: .utf8) {
            tail = String(text.suffix(1800))
        } else {
            tail = ""
        }
        let alert = NSAlert()
        alert.alertStyle = .critical
        alert.messageText = appName
        alert.informativeText = message + (tail.isEmpty ? "" : "\n\n—— 日志 ——\n" + tail)
        alert.addButton(withTitle: "打开日志")
        alert.addButton(withTitle: "退出")
        if alert.runModal() == .alertFirstButtonReturn {
            NSWorkspace.shared.open(logURL)
        }
        NSApp.terminate(nil)
    }

    // MARK: - 网页回调 -------------------------------------------------------
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        removeOverlay()
        if let content = window.contentView {
            appendLog(Data("desktop: window=\(window.frame.size) content=\(content.bounds.size) web=\(webView.frame.size)\n".utf8))
        }
        window.title = webView.title?.isEmpty == false ? webView.title! : appName
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        let ns = error as NSError
        if ns.code == NSURLErrorCancelled { return }
        fail("页面加载失败：\(error.localizedDescription)")
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let ns = error as NSError
        if ns.code == NSURLErrorCancelled { return }
        fail("页面加载失败：\(error.localizedDescription)")
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.allow); return }
        if let scheme = url.scheme, scheme == "http" || scheme == "https" {
            if let host = url.host, host == "127.0.0.1" || host == "localhost" {
                decisionHandler(.allow)
            } else {
                NSWorkspace.shared.open(url)
                decisionHandler(.cancel)
            }
            return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url { NSWorkspace.shared.open(url) }
        return nil
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = appName
        alert.informativeText = message
        alert.addButton(withTitle: "好")
        alert.beginSheetModal(for: window) { _ in completionHandler() }
    }

    // MARK: - 菜单 -----------------------------------------------------------
    @discardableResult
    private func add(_ menu: NSMenu, _ title: String, _ action: Selector, _ key: String = "",
                     _ mask: NSEvent.ModifierFlags = .command) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: key)
        item.keyEquivalentModifierMask = mask
        item.target = self
        menu.addItem(item)
        return item
    }

    private func buildMenu() {
        let main = NSMenu()

        let appItem = NSMenuItem()
        main.addItem(appItem)
        let appMenu = NSMenu(title: appName)
        appMenu.addItem(withTitle: "关于每日一卦",
                        action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)),
                        keyEquivalent: "")
        appMenu.addItem(.separator())
        add(appMenu, "设置…", #selector(openSettings), ",")
        appMenu.addItem(withTitle: "隐藏每日一卦", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let hideOthers = NSMenuItem(title: "隐藏其他", action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        hideOthers.keyEquivalentModifierMask = [.command, .option]
        appMenu.addItem(hideOthers)
        appMenu.addItem(withTitle: "显示全部", action: #selector(NSApplication.unhideAllApplications(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "退出每日一卦", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu

        let editItem = NSMenuItem()
        main.addItem(editItem)
        let edit = NSMenu(title: "编辑")
        edit.addItem(withTitle: "撤销", action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: "重做", action: Selector(("redo:")), keyEquivalent: "Z")
        edit.addItem(.separator())
        edit.addItem(withTitle: "剪切", action: Selector(("cut:")), keyEquivalent: "x")
        edit.addItem(withTitle: "拷贝", action: Selector(("copy:")), keyEquivalent: "c")
        edit.addItem(withTitle: "粘贴", action: Selector(("paste:")), keyEquivalent: "v")
        edit.addItem(withTitle: "全选", action: Selector(("selectAll:")), keyEquivalent: "a")
        editItem.submenu = edit

        let viewItem = NSMenuItem()
        main.addItem(viewItem)
        let view = NSMenu(title: "显示")
        add(view, "重新载入", #selector(reloadPage), "r")
        add(view, "起卦", #selector(castNow), "\r")
        add(view, "跳到今日卦", #selector(jumpToReading), "j")
        view.addItem(.separator())
        add(view, "放大", #selector(zoomIn), "+")
        add(view, "缩小", #selector(zoomOut), "-")
        add(view, "实际大小", #selector(actualSize), "0")
        view.addItem(.separator())
        add(view, "进入全屏", #selector(toggleFullScreen), "f", [.command, .control])
        viewItem.submenu = view

        let windowItem = NSMenuItem()
        main.addItem(windowItem)
        let windowMenu = NSMenu(title: "窗口")
        windowMenu.addItem(withTitle: "最小化", action: Selector(("performMiniaturize:")), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "缩放", action: Selector(("performZoom:")), keyEquivalent: "")
        windowMenu.addItem(.separator())
        windowMenu.addItem(withTitle: "前置全部窗口", action: Selector(("arrangeInFront:")), keyEquivalent: "")
        windowItem.submenu = windowMenu
        NSApp.windowsMenu = windowMenu

        let helpItem = NSMenuItem()
        main.addItem(helpItem)
        let help = NSMenu(title: "帮助")
        add(help, "打开数据目录", #selector(openDataDir), "")
        add(help, "打开运行日志", #selector(openLog), "")
        help.addItem(.separator())
        add(help, "重新启动本地服务", #selector(restartServer), "")
        helpItem.submenu = help
        NSApp.helpMenu = help

        NSApp.mainMenu = main
    }

    @objc private func reloadPage() {
        if webView.url != nil { webView.reload() } else { startServer() }
    }
    @objc private func openSettings() {
        webView.evaluateJavaScript("document.querySelector('.nav-btn[data-view=settings]')?.click()") { _, _ in }
    }
    @objc private func castNow() {
        webView.evaluateJavaScript("document.querySelector('#cast-btn')?.click()") { _, _ in }
    }
    @objc private func jumpToReading() {
        webView.evaluateJavaScript("document.querySelector('#reading')?.scrollIntoView({behavior:'smooth', block:'start'})") { _, _ in }
    }
    @objc private func zoomIn() { webView.pageZoom = min(2.0, webView.pageZoom + 0.1) }
    @objc private func zoomOut() { webView.pageZoom = max(0.7, webView.pageZoom - 0.1) }
    @objc private func actualSize() { webView.pageZoom = 1.0 }
    @objc private func toggleFullScreen() { window.toggleFullScreen(nil) }

    @objc private func openDataDir() {
        try? FileManager.default.createDirectory(at: dataDir, withIntermediateDirectories: true)
        NSWorkspace.shared.open(dataDir)
    }

    @objc private func openLog() {
        if FileManager.default.fileExists(atPath: logURL.path) {
            NSWorkspace.shared.open(logURL)
        } else {
            let alert = NSAlert()
            alert.messageText = appName
            alert.informativeText = "还没有运行日志。"
            alert.addButton(withTitle: "好")
            alert.runModal()
        }
    }

    @objc private func restartServer() {
        guard !hasFailed else { return }
        stopServer()
        appURL = nil
        outBuffer = ""
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { [weak self] in
            self?.startServer()
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
