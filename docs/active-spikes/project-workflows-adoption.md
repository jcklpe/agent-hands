---
attention: live
---

# Project Workflows Adoption

Current source: the collection uses an exact detached shared-main pin with project-owned settings in [docs/workflow.toml](../workflow.toml). [AGENTS.md](../../AGENTS.md) owns current routing. The setup and reconciliation details below describe their dated checkpoints; they do not direct agents to select the retired adaptation branch.

Opened: 2026-10-25. Slug: `project-workflows-adoption`.

Agent Hands adopts the complete Project Workflows collection as its root-level `project-workflows/` Git submodule at an exact detached shared-source pin. Configuration and local authority stay in Agent Hands. The containing configs project's separate workflow adoption is not the baseline for Agent Hands.

The initial request authorized local setup, including the project branch, documentation integration, and scoped commits. A later request on 2026-10-25 authorized platform-neutral naming, reusable upstream improvements, reconciliation of both adaptations, and scoped publication needed for retrievable pins. CLI fixes and provider configuration remain outside this work; outer configs pin coordination is tracked in its own workflow-reconciliation spike. See the [task record](project-workflows-adoption.todo.md) for checks and outstanding limits.

## Ownership and configuration
[workflow.toml](../workflow.toml) names `agent-hands`, resolves the project root as `..` from the documentation folder, and maps document locations inside Agent Hands. It selects unchanged shared source with project-owned settings outside the package. The Agent Hands gitlink pins the exact child commit; the branch setting in [.gitmodules](../../.gitmodules) is descriptive tracking metadata, not a substitute for that pin.

The complete shared procedures and supporting resources stay together at the collection root. Project configuration remains outside that package. Both repositories retain their AGPL-3.0-only LICENSE; the redundant owner NOTICE was removed in the later authorized cleanup. Actual project reasoning, tasks, and policies stay outside the workflow submodule.

The unused workflow env scaffold has been removed upstream. No workflow env file or private-context integration is required or created. Parent ignore rules and established private configuration remain with their existing owners.

## Documentation and routing
[AGENTS.md](../../AGENTS.md) points agents to the adopted collection and its configuration before global workflow seeds. [README.md](../../README.md) explains recursive submodule initialization, the detached shared-source pin and project-owned configuration. [TODO.md](../../TODO.md) remains the short index.

The existing [CLI feedback concept](cli-review-feedback.md) and [task record](cli-review-feedback.todo.md) stay at their original paths. The concept and its proposals are preserved; the task record receives only a current workflow-routing clarification. This adoption does not start any of its proposed CLI implementation work.

Active pairs live in `docs/active-spikes/`. The configured `docs/scratch/`, `docs/archive/`, and `docs/policies/` destinations are created when there is content for them. Empty placeholders and redundant folder READMEs add no useful record. No client installation or automatic discovery is implied by having nested skills; this setup provides explicit repository routing.

## Future reconciliation
Use the adopted [update-project-workflows](../../project-workflows/update-project-workflows/SKILL.md) to verify exact shared-source upgrades while preserving project-owned configuration and copied assets. Propose reusable procedure improvements upstream; project-only settings stay in Agent Hands.

A normal submodule update restores the recorded detached pin. Change settings in `docs/workflow.toml`; source experiments require their own reviewed scope. Publish an accepted shared revision before Agent Hands records that exact gitlink with its directly related documentation.

## Earlier naming and reconciliation follow-up
The initial branch was named `codex/project-agent-hands` using the setup skill's former fallback. The user's platform-neutral preference superseded that default. The local branch is now `project/agent-hands`, with matching configuration, consumer metadata, current routing, and Git upstream. Existing folder paths are unchanged. At that checkpoint the configs adaptation was separately named `project/configs`. Configs now uses canonical shared `main`; its containing repository stays on `master`.

The accepted shared `main` now covers neutral naming, clean extraction of reusable changes, mixed-commit handling, metadata/tracking repair, merges into each adaptation, nested consumer pins, complete outgoing-history review, and publication/clone evidence. This adaptation merges the accepted shared revision and retains Agent Hands configuration as its only tree difference from shared `main`. Shared guidance and both neutral project refs have been published; no old remote branch was deleted.

## Earlier publication and validation
The following records the initial published checkpoint, not the later local-only rollout below.
The user explicitly authorized scoped normal publication for this follow-up. Agent Hands contains only the reviewed feedback, adoption, and reconciliation commits beyond its prior remote tip. The containing configs repository has unrelated unpublished history, so its pin updates remain local rather than publishing that history with this change.

The consumer checkpoint is published, and a fresh public recursive clone retrieved its exact nested workflow pin and the accepted shared revision. Local checks cover configuration, links, inherited shared guidance, ancestry, and preservation of the feedback concept. Automatic client discovery and fresh-platform behavior remain unverified. Keep this pair live pending those QA and closure decisions.

## Local collection rollout
The later local-only rollout merges reviewed shared main `b79f368` into the existing `project/agent-hands` history from `f566247`. It brings root-level procedures, capture-for-later, removal of the unused env/NOTICE scaffold, and target-aware setup/update guidance. Agent Hands metadata remains intact. Current routing is updated without changing its 39 root service skills, feedback pair, tools, or existing notes. Earlier publication and recursive-clone checks describe the old pin; they do not verify availability of this new local merge. Security/privacy review and separate publication are still required before a fresh collaborator clone can retrieve it.

## Shared rollout follow-up
Reconciled shared main `8f6bdcf` locally, preserving this project's adaptation. The follow-up clarifies separately authorized list migration, incomplete parent scaffolds, and private local recovery. Publication remains on hold; the public source URL does not make this new child pin available remotely.
The bounded legacy-register check found no remaining pinned-issues or future-ideas list in this project's documentation; existing individual notes and deferred work were preserved.
