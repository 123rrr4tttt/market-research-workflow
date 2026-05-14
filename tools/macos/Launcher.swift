import SwiftUI
import AppKit
import Foundation

enum LauncherConfig {
    static let repoPath = "/Users/wangyiliang/market-research-workflow"
}

struct CodexBootstrapEnvelope: Decodable {
    let data: CodexBootstrapData?
}

struct CodexBootstrapData: Decodable {
    let authenticated: Bool
    let codex_cli_installed: Bool?
    let install_attempted: Bool?
    let install_succeeded: Bool?
    let device_url: String?
    let device_code: String?
    let hint: String?
}

func bootstrapCodexAuth(completion: @escaping (Result<CodexBootstrapData, Error>) -> Void) {
    guard let url = URL(string: "http://localhost:8000/api/v1/codex-auth/cli/bootstrap") else {
        completion(.failure(URLError(.badURL)))
        return
    }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.httpBody = Data("{}".utf8)

    URLSession.shared.dataTask(with: request) { data, _, error in
        if let error {
            completion(.failure(error))
            return
        }
        guard let data else {
            completion(.failure(URLError(.badServerResponse)))
            return
        }
        do {
            let envelope = try JSONDecoder().decode(CodexBootstrapEnvelope.self, from: data)
            if let payload = envelope.data {
                completion(.success(payload))
            } else {
                completion(.failure(URLError(.cannotParseResponse)))
            }
        } catch {
            completion(.failure(error))
        }
    }.resume()
}

@main
struct MarketResearchLauncherApp: App {
    var body: some Scene {
        WindowGroup {
            LauncherView()
                .frame(width: 700, height: 780)
        }
        .windowStyle(.hiddenTitleBar)
    }
}

