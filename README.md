<div align="center">
  <img src="assets/icon.png" alt="MapRemote icon" width="128" height="128" />
  <h1>MapRemote</h1>
  <p><strong>Redirect requests. Keep your frontend unchanged.</strong></p>
  <p>A focused macOS development proxy for mapping remote HTTP and HTTPS endpoints to local or alternative backends.</p>
  <p>
    <a href="https://github.com/abdulsalamalkhatib96/MapRemote/actions/workflows/ci.yml"><img src="https://github.com/abdulsalamalkhatib96/MapRemote/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
    <img src="https://img.shields.io/badge/version-2.5-0F9F9A" alt="Version 2.5" />
    <img src="https://img.shields.io/badge/macOS-12%2B-222222?logo=apple" alt="macOS 12+ target" />
    <img src="https://img.shields.io/badge/Swift-AppKit-F05138?logo=swift&logoColor=white" alt="Swift" />
    <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python" />
  </p>
  <p><a href="#quick-start">Quick start</a> · <a href="#mapping-rules">Mapping rules</a> · <a href="#architecture">Architecture</a> · <a href="#troubleshooting">Troubleshooting</a></p>
</div>

## Why MapRemote?

Develop a local API against an existing frontend without changing its environment variables, deployed configuration or request URLs. MapRemote applies ordered URL-mapping rules to traffic from proxy-aware applications and forwards matching requests to the backend of your choice.

```mermaid
flowchart LR
    A[Browser / frontend] --> B[MapRemote proxy :9090]
    B --> C{First matching rule?}
    C -->|Yes| D[Local / alternative API]
    C -->|No| E[Original destination]
```

MapRemote is deliberately narrow in scope: it provides a rule editor, mapping preview, automatic system proxy management, and explicit HTTPS certificate controls. It is not a general-purpose traffic inspection suite, and is not affiliated with Proxyman or mitmproxy.

## Features

| Capability | Description |
| --- | --- |
| HTTP and HTTPS mapping | Rewrite scheme, host, port and path for matching requests. HTTPS requires trusted local CA. |
| Exact and prefix paths | Match a single endpoint or preserve the suffix of an API subtree. |
| Wildcard source hosts | Match subdomains such as `*.example.com`. |
| Method filtering | Apply a rule to all methods or a selected HTTP method. |
| Query strings | Preserve the original query or replace it with the destination query. |
| Host header | Optionally keep the original Host header. |
| Rule priorities | First enabled matching rule wins; reorder rules from the interface. |
| Live rule updates | Persist and reload mapping configuration without restarting the engine. |
| Preview | Evaluate a URL without sending a network request. |
| macOS integration | Start and Stop manage HTTP/HTTPS system proxy settings automatically. |
| Recovery | A privileged supervisor journals previous settings and watches controller and engine processes. |
| HTTPS trust | Explicit certificate installation and removal controls. |

## Quick start

### Requirements

