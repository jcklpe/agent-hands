# Private Word browser setup
The [Word capability](../../use-word-documents/SKILL.md) runs its own headless Chrome process and uses Word's Office.js coauthoring session to save. Its Microsoft Graph dependency only checks identity, resolves exact targets and downloads cloud readback. A Graph sign-in does not sign a browser in. An existing Word web sign-in can run the prototype, but this packaged route deliberately owns a separate profile so ordinary Chrome can continue independently.

## Install and initialize
Install Node 22+ and Google Chrome using the platform's normal installer when authorized. Keep the selected Microsoft provider and Microsoft Files dependencies working. From the Agent Hands checkout root:

```sh
npm ci --ignore-scripts --prefix use-word-documents
node setup-microsoft-services/scripts/word-browser.mjs init example --port 43189
```

Choose an unused loopback port and retain it. The command creates private state in the designated user-state root: `~/.agent-hands/office/ALIAS/` on all platforms, resolving `~` to the current user’s home directory. `AGENT_HANDS_STATE_DIR` selects an absolute private base directory; `office/ALIAS/` is appended. Checkout and symlink roots are refused. The account contains the owned browser directory, certificate/key, manifest and operation records. Actual state is never tracked; the source inventory and synthetic fixtures are tracked. There is no arbitrary browser-directory option, profile import or cookie-copy function. Never point the launcher at ordinary browser data or delete an active profile lock. The supported setup flow establishes its own sign-in; an explicitly requested session-transfer experiment must remain separate, use only the selected service state, preserve the source browser, and verify the resulting account. Profiles persist between invocations and are never reset automatically.

Chrome's sandbox remains enabled, and the launcher removes Playwright's mock-keychain/basic-password-store flags so Chrome uses its normal platform credential protection. Native credential-store access can itself need an OS prompt; do not suppress that protection to make a run headless. Platform-specific guarantees still need testing.

The loopback server binds only `127.0.0.1`. The owned Chrome process trusts only the generated certificate's public-key fingerprint through Chromium's scoped SPKI switch; no operating-system trust store is modified and unrelated HTTPS errors are not disabled. The certificate expires after a year; expiry stops execution until deliberate renewal. Browser local-network permission is granted only for the exact target origin and observed Microsoft Office frame origins. Tenant/browser restrictions are independent of Graph consent.

## Office file contract
The whole account is private persistent state, never a tracked fixture or disposable run folder. Its owner-only root protects browser-created descendant files whose original modes are preserved.

| Files | Purpose/content | Removal boundary |
| --- | --- | --- |
| `account.json`, `browser/agent-hands-owner.json` | Account alias, owner and add-in identities, loopback configuration and local bridge path; browser ownership binding | Keep with the complete account. Do not regenerate to bypass a failed write. |
| `browser/` | Dedicated Chrome sign-in, catalog, cache and other browser-managed storage | Credential-bearing. Keep for account reuse; intentional account retirement is separate from cleanup. Do not sweep individual browser files. |
| `key.pem`, `cert.pem`, `manifest.xml` | Private HTTPS key/certificate and generated add-in manifest | Keep with the account. Renew certificate explicitly; account retirement handles keys and manifest. |
| `plans/*.json`, `plans/*.journal.json` | Exact document targets, before/after text, preview hashes and dispatch outcomes | Preserve unresolved operations. Completed records may be retired only after outcome verification and an intentional retention decision. |
| `powerpoint/` | PowerPoint add-in settings and equivalent plans/receipts | Shares the browser/account lock; migrate and retire together with Word state. |
| `lock.json`, browser singleton markers | Controller and native-browser ownership/serialization | Never expire by age. Diagnose and establish stopped owners before manual recovery. |
| `.migration-ALIAS.json` beside account directories | Private source/destination, owner, phase and tree fingerprint | Created before a move, removed after verified success; retain on failure until explicit reconciliation. |
| Legacy `.word-state/ALIAS/account.json` tombstone | Credential-free destination pointer and retired-store type | Retain while older installed clients could use the old location. It prevents duplicate profiles/journals. |
| Atomic-write `*.tmp` siblings | In-progress settings/journal/certificate publication | Owner-controlled writes publish by rename; interrupted leftovers require writer/outcome inspection, not blanket deletion. |

Cloud verification downloads and synthetic test profiles instead use per-run private system temp with scoped cleanup. Real configuration stays private/untracked; the existing provider `.env.example` and account JSON examples are tracked synthetic setup references. Default Office storage needs no configuration file; callers can explicitly set `AGENT_HANDS_STATE_DIR` in their private process environment, consistently across Word and PowerPoint. Public evidence consists of procedures, fake fixtures and sanitized results. No default screenshot, raw response or browser-state export is retained.