struct LauncherView: View {
    @State private var status = "Ready"
    @State private var lastAction = "Choose a run mode"
    @State private var checks: [ServiceCheck] = ServiceCheck.placeholder
    @State private var lastRefresh = "Not refreshed yet"
    @State private var isRefreshing = false
    @State private var enableSearXNG = false
    @State private var enableYaCy = false
    @State private var enableLanceDB = false
    @State private var showSettingsSheet = false
    private let refreshTimer = Timer.publish(every: 15, on: .main, in: .common).autoconnect()

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [Color(red: 0.08, green: 0.11, blue: 0.16), Color(red: 0.13, green: 0.18, blue: 0.23)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    header
                    overviewPanel
                    runModes
                    optionalEnhancementsPanel
                    externalServicesPanel
                    monitorPanel
                    Divider().overlay(Color.white.opacity(0.12))
                    utilityGrid
                    footer
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(28)
            }
        }
        .onAppear {
            refreshMonitor()
        }
        .onReceive(refreshTimer) { _ in
            refreshMonitor()
        }
        .sheet(isPresented: $showSettingsSheet) {
            SettingsEditorView(repoPath: LauncherConfig.repoPath) {
                showSettingsSheet = false
                refreshMonitor()
            }
            .frame(width: 760, height: 680)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 10)
                        .fill(Color.cyan.opacity(0.18))
                        .frame(width: 42, height: 42)
                    Image(systemName: "chart.xyaxis.line")
                        .font(.system(size: 22, weight: .semibold))
                        .foregroundStyle(.cyan)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text("Market Research Workflow")
                        .font(.system(size: 23, weight: .semibold))
                        .foregroundStyle(.white)
                    Text(lastAction)
                        .font(.system(size: 13))
                        .foregroundStyle(.white.opacity(0.62))
                }
                Spacer()
                Button(action: refreshMonitor) {
                    HStack(spacing: 6) {
                        Image(systemName: "arrow.clockwise")
                            .font(.system(size: 12, weight: .semibold))
                        Text("Refresh")
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .foregroundStyle(.white.opacity(0.9))
                    .padding(.horizontal, 11)
                    .frame(height: 30)
                    .background(Color.white.opacity(0.08))
                    .clipShape(Capsule())
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var overviewPanel: some View {
        let localCount = localRunningCount
        let healthState = check(id: "deep")?.state ?? .unknown
        let dockerDetail = check(id: "docker")?.detail ?? "Waiting"

        return VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center, spacing: 18) {
                RingGauge(
                    progress: Double(goodCheckCount) / Double(max(checks.count, 1)),
                    color: healthState == .bad ? .red : .cyan
                )
                VStack(alignment: .leading, spacing: 5) {
                    Text(runtimeTitle)
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(.white)
                    Text(runtimeSubtitle)
                        .font(.system(size: 12))
                        .foregroundStyle(.white.opacity(0.58))
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 6) {
                    MetricPill(title: "Local", value: "\(localCount)/3", color: localCount == 3 ? .green : .orange)
                    MetricPill(title: "Docker", value: dockerDetail.replacingOccurrences(of: " compose services", with: ""), color: (check(id: "docker")?.state.color ?? .gray))
                }
            }

            HStack(spacing: 8) {
                MiniHealthBar(title: "Backend", check: check(id: "backend"))
                MiniHealthBar(title: "Frontend", check: check(id: "frontend"))
                MiniHealthBar(title: "Worker", check: check(id: "worker"))
                MiniHealthBar(title: "API", check: check(id: "health"))
                MiniHealthBar(title: "DB/ES", check: check(id: "deep"))
            }
        }
        .padding(14)
        .background(
            LinearGradient(
                colors: [Color.white.opacity(0.10), Color.white.opacity(0.045)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(Color.white.opacity(0.12), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private var runModes: some View {
        return HStack(spacing: 12) {
            ActionCard(
                title: "Local",
                subtitle: "Backend + frontend + worker",
                icon: "laptopcomputer",
                tint: .cyan,
                statusText: localRunningCount == 3 ? "Running" : "\(localRunningCount)/3 online",
                statusColor: localRunningCount == 3 ? .green : .orange
            ) {
                runTerminalAction(
                    name: "Switch to Local",
                    command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/local-deploy.sh start --force"
                        + enhancementArgs
                )
            }

            ActionCard(
                title: "Docker",
                subtitle: "Open launcher first, then control services",
                icon: "shippingbox",
                tint: .orange,
                statusText: dockerStatusText,
                statusColor: check(id: "docker")?.state.color ?? .gray
            ) {
                runTerminalAction(
                    name: "Open Docker Launcher",
                    command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/docker-launcher-ui.sh"
                )
            }
        }
    }

    private var optionalEnhancementsPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("Optional Startup Enhancements", systemImage: "slider.horizontal.3")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(.white)
                Spacer()
                Text("Only starts when checked")
                    .font(.system(size: 11))
                    .foregroundStyle(.white.opacity(0.48))
            }
            HStack(spacing: 10) {
                EnhancementToggle(title: "SearXNG", subtitle: "External metasearch :8088", icon: "magnifyingglass", isOn: $enableSearXNG)
                EnhancementToggle(title: "YaCy", subtitle: "Local corpus search :8090", icon: "externaldrive.connected.to.line.below", isOn: $enableYaCy)
                EnhancementToggle(title: "LanceDB", subtitle: "Local index adapter", icon: "square.stack.3d.up", isOn: $enableLanceDB)
            }
        }
        .padding(12)
        .background(Color.black.opacity(0.16))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.white.opacity(0.10), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var utilityGrid: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
            SmallButton(title: "Stop Local", icon: "stop.fill") {
                runTerminalAction(name: "Stop Local", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/local-service-control.sh local-stop")
            }
            SmallButton(title: "Stop Docker", icon: "xmark.octagon.fill") {
                runTerminalAction(name: "Stop Docker App", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/docker-app-control.sh stop --with-search")
            }
            SmallButton(title: "Status", icon: "waveform.path.ecg") {
                runTerminalAction(name: "Status", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/local-deploy.sh status; echo; ./scripts/docker-deploy.sh status")
            }
            SmallButton(title: "Configure Keys", icon: "key.fill") {
                openSettingsUI()
            }
            SmallButton(title: "Service Doctor", icon: "stethoscope") {
                runTerminalAction(name: "Service Doctor", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/platform-macos.sh doctor")
            }
            SmallButton(title: "Reset Runtime", icon: "arrow.triangle.2.circlepath") {
                runTerminalAction(name: "Reset Runtime", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/local-service-control.sh local-stop || true; pkill -f 'codex app-server --listen ws://127.0.0.1:0' || true; ./scripts/docker-deploy.sh stop --profile modern-ui --profile search-enhancements || true")
            }
            SmallButton(title: "Frontend", icon: "safari.fill") {
                openURL("http://127.0.0.1:5173")
            }
            SmallButton(title: "Docker UI", icon: "globe") {
                openURL("http://127.0.0.1:5176")
            }
            SmallButton(title: "API Docs", icon: "doc.text.fill") {
                openURL("http://localhost:8000/docs")
            }
            SmallButton(title: "Codex Auth", icon: "person.crop.circle.badge.checkmark") {
                openCodexAuth()
            }
            SmallButton(title: "Repo", icon: "folder.fill") {
                NSWorkspace.shared.open(URL(fileURLWithPath: LauncherConfig.repoPath))
            }
        }
    }

    private var externalServicesPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 122), spacing: 8)], spacing: 8) {
                ExternalStatusPill(title: "Env", check: check(id: "env"))
                ExternalStatusPill(title: "LLM", check: check(id: "llm"))
                ExternalStatusPill(title: "Search", check: check(id: "search"))
                ExternalStatusPill(title: "SearXNG", check: check(id: "searxng"))
                ExternalStatusPill(title: "YaCy", check: check(id: "yacy"))
                ExternalStatusPill(title: "Ollama", check: check(id: "ollama"))
            }
            HStack(spacing: 10) {
                Button(action: {
                    openSettingsUI()
                }) {
                    Label("Configure", systemImage: "key.fill")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.92))
                        .padding(.horizontal, 11)
                        .frame(height: 30)
                        .background(Color.cyan.opacity(0.18))
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)
                Button(action: {
                    openSettingsUI()
                }) {
                    Label("Settings UI", systemImage: "slider.horizontal.3")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.92))
                        .padding(.horizontal, 11)
                        .frame(height: 30)
                        .background(Color.white.opacity(0.08))
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)
                Spacer()
                Button(action: { openURL("https://platform.openai.com/api-keys") }) {
                    Label("OpenAI", systemImage: "arrow.up.right.square")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.86))
                        .padding(.horizontal, 9)
                        .frame(height: 30)
                        .background(Color.white.opacity(0.055))
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)
                Button(action: { openURL("https://serper.dev/api-key") }) {
                    Label("Serper", systemImage: "arrow.up.right.square")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.86))
                        .padding(.horizontal, 9)
                        .frame(height: 30)
                        .background(Color.white.opacity(0.055))
                        .clipShape(Capsule())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(12)
        .background(Color.black.opacity(0.16))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.white.opacity(0.10), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var monitorPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("Runtime Monitor", systemImage: "gauge.with.dots.needle.bottom.100percent")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(.white)
                Spacer()
                HStack(spacing: 6) {
                    if isRefreshing {
                        ProgressView()
                            .controlSize(.small)
                            .scaleEffect(0.65)
                    }
                    Text(lastRefresh)
                        .font(.system(size: 11))
                        .foregroundStyle(.white.opacity(0.46))
                }
            }

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 9) {
                ForEach(checks) { check in
                    StatusTile(check: check, actionTitle: monitorActionTitle(for: check)) {
                        handleMonitorAction(check)
                    }
                }
            }
        }
        .padding(14)
        .background(Color.black.opacity(0.18))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.white.opacity(0.1), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var footer: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(status == "Ready" ? Color.green : Color.cyan)
                .frame(width: 8, height: 8)
            Text(status)
                .font(.system(size: 12))
                .foregroundStyle(.white.opacity(0.66))
            Spacer()
            Text("Terminal shows live logs")
                .font(.system(size: 12))
                .foregroundStyle(.white.opacity(0.45))
        }
    }

    private func runTerminalAction(name: String, command: String) {
        lastAction = name
        status = "Opening Terminal..."
        let wrapped = "clear; echo 'Market Research Workflow - \(name)'; echo; \(command); status=$?; echo; echo 'Exit status: '$status; echo 'Press any key to close this Terminal tab.'; read -n 1; exit $status"
        let script = """
        tell application "Terminal"
            activate
            do script \(appleScriptString(wrapped))
        end tell
        """
        var error: NSDictionary?
        NSAppleScript(source: script)?.executeAndReturnError(&error)
        if let error {
            status = "Terminal launch failed: \(error)"
        } else {
            status = "Command sent to Terminal"
            for delay in [2.0, 6.0, 12.0] {
                DispatchQueue.main.asyncAfter(deadline: .now() + delay) {
                    refreshMonitor()
                }
            }
        }
    }

    private func openURL(_ string: String) {
        lastAction = "Opening \(string)"
        status = "Opening browser..."
        if let url = URL(string: string) {
            NSWorkspace.shared.open(url)
            status = "Ready"
        }
    }

    private func openCodexAuth() {
        lastAction = "Opening Codex Auth"
        status = "Checking Codex auth..."
        bootstrapCodexAuth { result in
            DispatchQueue.main.async {
                switch result {
                case .success(let payload):
                    if payload.authenticated {
                        self.openURL(self.preferredFrontendURL())
                        self.status = "Codex already authenticated"
                        return
                    }
                    if let deviceURL = payload.device_url, let url = URL(string: deviceURL) {
                        NSWorkspace.shared.open(url)
                        let code = payload.device_code.map { " code \($0)" } ?? ""
                        self.status = "Complete Codex device auth\(code)"
                        return
                    }
                    self.status = "Codex auth unavailable: \(payload.hint ?? "no device URL returned")"
                case .failure(let error):
                    self.status = "Codex auth bootstrap failed: \(error.localizedDescription)"
                }
            }
        }
    }

    private func openSettingsUI() {
        lastAction = "Opening Settings UI"
        status = "Settings panel opened"
        showSettingsSheet = true
    }

    private func handleMonitorAction(_ check: ServiceCheck) {
        switch check.id {
        case "backend":
            if check.state == .good {
                runTerminalAction(name: "Stop Local Backend", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/local-service-control.sh backend-stop")
            } else {
                runTerminalAction(name: "Start Local Backend", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/local-service-control.sh backend-start")
            }
        case "frontend":
            if check.state == .good {
                runTerminalAction(name: "Stop Local Frontend", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/local-service-control.sh frontend-stop")
            } else {
                runTerminalAction(name: "Start Local Frontend", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/local-service-control.sh frontend-start")
            }
        case "worker":
            if check.state == .good {
                runTerminalAction(name: "Stop Local Worker", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/local-service-control.sh worker-stop")
            } else {
                runTerminalAction(name: "Start Local Worker", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/local-service-control.sh worker-start")
            }
        case "health", "deep":
            if check.state == .good {
                openURL("http://localhost:8000/docs")
            } else {
                runTerminalAction(name: "Start Local Backend", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/local-service-control.sh backend-start")
            }
        case "docker":
            if check.state == .good && !check.detail.hasPrefix("0 ") {
                runTerminalAction(name: "Stop Docker App", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/docker-app-control.sh stop --with-search")
            } else {
                runTerminalAction(name: "Open Docker Launcher", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/docker-launcher-ui.sh")
            }
        case "dockerLauncher":
            if check.state == .good {
                openURL("http://127.0.0.1:5176")
            } else {
                runTerminalAction(name: "Open Docker Launcher", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/docker-launcher-ui.sh")
            }
        case "searxng":
            if check.state == .good {
                runTerminalAction(name: "Stop SearXNG", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/optional-enhancements.sh stop --searxng")
            } else {
                runTerminalAction(name: "Start SearXNG", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/optional-enhancements.sh start --searxng")
            }
        case "yacy":
            if check.state == .good {
                runTerminalAction(name: "Stop YaCy", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/optional-enhancements.sh stop --yacy")
            } else {
                runTerminalAction(name: "Start YaCy", command: "cd \(shellQuote(LauncherConfig.repoPath)) || exit 1; ./scripts/optional-enhancements.sh start --yacy")
            }
        case "ollama":
            if check.state == .good {
                runTerminalAction(name: "Stop Ollama", command: "if command -v brew >/dev/null 2>&1; then brew services stop ollama || true; fi; pkill -f 'ollama serve' || true")
            } else {
                openURL("https://ollama.com/download")
            }
        case "env", "llm", "search":
            openSettingsUI()
        default:
            refreshMonitor()
        }
    }

    private func monitorActionTitle(for check: ServiceCheck) -> String {
        switch check.id {
        case "env", "llm", "search":
            return "Configure"
        case "ollama":
            return check.state == .good ? "Stop" : "Open"
        case "health", "deep":
            return check.state == .good ? "Open" : "Start"
        case "docker":
            return (check.state == .good && !check.detail.hasPrefix("0 ")) ? "Stop" : "Start"
        case "dockerLauncher":
            return check.state == .good ? "Open" : "Start"
        default:
            return check.state == .good ? "Stop" : "Start"
        }
    }

    private func refreshMonitor() {
        guard !isRefreshing else { return }
        isRefreshing = true
        runShell(monitorCommand()) { output in
            let nextChecks = parseMonitorOutput(output)
            DispatchQueue.main.async {
                if !nextChecks.isEmpty {
                    checks = nextChecks
                }
                lastRefresh = formattedRefreshTime()
                status = "Monitor refreshed"
                isRefreshing = false
            }
        }
    }

    private var goodCheckCount: Int {
        checks.filter { $0.state == .good }.count
    }

    private var localRunningCount: Int {
        ["backend", "frontend", "worker"].compactMap { check(id: $0) }.filter { $0.state == .good }.count
    }

    private var runtimeTitle: String {
        if localRunningCount == 3 {
            return "Local stack is running"
        }
        if (check(id: "docker")?.state == .good) && !(check(id: "docker")?.detail.hasPrefix("0 ") ?? true) {
            return "Docker stack is active"
        }
        if goodCheckCount > 0 {
            return "Partial services detected"
        }
        return "No complete stack detected"
    }

    private var runtimeSubtitle: String {
        let api = check(id: "health")?.state == .good ? "API healthy" : "API not ready"
        return "\(api) · \(lastRefresh)"
    }

    private var dockerStatusText: String {
        guard let docker = check(id: "docker") else { return "Waiting" }
        if docker.detail.hasPrefix("0 ") {
            if check(id: "dockerLauncher")?.state == .good {
                return "Launcher"
            }
            return "Idle"
        }
        return docker.detail
    }

    private func check(id: String) -> ServiceCheck? {
        checks.first { $0.id == id }
    }

    private var enhancementArgs: String {
        var args: [String] = []
        if enableSearXNG { args.append("--with-searxng") }
        if enableYaCy { args.append("--with-yacy") }
        if enableLanceDB { args.append("--with-lancedb") }
        return args.isEmpty ? "" : " " + args.joined(separator: " ")
    }

    private func preferredFrontendURL() -> String {
        let docker = check(id: "docker")
        if docker?.state == .good && !(docker?.detail.hasPrefix("0 ") ?? true) {
            return "http://localhost:5174"
        }
        return "http://localhost:5173"
    }
}

struct ServiceCheck: Identifiable {
    let id: String
    let title: String
    let detail: String
    let state: CheckState
    let icon: String

    static let placeholder = [
        ServiceCheck(id: "backend", title: "Backend", detail: "Waiting", state: .unknown, icon: "server.rack"),
        ServiceCheck(id: "frontend", title: "Frontend", detail: "Waiting", state: .unknown, icon: "display"),
        ServiceCheck(id: "worker", title: "Worker", detail: "Waiting", state: .unknown, icon: "gearshape.2"),
        ServiceCheck(id: "health", title: "Health", detail: "Waiting", state: .unknown, icon: "heart.text.square"),
        ServiceCheck(id: "deep", title: "Deep Health", detail: "Waiting", state: .unknown, icon: "waveform.path.ecg.rectangle"),
        ServiceCheck(id: "docker", title: "Docker", detail: "Waiting", state: .unknown, icon: "shippingbox"),
        ServiceCheck(id: "dockerLauncher", title: "Docker Launcher", detail: "Waiting", state: .unknown, icon: "rectangle.connected.to.line.below"),
        ServiceCheck(id: "env", title: "Env", detail: "Waiting", state: .unknown, icon: "doc.badge.gearshape"),
        ServiceCheck(id: "llm", title: "LLM", detail: "Waiting", state: .unknown, icon: "brain.head.profile"),
        ServiceCheck(id: "search", title: "Search Keys", detail: "Waiting", state: .unknown, icon: "magnifyingglass.circle"),
        ServiceCheck(id: "searxng", title: "SearXNG", detail: "Waiting", state: .unknown, icon: "magnifyingglass"),
        ServiceCheck(id: "yacy", title: "YaCy", detail: "Waiting", state: .unknown, icon: "externaldrive.connected.to.line.below"),
        ServiceCheck(id: "ollama", title: "Ollama", detail: "Waiting", state: .unknown, icon: "desktopcomputer")
    ]
}

enum CheckState: Equatable {
    case good
    case warning
    case bad
    case unknown

    var color: Color {
        switch self {
        case .good: return .green
        case .warning: return .orange
        case .bad: return .red
        case .unknown: return .gray
        }
    }
}

struct StatusTile: View {
    let check: ServiceCheck
    let actionTitle: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                ZStack {
                    Circle()
                        .fill(check.state.color.opacity(0.16))
                        .frame(width: 34, height: 34)
                    Image(systemName: check.icon)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(check.state.color)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(check.title)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.92))
                    Text(check.detail)
                        .font(.system(size: 11))
                        .foregroundStyle(.white.opacity(0.54))
                        .lineLimit(1)
                }
                Spacer()
                Text(actionTitle)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.78))
                    .padding(.horizontal, 7)
                    .frame(height: 22)
                    .background(check.state.color.opacity(0.16))
                    .clipShape(Capsule())
            }
            .padding(.horizontal, 10)
            .frame(height: 54)
            .background(Color.white.opacity(0.055))
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
    }
}

struct ActionCard: View {
    let title: String
    let subtitle: String
    let icon: String
    let tint: Color
    let statusText: String
    let statusColor: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Image(systemName: icon)
                        .font(.system(size: 26, weight: .semibold))
                        .foregroundStyle(tint)
                    Spacer()
                    HStack(spacing: 6) {
                        Circle()
                            .fill(statusColor)
                            .frame(width: 7, height: 7)
                        Text(statusText)
                            .font(.system(size: 11, weight: .semibold))
                    }
                    .foregroundStyle(.white.opacity(0.86))
                    .padding(.horizontal, 9)
                    .frame(height: 24)
                    .background(statusColor.opacity(0.16))
                    .clipShape(Capsule())
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundStyle(.white)
                    Text(subtitle)
                        .font(.system(size: 12))
                        .foregroundStyle(.white.opacity(0.58))
                        .lineLimit(2)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
            .background(Color.white.opacity(0.075))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.white.opacity(0.12), lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
        .buttonStyle(.plain)
    }
}

struct RingGauge: View {
    let progress: Double
    let color: Color

    var body: some View {
        ZStack {
            Circle()
                .stroke(Color.white.opacity(0.10), lineWidth: 8)
            Circle()
                .trim(from: 0, to: max(0.04, min(progress, 1)))
                .stroke(color, style: StrokeStyle(lineWidth: 8, lineCap: .round))
                .rotationEffect(.degrees(-90))
            VStack(spacing: 0) {
                Text("\(Int(progress * 100))")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundStyle(.white)
                Text("%")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.48))
            }
        }
        .frame(width: 72, height: 72)
    }
}

struct MetricPill: View {
    let title: String
    let value: String
    let color: Color

    var body: some View {
        HStack(spacing: 6) {
            Text(title)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(.white.opacity(0.55))
            Text(value)
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(color)
        }
        .padding(.horizontal, 10)
        .frame(height: 26)
        .background(Color.black.opacity(0.16))
        .clipShape(Capsule())
    }
}

struct MiniHealthBar: View {
    let title: String
    let check: ServiceCheck?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 5) {
                Circle()
                    .fill((check?.state.color ?? .gray))
                    .frame(width: 7, height: 7)
                Text(title)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.76))
            }
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.white.opacity(0.08))
                    Capsule()
                        .fill(check?.state.color ?? .gray)
                        .frame(width: proxy.size.width * fillRatio)
                }
            }
            .frame(height: 5)
        }
        .frame(maxWidth: .infinity)
    }

    private var fillRatio: Double {
        switch check?.state ?? .unknown {
        case .good: return 1
        case .warning: return 0.55
        case .bad: return 0.18
        case .unknown: return 0.3
        }
    }
}

