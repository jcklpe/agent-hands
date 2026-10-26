---
attention: live
---
# Selective global skill installation — Tasks
Opened: 2026-10-26. Slug: `selective-skill-installation`. [Concept](selective-skill-installation.md).

## To Do
No implementation items remain in the approved scope.

## Ready for Human QA
Fresh Codex/Claude discovery and fresh Linux/Windows environments are not yet verified. No actual client links, credentials or service permissions need changing to implement this feature.

## Done
- [x] Inspect current setup ownership and installer behavior; identify automatic service-wide global links and separate the concurrent workflow pin.

- [x] Implement one shared preview/apply linker with explicit selection, conflict refusal, idempotence and recoverable exact-source repair. Implemented one standard-library primitive; conflicts preflight the whole selection and explicit exact-source repair preserves links with a recovery manifest.
- [x] Add service-owned entrypoints and update setup dialogue/guidance, README and standalone renderer routes without copying installation logic. Twelve owner entrypoints cover nine service setup owners, the optional setup dialogue and two standalone renderers. Multi-capability selections are explicit, and Google Calendar adds only its renderer dependency.
- [x] Remove Agent Hands link ownership from the containing dotfile installer and route users to service setup while preserving unrelated installer behavior. Removed 70 Agent Hands create/remove calls. All 61 unrelated installer calls are unchanged; the containing setup notice and README route to service-owned setup. Existing global links remain intact.
- [x] Verify selected/fresh/repeat/conflict/repair cases, shell invocation, skill/resource validation and private-file preservation; record platform/discovery limits. Sixteen synthetic tests pass on Python 3.9 and 3.13, all 33 skills validate, Bash/Zsh invocation and installer syntax/notice checks pass, and all 18 private metadata records plus 58 existing client links remain unchanged. Real existing Trello links preview as unchanged for both clients.
- [x] Commit reviewed source and containing installer/pin changes locally while excluding the concurrent Project Workflows pin. Source and containing installer/Agent Hands pin checkpoints are scoped locally. The separate workflow worker committed its new canonical workflow pin; this work excludes that path.

## Verification and recovery
Run `python3 setup-agent-hands/tests/test_skill_links.py` for the synthetic suite. Checks cover all owner entrypoints, selected/fresh/repeat installs, two-client preflight, relative links, missing sources, conflicting files/directories/links, explicit repair recovery, partial/racing failures, invocation through an installed symlink, and Bash/Zsh commands. No provider runtime code or service state changed, so unrelated service suites were not rerun. The prior Penpot process-inspection restriction remains untouched.

No live link was created or repaired for this feature. Future explicit repairs save old links and `recovery.json` beside the selected discovery root; maintained recovery instructions live in [the link procedure](../../setup-agent-hands/references/global-skill-links.md). Source recovery uses scoped local Git history. No pushes or credential changes occurred.