- macOS 12 or later is the deployment target; actual compatibility depends on the installed SDK and dependencies. Full native compatibility has not yet been validated on every supported release.
- Python 3.10+ available in a standard Homebrew or system path.
- `mitmdump` from [mitmproxy](https://mitmproxy.org/).
- Apple Command Line Tools for building, and administrator approval for changing network proxy settings.
- Homebrew is optional but convenient for installing dependencies.

```bash
brew install python
brew install --cask mitmproxy
xcode-select --install # only if the command line tools are missing
```

### Build from source

```bash
git clone https://github.com/abdulsalamalkhatib96/MapRemote.git
cd MapRemote
python3 smoke_test.py
bash Build.command
```

`Build.command` compiles the Swift application and privileged helper, creates the macOS icon, copies the controller resources and ad-hoc signs the resulting `MapRemote.app`. It opens the app on success. Move the app to Applications if desired. To rebuild, quit and remove the existing generated app first. For build-only mode, use `MAPREMOTE_BUILD_ONLY=1 bash Build.command`.

This repository distributes source code, not a notarized standalone binary. The generated app still requires Python and mitmproxy on the destination Mac, and uses the build machine's architecture. If macOS displays an unverified-developer warning, review the source and use Apple's [per-app approval process](https://support.apple.com/en-us/102445) only if you trust it. Do not disable Gatekeeper or SIP.

### First run

1. Quit other debugging proxies and stop any manually launched `mitmdump` process.
2. If an earlier MapRemote v1 manually configured the same system proxy, disable only that old configuration before starting.
3. Open MapRemote, add a rule, and click **Start proxy**. Approve the administrator prompt.
4. For HTTPS, click **Install & Trust Certificate** after the CA has been generated. Review and approve the macOS trust prompt; use Keychain Access if interactive trust cannot be granted by the button.
5. Test your request from a proxy-aware client. Click **Stop** or quit when finished.

## Mapping rules

### Example: local Laravel API

Assume a frontend calls `https://api.example.com/v1/users?page=2` and your local API is running at port 8000.

| Field | Value |
| --- | --- |
| Name | Local Laravel API |
| Source URL | `https://api.example.com/v1` |
| Destination URL | `http://127.0.0.1:8000/api` |
| Path match | Prefix |
| HTTP method | All methods |
| Query string | Preserve original |
| Keep original Host | Off (unless required by the backend) |

The forwarded URL becomes:

```text
http://127.0.0.1:8000/api/users?page=2
```

The browser continues requesting the original URL. The local backend must still satisfy any relevant CORS, cookie, authentication and response requirements. Mapping does not bypass browser security or certificate pinning.

### Rule semantics

The source scheme, host and effective port must match. Prefix matching respects path segment boundaries (`/api` does not match `/apix`). Wildcards are allowed only at the start of the source hostname and do not match the bare parent domain. Source query matching is not supported. The rule list is evaluated top to bottom and the first enabled matching rule wins. Disable the mapping tool to forward requests unchanged, or stop the proxy to restore system settings.

## Architecture

| Component | Responsibility |
| --- | --- |
| `NativeApp.swift` | AppKit window and embedded WebKit interface; launches the Python controller. |
| `index.html` | Rule editor, preview and lifecycle controls. |
| `app.py` | Loopback control API, engine startup, diagnostics and shutdown. |
| `rules.py` | Validation, deterministic mapping and atomic JSON persistence. |
| `addon.py` | mitmproxy request-header hook and live rule reload. |
| `system_proxy.py` | Administrator prompts, helper supervision and certificate actions. |
| `ProxyHelper.swift` | SystemConfiguration changes, recovery journal and PID monitoring. |
| `smoke_test.py` | Real loopback HTTP mapping test with installed mitmdump. |
| `assets/` | Original vector icon and 1024px raster source. |

The proxy listens on `127.0.0.1:9090` by default. The controller uses an ephemeral loopback port, a session token, and Host/Origin checks. Rules and CA material remain local:

```text
~/Library/Application Support/MapRemote/
├── rules.json
├── ca/
└── instance.lock
```

The privileged helper stores a root-owned recovery journal at `/private/var/db/com.mapremote.proxy/snapshot.plist`. Do not manually delete it. Enabled Wi-Fi/Ethernet services in the current network location are managed; existing bypass entries are retained, and PAC/WPAD/SOCKS enable flags are temporarily disabled and restored. If a service's managed settings were independently changed, restoration avoids overwriting them. Immediate recovery after power loss or simultaneous supervisor failure is not guaranteed; reopen MapRemote and use **Recover network settings**.

## Testing

```bash
python3 -m unittest discover -s tests -v
python3 smoke_test.py
MAPREMOTE_BUILD_ONLY=1 bash Build.command # macOS only
codesign --verify --deep --strict --verbose=2 MapRemote.app
```

The smoke test uses a temporary CA, temporary rules and loopback HTTP server without modifying system proxy settings or trust. GitHub Actions is configured for Python unit tests, native macOS build and a live proxy smoke test. Privileged network changes, HTTPS trust prompts, crash recovery and end-to-end native UI behavior still require manual testing on a Mac. CI configuration is not evidence of a successful run.

## Troubleshooting

| Error / symptom | Action |
| --- | --- |
| Proxy port is already in use | Run `lsof -nP -iTCP:9090 -sTCP:LISTEN`; stop only the confirmed conflicting process or choose another port. |
| `mitmdump` not found | Run `mitmdump --version`; install mitmproxy and restart the app. |
| Proxy exits during startup | Read the engine diagnostics in the UI and run `python3 smoke_test.py` from the source directory. |
| Addon collision or `Loader` error | Quit the old app and rebuild from current source; the app embeds its own addon. |
| `nohup: can't detach from console` | Rebuild using 2.5 or later; this version no longer uses nohup. |
| Certificate authorization denied | Use Keychain Access to inspect the exact generated public CA certificate and approve trust interactively. |
| Internet stops working | Use Recover network settings, then verify Network > Details > Proxies; do not remove the journal. |
| Request is not mapped | Check the rule preview, source scheme/port, priority, bypass entries and client proxy support. |

## Security and limitations

- Intended only for authorized local development; HTTPS inspection grants trust to a local CA. Protect the private CA key and remove trust when it is no longer needed.
- A matching request can forward its original authorization headers, cookies and body to a different destination. Never map sensitive traffic to an untrusted backend.
- No request capture UI or persistent flow logging is provided. The underlying proxy still processes request content.
- Applications that ignore system proxy settings, pinned TLS clients, VPN/custom network services and proxy-bypassed destinations may not work.
- This is not a self-contained or Apple-notarized distribution. It has not undergone a complete macOS integration or independent security audit.

See [SECURITY.md](SECURITY.md) for responsible disclosure and [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## Changelog and roadmap

See [CHANGELOG.md](CHANGELOG.md) for version history. Future work may include a self-contained runtime, universal binaries, signed/notarized releases, DMG packaging and additional macOS integration testing. These are not implemented in this version.

## Author and licensing

Developed for [Abdulsalam Al-Khatib](https://github.com/abdulsalamalkhatib96). Powered by [mitmproxy](https://github.com/mitmproxy/mitmproxy), Swift and Python. Third-party components retain their respective licenses.

No license has been selected for MapRemote itself. Public source visibility alone does not grant permission to redistribute or modify it; contact the owner for licensing terms.