struct SmallButton: View {
    let title: String
    let icon: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.system(size: 13, weight: .semibold))
                    .frame(width: 18)
                Text(title)
                    .font(.system(size: 13, weight: .medium))
                Spacer()
            }
            .foregroundStyle(.white.opacity(0.9))
            .padding(.horizontal, 12)
            .frame(height: 40)
            .background(Color.white.opacity(0.06))
            .clipShape(RoundedRectangle(cornerRadius: 9))
        }
        .buttonStyle(.plain)
    }
}

struct EnhancementToggle: View {
    let title: String
    let subtitle: String
    let icon: String
    @Binding var isOn: Bool

    var body: some View {
        Toggle(isOn: $isOn) {
            HStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.system(size: 13, weight: .semibold))
                    .frame(width: 18)
                    .foregroundStyle(isOn ? .cyan : .white.opacity(0.58))
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.9))
                    Text(subtitle)
                        .font(.system(size: 10))
                        .foregroundStyle(.white.opacity(0.48))
                        .lineLimit(1)
                }
                Spacer()
            }
        }
        .toggleStyle(.checkbox)
        .padding(.horizontal, 10)
        .frame(height: 48)
        .background(Color.white.opacity(isOn ? 0.09 : 0.045))
        .clipShape(RoundedRectangle(cornerRadius: 9))
    }
}

