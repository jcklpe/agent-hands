# Private PowerPoint browser setup
[PowerPoint Presentations](../../use-powerpoint-presentations/SKILL.md) uses the same owned Office browser lifecycle and authentication as [Word browser setup](word-browser.md), with a distinct PowerPoint add-in identity and operation store. The implementation is macOS-focused. There is no normal-profile attachment, cookie-copy route or shared-tab control.

## Install and select the account
Keep Microsoft Files and the selected provider working. Install Node 22+ and Google Chrome through their normal installers when authorized. From the checkout root:
```sh
npm ci --ignore-scripts --prefix use-word-documents
```
PowerPoint imports Word's locked Node dependencies and browser primitives. Keep both sibling folders; selecting the PowerPoint capability through the Microsoft skill linker includes Word and Microsoft Files as dependencies.

If this account already has an owned Word profile, reuse it directly. Do not initialize it again or copy credentials. For a new owned Office profile only:
```sh
node setup-microsoft-services/scripts/powerpoint-browser.mjs init example --port 43189
```
Choose an unused loopback port. State lives under the existing ignored `.word-state/ALIAS/` provider directory; PowerPoint's distinct configuration, generated fallback manifest and operation plans live in its `powerpoint/` child. The shared ownership marker and account lock serialize Word and PowerPoint operations. No path override is accepted. Verify ignores before initializing in another checkout.

Resolve an exact PPTX through Microsoft Files, then establish or renew normal sign-in if needed:
```sh
node setup-microsoft-services/scripts/powerpoint-browser.mjs login example --drive DRIVE_ID --item ITEM_ID
```
Only this login window is visible; it closes after the selected browser identity matches Graph. Complete the tenant's ordinary MFA. Graph PowerShell/MSAL authentication does not replace the browser sign-in. A valid existing owned profile is reused without a new login requirement.

## Automatic setup
For an authorized edit permitting document metadata:
```sh
node setup-microsoft-services/scripts/powerpoint-browser.mjs prepare example --drive DRIVE_ID --item ITEM_ID --execute
```
Preparation installs/opens **Agent Hands → Open PowerPoint tools** in the owned headless browser, saves automatic startup and independently verifies the package's linked add-in reference and startup setting. `document_prepared` confirms that metadata; no content edit was sent. Reads and previews require the presentation already prepared and never install an add-in implicitly. This per-document setting is automated; it is not a separate document-scoped authentication grant.

If normal English controls or the tenant's add-in policy prevent automatic setup, the explicit visible fallback is:
```sh
node setup-microsoft-services/scripts/powerpoint-browser.mjs configure example --drive DRIVE_ID --item ITEM_ID --execute
```
It prints a private manifest path, opens only the owned profile, and waits for the user to upload the manifest through PowerPoint's Add-ins → Advanced → Upload My Add-in route and open **Open PowerPoint tools**. It then saves and independently verifies startup. Report partial setup if verification fails. Never bypass a tenant restriction or fall back to a whole-file replacement to escape an open-file lock.

## Privacy and document metadata
The presentation retains an add-in identity/catalog reference, task-pane association and automatic-startup property. These travel with copies and can produce an unavailable add-in pane for recipients. The add-in writes only its startup boolean and authorized slide text; it does not embed browser cookies, authentication caches, bridge run tokens or private keys. The bridge manifest is local; the document is not a transferable signed-in session.

Cookies and other browser session storage remain in the shared owned Office profile. Chrome's sandbox and native credential protection are retained, but not all profile storage is encrypted. Keep the entire directory owner-only, ignored, unshared and outside public backups or folder exports. Graph credentials remain in the provider's separate authentication store. The bridge uses an independent random per-run token in memory, binds only to loopback, verifies host/origin and exact document identity, and accepts fixed commands. It retains the Word launcher's scoped certificate trust and local-network permission bounds.

Read output contains presentation text for the calling agent. Private plans contain file/shape identifiers and before/after text; journals retain dispatch state. Verification downloads are removed on ordinary completion. An abrupt termination may leave a private download or profile lock; reconcile rather than deleting records to force replay. The CLI does not generate real-account screenshots, page dumps or browser storage exports. The read/write add-in and its dependencies are trusted local code, so this is not protection against a compromised local account.

## Recovery and acceptance limits
Use `powerpoint status` and cloud-only `powerpoint verify` for a dispatched operation. Never repeat its mutation. Keep the shared profile lock if a browser shutdown fails, and establish that its recorded process and owned Chrome have stopped before deliberate stale-lock recovery. Authentication renewal uses `login`; normal Chrome remains untouched. The shared certificate expires after a year and still requires deliberate maintenance, as documented for Word.

This tool requires independent cloud verification because PowerPoint autosaves instead of exposing Word's document-save method. Same-shape edits are non-atomic; coordinate them and inspect uncertain outcomes. The completed prototype established two-way different-shape text edits on one disposable macOS presentation with the user's browser open. The packaged two-slide test verified automatic setup/reuse, exact targeting, cloud persistence and stale/replay refusal. [Historical evidence](../../docs/archive/powerpoint-live-editing.todo.md) records those checks; [deferred validation](../../docs/scratch/powerpoint-validation.md) retains the follow-up. Windows/Linux, wider tenant deployment, sustained use and PowerPoint-specific interrupted-save/MFA-renewal acceptance are deferred.

## Primary references
- [PowerPoint TextRange](https://learn.microsoft.com/en-us/javascript/api/powerpoint/powerpoint.textrange?view=powerpoint-js-preview).
- [PowerPoint Presentation](https://learn.microsoft.com/en-us/javascript/api/powerpoint/powerpoint.presentation?view=powerpoint-js-preview).
- [Automatic task-pane startup](https://learn.microsoft.com/en-us/office/dev/add-ins/develop/automatically-open-a-task-pane-with-a-document).
- [Shared browser security and recovery](word-browser.md#document-metadata-and-session-security).
