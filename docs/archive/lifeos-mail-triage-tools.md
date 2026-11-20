---
attention: historical
---
# LifeOS Mail Triage Tools
Opened: 2026-09-30. Closed: 2026-11-18. Slug: `lifeos-mail-triage-tools`.

Historical record of the completed spike. Maintained behavior and limits belong to [Use Gmail](../../use-gmail/SKILL.md), [Use Outlook Mail](../../use-outlook-mail/SKILL.md), their provider setup references and [BOUND-MAIL-RULES](../agent-policies/BOUND-MAIL-RULES-limit-standing-automation.md).

Ownership update (2026-10-30): moved from `configs/docs/active-spikes/lifeos-mail-triage-tools.md` into Agent Hands. Stable slug, recorded decisions, completed work and open QA are preserved; this move does not close or reactivate the spike. Current native guidance: [use-gmail](../../use-gmail/SKILL.md), [use-outlook-mail](../../use-outlook-mail/SKILL.md). The aggregate `lifeos` launcher and compatibility tree are retired; old commands and test paths below record the original implementation, not a current entrypoint.

Status: closed 2026-11-18 after explicit approval of closure and the complete archival wording. Continues from [LifeOS Microsoft 365 Mail Archive](../active-spikes/lifeos-m365-mail-archive.md), which added archive, folder moves, labels, and spam rescue.

## Purpose
Give the `lifeos` mail commands what an agent needs to walk a person through **per-email triage toward inbox zero**: each message gets a recommended outcome, and the person approves outcomes one message at a time. The calling vault owns the workflow and its judgment (what counts as noise, how tasks are framed, where information is filed). This repo supplies the capabilities.

A triage outcome may combine archiving, tagging, turning the email into a follow-up task, snoozing, or filing the information elsewhere. Alternatively it may leave the email for the person, or mark it for later deletion and archive it, optionally unsubscribing. A spam and junk check sits alongside: real mail in Spam is rescued, and spam means scams or unsolicited advertising, not merely unwanted mail.

## What Exists (2026-09-30)
- Gmail: `labels`, `list`, `archive`/`unarchive`, `label [--skip-inbox]`/`unlabel`, `create-label`, `spam`, `not-spam`.
- Microsoft 365: `mail folders`, `mail list`, `mail archive`/`unarchive`, `mail move`, `mail create-folder`, `mail junk`, `mail not-junk`, `mail attachments`.
- Trello `add-card`, `comment`, and `snooze`, for follow-up tasks.
- Bounded Inbox snapshots via `gmail sync` and `m365 mail sync`.

## Gaps
Revised 2026-09-30. The `lifeos` tools stay procedural and deterministic; the triage judgment and the approval slate live in the calling vault's skill, not here. Most of what triage needs already exists in `gmail sync` / `m365 mail sync`, which write IDs, sender, subject, date, labels, read state, and body text (to the vault, or to any `--output` file). The remaining gaps are additions to that sync, not new commands:

1. **Gmail web link** in the sync output: `https://mail.google.com/mail/u/?authuser=ADDRESS#all/THREAD_ID`. Microsoft 365 output already carries Graph's `webLink`.
2. **Unsubscribe header** in the sync output: the `List-Unsubscribe` value (and whether `List-Unsubscribe-Post` one-click is offered), so a person can click it. Unsubscribing itself stays manual.
3. **HTML-to-text** for HTML-only messages. These currently render as raw markup and CSS, so their bodies are unreadable in the snapshot.
4. **A query override** (for example `--query`) on `gmail sync`, so a one-off run into a scratch `--output` file can see beyond the configured window without changing the account config.
5. **Rate-limit reliability.** One configured account's sync failed from about 2026-09-15 with a bare `curl: (56) ... 403`. The underlying Gmail error was `rateLimitExceeded` on the per-user query-cost quota. It recovered on 2026-09-30 after the inbox shrank. Surface Google's error message, back off and retry, and let `--all` continue past one failing account ([REJECT-GUESSES](../agent-policies/REJECT-GUESSES-stop-writes-with-unknown-critical-values.md): name the cause).
6. **Outlook categories** (`m365 mail categorize` / `uncategorize`), only if the calling workflow tags Microsoft 365 mail. Deferred until asked.
7. **Junk training on Microsoft 365.** `not-junk` is a folder move and may not train Outlook's filter. Check whether Graph v1.0 has a supported action.
8. **Standing filters and rules** (scope widened 2026-10-02 at the user's request). Triage kept re-tagging the same senders by hand, so recurring patterns become Gmail filters and Microsoft 365 Inbox rules, limited to labeling or categorizing, skipping the Inbox, and moving to an allowed folder. See [BOUND-MAIL-RULES](../agent-policies/BOUND-MAIL-RULES-limit-standing-automation.md).
9. **Address-specific duplicate rules** (scope widened 2026-10-07 at the user's request). Native Microsoft 365 rules can combine sender and recipient matching and move duplicate-address mail to Deleted Items. `--delete` requires complete sender and recipient addresses; permanent deletion and one-off message deletion stay out of scope. See [BOUND-MAIL-RULES](../agent-policies/BOUND-MAIL-RULES-limit-standing-automation.md#duplicate-mail-exception).

Dropped 2026-09-30: **snooze**, which neither Gmail's API nor Graph exposes (people snooze in the mail client); **one-click unsubscribe automation**, since people click the link themselves for now; and **a separate triage listing or full-message read command**, which the sync with `--output` covers.

## Out Of Scope
Sending mail, sending replies, creating drafts in the mailbox, one-off message deletion, permanent deletion, mark-read, filters or rules that forward, redirect, or mark read, snooze, automated unsubscribing, and any scheduler. Native deletion rules are restricted to item 9's explicitly authorized sender-and-recipient duplicate cleanup. Drafted replies stay in the chat. Whether mailbox drafts are ever wanted is an open question for later.

## Later drafting proposal (2026-11-13)
The out-of-scope paragraph above preserves this triage spike's original implementation boundary, not a current claim that mailbox drafts are unwanted. Gmail draft creation was added separately in [Gmail attachments and drafts](../archive/gmail-attachments-drafts.md). The user has now selected the existing `use-outlook-mail` capability as the home for a future Outlook drafting action, with genuine reply relationships, account-specific signature handling, formatting and quoted-history readback. See the [Outlook reply-draft record](../archive/outlook-reply-drafts.md) for the captured scope and guardrails. A broader composition/orchestration skill, if needed later, may belong in LifeOS rather than Agent Hands. This note does not implement drafting, widen this triage work, change current policy or authorize sending.

## Safety
Same model as 0007: exact IDs, dry-run by default, per-call caps, readback, the ignored audit log, and per-account opt-in. Items 1–7 are reads or output-format changes; items 8–9 write standing rules, under their own opt-in flags (`gmail.filters_enabled`, `mail.rules_enabled`) and [BOUND-MAIL-RULES](../agent-policies/BOUND-MAIL-RULES-limit-standing-automation.md).

## Related
- [LifeOS Microsoft 365 Mail Archive](../active-spikes/lifeos-m365-mail-archive.md), the predecessor.
- [BOUND-MICROSOFT-ACCESS](../agent-policies/BOUND-MICROSOFT-ACCESS-limit-delegated-service-access.md), [REJECT-GUESSES](../agent-policies/REJECT-GUESSES-stop-writes-with-unknown-critical-values.md), [BOUND-MAIL-WRITES](../agent-policies/BOUND-MAIL-WRITES-limit-reversible-filing.md), [BOUND-MAIL-RULES](../agent-policies/BOUND-MAIL-RULES-limit-standing-automation.md).
- `agent-hands/use-gmail/SKILL.md`, `agent-hands/use-outlook-mail/SKILL.md`.

## Gmail read reliability — 2026-11-17
The user selected the remaining non-export read-retry gap for implementation. Route native Gmail GETs through the existing Gmail-specific rate-limit helper, including message lists, labels, filters, write previews and readback. Preserve request arguments, account/target bounds and single-dispatch mutations. Exercise throttling, exhaustion, non-retryable errors and post-write readback using synthetic transport only; this work does not create a live filter, change grants, send mail or authorize publication.

The reliability change is implemented and fixture-verified: eight command-level Python tests and all six Gmail shell programs pass. GET retries retain the exact request, and no write transport was placed behind a retry loop. A non-JSON HTTP 429 still follows the bounded retry policy; exhausted or non-retryable reads retain useful errors. Preview failures stop before writes, and failed filing readback explicitly reports that the mutation was already sent. The first live Gmail filter creation is recorded separately below; synthetic tests alone do not establish it. Maintained behavior lives in [Use Gmail](../../use-gmail/SKILL.md); [Google's error guide](https://developers.google.com/workspace/gmail/api/guides/handle-errors) supplies the rate-limit classifications.

## Live Gmail filter verification — 2026-11-18
An explicitly approved disposable rule was previewed and created once through the native macOS CLI using an existing opted-in account. Both a reserved synthetic sender and a unique subject were required; its only action was Inbox removal for future matching mail. The preview found no existing matches. Exact-ID readback and an independent filter listing verified the complete criteria and action, exactly one added rule, unchanged prior rules and a successful private audit record. No mail was sent or retroactively changed, and no label, grant or persistent account setting was added. Raw receipts and actual account/rule identifiers remain owner-only outside Git.

The live create/readback acceptance passes. After separate deletion-only approval, the exact disposable rule was removed once; an independent listing exactly matched the original filter set, and both private audit records verified. Matching-arrival behavior was not exercised; message delivery and consumer triage decisions remain separate from portable rule creation/readback. Closure and the complete archival wording were approved on 2026-11-18.