## Existing Office state migration
Existing `.word-state/ALIAS/` accounts or the earlier platform-specific Office state roots require explicit migration; normal operations and initialization stop rather than choosing an empty replacement journal. Stop every Word/PowerPoint caller, including older installed revisions, for the whole operation:

```sh
node setup-microsoft-services/scripts/word-browser.mjs migrate-state example
node setup-microsoft-services/scripts/word-browser.mjs migrate-state example --execute
```

Preview identifies the exact locations, a content/permission fingerprint and the complete shared account scope. Execution locks the source, refuses native browser singleton markers or destination collisions, and atomically renames the whole account on the same filesystem. It verifies the complete file tree, including Word/PowerPoint plans and journals, without exporting credentials. Existing browser-created descendant file modes are preserved behind the owner-only account root. A credential-free legacy tombstone prevents old clients from loading or initializing the migrated account. It is intentional persistent routing state, not a forgotten temporary file. Keep the selected state override consistent across all callers; changing it requires another deliberate migration. Do not relocate the owned browser alone or copy an ordinary personal profile.

If exactly one account exists in the known legacy roots, migration selects it; multiple live copies refuse. Existing retired pointers are updated after the verified move. An interrupted move retains `.migration-ALIAS.json` in the private destination root. That record blocks normal new-client use; it includes source/destination, ownership, phase and the expected tree hash. Stop all callers and inspect both locations before recovery. Before the rename, the original account is authoritative; afterward, the destination is authoritative and may retain its migration lock. Verify the complete destination fingerprint excluding the migration lock, preserve every journal, restore the source tombstone if necessary, and clear only the verified migration record/lock after confirming the controller and browser stopped. Do not merge stores, auto-retry a move, replay document writes or fall back to a fresh sign-in. Cross-filesystem migration and automated crash reconciliation are not implemented.

The initial macOS migration preserved the installed shared Office account byte-for-byte and a fresh headless Word read reused its sign-in. Other platforms have synthetic path selection only; live migration is unverified there. Provider/MSAL/Graph PowerShell authentication stays with its existing owner.

## Temporary readback cleanup
Each new Office readback directory contains an owner-only `.agent-hands-run.json` registration with its controller PID, creation time and random run identity. Ordinary completion/failure removes the entire run directory in `finally`. Before creating another readback, cleanup removes only registered Word/PowerPoint readback directories at least 24 hours old whose controller is confirmed absent. Live PIDs (including reused ones), permission-denied checks, unregistered folders, unsafe permissions and symlinks are preserved. Only the relevant readback prefixes in the selected validated system temp root are considered; no general temp sweep is performed.

Run an explicit preview or cleanup without opening a browser:

```sh
node setup-microsoft-services/scripts/word-browser.mjs cleanup-temp example
node setup-microsoft-services/scripts/word-browser.mjs cleanup-temp example --execute
```

This is on-demand/next-use cleanup, not a scheduled daily service. Power loss or SIGKILL can leave readable private bytes until the next cleanup. Owner-only permissions limit access by other users but do not encrypt content or protect it from same-user malware. No zero-retention or secure-erasure claim is made. Historical unregistered temp folders require separate classification; they are not automatically deleted. Microsoft shell request/cache cleanup remains its separate owner and currently lacks this Office registration mechanism.

## Deliberate certificate maintenance
Inspect expiry without changing state, then renew only when maintenance is intended:

```sh
node setup-microsoft-services/scripts/word-browser.mjs renew-certificate example
node setup-microsoft-services/scripts/word-browser.mjs renew-certificate example --execute
```

Renewal acquires the account lock and refuses existing browser singleton markers, unsafe file ownership/permissions, symlinks or a certificate/key mismatch. It preserves the private key and public-key fingerprint, account and add-in identities, manifest, browser sign-in and dispatch journals. Only the certificate is replaced, through a validated, owner-only temporary file and atomic rename. No system trust store, document metadata or service permissions change. This is validity renewal, not key rotation or remediation for a compromised key. No automatic renewal or stale-lock reclamation is performed. A failed or interrupted maintenance operation requires inspection before another attempt; it never authorizes deleting profiles, browser singleton markers or dispatch records.

## Prepare an authorized document headlessly
After one normal sign-in in the owned profile, Agent Hands can do per-document setup without manual manifest uploads. For an authorized Word editing target:

```sh
node setup-microsoft-services/scripts/word-browser.mjs prepare example --drive DRIVE_ID --item ITEM_ID --execute
```

The command verifies the selected account and document, opens the bridge from the ribbon or installs the generated manifest through Word's upload dialog, saves startup and checks the setting in an independent cloud download. It uses deterministic English Word web controls in the owned headless browser; document editing itself uses Office.js. A verified existing startup setting is reused without another save. It never navigates or closes normal Chrome tabs and sends no body-text edit. The next read/preview/apply invocation starts the add-in automatically.