struct EnvSetting: Identifiable {
    let id: String
    let label: String
    let group: String
    let secret: Bool
    let hint: String
    let url: String

    init(id: String, label: String, group: String, secret: Bool, hint: String, url: String = "") {
        self.id = id
        self.label = label
        self.group = group
        self.secret = secret
        self.hint = hint
        self.url = url
    }
}

let launcherEnvSettings: [EnvSetting] = [
    EnvSetting(id: "OPENAI_API_KEY", label: "OpenAI API Key", group: "LLM", secret: true, hint: "Chat, embeddings, extraction", url: "https://platform.openai.com/api-keys"),
    EnvSetting(id: "OPENAI_API_BASE", label: "OpenAI API Base", group: "LLM", secret: false, hint: "OpenAI-compatible endpoint", url: "https://platform.openai.com/docs"),
    EnvSetting(id: "AZURE_API_KEY", label: "Azure OpenAI Key", group: "LLM", secret: true, hint: "Azure OpenAI", url: "https://portal.azure.com/"),
    EnvSetting(id: "AZURE_API_BASE", label: "Azure OpenAI Endpoint", group: "LLM", secret: false, hint: "Azure endpoint", url: "https://portal.azure.com/"),
    EnvSetting(id: "AZURE_CHAT_DEPLOYMENT", label: "Azure Chat Deployment", group: "LLM", secret: false, hint: "Chat model deployment"),
    EnvSetting(id: "AZURE_EMBEDDING_DEPLOYMENT", label: "Azure Embedding Deployment", group: "LLM", secret: false, hint: "Embedding model deployment"),
    EnvSetting(id: "OLLAMA_BASE_URL", label: "Ollama Base URL", group: "LLM", secret: false, hint: "Local model endpoint", url: "https://ollama.com/download"),
    EnvSetting(id: "SERPER_API_KEY", label: "Serper Key", group: "Search", secret: true, hint: "External web search", url: "https://serper.dev/api-key"),
    EnvSetting(id: "GOOGLE_SEARCH_API_KEY", label: "Google Search API Key", group: "Search", secret: true, hint: "Google Custom Search", url: "https://console.cloud.google.com/apis/credentials"),
    EnvSetting(id: "GOOGLE_SEARCH_CSE_ID", label: "Google Search CSE ID", group: "Search", secret: false, hint: "Programmable Search engine", url: "https://programmablesearchengine.google.com/controlpanel/all"),
    EnvSetting(id: "SERPAPI_KEY", label: "SerpApi Key", group: "Search", secret: true, hint: "External web search", url: "https://serpapi.com/manage-api-key"),
    EnvSetting(id: "SERPSTACK_KEY", label: "Serpstack Key", group: "Search", secret: true, hint: "External web search", url: "https://serpstack.com/dashboard"),
    EnvSetting(id: "BING_SEARCH_KEY", label: "Bing Search Key", group: "Search", secret: true, hint: "Bing web search", url: "https://portal.azure.com/#view/Microsoft_Azure_ProjectOxford/CognitiveServicesHub/~/BingSearch"),
    EnvSetting(id: "SEARXNG_BASE_URL", label: "SearXNG Base URL", group: "Optional Enhancements", secret: false, hint: "Default http://127.0.0.1:8088", url: "http://127.0.0.1:8088"),
    EnvSetting(id: "SEARXNG_MAX_PAGES", label: "SearXNG Max Pages", group: "Optional Enhancements", secret: false, hint: "Paged result volume"),
    EnvSetting(id: "YACY_BASE_URL", label: "YaCy Base URL", group: "Optional Enhancements", secret: false, hint: "Default http://127.0.0.1:8090", url: "http://127.0.0.1:8090"),
    EnvSetting(id: "YACY_RESOURCE_MODE", label: "YaCy Resource Mode", group: "Optional Enhancements", secret: false, hint: "local or global", url: "https://wiki.yacy.net/index.php/Dev:APIyacysearch"),
    EnvSetting(id: "LEGISCAN_API_KEY", label: "LegiScan Key", group: "Data", secret: true, hint: "Policy ingestion", url: "https://legiscan.com/legiscan"),
    EnvSetting(id: "TWITTER_BEARER_TOKEN", label: "Twitter Bearer Token", group: "Data", secret: true, hint: "Twitter/X ingestion", url: "https://developer.x.com/en/portal/dashboard")
]

