---
attention: historical
---
# Canvas snapshot companion
Historical record. Closed October 31, 2026. Stable slug: `canvas-snapshots`. Current behavior and limits belong to [Use Canvas Snapshots](../../use-canvas-snapshots/SKILL.md).
## Purpose
Provide a reusable local consumer of native Canvas exports: validate identity and coverage, compare stable resources, retain unresolved findings and replace a recognized snapshot safely. Keep service transport and authentication in use-canvas. Keep project interpretation and work ownership in the calling workflow.

## Design
One standard-library-only CLI lives beside its owning `use-canvas-snapshots/SKILL.md`. All selections, runtime locations, consumer markers and storage destinations are explicit caller inputs. The tool returns neutral findings and preserves unresolved state without prescribing a project structure or task system. Comparison and acknowledgment are offline; refresh invokes the native export interface.

## Bounds
No remote content writes, automatic credential setup, new provider dependencies or background jobs. No historical exports are archived automatically. Publication replaces only a recognized local package; symlinks, unknown formats and incomplete retrieval are refused. Fixtures and examples use synthetic sources and identities.

## Review state
Implementation review is complete. The companion, its standalone packaged installer and live refresh passed the checks recorded in [tasks and verification](canvas-snapshots.todo.md). Explicit user authorization covered global links for Codex and Claude and live refresh. The user approved the local commit and spike closure on October 31, 2026; no push is authorized. Maintained behavior and limits belong to [Use Canvas Snapshots](../../use-canvas-snapshots/SKILL.md).
