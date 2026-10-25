---
attention: live
---

# Project Workflows Adoption
Opened: 2026-10-25. Slug: `project-workflows-adoption`.

Agent Hands now adopts the complete Project Workflows collection as its root-level `project-workflows/` Git submodule. Its project branch is `codex/project-agent-hands`, created from the shared `main` branch. The branch lives inside Project Workflows so project-specific configuration and later procedural adaptations retain a shared ancestor for reconciliation with upstream. The containing configs project's separate workflow adoption is not the baseline for Agent Hands.

The user authorized local setup, including the project branch, documentation integration, and scoped commits. Publication, CLI fixes, provider configuration, and changes to the containing configs repository's recorded pin remain outside this work. See the [task record](project-workflows-adoption.todo.md) for checks and outstanding limits.

## Ownership and configuration
[workflow.toml](../../project-workflows/workflow.toml) names `agent-hands`, resolves the project root as `..` from the collection, and maps document locations inside Agent Hands. It records the public upstream URL, upstream branch `main`, and project branch. The Agent Hands gitlink pins the exact child commit; the branch setting in [.gitmodules](../../.gitmodules) is descriptive tracking metadata, not a substitute for that pin.

The full set of eight procedures and supporting templates stays together. The initial project adaptation changes configuration only; shared skill bodies, license text, and source notices are retained. Agent Hands and Project Workflows both declare AGPL-3.0-only and retain their source notices. Actual project reasoning, tasks, and policies stay outside the workflow submodule.

The collection's `.workflow.env.example` remains the generic optional private-context template. Its real `.workflow.env` is ignored and no private context file is created. The parent ignore rules are retained rather than copying unrelated build/editor patterns from the setup template.

## Documentation and routing
[AGENTS.md](../../AGENTS.md) points agents to the adopted collection and its configuration before global workflow seeds. [README.md](../../README.md) explains recursive submodule initialization, project-branch selection, and the publication dependency. [TODO.md](../../TODO.md) remains the short index.

The existing [CLI feedback concept](cli-review-feedback.md) and [task record](cli-review-feedback.todo.md) stay at their original paths. The concept and its proposals are preserved; the task record receives only a current workflow-routing clarification. This adoption does not start any of its proposed CLI implementation work.

Active pairs live in `docs/active-spikes/`. The configured `docs/scratch/`, `docs/archive/`, `docs/policies/`, and `docs/pinned-issues.md` destinations are created when there is content for them. Empty placeholders and redundant folder READMEs add no useful record. No client installation or automatic discovery is implied by having nested skills; this setup provides explicit repository routing.

## Future reconciliation
Use the adopted [update-project-workflows](../../project-workflows/skills/update-project-workflows/SKILL.md) to compare shared ancestry, preserve intentional project differences, and reconcile later upstream changes. Keep Agent Hands metadata on its project branch. Separate reusable procedure improvements into focused changes suitable for upstream review; no such procedural changes are needed for initial setup.

A normal submodule update may leave the collection at detached HEAD. Before editing it, select `codex/project-agent-hands` and verify its relationship to the Agent Hands pin. Do not reset an existing project branch or replace local differences with a global copy. Scoped child changes are committed first, then Agent Hands records the corresponding gitlink and directly related documentation together.

## Local readiness and publication boundary
The public upstream `main` was verified and cloned without stored credentials. The new project branch and its configuration commit are local. A collaborator cannot be assumed to obtain that commit from the recorded URL until it has been published there; no fresh remote recursive clone of the final unpublished adoption is claimed.

Publication is a separate human step: make the child project branch/commit available at the recorded Project Workflows URL before publishing an Agent Hands commit that pins it. The outer configs checkout can later record the Agent Hands pin under its own scope. This setup does not push any repository or update that outer pin.

Current validation establishes local configuration, file routing, preserved content, Git ancestry, and the nested pin. It does not establish another agent client's discovery, fresh-platform operation, or remote availability of the unpublished commits. Keep the spike live pending the user's publication/QA and closure decisions.
