---
attention: historical
reviewed: 2026-11-02
---
# Retain legacy 0006 policy history
Legacy identity: `0006`. Status: **retired** on 2026-11-02 under the user's explicit Agent Hands pilot approval. This record is historical, not an operative policy or procedure.

The reviewed current obligation is [REJECT-GUESSES](../../agent-policies/REJECT-GUESSES-stop-writes-with-unknown-critical-values.md). Its identity/scope/dependent review is recorded in the [pilot](../agent-policy-pilot.todo.md). The old numeric identity remains reserved; this link supplies provenance, not a live override chain or independent adoption.

Original source: `docs/policies/0006-writes-fail-rather-than-guess.md`. Exact original SHA-256: `e39e184b65f6eff7499923c09999b75c40277cf2439c6127fcd7bd5c3b4d4982`. The full original bytes are preserved in the following literal block; dated implementation/permission claims below are historical and must be checked against the current skill. Legacy fragment anchors are retained for navigation.

<a id="0006-writes-fail-rather-than-guess"></a>
<a id="current-approach"></a>
<a id="rationale"></a>
<a id="operating-notes"></a>

````text
# 0006 Writes Fail Rather Than Guess

Ownership update (2026-10-31): this document owns portable capability behavior and rationale. Account-specific history and private consumer decisions were separated from this public record. The numbered filename stays stable for navigation; the owning setup/use skills document current executable instructions.

## Current Approach
**When a write cannot be constructed correctly, fail and surface it. Never complete the write on a guessed value.**

This applies to any native capability write path, not only calendar events. A value that is *load-bearing for correctness* — a time zone, a target calendar, an attendee's address, a record identifier — must be either known or fatal. Defaulting it is only acceptable where being wrong is visible and cheap.

Two obligations come with the stop, and they are what make it acceptable rather than merely obstructive:

- **The error must name the workaround.** The time-zone failure prints the exact flag and a concrete value to use (`--tz America/Chicago`, drawn from the machine's own zone when detectable). Writing is therefore never blocked; it stops being *automatic* in the one case where automatic is unsafe.
- **The error must name the likely cause**, so the underlying breakage can be fixed rather than papered over with the flag forever. The time-zone failure points at the native Calendar `list-calendars ALIAS` command and the token scope.

Detection helpers may survive as **hint generators** even when they are no longer permitted to supply values. `_system_tz` is retained on exactly this basis: it populates the error message and nothing else.

## Rationale
A plausible guessed value can silently corrupt a real write: a wrong time zone produces a valid event at the wrong hour. Warnings can be missed in a long transcript. Failing with a concrete remedy and likely cause makes the problem visible without forcing the caller to reconstruct the failure. Dry-run review remains useful but cannot replace correctness checks.

## Operating Notes
- A metadata-read outage now stops timed-event writes instead of producing wrong-hour events. This is the intended trade: a visible stop with a one-flag remedy beats an invisible corruption.
- Warnings are not an acceptable substitute for a failure on any correctness-critical value. Where a `WARN:` currently guards one, it should be re-examined.
- Dry-run-by-default (0002) is reinforced rather than replaced. It caught this bug, but it is a *review* gate that depends on a human reading the plan; it is not a correctness guarantee. Both layers are wanted.
- The offline test for a correctness-critical default should assert the **failure** path, not just the happy path — including that nothing is emitted on stdout and that the remedy appears in the error. See `use-google-calendar/tests/test-timezone.sh`.
````
