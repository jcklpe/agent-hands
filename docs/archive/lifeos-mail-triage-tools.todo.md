---
attention: historical
---
# LifeOS Mail Triage Tools — To Do
Opened: 2026-09-30. Closed: 2026-11-18. Slug: `lifeos-mail-triage-tools`.

Historical record of the completed spike. Maintained behavior and limits belong to [Use Gmail](../../use-gmail/SKILL.md), [Use Outlook Mail](../../use-outlook-mail/SKILL.md), their provider setup references and [BOUND-MAIL-RULES](../agent-policies/BOUND-MAIL-RULES-limit-standing-automation.md).

Privacy separation (2026-11-02): consumer-specific passages and actual account-validation chronology were preserved privately before removal from this public record. Portable requirements, recorded tooling evidence and stable slugs remain; historical instructions below are not current operating guidance.

Ownership update (2026-10-30): moved from `configs/docs/active-spikes/lifeos-mail-triage-tools.todo.md` into Agent Hands. Stable slug, recorded decisions, completed work and open QA are preserved; this move does not close or reactivate the spike. Current native guidance: [use-gmail](../../use-gmail/SKILL.md), [use-outlook-mail](../../use-outlook-mail/SKILL.md). The aggregate `lifeos` launcher and compatibility tree are retired; old commands and test paths below record the original implementation, not a current entrypoint.

Concept: [lifeos-mail-triage-tools.md](lifeos-mail-triage-tools.md).

## Current State
- 2026-10-07: address-specific duplicate rules implemented with `--recipient-contains` and bounded `--delete` (to Deleted Items). Complete rule conditions, exceptions, enabled state, sequence, and actions now undergo readback checks. Offline tests pass; one explicitly requested native duplicate-mail rule was created and fully verified by live readback. Matching-arrival behavior awaits a later real message.
- 2026-10-02: scope widened to standing Gmail filters and Microsoft 365 Inbox rules; commands built, tested offline, read-verified live, and all four accounts re-authorized. No filter or rule has been created yet.
- Implemented 2026-09-30: sync reliability, web links, unsubscribe headers, HTML-to-text, and the query override. Live-verified on one Gmail account and one Microsoft 365 account: every message has a link, 8 of each inbox carried unsubscribe headers, and no stylesheet text leaked into bodies. Full offline suite green.
- Decisions settled the same day: no junk report to Microsoft, and Outlook categories added.

## To Do
- [x] Add sender-and-recipient native duplicate-mail rules at the user's request (2026-10-07): complete address requirements, refusal of category/folder combinations with deletion, no permanent deletion, full readback verification, and offline negative tests for altered predicates or actions.
- [x] Verify an approved duplicate-mail rule by live create and full readback (2026-10-07). Exact sender and recipient conditions, enabled state, delete-to-Deleted-Items action, and stop-processing action all matched.
- [x] Observe the approved duplicate-mail rule's behavior on a later matching arrival without sending synthetic mail. — Deferred to the consumer’s rule-validation work; no matching arrival was observed by this documentation cleanup. Portable rule creation/readback and predicate coverage remain recorded here.
- [x] Gmail sync reliability: `_gmail_get` surfaces Google's error reason and message, backs off (2 s, doubling) and retries on 429 and 403 `rateLimitExceeded`/`userRateLimitExceeded` up to `LIFEOS_GMAIL_MAX_RETRIES` (default 5), and names a remedy. `--all` continues past a failing account, reports every failure, exits non-zero, and leaves failed snapshots unchanged.
- [x] Fixed an ordering bug found along the way: per-message files were named `0.json … 10.json` and globbed in text order, so snapshots interleaved out of order. They are now zero-padded.
- [x] Gmail web link in sync output (`- Link:`).
- [x] `List-Unsubscribe` / `List-Unsubscribe-Post` in sync output for both services (`- Unsubscribe:`, marked "one-click supported"). Microsoft 365 requests `internetMessageHeaders`.
- [x] HTML-to-text: both renderers drop `<style>`, `<script>`, `<head>`, and `<title>` content, and Gmail treats an HTML document inside a `text/plain` part as HTML.
- [x] `--query` and `--max-results` overrides on `gmail sync`, refused unless combined with `--output` or `--qa`, so the vault snapshot keeps its configured query.
- [x] Offline tests: `tests/test-mail-sync-triage.sh`, mutation-checked against style skipping, HTML-in-plain detection, rate-limit retry, and `--all` continuation.
- [x] Microsoft 365 junk: checked. Graph's `markAsNotJunk` was beta-only and was retired on 2025-12-30. The replacement, `reportMessage`, reports to Microsoft (outward-facing). `not-junk` keeps moving rescued mail into the Inbox; the no-filter-training limit is documented in the `lifeos-m365` skill.
- [x] Docs: `lifeos-gmail` and `lifeos-m365` skills, README, and `lifeos help`.
- [x] `not-junk` decision (the user, 2026-09-30): rescued mail goes into the Inbox and is triaged like any other item, which is current behavior. No report to Microsoft.
- [x] Outlook categories (the user asked 2026-09-30): `m365 mail categorize` / `uncategorize`, categories shown in `mail list` and the snapshot, offline tests, a live add-then-remove round trip on one the managed tenant message, and a 0007 addendum.
- [x] Preserve configured Inbox export bounds; callers can use bounded listing/reads for additional coverage. Consumer account preferences are retained privately.
- [x] Scope widened to standing filters and rules (the user, 2026-10-02), recorded in [0009](../archive/agent-policy-retirements/0009-mail-filters-and-rules.md) with a 0007 amendment.
- [x] Gmail filters: `gmail filters`, `create-filter` (from/to/subject/query; one user label and/or skip Inbox), `delete-filter`; dry run previews recent matches. Needs `gmail.filters_enabled` (adds `gmail.settings.basic`).
- [x] Microsoft 365 Inbox rules: `m365 mail rules`, `create-rule` (from/sender-contains/subject-contains; category, allowed-folder move, stop), `delete-rule`. Needs `mail.rules_enabled` (adds `MailboxSettings.ReadWrite`).
- [x] Offline tests: `tests/test-mail-filters.sh`. Representative Gmail filter and Microsoft 365 rule reads were verified live (2026-10-02). Actual account and reauthorization chronology is retained privately.
- [x] First live Gmail filter create verified on 2026-11-18 with an explicitly approved disposable rule; complete independent readback and unchanged prior rules passed. Microsoft 365 category-rule creation/readback was verified on 2026-10-02, and a bounded duplicate-mail rule was created and verified on 2026-10-07; those are completed rule checks, not pending first creates. Further rule changes require their own authorization.

