# Security policy

MapRemote is a local development tool, not a production traffic gateway. HTTPS mapping requires explicit trust in a locally generated certificate authority. Only inspect traffic on devices and services you are authorized to use. Mapping can forward original request headers and bodies to a different host; choose destinations carefully.

Do not post CA private keys, credentials, tokens or real customer traffic in issues. Report vulnerabilities privately to the repository owner (use GitHub private vulnerability reporting if enabled). Include reproduction steps, version and impact, using sanitized data. No guaranteed response SLA is currently offered.

When finished, stop the proxy and remove its CA trust if it is no longer needed. Do not disable Gatekeeper or modify macOS authorization policies. If restoration fails, use the recovery action and verify Network settings before resuming normal use.
