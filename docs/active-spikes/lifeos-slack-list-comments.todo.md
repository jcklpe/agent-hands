---
attention: live
---
# LifeOS Slack List Comments Tasks

Ownership update (2026-10-30): moved from `configs/docs/active-spikes/lifeos-slack-list-comments.todo.md` into Agent Hands. Stable slug, recorded decisions, completed work and open QA are preserved; this move does not close or reactivate the spike. Current native guidance: [use-slack-lists](../../use-slack-lists/SKILL.md). The aggregate `lifeos` launcher and compatibility tree are retired; old commands and test paths below record the original implementation, not a current entrypoint.

## Background
Slug: `lifeos-slack-list-comments`. Add the smallest supported discussion interface without guessing IDs, changing persistent permissions, posting test messages, or closing the spike.
## Current State
Implemented automatic per-item root discovery in a known List conversation, URL-free reads, and dry-run-first comments including first user comments on existing zero-reply roots. Live reads and one explicitly authorized disposable first-comment send are verified; offline checks and the bounded visual result are recorded below.
## To Do
- Keep the spike open pending explicit closure authorization. The bounded send test is verified; full archival wording review is the remaining closure step.
## Ready for Human QA
- No additional send is needed. The authorized comment passed exact readback and was rendered under the expected author in Slack search. The List view stalled, so reliable deep-link navigation is not established.
## Done
- Verify one specifically approved comment send, author, rendered text, discussion association, and API permalink in Slack. If Slack normalizes text, inspect any `PARTIAL` result before considering a retry. Completed through exact API readback and delegated search-view visual QA; direct List navigation retains the limit below.
- Obtain a specifically approved live destination and comment before exercising `lists comment --execute`; do not duplicate an existing real comment. Completed on 2026-11-20 after the user selected a disposable test item/comment and retained cleanup responsibility.
- Inspect CLI, official APIs, existing identity/scopes, and supplied discussion read-only. Verified user identity, available scopes, root association, three existing replies, and real API permalink. Item metadata lacks a thread locator.
- Add bounded List item comments read/post commands with dry-run-first behavior, target/identity checks, readback, and API permalinks. `lists comments` and `lists comment` initially required a copied existing comment URL and refused mismatched or missing root metadata. Follow-up history discovery below removes the per-item URL requirement. Partial/uncertain sends are surfaced without automatic retries.
- Add offline tests and maintained CLI/skill documentation. Test commands: `python3 agent-hands/compat/lifeos/tests/test-slack-comments.py` and `bash agent-hands/compat/lifeos/tests/test-slack.sh`; both pass (11 new unittest cases plus existing Slack regression checks). The new read command also passed against the supplied live discussion and returned its API root permalink. A bounded scan found no invalidated vault skill assumptions. New tests use invented IDs and text only.
- Investigate supported conversation/history/search routes and official SDKs beyond item-info metadata. Full conversation listings omitted the known file discussion, but history exposed a matching root for every current List item, including many with no replies. This corrects the initial first-comment limitation; user comments can target those roots without creating a new root.
- Add automatic history discovery and verified per-List mapping. `discussion_channel_id` is now supported in account List entries, with optional `--channel` / `--url` overrides. The supplied List's verified mapping was saved only in ignored local config; no credentials or permissions changed. Missing/ambiguous roots, stale mappings, pagination failures, and mismatched root readback are refused. URL-free reads passed live for the supplied item and a zero-reply item. All 21 offline cases plus existing Slack regression checks pass; first-comment sends are mock-tested only.
## Remaining API limitation
A previously unknown List needs a verified discussion conversation mapping. The original investigation did not establish a supported lookup: `files.info` was denied for missing `files:read`, and message search was unavailable to that test. Later conversation-search support does not itself prove List-to-conversation bootstrap. No supported method for creating a genuinely missing root was established in public Lists methods or official SDK types. This is distinct from first comments on the accessible roots already present. One specifically approved disposable send is now verified as recorded below; unknown-List mapping and genuinely missing-root creation remain unimplemented. No permission changes occurred.

## Live send and delegated visual QA — 2026-11-20
- Created one clearly named synthetic List item with no assignee or due date, after the user authorized a disposable item and offered to delete it afterward. Create preview and readback agreed on the exact name and description.
- Automatic discovery found its zero-reply root; comment preview then one execution verified exact text, expected author, exact List/item/thread association and the API-returned permalink. No retry or second comment was sent.
- Slack web search returned one result and visibly rendered the exact comment under the expected author and List. The List view remained at a loading screen after one reload, so this does not certify direct record/permalink navigation. No message was forwarded.
- The test item/comment remain for user cleanup. Account IDs, item/thread identifiers, actual link and screenshot remain outside Git; no other List item, status or grant changed.
