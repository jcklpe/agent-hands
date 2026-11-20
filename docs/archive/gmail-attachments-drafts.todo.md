---
attention: historical
---
# Gmail attachments and manually sent drafts tasks

Historical record. Closed 2026-11-17. Slug: `gmail-attachments-drafts`. Maintained commands and safeguards live in [Use Gmail](../../use-gmail/SKILL.md) and the [mail-write policy](../agent-policies/BOUND-MAIL-WRITES-limit-reversible-filing.md).

## Scope
Implement the user's requested native Gmail attachment reads and drafts for manual sending. Keep private mail/documents outside the public source tree and preserve concurrent work. No send, signing, acceptance, consent expansion, publication or containing-repository pin update.
## Done
- Recheck the existing Gmail CLI and inspect OAuth scope metadata. No attachment/draft commands existed. Google's draft-create API accepts modify/compose grants; neither is draft-only. No credentials or scope configuration changed.
- Implement exact-message attachment listing/downloading, including embedded bytes and external attachment IDs, private output publication and preserved old files on failures.
- Implement preview-first draft creation with explicit recipients, optional reply threading/attachments, action-time opt-in, mailbox/content verification and review links.
- Restrict native mutation transport to supported filing/filter/draft-create endpoints; send endpoints are refused before token acquisition or HTTP.
- Amend the existing mail-write policy only for the explicitly requested Gmail draft exception. Identity/dependencies remain intact; standing rules and Outlook remain unchanged.
- Run all Gmail regression checks, inspect the complete selected diff and install the reviewed source changes. All six Gmail test programs pass on macOS Bash/Python 3.14; source is installed through the existing skill link. The complete 11-policy graph/index passes the existing checker. The optional skill validator lacks PyYAML in the existing Python runtime; frontmatter and local references were checked separately without installing dependencies.
- Verify attachment reads on the authorized live target without copying private evidence into this repository. Listing and binary download succeeded for two selected messages with separate owner-only output files; original document review stays in the private caller workspace.
- Finish permitted follow-up QA without a real draft or send. Expanded mocks cover exact account/returned-thread review URLs, folder fallback, new and reply MIME requests, altered content/IDs/SENT labels and mismatched threads. A reproduced create-response/readback thread disagreement is now rejected, including new-draft readback mismatches. Native Quick Look produced a first-page preview on the private target; complete Word pagination remains unverified. Scope research confirms that separate compose authorization still permits sending and insert-only access cannot create API drafts. No credentials, grants or account flags changed.
## Ready for Human QA
No remaining visual check for the selected draft capability. Live creation, readback, attachment round trip and review-link inspection passed on 2026-11-17. The synthetic draft remains unsent; actual sending and recipient-side delivery are outside this capability and were not tested. Closure and archival wording were approved on 2026-11-17.

## Live QA — 2026-11-17
- Exercise a real, user-authorized draft, confirm its review link opens the right draft, then manually send only after reviewing recipients/content. No real draft or send is part of offline validation. — Draft QA completed through the native CLI and separately approved browser inspection. The manual-send action in the original QA wording was not performed: the authorized capability and this test stop at an unsent draft.
- Created one synthetic, self-addressed draft after preview, using existing account access and the action-time draft opt-in. Native readback verified the account, unsent state, recipient, subject, paragraphs, Unicode text and attachment hash. No credentials, persistent account settings or grants changed.
- Listed the exact draft's MIME attachment and downloaded the selected part to a private owner-only file. All 74 bytes matched the synthetic source. The returned account-specific review link opened the exact draft in Gmail; its subject, separated paragraphs, Unicode and attachment rendered correctly.
- All six Gmail shell regression programs passed with an existing supported Python environment. Existing private audit receipts also showed successful draft creation during ordinary use; no private IDs, addresses, browser snapshots or message contents were copied into public records.
- One test draft remains in the selected mailbox. No mail was sent or deleted, no other draft was edited, and existing browser tabs were preserved. QA tabs were separate from the user's existing tabs.

## Closure — 2026-11-17
The user authorized closure after successful QA. Maintained commands, draft safeguards and private-state handling live in [Use Gmail](../../use-gmail/SKILL.md); the [mail-write policy](../agent-policies/BOUND-MAIL-WRITES-limit-reversible-filing.md) owns the adopted write boundary. Sending, recipient delivery and complete Word pagination are outside this capability's acceptance scope. No deletion, additional mailbox write or push is part of closure.
