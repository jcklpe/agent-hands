---
attention: live
---
# LifeOS Calendar Event Settings — Tasks

Ownership update (2026-10-30): moved from `configs/docs/active-spikes/lifeos-calendar-event-settings.todo.md` into Agent Hands. Stable slug, recorded decisions, completed work and open QA are preserved; this move does not close or reactivate the spike. Current native guidance: [use-google-calendar](../../use-google-calendar/SKILL.md). The aggregate `lifeos` launcher and compatibility tree are retired; old commands and test paths below record the original implementation, not a current entrypoint.

Opened 2026-10-22. Slug: `lifeos-calendar-event-settings`. [Reasoning](lifeos-calendar-event-settings.md).

## Current State
Free/Busy and one-popup settings are implemented for Google Calendar create/update. Defaults remain unchanged. Sixteen new offline tests, existing timezone tests and shell syntax checks pass. An authorized disposable create and settings-only update passed native and independent service readback on 2026-11-21, and the user confirmed Google Calendar web popup delivery. No auth or scope changes occurred; the event is retained until separately approved cleanup. Bounded implementation and QA are complete; closure authorization and archival wording review remain.

## To Do
- Review and explicitly authorize closure before archiving the spike.

## Ready for Human QA
None. The selected client check passed; closure remains a separate decision.

## Done
- During authorized use, confirm popup delivery in the user's calendar client/device. The user selected Google Calendar web and confirmed that the disposable event's one-minute popup appeared on 2026-11-21. This verifies the selected client only, not notification delivery on other devices.
- Live-verify settings only as part of a separately authorized calendar write; inspect the existing event first after any `PARTIAL` response. Do not create a test event without authorization. Completed 2026-11-21 on the user-selected personal calendar: one disposable create with Busy/two-minute popup, then a settings-only update to Free/one-minute popup, each with native post-write verification. Independent connected readback confirmed the final settings, unchanged title/description/times and no attendees. No invitations, retries or permission changes; the event remains for separately approved cleanup.
- Add explicit availability support to create and update. `--transparency transparent|opaque` serializes the Google field; omitted options preserve defaults/current state and settings-only patches leave other fields out.
- Determine whether explicit personal event reminders are already supported. Existing `--notify` is attendee email only. Added `--popup-minutes 0..40320`, replacing event overrides with one popup and disabling calendar-default reminders only when explicitly supplied.
- Verify explicit settings after an accepted write. Fetches the actual event/master target, checks identity and requested fields, accepts the documented omitted Busy default, and reports `PARTIAL` on failed readback without retrying a write.
- Add synthetic offline tests and maintained usage guidance. Sixteen tests pass, with transport stubbed throughout; existing timezone tests and Bash syntax checks pass. Updated dispatcher help, tool README and Calendar skill. The stable installed wrapper resolves directly to repository files; no rollout step is needed.

## Original validation commands (historical paths)
These commands record the original checkpoint; use the native skill for current validation.
```sh
PYTHONDONTWRITEBYTECODE=1 python3 agent-hands/compat/lifeos/tests/test-calendar-settings.py
bash agent-hands/compat/lifeos/tests/test-calendar-tz.sh
bash -n agent-hands/compat/lifeos/lib/google.sh
bash -n agent-hands/compat/lifeos/lifeos.sh
git diff --check
```