struct SettingsEditorView: View {
    let repoPath: String
    let onClose: () -> Void
    @State private var values: [String: String] = [:]
    @State private var message = "Loading settings..."
    @State private var showSecrets = false
    @State private var codexOAuthEnabled = true

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("API Settings")
                        .font(.system(size: 22, weight: .semibold))
                    Text(envPath.path)
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Toggle("Show secrets", isOn: $showSecrets)
                    .toggleStyle(.checkbox)
                Button("Close", action: onClose)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    codexAuthPanel
                    ForEach(groupNames, id: \.self) { group in
                        settingsGroup(group)
                    }
                }
                .padding(.vertical, 2)
            }

            HStack {
                Text(message)
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                Spacer()
                Button("Open .env Folder") {
                    NSWorkspace.shared.open(envPath.deletingLastPathComponent())
                }
                Button("Reload") {
                    load()
                }
                Button("Save") {
                    save()
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .onAppear(perform: load)
    }

    private var codexAuthPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Codex Auth")
                        .font(.system(size: 14, weight: .semibold))
                    Text("点击后先复用本机 Codex 登录；未认证时打开设备认证页，缺少 Codex CLI 时显示安装提示。")
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Toggle("Enable OAuth", isOn: $codexOAuthEnabled)
                    .toggleStyle(.checkbox)
                Button("Open Codex Auth") {
                    saveCodexAuthDefaults()
                    openCodexAuthFromSettings()
                }
            }
        }
        .padding(12)
        .background(Color(NSColor.windowBackgroundColor))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.primary.opacity(0.08), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private var envPath: URL {
        URL(fileURLWithPath: repoPath).appendingPathComponent("main/backend/.env")
    }

    private var envExamplePath: URL {
        URL(fileURLWithPath: repoPath).appendingPathComponent("main/backend/.env.example")
    }

    private var groupNames: [String] {
        var names: [String] = []
        for setting in launcherEnvSettings where !names.contains(setting.group) {
            names.append(setting.group)
        }
        return names
    }

    private func settingsGroup(_ group: String) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            Text(group)
                .font(.system(size: 14, weight: .semibold))
            ForEach(launcherEnvSettings.filter { $0.group == group }) { setting in
                HStack(spacing: 10) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(setting.label)
                            .font(.system(size: 12, weight: .medium))
                        Text(setting.hint)
                            .font(.system(size: 10))
                            .foregroundStyle(.secondary)
                    }
                    .frame(width: 180, alignment: .leading)

                    if setting.secret && !showSecrets {
                        SecureField(setting.id, text: binding(for: setting.id))
                            .textFieldStyle(.roundedBorder)
                    } else {
                        TextField(setting.id, text: binding(for: setting.id))
                            .textFieldStyle(.roundedBorder)
                    }

                    Button {
                        openProviderURL(setting.url)
                    } label: {
                        Image(systemName: "arrow.up.right.square")
                            .frame(width: 22)
                    }
                    .buttonStyle(.borderless)
                    .disabled(setting.url.isEmpty)
                }
            }
        }
        .padding(12)
        .background(Color(NSColor.windowBackgroundColor))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.primary.opacity(0.08), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    private func binding(for key: String) -> Binding<String> {
        Binding(
            get: { values[key, default: ""] },
            set: { values[key] = $0 }
        )
    }

    private func load() {
        ensureEnvFile()
        values = parseEnvFile(envPath)
        codexOAuthEnabled = (values["CODEX_OAUTH_ENABLED"] ?? "true").lowercased() != "false"
        message = "Loaded \(envPath.path)"
    }

    private func save() {
        ensureEnvFile()
        do {
            var updates = values
            updates["CODEX_OAUTH_ENABLED"] = codexOAuthEnabled ? "true" : "false"
            updates["CODEX_OAUTH_REDIRECT_URI"] = values["CODEX_OAUTH_REDIRECT_URI"] ?? "http://localhost:8000/api/v1/codex-auth/callback"
            updates["CODEX_OAUTH_FRONTEND_SUCCESS_URL"] = values["CODEX_OAUTH_FRONTEND_SUCCESS_URL"] ?? "http://localhost:5173"
            updates["CODEX_OAUTH_FRONTEND_ERROR_URL"] = values["CODEX_OAUTH_FRONTEND_ERROR_URL"] ?? "http://localhost:5173"
            try writeEnvFile(envPath, updates: updates)
            values = updates
            message = "Saved settings"
        } catch {
            message = "Save failed: \(error.localizedDescription)"
        }
    }

    private func saveCodexAuthDefaults() {
        var updates = values
        updates["CODEX_OAUTH_ENABLED"] = codexOAuthEnabled ? "true" : "false"
        updates["CODEX_OAUTH_REDIRECT_URI"] = "http://localhost:8000/api/v1/codex-auth/callback"
        updates["CODEX_OAUTH_FRONTEND_SUCCESS_URL"] = "http://localhost:5173"
        updates["CODEX_OAUTH_FRONTEND_ERROR_URL"] = "http://localhost:5173"
        do {
            try writeEnvFile(envPath, updates: updates)
            values = updates
            message = codexOAuthEnabled ? "Codex OAuth enabled; opening auth page" : "Codex OAuth is disabled"
        } catch {
            message = "Cannot save Codex Auth setting: \(error.localizedDescription)"
        }
    }

    private func openCodexAuthFromSettings() {
        guard codexOAuthEnabled else {
            message = "Enable OAuth first, then start Codex auth."
            return
        }
        message = "Checking Codex auth..."
        bootstrapCodexAuth { result in
            DispatchQueue.main.async {
                switch result {
                case .success(let payload):
                    if payload.authenticated {
                        if let url = URL(string: "http://localhost:5173") {
                            NSWorkspace.shared.open(url)
                        }
                        self.message = "Codex is already authenticated on this machine."
                        return
                    }
                    if let deviceURL = payload.device_url, let url = URL(string: deviceURL) {
                        NSWorkspace.shared.open(url)
                        let code = payload.device_code.map { " Device code: \($0)." } ?? ""
                        self.message = "Complete Codex device authentication in the opened browser.\(code)"
                        return
                    }
                    self.message = "Codex CLI auth could not start: \(payload.hint ?? "no device URL returned")"
                case .failure(let error):
                    self.message = "Codex auth bootstrap failed: \(error.localizedDescription)"
                }
            }
        }
    }

    private func openProviderURL(_ value: String) {
        guard let url = URL(string: value), !value.isEmpty else {
            return
        }
        NSWorkspace.shared.open(url)
    }

    private func ensureEnvFile() {
        let manager = FileManager.default
        if manager.fileExists(atPath: envPath.path) {
            return
        }
        do {
            try manager.createDirectory(at: envPath.deletingLastPathComponent(), withIntermediateDirectories: true)
            if manager.fileExists(atPath: envExamplePath.path) {
                try manager.copyItem(at: envExamplePath, to: envPath)
            } else {
                try "".write(to: envPath, atomically: true, encoding: .utf8)
            }
        } catch {
            message = "Cannot create .env: \(error.localizedDescription)"
        }
    }
}

