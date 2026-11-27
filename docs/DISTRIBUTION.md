# macOS distribution

MapRemote 3.0 packages CPython 3.12.16 from the pinned Python Build Standalone release 20261124 and mitmproxy 12.3.1 into the app. Its native shell and helper are compiled on the target architecture. Users do not need Python, Homebrew or Xcode. The build machine needs Apple Command Line Tools, Python 3 and network access.

## Architecture and releases

The [distribution workflow](../.github/workflows/distribution.yml) uses macOS 15 Apple Silicon and Intel runners. It tests the relocated application under a path containing spaces with a restricted PATH and temporary HOME; checks signatures; exercises real HTTP and HTTPS mapping using a temporary CA; builds a compressed DMG with an Applications symlink; and uploads checksums.

Both jobs must succeed before a preview is published. Pushes to main trigger ad-hoc-signed previews, not notarized releases. The manual workflow can produce a signed release only when all Apple Developer credentials are configured. If a release tag already exists, publishing fails rather than silently replacing assets.

## Apple Developer ID (owner only)

A paid Apple Developer Program membership and a **Developer ID Application** certificate are required for normal Gatekeeper-compatible distribution outside the App Store. Export the certificate and private key as a password-protected P12 from Keychain Access. Do not commit them or paste credentials into issues or chats.

Configure these repository Actions secrets:

| Secret | Value |
| --- | --- |
| APPLE_CERTIFICATE_BASE64 | Base64-encoded password-protected P12 |
| APPLE_CERTIFICATE_PASSWORD | P12 export password |
| APPLE_SIGN_IDENTITY | Full Developer ID Application signing identity |
| APPLE_ID | Apple account email |
| APPLE_TEAM_ID | Developer team identifier |
| APPLE_APP_PASSWORD | Apple app-specific password for notarytool |

Run **Actions → macOS distribution → Run workflow**, selecting main and enabling sign. The workflow imports the key into a temporary keychain, signs nested Mach-O code and the application with hardened runtime and secure timestamps, submits the app and DMG to Apple using notarytool, staples and validates tickets, and checks Gatekeeper assessment. Credentials are removed from the temporary runner keychain after the build. This is a configured pipeline, not proof that notarization has already succeeded.

For a local signed build, configure a Developer ID certificate in your keychain and a notarytool profile using Apple's official guidance. Export MAPREMOTE_SIGN_IDENTITY and MAPREMOTE_NOTARY_PROFILE before running Build.command and scripts/package-dmg.sh.

References: [Apple notarization documentation](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution), [notarytool workflow](https://developer.apple.com/documentation/security/customizing-the-notarization-workflow).

## Manual validation before stable release

- Install both DMGs on clean compatible Macs; confirm Finder launch, Start, Stop, normal quit, crash recovery, and network settings restoration.
- Verify the explicit administrator and local CA trust prompts in a logged-in user session.
- Confirm HTTPS mapping from a browser, removal of the exact CA, and preservation of existing proxy settings.
- Test supported older macOS versions. macOS 12 is the deployment target, not a tested compatibility guarantee.
- Audit privileged helper authorization and bundled third-party licenses before distributing broadly.

## Third-party components

The CPython distribution and mitmproxy are separately licensed. The runtime preserves upstream distribution notices and package metadata/licenses, and records resolved dependencies in installed-packages.txt. Transitive wheels are resolved at build time; a fully hash-locked wheelhouse, software bill of materials and redistribution/license audit remain follow-up tasks. MapRemote's own license remains undecided. Never bundle a generated CA private key, existing user rules, or signing credentials.
