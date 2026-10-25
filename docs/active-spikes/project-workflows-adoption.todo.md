---
attention: live
---

# Project Workflows Adoption — Tasks
Opened: 2026-10-25. Slug: `project-workflows-adoption`.

## Background
The user requested a nested Project Workflows submodule, a project-specific branch created from its `main`, and documentation setup using the current setup skill. [Concept and ownership model](project-workflows-adoption.md).

## Project Organization
Agent Hands owns `AGENTS.md`, `README.md`, `TODO.md`, the existing CLI feedback pair, and this adoption pair. The nested `project-workflows/` repository owns its eight procedures, templates, ignored local-context convention, and the tracked Agent Hands configuration on `project/agent-hands`. The containing configs checkout and its separate Project Workflows adoption stay outside this change.

## General Principles
Preserve existing feedback and unrelated work. Use the current setup/run-spike/commit procedures, keep source notices and complete supporting files, and commit each repository's coherent scope separately. Publish only the refs covered by the later explicit authorization; do not install client skills, change credentials, or implement CLI proposals. A local commit is not proof of collaborator availability.

## Current State Overview
The initial local setup is complete. The follow-up renamed the workflow branch to `project/agent-hands`, adopted the accepted shared procedure improvements, preserved project configuration, and published the new workflow ref. Agent Hands consumer publication and a fresh public recursive clone now verify the exact nested workflow pin; client QA remains separate.

## To Do
No Git publication work remains in Agent Hands. Client QA and closure decisions remain separate.

## Ready for Human QA
- Confirm the intended agent client follows `AGENTS.md` into the adopted workflow files. Local routing and Git clone checks do not establish client discovery or interaction behavior.

## Done
- [x] Inspect actual repository state, remotes, current instructions, and the current Project Workflows setup procedure. Agent Hands began clean with the CLI feedback checkpoint; the containing configs checkout already showed that child advance. The public Project Workflows remote advertised `main` as its default branch and no existing Agent Hands project branch.
- [x] Add `project-workflows/` using the public upstream URL and create `codex/project-agent-hands` from its verified `main`. The branch belongs to the nested repository, not to Agent Hands or the containing configs workflow checkout.
- [x] Adapt the tracked workflow configuration and repository routing without replacing existing project guidance. Keep all eight procedures, templates, source notices, and private-context ignore rules; do not introduce unrelated provider or global-client setup.
- [x] Reconcile documentation setup with the existing CLI feedback pair. Preserve its concept and task content, add only a workflow-routing clarification to its task record, retain its index entry, and give this separate adoption scope its own pair and index entry.

- [x] Verify configuration parsing, document destinations, all eight skills and supporting resources, ignore behavior, links/frontmatter, branch ancestry, preserved feedback, and full selected diffs. Passed TOML/root resolution, eight skill frontmatter/resource checks, 80 local links, live attention markers, `.workflow.env` ignore checks, ancestry, unchanged concept content, additive-only task routing, and full selected-diff/whitespace review. The existing configs workflow checkout and outer recorded pin were preserved.
- [x] Commit the project-specific workflow configuration in the child repository, then commit the exact child pin and documentation integration in Agent Hands. The child checkpoint changes only `workflow.toml`; this Agent Hands checkpoint records the pin and directly related docs. Both are scoped local commits with spike trailers.

- [x] Rename the workflow adaptation to `project/agent-hands` and reconcile the reusable upstream update. The original `codex/project-agent-hands` name in the initial Done entries is historical. The new branch includes accepted shared `main`, retains only project configuration divergence, and tracks the published matching remote ref. Metadata and current routing use the neutral name; no folder or remote branch was deleted.

- [x] Publish the reviewed Agent Hands consumer checkpoint and verify a fresh remote recursive clone retrieves its exact nested workflow pin. Normal publication succeeded after full outgoing-range review. A fresh public recursive clone retrieved the recorded workflow commit, included accepted shared `main`, preserved feedback, and had clean parent/child status.

## Verification and Publication
The initial setup checks above remain its dated record. For the reconciliation follow-up, shared `main` and `project/agent-hands` are remotely available, accepted-main ancestry is verified, and the only resulting difference from shared `main` is Agent Hands configuration. The CLI feedback concept remains unchanged; no runtime or provider operation was performed.

The installed Python skill validator could not import PyYAML; direct YAML parsing and reference/TOML checks were used and the failure remains recorded in the coordinating workflow-reconciliation task. Consumer publication and fresh public recursive retrieval passed. Exact remote refs and the nested gitlink were verified; the final verification-record commit retains the same workflow pin. The outer configs pin will be updated locally; its unrelated existing unpublished commits are not part of this publication scope.
