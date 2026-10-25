---
attention: live
---

# Project Workflows Adoption — Tasks
Opened: 2026-10-25. Slug: `project-workflows-adoption`.

## Background
The user requested a nested Project Workflows submodule, a project-specific branch created from its `main`, and documentation setup using the current setup skill. [Concept and ownership model](project-workflows-adoption.md).

## Project Organization
Agent Hands owns `AGENTS.md`, `README.md`, `TODO.md`, the existing CLI feedback pair, and this adoption pair. The nested `project-workflows/` repository owns its eight procedures, templates, ignored local-context convention, and the tracked Agent Hands configuration on `codex/project-agent-hands`. The containing configs checkout and its separate Project Workflows adoption stay outside this change.

## General Principles
Preserve existing feedback and unrelated work. Use the current setup/run-spike/commit procedures, keep source notices and complete supporting files, and commit each repository's coherent scope separately. Do not push, install client skills, change credentials, or implement CLI proposals. A local commit is not proof of collaborator availability.

## Current State Overview
Local setup and verification are complete. The workflow configuration is committed on `codex/project-agent-hands`; the Agent Hands checkpoint records that exact child pin with the related documentation. All shared procedure bodies remain unchanged. Publication, fresh remote recursive cloning, and client QA remain separate.

## To Do
No local setup work remains. Publication and closure decisions stay with the user; the external checks below remain outstanding.

## Ready for Human QA
- After the required child commit is published by the human, verify a fresh recursive clone can retrieve the Agent Hands pin and that the intended agent client follows `AGENTS.md` into the adopted workflow files. Local routing checks do not establish that client behavior or remote availability.

## Done
- [x] Inspect actual repository state, remotes, current instructions, and the current Project Workflows setup procedure. Agent Hands began clean with the CLI feedback checkpoint; the containing configs checkout already showed that child advance. The public Project Workflows remote advertised `main` as its default branch and no existing Agent Hands project branch.
- [x] Add `project-workflows/` using the public upstream URL and create `codex/project-agent-hands` from its verified `main`. The branch belongs to the nested repository, not to Agent Hands or the containing configs workflow checkout.
- [x] Adapt the tracked workflow configuration and repository routing without replacing existing project guidance. Keep all eight procedures, templates, source notices, and private-context ignore rules; do not introduce unrelated provider or global-client setup.
- [x] Reconcile documentation setup with the existing CLI feedback pair. Preserve its concept and task content, add only a workflow-routing clarification to its task record, retain its index entry, and give this separate adoption scope its own pair and index entry.

- [x] Verify configuration parsing, document destinations, all eight skills and supporting resources, ignore behavior, links/frontmatter, branch ancestry, preserved feedback, and full selected diffs. Passed TOML/root resolution, eight skill frontmatter/resource checks, 80 local links, live attention markers, `.workflow.env` ignore checks, ancestry, unchanged concept content, additive-only task routing, and full selected-diff/whitespace review. The existing configs workflow checkout and outer recorded pin were preserved.
- [x] Commit the project-specific workflow configuration in the child repository, then commit the exact child pin and documentation integration in Agent Hands. The child checkpoint changes only `workflow.toml`; this Agent Hands checkpoint records the pin and directly related docs. Both are scoped local commits with spike trailers.

## Verification and Publication
The project branch descends directly from the verified public `main` baseline; its only initial divergence is the Agent Hands configuration. The complete shared collection, templates, license, and source notices are retained. No runtime tests or external service operations were needed. The containing configs index and recorded Agent Hands pin remain unchanged.

The public upstream baseline was reachable, but the new child branch and Agent Hands checkpoint remain unpublished. A fresh remote recursive clone of the final pins and the intended client's workflow routing remain unverified. Publish the required child commit first, then the Agent Hands commit, under the human publication boundary. Updating the outer configs pin is a separate later action.
