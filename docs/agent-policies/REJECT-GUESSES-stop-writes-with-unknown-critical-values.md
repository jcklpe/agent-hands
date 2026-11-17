---
id: REJECT-GUESSES
type: operational
scope: "Agent construction and implementation of correctness-critical native capability writes."
status: adopted
authority: "User's explicit Agent Hands policy-pilot approval, 2026-11-02; recorded in agent-policy-pilot."
revised: "2026-11-02"
depends_on: []
related_to: ["GUARD-CALENDAR-WRITES"]
---
# Reject correctness-critical guesses
When a write cannot be constructed correctly, stop and surface the gap instead of supplying a guessed correctness-critical value. A time zone, destination calendar, attendee address or record identifier that is load-bearing for correctness must be known or fatal. Defaults are acceptable only where being wrong is visible and cheap; do not treat that exception as permission to guess a load-bearing value.

An actionable failure must name the likely cause and a concrete remedy or workaround. A detected system value may generate an error-message hint without becoming an automatic write input. A warning is not a substitute for failing on a correctness-critical unknown. Preview review and correctness checks are separate safeguards; neither replaces the other.

A regression test for a correctness-critical fallback must exercise the failure, including absence of a write payload on stdout and the remedy in the error, rather than only its successful path. A stopped write is a visible boundary to resolve, not permission to bypass the guard or expand access.

## Enforcement and procedures
The [Calendar time-zone tests](../../use-google-calendar/tests/test-timezone.sh) and [Calendar capability](../../use-google-calendar/SKILL.md) supply the original concrete guard/example. This obligation applies to all native capability write paths; each service skill owns its actual procedure and implementation.

## Identity history
This obligation continues the reviewed legacy record [0006](../archive/agent-policy-retirements/0006-writes-fail-rather-than-guess.md), retired as an operative document during this authorized migration. Its source text and numeric identity remain reserved; the history link is not an override or automatic authority transfer.
