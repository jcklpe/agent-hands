---
attention: historical
---
# Selective global skill installation — Tasks

Historical record. Closed 2026-11-17. Slug: `selective-skill-installation`. Current installation and recovery guidance lives in [Optional global skill links](../../setup-agent-hands/references/global-skill-links.md); Windows/Linux validation is [parked until relevant](../scratch/skill-installation-windows-linux-validation.md).
Opened: 2026-10-26. Slug: `selective-skill-installation`. [Concept](selective-skill-installation.md).

## To Do
No implementation items remain in the approved scope.

## Ready for Human QA
No remaining macOS acceptance check. The user confirmed Codex and Claude Code discovery and project-local-over-global selection through ordinary use. Windows/Linux verification is explicitly deferred until relevant and does not block closure. Closure and archival wording were approved on 2026-11-17.

## Done
- [x] Accept the user's 2026-11-17 confirmation that installed skills appear in Claude Code and project-local skills override global skills during ordinary use. This completes the selected macOS acceptance checks without claiming a fresh-machine installation. The current synthetic linker suite also passes all 17 tests with Python 3.12.
- [x] Verify Codex discovery during ordinary use on the current Mac (2026-11-17). The user reports the installed skills in the slash menu, and the active session exposes the relevant skills. Representative Gmail, Planner and provider setup links resolve to the intended source for both Codex and Claude; filesystem resolution alone does not establish Claude runtime discovery or precedence.
- [x] Inspect current setup ownership and installer behavior; identify automatic service-wide global links and separate the concurrent workflow pin.

- [x] Implement one shared preview/apply linker with explicit selection, conflict refusal, idempotence and recoverable exact-source repair. Implemented one standard-library primitive; conflicts preflight the whole selection and explicit exact-source repair preserves links with a recovery manifest.
- [x] Add service-owned entrypoints and update setup dialogue/guidance, README and standalone renderer routes without copying installation logic. Twelve owner entrypoints cover nine service setup owners, the optional setup dialogue and two standalone renderers. Multi-capability selections are explicit, and Google Calendar adds only its renderer dependency.
- [x] Remove Agent Hands link ownership from the containing dotfile installer and route users to service setup while preserving unrelated installer behavior. Removed 70 Agent Hands create/remove calls. All 61 unrelated installer calls are unchanged; the containing setup notice and README route to service-owned setup. Existing global links remain intact.
- [x] Verify selected/fresh/repeat/conflict/repair cases, shell invocation, skill/resource validation and private-file preservation; record platform/discovery limits. Sixteen synthetic tests pass on Python 3.9 and 3.13, all 33 skills validate, Bash/Zsh invocation and installer syntax/notice checks pass, and all 18 private metadata records plus 58 existing client links remain unchanged. Real existing Trello links preview as unchanged for both clients.
- [x] Commit reviewed source and containing installer/pin changes locally while excluding the concurrent Project Workflows pin. Source and containing installer/Agent Hands pin checkpoints are scoped locally. The separate workflow worker committed its new canonical workflow pin; this work excludes that path.

## Verification and recovery
Run `python3 setup-agent-hands/tests/test_skill_links.py` for the synthetic suite. Checks cover all owner entrypoints, selected/fresh/repeat installs, two-client preflight, relative links, missing sources, conflicting files/directories/links, explicit repair recovery, partial/racing failures, invocation through an installed symlink, and Bash/Zsh commands. No provider runtime code or service state changed, so unrelated service suites were not rerun. The prior Penpot process-inspection restriction remains untouched.

No live link was created or repaired for this feature. Future explicit repairs save old links and `recovery.json` beside the selected discovery root; maintained recovery instructions live in [the link procedure](../../setup-agent-hands/references/global-skill-links.md). Source recovery uses scoped local Git history. No pushes or credential changes occurred.

## Remaining client/platform verification
Windows/Linux linker and client checks are [parked until relevant](../scratch/skill-installation-windows-linux-validation.md) at the user's explicit direction. Current macOS acceptance rests on ordinary Codex/Claude use, the user's precedence confirmation and synthetic filesystem tests; fresh-machine onboarding is not claimed. Provider onboarding remains with the setup/use scope, and missing runtime/tool provisioning remains [captured separately](../scratch/agent-hands-cli-tool-provisioning.md).

## Closure — 2026-11-17
The user authorized closure after the macOS acceptance checks passed. Maintained installation, conflict and recovery guidance lives in [Optional global skill links](../../setup-agent-hands/references/global-skill-links.md) and service-owned setup entrypoints. No provider access, credential changes or new installation is needed for closure. The user approved the complete archival commit wording and this pair is archived.