struct ExternalStatusPill: View {
    let title: String
    let check: ServiceCheck?

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill((check?.state.color ?? .gray))
                .frame(width: 7, height: 7)
            Text(title)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.white.opacity(0.82))
            Text(check?.detail ?? "Waiting")
                .font(.system(size: 11))
                .foregroundStyle(.white.opacity(0.52))
                .lineLimit(1)
        }
        .padding(.horizontal, 10)
        .frame(maxWidth: .infinity, minHeight: 30)
        .background(Color.white.opacity(0.055))
        .clipShape(Capsule())
    }
}

func shellQuote(_ value: String) -> String {
    return "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'"
}

func appleScriptString(_ value: String) -> String {
    let escaped = value
        .replacingOccurrences(of: "\\", with: "\\\\")
        .replacingOccurrences(of: "\"", with: "\\\"")
        .replacingOccurrences(of: "\n", with: "\\n")
    return "\"\(escaped)\""
}

func parseEnvFile(_ url: URL) -> [String: String] {
    guard let text = try? String(contentsOf: url, encoding: .utf8) else {
        return [:]
    }
    var values: [String: String] = [:]
    for line in text.components(separatedBy: .newlines) {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        if trimmed.isEmpty || trimmed.hasPrefix("#") {
            continue
        }
        guard let equalIndex = trimmed.firstIndex(of: "=") else {
            continue
        }
        let key = String(trimmed[..<equalIndex]).trimmingCharacters(in: .whitespaces)
        let rawValue = String(trimmed[trimmed.index(after: equalIndex)...]).trimmingCharacters(in: .whitespaces)
        if !key.isEmpty {
            values[key] = unquoteEnvValue(rawValue)
        }
    }
    return values
}