Preparation is a metadata write covered by an authorized editing task that permits this route, not by a read-only request. It requires `--execute` and the existing file-write opt-in. There is no bulk enrollment of unrelated documents, tenant-wide deployment, new permission grant or whole-file replacement. A missing sign-in needs `login`; unavailable/localized upload controls, tenant restrictions or a failed bridge connection require the visible `configure` fallback below. A failed setup may already have inserted the add-in reference, so report that partial result and inspect it; do not bypass policy or repeat content edits.

Uploading can open the task pane before Word exposes its ribbon button. Setup accepts the authenticated bridge for the exact document in that case; ribbon appearance is not an additional success requirement. A cloud startup flag alone does not establish that the current browser can load the add-in. If a read returns `addin_setup_required`, an authorized `prepare` can restore the catalog/pane connection while reusing a verified existing startup setting.

## Authenticate and configure an authorized document
Resolve the selected document through Microsoft Files and retain both drive and item IDs. For sign-in alone, run `login` with those IDs. For visible fallback when automatic preparation cannot complete, run:

```sh
node setup-microsoft-services/scripts/word-browser.mjs configure example --drive DRIVE_ID --item ITEM_ID --execute
```

The command prints the manifest path and opens only the separate Agent Hands browser. Complete the tenant's ordinary sign-in/MFA there. Open Word's Add-ins dialog, choose Upload My Add-in, select the printed manifest, then open **Agent Hands → Open Word bridge**. Word's menu placement varies: the upload dialog may be under Home → Add-ins → Advanced, and the bridge command may be inside Home's More Options overflow menu. The tool verifies the browser account and exact document before requesting automatic startup. It closes its own browser when the startup save returns. A successful setting save is not yet independent cloud verification; next run:

```sh
node use-word-documents/scripts/word.mjs read example --drive DRIVE_ID --item ITEM_ID
```

This fresh headless process must start the add-in automatically and return the document body. Installing the add-in and enabling startup are setup steps per profile and document; they do not authorize arbitrary document edits. Upload UI availability is not proof that a tenant permits installation. Do not create application registrations, broaden consent or bypass MFA to make setup pass. If authentication or add-in installation is unavailable, keep it pending and continue only local validation.

Normal Chrome and native Word need not be closed. If authentication expires, `login` reopens only the tool-owned profile and waits for normal sign-in. `configure` additionally changes this document's startup setting, so use it only within approved setup scope. Neither command copies a normal browser session. The profile is credential-bearing private data and must not be committed or shared.

