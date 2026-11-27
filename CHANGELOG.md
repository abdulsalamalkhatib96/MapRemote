# Changelog

## Unreleased
- Adopt stale matching loopback proxy settings automatically and disable them on Stop instead of restoring an abandoned listener.
- Restore HTTP/HTTPS and other network settings independently; refuse to overwrite unrelated active proxy configurations.
- Tunnel TLS outside enabled HTTPS mapping authorities without interception or CA trust requirements; reload scope from rules on each new TLS connection.
- Add regression coverage for TLS scope and end-to-end passthrough.

## 3.0.1
- Independently sign the native privileged helper before embedding it in Contents/Helpers.
- Verify the helper before and after copying to a fresh root-owned staging directory; report signature and SIGKILL diagnostics.
- Require a real root-level staged helper execution test in distribution CI, without changing host network settings.

## 3.0
- Bundle a relocatable CPython runtime and mitmproxy engine in the macOS application; remove runtime dependency on Homebrew.
- Add native arm64 and x86_64 distribution builds, DMG packaging, SHA-256 checksums and release automation.
- Add opt-in Developer ID signing, hardened runtime and Apple notarization pipeline.
- Add relocation and live HTTP/HTTPS smoke tests before publishing; retain explicit CA trust and administrator approval.
- Preserve existing mapping rules and user-generated CA files in Application Support.

## 2.5
- Replace `nohup` with a redirected background subshell to avoid macOS console-detachment failures.
- Repository packaging: add application icon, English documentation, CI configuration and contribution/security guides.

## 2.4
- Resolve the `load` lifecycle hook collision with mitmproxy.
- Capture bounded startup diagnostics and add a live loopback HTTP smoke test.

## 2.3
- Rename the custom add-on to avoid conflict with mitmproxy's built-in `MapRemote`.

## 2.2
- Add bounded readiness and preferences-lock waits, error diagnostics and recovery handling.

## 2.1
- Request CA trust in the logged-in user's session instead of an elevated non-interactive shell.

## 2.0
- Add AppKit/WebKit desktop shell, automatic system proxy configuration and recovery supervisor.

## 1.0
- Initial local HTTP/HTTPS mapping engine, rule editor and URL preview.