func writeEnvFile(_ url: URL, updates: [String: String]) throws {
    let existingText = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
    let lines = existingText.components(separatedBy: .newlines)
    var seen = Set<String>()
    var nextLines: [String] = []

    for line in lines {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        if trimmed.isEmpty || trimmed.hasPrefix("#") || !trimmed.contains("=") {
            nextLines.append(line)
            continue
        }
        guard let equalIndex = line.firstIndex(of: "=") else {
            nextLines.append(line)
            continue
        }
        let key = String(line[..<equalIndex]).trimmingCharacters(in: .whitespaces)
        if let value = updates[key] {
            let prefix = String(line[..<equalIndex])
            nextLines.append("\(prefix)=\(quoteEnvValue(value))")
            seen.insert(key)
        } else {
            nextLines.append(line)
        }
    }

    let missing = updates.keys.sorted().filter { !seen.contains($0) }
    if !missing.isEmpty && !(nextLines.last?.trimmingCharacters(in: .whitespaces).isEmpty ?? true) {
        nextLines.append("")
    }
    for key in missing {
        nextLines.append("\(key)=\(quoteEnvValue(updates[key] ?? ""))")
    }

    try (nextLines.joined(separator: "\n").trimmingCharacters(in: .newlines) + "\n").write(to: url, atomically: true, encoding: .utf8)
}

func unquoteEnvValue(_ value: String) -> String {
    if value.count >= 2 {
        let first = value.first
        let last = value.last
        if (first == "'" && last == "'") || (first == "\"" && last == "\"") {
            return String(value.dropFirst().dropLast())
        }
    }
    return value
}

func quoteEnvValue(_ value: String) -> String {
    let escaped = value
        .replacingOccurrences(of: "\\", with: "\\\\")
        .replacingOccurrences(of: "'", with: "\\'")
    return "'\(escaped)'"
}

func monitorCommand() -> String {
    return """
    cd \(shellQuote(LauncherConfig.repoPath))
    backend=down
    backend_count=0
    frontend=down
    worker=down
    health=down
    deep=down
    docker_state=off
    docker_count=0
    env_file=missing
    llm=missing
    search=missing
    searxng=down
    yacy=down
    ollama=down

    backend_count=$(lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print $2}' | sort -u | wc -l | tr -d ' ')
    [ "$backend_count" != "0" ] && backend=up
    lsof -nP -iTCP:5173 -sTCP:LISTEN >/dev/null 2>&1 && frontend=up
    if [ -f /tmp/celery-local-worker.pid ]; then
      worker_pid=$(cat /tmp/celery-local-worker.pid 2>/dev/null || true)
      if [ -n "$worker_pid" ] && kill -0 "$worker_pid" >/dev/null 2>&1; then
        worker=up:$worker_pid
      fi
    fi
    curl -fsS --max-time 2 http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1 && health=ok
    curl -fsS --max-time 3 http://127.0.0.1:8000/api/v1/health/deep >/dev/null 2>&1 && deep=ok
    if docker info >/dev/null 2>&1; then
      docker_state=ready
      docker_count=$(cd main/ops && docker compose --profile modern-ui --profile search-enhancements ps --status running --services 2>/dev/null | awk 'NF && $0 != "launcher-agent" && $0 != "launcher-ui"' | wc -l | tr -d ' ')
      docker_launcher=down
      if cd main/ops && docker compose --project-name mrw-launcher --profile modern-ui ps --status running --services 2>/dev/null | awk 'NF' | grep -Eq '^(launcher-agent|launcher-ui)$'; then
        docker_launcher=up
      fi
    fi
    if [ -f main/backend/.env ]; then
      env_file=present
      env_has() {
        awk -F= -v key="$1" '$1 == key {gsub(/^[ "'\\''"]+|[ "'\\''"]+$/, "", $2); if ($2 != "") found=1} END {exit found ? 0 : 1}' main/backend/.env
      }
      if env_has OPENAI_API_KEY || env_has AZURE_API_KEY || curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        llm=configured
      fi
      if env_has SERPER_API_KEY || env_has GOOGLE_SEARCH_API_KEY || env_has SERPAPI_KEY || env_has SERPSTACK_KEY || env_has BING_SEARCH_KEY; then
        search=configured
      fi
    fi
    curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && ollama=up
    curl -fsS --max-time 2 'http://127.0.0.1:8088/search?q=health&format=json' >/dev/null 2>&1 && searxng=up
    curl -fsS --max-time 2 'http://127.0.0.1:8090/yacysearch.json?query=health&resource=local&maximumRecords=1' >/dev/null 2>&1 && yacy=up

    printf 'backend=%s\\n' "$backend"
    printf 'backend_count=%s\\n' "$backend_count"
    printf 'frontend=%s\\n' "$frontend"
    printf 'worker=%s\\n' "$worker"
    printf 'health=%s\\n' "$health"
    printf 'deep=%s\\n' "$deep"
    printf 'docker=%s:%s\\n' "$docker_state" "$docker_count"
    printf 'docker_launcher=%s\\n' "$docker_launcher"
    printf 'env_file=%s\\n' "$env_file"
    printf 'llm=%s\\n' "$llm"
    printf 'search=%s\\n' "$search"
    printf 'searxng=%s\\n' "$searxng"
    printf 'yacy=%s\\n' "$yacy"
    printf 'ollama=%s\\n' "$ollama"
    """
}

