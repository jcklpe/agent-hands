---
name: setup-workday
description: "Assess Workday transport and authorization prerequisites and diagnose the current offline-only CLI. No live Workday transport or browser-session attachment is implemented."
---
# Setup Workday
This capability is an incomplete integration with a usable offline contract. Read [transport status and prerequisites](references/transport.md) before attempting setup. The use skill owns the [offline CLI and draft-save engine](../use-workday/SKILL.md); this setup skill owns future service transport, session binding and authorization. No unrelated provider or personal vault is required.

1. Use Python 3.9+ and system IANA timezone data. Run `python3 use-workday/scripts/workday doctor` from the checkout root. Its current exit status 2 and `TRANSPORT_UNAVAILABLE` are intentional; it does not contact Workday or inspect a browser.
2. Use supplied normalized snapshots for local validation and preview. Keep actual worker identifiers, schedules, snapshots, plans and journals outside version control, or under the ignored `private/` directory in this skill. Verify ignores before storing anything; use owner-only directory/file permissions (0700/0600). Do not copy credentials or browser state into fixtures.
3. To finish integration, establish one documented, authorized API/MCP client or supported host attachment from the intended runtime. Confirm exact tenant/worker binding, complete week retrieval, timezone, classifications, payroll periods and draft-only semantics. A missing personal client or empty search result is not proof that the tenant prohibits integration.
4. Respect the consumer's browser approval requirements. Implementation permission does not authorize browser use. Never extract cookies, copy profiles, guess private debugging endpoints or change browser security settings. Prefer existing-session reuse only where the host documents and permits it; a separate profile requires an explicit choice.
5. Before enabling writes, implement and verify the bounded adapter contract and recovery described in the transport reference. Do not run payroll test writes for onboarding. Real operations require their exact target/data authorization; submission remains unsupported.

No installation, PATH links, client registration, authorization grant, dedicated browser profile or credentials are created by this skill. Invoke the repository-relative command directly. Global installation and fresh-client discovery are not implemented or claimed. Offline checks run on macOS; Linux/WSL and native Windows remain unverified. The private journal uses Unix `fcntl` locking and is not a native Windows implementation.