Authentication is per account and reused across documents. Exact document checks prevent accidental edits to another target; they do not require a separate credential or permission grant for each document. The automatic-startup setting remains per document because that is Word's mechanism. Graph PowerShell's CurrentUser cache already supports the independent file checks, but it is not a replacement for the browser sign-in. Graph access tokens are audience-bound to Graph and do not authenticate the Word web editor; see [Microsoft's resource/audience guidance](https://learn.microsoft.com/en-us/graph/resolve-auth-errors). No SDK-cache extraction or token-to-cookie conversion is implemented.

## Document metadata and session security
The DOCX stores an add-in identity/version, a catalog reference, task-pane association and the automatic-startup property. These are document metadata and travel with downloaded or shared copies. The sideloaded implementation's manifest, HTML and JavaScript remain in the browser catalog/local service rather than becoming a portable signed-in session. A recipient may see an add-in reference, prompt or unavailable pane depending on their Office setup; ordinary document content remains standard Word content.

The inspected disposable packages contained only the expected add-in metadata: no browser cookies, OAuth tokens, bridge run token, private key or local service URL. The generated add-in writes only the startup boolean to Office document settings; content replacement writes the authorized text. Cookies remain in the private owned browser, Graph authentication remains with the provider, and the bridge's separate random per-run token exists in process/page memory. The manifest's opaque localhost path is not an authentication credential; requests still need the run token, exact host/origin and verified document. Downloading the document does not grant the downloader the author's Microsoft session or remote access to the author's loopback server.

The entire local profile/provider state must remain owner-only, ignored and unshared. Native cookie encryption does not encrypt all browser storage: Local Storage and session-restore files can contain readable session tokens. Chrome and Playwright handle usable session data in memory and send matching cookies to the relevant HTTPS sites; the account-identity request shares the browser cookie jar. The loopback bridge uses its own temporary token. Graph authentication remains separate. Git ignores do not protect folder archives, filesystem backups or synchronization.

Reads return document body text to the calling agent, and previews retain document identifiers and before/after paragraph text in private plan files. Browser caches and diagnostic exports can also retain content. Verification downloads are removed on ordinary completion, while abrupt termination can leave private temporary files. Retain live dispatch journals for reconciliation; remove retired experiment artifacts only under the selected cleanup scope. The add-in has read/write permission to the open document, so its code and dependencies are trusted code. Tenant edit/add-in restrictions still apply. This design does not certify arbitrary document content as secret-free, protect against a compromised local account, or establish a workflow for removing add-in associations from distribution copies.

## Acceptance and recovery
Before relying on a tenant, use a disposable document. Verify a headless read, preview/apply, independent cloud text, and a second editor's visibility; then change a different paragraph in the second session and verify both edits survive. Check a stale target, interrupted save and normal sign-in renewal. Keep all ordinary tabs open during isolation checks. A local fake host does not substitute for these checks.

If a process is interrupted, the dispatch journal remains authoritative. Run `node setup-microsoft-services/scripts/word-browser.mjs recovery-status example` for read-only diagnosis even while the profile is locked. It reports the lock controller as running, not running or unknown and lists native browser singleton marker names without resolving their targets. A running PID can be reused; absent markers do not prove the owned browser stopped. The diagnostic never removes locks, signals processes or authorizes automatic recovery. `word verify` only reads cloud content and never replays an edit. An existing `lock.json` is not auto-reclaimed: establish that its recorded tool process and owned Chrome process have stopped before manually removing only that stale lock. Never kill Chrome by application name. Do not erase the profile or journal to clear a login or save failure.

The runtime is experimental. Automatic preparation, reuse without another setting save, fresh headless read/edit/save and content-preserving setup passed on a new disposable document using an already authenticated profile with the manifest installed. The automatic upload branch has synthetic browser coverage and earlier deterministic live upload evidence. A separate disposable macOS Chrome test verified installation, cloud-persisted automatic startup, fresh headless read/edit/save and independent cloud text/formatting checks while another same-account Word web editor remained open. The second editor confirmed the agent's change; its subsequent edit in a different paragraph appeared in both a fresh headless read and a cloud download with both edits and untouched formatting preserved.

Next-day headless startup reused the sign-in and persisted setting. A stale preview was refused before dispatch. An intentional process kill after Word saved but before acknowledgment left an uncertain journal; after deliberate stale-lock recovery, cloud-only verification confirmed the edit and the same operation could not be dispatched again. Synthetic headless checks additionally cover refusal before mutation, failed synchronization after insertion, during save and before readback, plus an aborted result report that leaves a durable uncertain dispatch and refuses replay. These checks do not establish every tenant/network failure or fully automatic crash recovery. Two synchronized same-range Word edits produced mixed text despite successful save returns; cloud verification rejected both intended replacements. Avoid simultaneous edits to the same paragraph and inspect uncertain outcomes before any new preview. Linux/Windows onboarding, different-user coauthoring and sustained use remain unverified. Tenant Conditional Access can require human reauthentication; this is not a permanent MFA-free service.

An explicitly authorized session-loss test cleared cookies only in the owned profile while retaining its add-in catalog and other setup. Headless identity verification returned `authentication_required`; the normal `login` command opened only that profile, the user completed MFA, and the selected account was verified. After the visible window closed, a fresh headless read started the add-in automatically. Independent cloud checks confirmed the startup setting and unchanged document body. No normal-profile access, global sign-out, cookie export or add-in reinstallation occurred. This verifies interactive recovery from deliberate local session loss, not every tenant-triggered expiry or Conditional Access policy.

The initial macOS route is accepted within the stated operation and security bounds. [Reliability history](../../docs/archive/word-runtime-reliability.md) records completed checks and retained limits. Actual tenant-triggered expiry and longer sustained use remain unverified; future concrete failures can open focused spikes. [Windows/Linux validation](../../docs/scratch/word-windows-linux-validation.md) is parked until a concrete platform need arises; portable source is not a claim that those environments have been tested.

## Primary references
- [Microsoft: Office add-in privacy and security](https://learn.microsoft.com/en-us/office/dev/add-ins/concepts/privacy-and-security).
- [Microsoft: automatic task-pane startup](https://learn.microsoft.com/en-us/office/dev/add-ins/develop/automatically-open-a-task-pane-with-a-document).
- [Microsoft: sideloading add-ins](https://learn.microsoft.com/en-us/office/dev/add-ins/testing/sideload-office-add-ins-for-testing).
- [Microsoft: Word Range API](https://learn.microsoft.com/en-us/javascript/api/word/word.range?view=office-js).
- [Playwright: persistent browser contexts](https://playwright.dev/docs/api/class-browsertype#browser-type-launch-persistent-context) and [browser permissions](https://playwright.dev/docs/api/class-browsercontext#browser-context-grant-permissions).
- [Chromium: scoped SPKI certificate verification](https://chromium.googlesource.com/chromium/src/+/HEAD/services/network/ignore_errors_cert_verifier.h).