func runShell(_ command: String, completion: @escaping (String) -> Void) {
    DispatchQueue.global(qos: .utility).async {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-lc", command]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        do {
            try process.run()
            process.waitUntilExit()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            completion(String(data: data, encoding: .utf8) ?? "")
        } catch {
            completion("error=\(error.localizedDescription)")
        }
    }
}

func parseMonitorOutput(_ output: String) -> [ServiceCheck] {
    var values: [String: String] = [:]
    for line in output.split(separator: "\n") {
        let parts = line.split(separator: "=", maxSplits: 1).map(String.init)
        if parts.count == 2 {
            values[parts[0]] = parts[1]
        }
    }

    let backendUp = values["backend"] == "up"
    let backendCount = Int(values["backend_count"] ?? "0") ?? 0
    let frontendUp = values["frontend"] == "up"
    let workerValue = values["worker"] ?? "down"
    let workerUp = workerValue.hasPrefix("up:")
    let healthOk = values["health"] == "ok"
    let deepOk = values["deep"] == "ok"
    let dockerValue = values["docker"] ?? "off:0"
    let dockerLauncherUp = values["docker_launcher"] == "up"
    let dockerParts = dockerValue.split(separator: ":", maxSplits: 1).map(String.init)
    let dockerReady = dockerParts.first == "ready"
    let dockerCount = dockerParts.count > 1 ? dockerParts[1] : "0"
    let dockerRunningCount = Int(dockerCount) ?? 0
    let envPresent = values["env_file"] == "present"
    let llmConfigured = values["llm"] == "configured"
    let searchConfigured = values["search"] == "configured"
    let searxngUp = values["searxng"] == "up"
    let yacyUp = values["yacy"] == "up"
    let ollamaUp = values["ollama"] == "up"

    return [
        ServiceCheck(
            id: "backend",
            title: "Backend",
            detail: backendUp ? (backendCount > 1 ? "\(backendCount) listeners on :8000" : "Listening on :8000") : "Not listening",
            state: backendUp ? (backendCount > 1 ? .warning : .good) : .bad,
            icon: "server.rack"
        ),
        ServiceCheck(id: "frontend", title: "Frontend", detail: frontendUp ? "Listening on :5173" : "Not listening", state: frontendUp ? .good : .bad, icon: "display"),
        ServiceCheck(id: "worker", title: "Worker", detail: workerUp ? "PID \(workerValue.replacingOccurrences(of: "up:", with: ""))" : "Not running", state: workerUp ? .good : .warning, icon: "gearshape.2"),
        ServiceCheck(id: "health", title: "Health", detail: healthOk ? "API ok" : "No response", state: healthOk ? .good : .bad, icon: "heart.text.square"),
        ServiceCheck(id: "deep", title: "Deep Health", detail: deepOk ? "DB + ES ok" : "Check failed", state: deepOk ? .good : .warning, icon: "waveform.path.ecg.rectangle"),
        ServiceCheck(id: "docker", title: "Docker", detail: dockerReady ? "\(dockerCount) compose services" : "Docker not ready", state: dockerReady && dockerRunningCount > 0 ? .good : .warning, icon: "shippingbox"),
        ServiceCheck(id: "dockerLauncher", title: "Docker Launcher", detail: dockerLauncherUp ? "Listening on :5176" : "Offline", state: dockerLauncherUp ? .good : .warning, icon: "rectangle.connected.to.line.below"),
        ServiceCheck(id: "env", title: "Env", detail: envPresent ? ".env present" : ".env missing", state: envPresent ? .good : .bad, icon: "doc.badge.gearshape"),
        ServiceCheck(id: "llm", title: "LLM", detail: llmConfigured ? "Configured" : "Missing key", state: llmConfigured ? .good : .warning, icon: "brain.head.profile"),
        ServiceCheck(id: "search", title: "Search Keys", detail: searchConfigured ? "Configured" : "Missing key", state: searchConfigured ? .good : .warning, icon: "magnifyingglass.circle"),
        ServiceCheck(id: "searxng", title: "SearXNG", detail: searxngUp ? "Reachable :8088" : "Offline", state: searxngUp ? .good : .warning, icon: "magnifyingglass"),
        ServiceCheck(id: "yacy", title: "YaCy", detail: yacyUp ? "Reachable :8090" : "Offline", state: yacyUp ? .good : .warning, icon: "externaldrive.connected.to.line.below"),
        ServiceCheck(id: "ollama", title: "Ollama", detail: ollamaUp ? "Reachable" : "Offline", state: ollamaUp ? .good : .warning, icon: "desktopcomputer")
    ]
}

func formattedRefreshTime() -> String {
    let formatter = DateFormatter()
    formatter.dateFormat = "HH:mm:ss"
    return "Updated \(formatter.string(from: Date()))"
}
