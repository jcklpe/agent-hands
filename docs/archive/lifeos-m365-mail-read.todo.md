---
attention: historical
---
# LifeOS Microsoft 365 Mail Read — To Do

Historical record. Closed and archived 2026-10-31 during the authorized documentation separation. Stable slug: `lifeos-m365-mail-read`. Exact-message reads and mailbox/folder search were implemented and live-checked on archived and sent messages on 2026-10-05. The optional folder/search export was explicitly deferred and is not completed by closure; it stays recorded below as future scope. Current behavior belongs to [use-outlook-mail](../../use-outlook-mail/SKILL.md). No service operation, code change or new live QA was performed for this closure.

Ownership update (2026-10-30): moved from `configs/docs/active-spikes/lifeos-m365-mail-read.todo.md` into Agent Hands. Stable slug, recorded decisions, completed work and open QA are preserved; this move does not close or reactivate the spike. Current native guidance: [use-outlook-mail](../../use-outlook-mail/SKILL.md). The aggregate `lifeos` launcher and compatibility tree are retired; old commands and test paths below record the original implementation, not a current entrypoint.

Concept: [lifeos-m365-mail-read.md](lifeos-m365-mail-read.md).

## Current State
- 2026-10-05: read and search built, tested offline, and live-checked on the selected institutional alias. Only the optional sync scope remains, deferred until a caller needs a scratch file rather than stdout.

## Deferred optional scope (not completed)
- [ ] Optional: `m365 mail sync ALIAS (--folder … | --search …) --output FILE`, refused without `--output`. Deferred; `mail read` and `mail list --search` covered the first real use.

## Earlier manual check (covered by recorded live evidence)
The archived/sent-message reads and searches below were already verified on 2026-10-05 as recorded in Done. This closure does not claim a new human run.
- `lifeos m365 mail list institution --search 'from:someone received>=2026-10-01'`, then `lifeos m365 mail read institution --message ID` on a hit in Archive or Sent Items.

## Done
- [x] Spike sketched (2026-10-05).
- [x] Decision settled as an inline amendment to 0004 (2026-10-05).
- [x] `m365 mail read ALIAS --message ID [--full] [--json]`: headers, recipients, text body, attachment names, folder, web link; any folder (2026-10-05).
- [x] Web link in `m365 mail list` output, text and `--json` (2026-10-05).
- [x] `m365 mail list ALIAS --search "KQL" [--folder …]`: mailbox-wide by default, Junk Email left out unless named, folder per hit (2026-10-05).
- [x] Offline fixture tests, mutation-checked (2026-10-05).
- [x] Live check: an archived reply and a sent reply read in full; a phrase search and a `received>=` search across Archive and Sent Items (2026-10-05).
- [x] Docs: `lifeos-m365` skill, README, `lifeos help` (2026-10-05).
