import Foundation
import SystemConfiguration
import Darwin

let base = URL(fileURLWithPath: "/private/var/db/com.mapremote.proxy", isDirectory: true)
let journal = base.appendingPathComponent("snapshot.plist")
let keys = ["HTTPEnable", "HTTPProxy", "HTTPPort", "HTTPSEnable", "HTTPSProxy", "HTTPSPort", "ProxyAutoConfigEnable", "ProxyAutoDiscoveryEnable", "SOCKSEnable", "ExceptionsList"]
struct Failure: Error, CustomStringConvertible { let description: String; init(_ s: String) { description = s } }
func require(_ ok: Bool, _ message: String) throws { if !ok { throw Failure(message + " (SC status: \(SCError()))") } }
func save(_ value: [[String: Any]]) throws {
    let bytes = try PropertyListSerialization.data(fromPropertyList: value, format: .binary, options: 0)
    try bytes.write(to: journal, options: .atomic)
    guard chmod(journal.path, 0o600) == 0 else { throw Failure("Cannot protect recovery journal") }
}
func load() throws -> [[String: Any]] {
    let value = try PropertyListSerialization.propertyList(from: Data(contentsOf: journal), options: [], format: nil)
    guard let rows = value as? [[String: Any]] else { throw Failure("Invalid recovery journal") }; return rows
}
func phase(_ message: String) {
    FileHandle.standardError.write(Data((message + "\n").utf8))
}
func preferences(_ body: (SCPreferences) throws -> Void) throws {
    guard let p = SCPreferencesCreate(nil, "MapRemote" as CFString, nil) else { throw Failure("Cannot open network preferences") }
    phase("Acquiring network preferences lock")
    let deadline = ProcessInfo.processInfo.systemUptime + 8
    while !SCPreferencesLock(p, false) {
        let error = SCError()
        if ProcessInfo.processInfo.systemUptime >= deadline {
            throw Failure("Cannot acquire network preferences lock (SC status: \(error))")
        }
        Thread.sleep(forTimeInterval: 0.2)
    }
    defer { SCPreferencesUnlock(p) }
    SCPreferencesSynchronize(p)
    try body(p)
}
func subset(_ d: [String: Any]) -> [String: Any] { d.filter { keys.contains($0.key) } }
func equal(_ a: [String: Any], _ b: [String: Any]) -> Bool { NSDictionary(dictionary: a).isEqual(to: b) }
func config(_ proto: SCNetworkProtocol) -> [String: Any] { SCNetworkProtocolGetConfiguration(proto) as? [String: Any] ?? [:] }
func proxy(_ service: SCNetworkService) -> SCNetworkProtocol? { SCNetworkServiceCopyProtocol(service, kSCNetworkProtocolTypeProxies) }
// Restore coherent groups independently. An unrelated edit (for example a
// bypass-list change) must not leave an abandoned HTTP/HTTPS proxy enabled.
let proxyGroups = [
    ["HTTPEnable", "HTTPProxy", "HTTPPort"],
    ["HTTPSEnable", "HTTPSProxy", "HTTPSPort"],
    ["ProxyAutoConfigEnable"], ["ProxyAutoDiscoveryEnable"], ["SOCKSEnable"],
    ["ExceptionsList"]
]
func group(_ d: [String: Any], _ names: [String]) -> [String: Any] {
    d.filter { names.contains($0.key) }
}
func isEnabled(_ d: [String: Any], _ key: String) -> Bool {
    (d[key] as? NSNumber)?.boolValue == true
}
func matchesListener(_ d: [String: Any], _ prefix: String, _ port: Int) -> Bool {
    isEnabled(d, prefix + "Enable") &&
        (d[prefix + "Proxy"] as? String) == "127.0.0.1" &&
        (d[prefix + "Port"] as? NSNumber)?.intValue == port
}
func restore() throws {
    guard FileManager.default.fileExists(atPath: journal.path) else { return }
    let rows = try load()
    try preferences { p in
        for row in rows {
            guard let id = row["id"] as? String, let before = row["before"] as? [String: Any], let after = row["after"] as? [String: Any] else { throw Failure("Invalid journal entry") }
            guard let service = SCNetworkServiceCopy(p, id as CFString), let proto = proxy(service) else { continue }
            var current = config(proto)
            let original = current
            for names in proxyGroups where equal(group(current, names), group(after, names)) {
                for key in names { current.removeValue(forKey: key) }
                for (key, value) in group(before, names) { current[key] = value }
            }
            if !equal(original, current) {
                try require(SCNetworkProtocolSetConfiguration(proto, current as CFDictionary), "Cannot restore service \(id)")
            }
        }
        try require(SCPreferencesCommitChanges(p), "Cannot commit restore")
        try require(SCPreferencesApplyChanges(p), "Cannot apply restore")
    }
    try FileManager.default.removeItem(at: journal)
}
func apply(_ port: Int, sessionValid: () -> Bool) throws {
    try preferences { p in
        guard let set = SCNetworkSetCopyCurrent(p), let services = SCNetworkSetCopyServices(set) as? [SCNetworkService] else { throw Failure("No current network location") }
        var rows = [[String: Any]](); var changes = [(SCNetworkProtocol, [String: Any])]()
        for service in services where SCNetworkServiceGetEnabled(service) {
            guard let iface = SCNetworkServiceGetInterface(service), let type = SCNetworkInterfaceGetInterfaceType(iface) as String?, ["Ethernet", "IEEE80211"].contains(type), let proto = proxy(service), SCNetworkProtocolGetEnabled(proto), let id = SCNetworkServiceGetServiceID(service) as String? else { continue }
            let old = config(proto)
            var baseline = old
            // The controller verified this loopback listener was free before
            // starting its engine. A matching enabled entry would otherwise
            // be restored to a dead listener on Stop. Adopt it automatically.
            for prefix in ["HTTP", "HTTPS"] {
                if matchesListener(old, prefix, port) {
                    baseline[prefix + "Enable"] = 0
                    phase("Adopting stale loopback \(prefix) proxy for service \(id)")
                } else if isEnabled(old, prefix + "Enable") {
                    throw Failure("Another manual \(prefix) proxy is enabled. MapRemote will not replace a different proxy; close the other proxy app or use an explicit proxy client.")
                }
            }
            // Do not silently bypass a managed corporate PAC/SOCKS proxy.
            if ["ProxyAutoConfigEnable", "ProxyAutoDiscoveryEnable", "SOCKSEnable"].contains(where: { isEnabled(old, $0) }) {
                throw Failure("An existing PAC, automatic discovery or SOCKS proxy is enabled. MapRemote will not override it.")
            }
            var next = baseline
            next["HTTPEnable"] = 1; next["HTTPProxy"] = "127.0.0.1"; next["HTTPPort"] = port
            next["HTTPSEnable"] = 1; next["HTTPSProxy"] = "127.0.0.1"; next["HTTPSPort"] = port
            next["ProxyAutoConfigEnable"] = 0; next["ProxyAutoDiscoveryEnable"] = 0; next["SOCKSEnable"] = 0
            var exceptions = old["ExceptionsList"] as? [String] ?? []
            for host in ["localhost", "127.0.0.1", "::1"] where !exceptions.contains(host) { exceptions.append(host) }
            next["ExceptionsList"] = exceptions
            rows.append(["id": id, "before": subset(baseline), "after": subset(next)])
            changes.append((proto, next))
        }
        guard !rows.isEmpty else { throw Failure("No enabled Wi-Fi or Ethernet service with proxy configuration was found") }
        guard sessionValid() else { throw Failure("Startup cancelled before journaling") }
        phase("Saving network recovery journal")
        // Journal before committing anything, so the next launch can recover even after a power loss.
        try save(rows)
        for (proto, next) in changes { try require(SCNetworkProtocolSetConfiguration(proto, next as CFDictionary), "Cannot set proxy") }
        guard sessionValid() else { throw Failure("Startup cancelled before commit") }
        phase("Committing proxy settings")
        try require(SCPreferencesCommitChanges(p), "Cannot commit proxy")
        phase("Applying proxy settings")
        try require(SCPreferencesApplyChanges(p), "Cannot apply proxy")
    }
}
func identity(_ pid: Int32) -> String? {
    guard pid > 1, kill(pid, 0) == 0 else { return nil }
    let proc = Process(); proc.executableURL = URL(fileURLWithPath: "/bin/ps"); proc.arguments = ["-p", String(pid), "-o", "lstart=", "-o", "stat="]
    var env = ProcessInfo.processInfo.environment; env["LC_ALL"] = "C"; proc.environment = env
    let pipe = Pipe(); proc.standardOutput = pipe; proc.standardError = FileHandle.nullDevice
    do { try proc.run() } catch { return nil }
    let data = pipe.fileHandleForReading.readDataToEndOfFile(); proc.waitUntilExit()
    let words = (String(data: data, encoding: .utf8) ?? "").split(whereSeparator: { $0.isWhitespace })
    guard proc.terminationStatus == 0, words.count >= 6, !words.last!.contains("Z") else { return nil }
    return words.prefix(5).joined(separator: " ")
}
func status(_ path: String, _ value: String) throws { try value.write(toFile: path, atomically: true, encoding: .utf8) }
let args = CommandLine.arguments
var ready: String? = args.count == 6 && args[1] == "run" ? args[5] : nil
var ownsLock = false
var activated = false
var lockFD: Int32 = -1
do {
    phase("Helper started")
    guard geteuid() == 0 else { throw Failure("Administrator permission required") }
    // Exercise the actual signed executable without changing network settings.
    if args.count == 2 && args[1] == "self-test" {
        print("MapRemote ProxyHelper OK")
        exit(0)
    }
    try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o755])
    guard chmod(base.path, 0o755) == 0 else { throw Failure("Cannot set recovery directory permissions") }
    lockFD = open(base.appendingPathComponent("lock").path, O_CREAT | O_RDWR | O_NOFOLLOW, 0o600)
    guard lockFD >= 0, flock(lockFD, LOCK_EX | LOCK_NB) == 0 else { throw Failure("Another MapRemote system session is active") }
    ownsLock = true
    phase("Checking previous recovery journal")
    try restore()
    if args.count == 2 && args[1] == "recover" { exit(0) }
    guard args.count == 6, args[1] == "run", let parent = Int32(args[2]), let engine = Int32(args[3]), let port = Int(args[4]), (1024...65535).contains(port), let parentID = identity(parent), let engineID = identity(engine) else { throw Failure("Invalid or expired proxy session") }
    phase("Validating startup session")
    let sessionDirectory = URL(fileURLWithPath: args[5]).deletingLastPathComponent().path
    let sessionValid = {
        FileManager.default.fileExists(atPath: sessionDirectory) && identity(parent) == parentID && identity(engine) == engineID
    }
    guard sessionValid() else { throw Failure("Startup cancelled") }
    activated = true
    try apply(port, sessionValid: sessionValid)
    guard sessionValid() else { throw Failure("Startup cancelled after applying proxy") }
    phase("Proxy ready")
    try status(args[5], "OK"); ready = nil
    while identity(parent) == parentID && identity(engine) == engineID { Thread.sleep(forTimeInterval: 0.5) }
    try restore(); activated = false

} catch {
    if ownsLock && activated {
        do { try restore() } catch { phase("Recovery failed: \(error)") }
    }
    if let path = ready { try? status(path, "ERROR: \(error)") }
    FileHandle.standardError.write(Data("\(error)\n".utf8)); exit(1)
}
