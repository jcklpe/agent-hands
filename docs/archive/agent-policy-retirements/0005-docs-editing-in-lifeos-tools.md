---
attention: historical
reviewed: 2026-11-02
---
# Retain legacy 0005 policy history
Legacy identity: `0005`. Status: **retired** on 2026-11-02 under the user's explicit Agent Hands pilot approval. This record is historical, not an operative policy or procedure.

The reviewed current obligation is [KEEP-DOCS-PORTABLE](../../agent-policies/KEEP-DOCS-PORTABLE-separate-tools-from-domain-rules.md). Its identity/scope/dependent review is recorded in the [pilot](../agent-policy-pilot.todo.md). The old numeric identity remains reserved; this link supplies provenance, not a live override chain or independent adoption.

Original source: `docs/policies/0005-docs-editing-in-lifeos-tools.md`. Exact original SHA-256: `3f54773ee9084374376b963830c1fe1f952f524d28d56f7bf5f4d33578fae64c`. The full original bytes are preserved in the following literal block; dated implementation/permission claims below are historical and must be checked against the current skill. Legacy fragment anchors are retained for navigation.

<a id="0005-general-google-docs-capability-boundary"></a>
<a id="current-approach"></a>
<a id="rationale"></a>
<a id="links"></a>

````text
# 0005 General Google Docs Capability Boundary

Ownership update (2026-10-31): this document owns portable capability behavior and rationale. Account-specific history and private consumer decisions were separated from this public record. The numbered filename stays stable for navigation; the owning setup/use skills document current executable instructions.

## Current Approach
Maintain general Google Docs mechanics in `use-google-docs/`, with authorization in `setup-google-services/`. Invoke its documented native entrypoint. Preserve dry-run defaults, explicit execution, exact unique matches and revision guards.

The general capability must be usable without an organization-specific checkout. Consuming repositories own their domain procedures and may retain self-contained tooling when needed; this policy does not impose instructions on those repositories. The historical extraction accepted a small amount of duplication to preserve independent use.

Actual record edits require authorization from the consuming workflow. This service contract grants capability only and does not change that workflow’s approval rules.

## Rationale
Service-owned mechanics make the capability discoverable across workflows. Keeping domain rules with their consumers avoids making a portable capability depend on one organization’s repository, private workspace or meeting procedure.

## Links
- [Google Docs skill](../../use-google-docs/SKILL.md)
- [GitHub skill](../../use-github-issues/SKILL.md)
- [Docs editing history](../archive/lifeos-docs-editing.md)
- [GitHub tooling history](../archive/lifeos-github-sync.md)
````
