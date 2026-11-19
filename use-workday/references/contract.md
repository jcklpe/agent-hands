# Workday normalized contract v1
All objects reject missing/extra fields. Input files must be JSON under 1 MB, without duplicate object keys. Dates are exact `YYYY-MM-DD`; times are same-date, minute-precision `HH:MM` in a supplied IANA zone. Overnight blocks, overlapping blocks (including spans containing breaks), overlapping/out-of-range breaks, ambiguous/nonexistent local minutes and offset transitions are rejected. Monetary pay rates and inferred classifications are outside this contract. Limits are one week and at most 100 blocks per input.

## Target
```json
{"tenant":"example.invalid","worker":"synthetic-worker","week_start":"2026-02-02","timezone":"America/Chicago"}
```
`tenant` and `worker` must be stable exact identifiers established by a future authorized adapter; arbitrary display names are insufficient. Week start must be Monday. The target file contains this object alone.

## Allocation
```json
{
  "schema_version": 1,
  "target": {"tenant":"example.invalid","worker":"synthetic-worker","week_start":"2026-02-02","timezone":"America/Chicago"},
  "entries": [{"date":"2026-02-02","start":"09:00","end":"12:00","breaks":[],"time_type":"regular","worktags":{"job":"synthetic-job"}}],
  "expected_total_minutes": 180
}
```
This is the complete desired week, including any existing blocks that should remain. Breaks are explicit unpaid intervals with exactly `start` and `end` fields. Worktags are explicit string key/value pairs, including `{}` when none apply. Time types must be in the snapshot's allowed set. Worktag semantics and required tags must also be checked against tenant data by a future adapter; offline validation checks their shape only. Totals use integer minutes and subtract explicit breaks without service-specific rounding. Calculated service totals must agree exactly; otherwise the operation refuses.

## Snapshot
```json
{
  "schema_version": 1,
  "target": {"tenant":"example.invalid","worker":"synthetic-worker","week_start":"2026-02-02","timezone":"America/Chicago"},
  "revision":"synthetic-revision-1",
  "status":"empty",
  "entries":[],
  "allowed_time_types":["regular"],
  "pay_periods":{"2026-02-02":"p1","2026-02-03":"p1","2026-02-04":"p1","2026-02-05":"p1","2026-02-06":"p1","2026-02-07":"p1","2026-02-08":"p1"},
  "service_total_minutes":0,
  "draft_save_supported":true,
  "certification":""
}
```
Each saved `entries` item contains exactly `id`, `status`, and `entry` (the allocation block shape). Record IDs must be unique. Week states are `empty`, `draft`, `submitted`, `sent_for_approval`, `approved`, `denied`, and `unknown`; record states exclude `empty`. Unknown states never become drafts. Mixed/protected states remain readable but cannot be previewed for saving. The adapter must provide all entries, their actual status, every day's payroll period, permitted time types, service-calculated minutes and a concurrency revision. Incomplete/paginated data cannot masquerade as a whole week. `draft_save_supported: true` and empty certification mean the adapter has verified a save-only action; these fields in an offline file prove nothing about a real tenant.

## Results and execution
Read returns the validated snapshot, daily minutes and a SHA-256 fingerprint. Preview returns a plan bound to the snapshot fingerprint, desired allocation, exact additions/unchanged entries, daily/weekly minutes and payroll period map/crossing indicator. Object key order is immaterial; normalization sorts records by ID, blocks by date/time and breaks by start/end. Any service revision or protected state change invalidates execution. No expiry interval substitutes for a fresh read.

The internal executor requires the caller's approved plan fingerprint and recomputes the preview against live state. Before each addition it re-reads, writes a durable intent and calls `create_draft(target, entry, expected_revision=...)`; the adapter must atomically enforce that revision. Afterwards it verifies draft statuses, classification/period/save semantics, all prior IDs and content, exact new content and service totals. It never retries or rolls back automatically. A later preflight failure returns completed and pending blocks; a save/readback failure returns completed, attempted, observed draft and pending blocks with `status: uncertain`. Raw transport diagnostics are suppressed.

No public command accepts a Python module, shell command, arbitrary endpoint, selector, page script or serialized transport. The only fake service lives in the test module. A production adapter and reconciliation command remain unimplemented.
