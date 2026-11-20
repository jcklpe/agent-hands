---
attention: historical
tags:
  - spike
  - lifeos-tools
  - open-austin
  - architecture
---
# Spike: Open Austin Tool Boundary

Migration note (2026-10-30): moved from `configs/docs/archive/open-austin-tool-boundary.md` into Agent Hands as historical service-tooling context. Original body and task states are retained apart from navigation repairs. Old LifeOS commands, paths and account observations are not current Agent Hands instructions. The original Git history stays in the configs repository; stable slugs are unchanged. Current capabilities are documented in the [Agent Hands README](../../README.md).

## Status
- Complete and archived on 2026-07-29.

The private CLI now exposes only `open-austin-org path` and `sync`. Public issue creation and bounded shared-Doc tooling live in `<organization-repository>`; current LifeOS and configs instructions point to that authority.

## Purpose
Reduce the private LifeOS CLI's Open Austin surface to the thin adapter it actually owns: locate the public org repo, invoke its sync, and copy generated snapshots into LifeOS.

Reusable public writes belong in `<organization-repository>`. GitHub issue creation therefore moves to `work/org/tools/issues/create.sh`; bounded shared Google Docs writes live beside it. LifeOS keeps no duplicate implementation.

## Boundary
- `configs/lifeos-tools`: `open-austin-org path` and `open-austin-org sync` only.
- `work/org`: GitHub inspection, issue creation, weekly-meeting workflow, shared Google Docs reads/writes, and public write safety.
- `LifeOS`: generated snapshot context and private orchestration; never a second public write implementation.

## Compatibility Posture
The old `lifeos open-austin-org create-issue` command is removed rather than retained as a second wrapper. Current skills and docs point directly to the public org tool. Historical archived docs may continue to describe the command that existed at the time.