## Found in use (2026-09-30)
The recorded read-retry gap is completed below; the original item is preserved with its outcome.
- [x] One-click (RFC 8058) unsubscribe URLs from Google and Spotify return a 405 when opened in a browser. Consider marking them in the sync output so the triage workflow links to the email instead. — The native Gmail and Outlook renderers mark the header as "one-click supported", with fixtures in `use-gmail/tests/test-transport-render.sh` and `use-outlook-mail/tests/test-rich-body.sh`. Automated unsubscribe remains out of scope; the consumer chooses its presentation and handling.

## Ready For Human QA
- None. the user confirmed on 2026-09-30 that the `Link` lines open the right threads.

## Done
- [x] `gmail list`, `gmail spam`, `gmail labels`, and the label commands still fetch with `_google_get_url` (`curl -f`). On Gmail's per-minute rate limit they print a bare `curl: (56) ... 403` with no retry. Route them through `_gmail_get` like the sync. This hit right after a wide `--query` sync on 2026-09-30. — Completed 2026-11-17: all remaining native Gmail GETs now use `_gmail_get`, including filter reads, write previews and readback; mutation transport remains single-dispatch.
- [x] Spike opened (2026-09-30).
- [x] Scope trimmed (2026-09-30): snooze, unsubscribe automation, and a separate listing or read command dropped.
- [x] Implementation above (2026-09-30).

## Completed reliability work — 2026-11-17
- [x] Route remaining native Gmail GETs through the existing bounded retry helper, preserving exact requests and write safeguards. — Completed for all nine bypassing call sites; HTTP 429 with a non-JSON body also reaches bounded retry under shell errexit. Failed target reads preserve the actual cause instead of claiming the target does not exist.
- [x] Test command-level throttling, exhausted retries, non-rate-limit errors, truthful failure reporting and single-dispatch writes with synthetic transport. — Eight new Python test methods with command/status variants pass, along with all six existing Gmail shell regression programs. A fresh Bash process uses synthetic curl responses; a successful mutation followed by throttled or exhausted readback sends exactly one mutation. Baseline checks reproduced single-attempt failures before the routing change.
- [x] Update maintained guidance and the work index, review public-safe scope and checkpoint the reliability change locally. — Commands and limits live in [Use Gmail](../../use-gmail/SKILL.md); scoped source/fixture, local-link, whitespace and private-ignore checks pass. The reliability checkpoint includes the owning portable spike pair, not other untracked imports or unrelated changes.

The reliability implementation used synthetic transport. The separately authorized live filter test is recorded below.

## Live disposable filter — 2026-11-18
- [x] Resolve the existing account and opt-in through the native provider, preview complete synthetic conditions and the sole skip-Inbox action, and verify no existing match or duplicate probe rule.
- [x] Obtain exact-rule approval, create once and independently verify full criteria/actions, exactly one new rule, all prior rules unchanged and a verified private audit receipt. Existing grants and persistent configuration were preserved; no mail was sent or changed retroactively.
- [x] Prepare an exact-ID, read-only deletion preview after successful verification.
- [x] Obtain isolated deletion-only approval, remove the disposable rule once and verify the original filter set is restored. — Approved and completed 2026-11-18; native deletion readback and an independent full-set comparison passed. Both create/delete audit records verified; no message, draft, label or other filter was deleted.
- [x] Review closure and its complete archival wording after cleanup. — Explicitly approved 2026-11-18; the full pair is archived with historical attention.

Native create/readback passed on macOS. There was no actual matching arrival, other-platform test or credential expansion. Account identity, actual rule ID, raw responses and audit receipts remain outside Git in owner-only storage.

## Closure readiness — 2026-11-18
No selected implementation or live-acceptance item remains. Maintained command behavior and limits belong to [Use Gmail](../../use-gmail/SKILL.md), [Use Outlook Mail](../../use-outlook-mail/SKILL.md) and their provider setup references; standing-rule approval remains governed by [BOUND-MAIL-RULES](../agent-policies/BOUND-MAIL-RULES-limit-standing-automation.md). These owners retain bounded reads, explicit previews, per-account opt-ins, readback, private audit and single-dispatch writes. Actual matching-arrival behavior and consumer triage policy remain outside the completed portable create/readback check. Windows/Linux live access is not claimed. Closure and the complete archival wording were approved on 2026-11-18; this pair is archived. No publication is authorized.
