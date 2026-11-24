---
name: use-microsoft-forms
description: "Create and verify closed Microsoft Forms drafts through a specification-bound CLI using the owned Office browser session."
---
# Use Microsoft Forms
Use for explicitly authorized form authoring. Requires the selected Microsoft provider account, its files write opt-in, Node 22+, installed Chrome and the dependencies of [Word documents](../use-word-documents/SKILL.md). Forms uses the existing provider-owned browser profile and lock; it needs no Word add-in. Normal user browser tabs are untouched. Normal sign-in/MFA through provider browser setup persists automatically, but Microsoft can require renewed authentication.

## Review a specification
```sh
node scripts/forms.mjs validate --spec /private/intake.json
node scripts/forms.mjs preview example --spec /private/intake.json --url EXACT_EMPTY_FORM_DESIGN_URL
```
The version-1 specification has `title`, `description`, `acceptResponses:false` and `questions`. Each question has a unique lowercase `id`, `title`, explicit `required`, and `type` (`text`, `choice` or `date`). Text supports `longAnswer`; choice requires ordered `options`, optional `multiple`, and optional `branches` mapping exact option text to a later question ID or `end`. Optional `next` must also point forward. Questions may include `description`. Validation refuses unsupported fields, backward targets and multiple-answer branching. Keep private questions and exact target IDs outside this public package.

## Apply and verify
```sh
node scripts/forms.mjs apply example --plan OPERATION_ID --hash PREVIEW_SHA256 --execute --allow-form-write
node scripts/forms.mjs status example --plan OPERATION_ID
node scripts/forms.mjs verify example --plan OPERATION_ID
node scripts/forms.mjs visual example --plan OPERATION_ID --out /private/preview-output
```
Preview binds the account, exact target and specification hash. Apply accepts only an empty untitled draft, or creates a new draft when preview omits `--url`; its duplicate-title check covers the displayed My forms inventory. Dispatch is journaled before mutation. Partial/uncertain results retain the exact target and cannot be automatically replayed. Inspect that target before any further write. A missing target after creation is an uncertain result, never permission to create again.

Verification independently reopens the editor and compares wording, options/order, required flags, text types, branch destinations and closed response collection. Forms normalizes rich-text whitespace. Visual checks capture desktop/mobile previews and exercise two derived choice paths without submitting a response. They do not constitute an accessibility audit or every possible route.

`author` is a bounded incremental alternative using the same plan/hash/execute gates. Its stdin commands are `inspect`, `introduce`, `begin`, `configure`, `build-remaining`, `branch`, `verify`, `quit`. Explicit `--resume` supports only a reconciled introduction with zero questions; other partial results require investigation. It exposes no arbitrary JavaScript, selectors or requests. `subtitle.mjs` supports a separate preview/apply amendment to one subtitle, bound to the original plan and complete before/after verification; use its `--help` for arguments.

## Bounds
Only closed drafts are supported. No submissions, invitations, distribution, response export, ownership transfer, sharing/access changes or deletion. Respondent eligibility is retained from the existing tenant default, not selected by this tool. Confirm ownership and respondent access before launch. Authentication, localized or changed controls, profile contention and ambiguous state stop execution. Do not attach to normal browser profiles, bypass tenant restrictions, reset journals or inspect tokens.

The English editor on macOS was exercised against an authorized existing empty draft: 21 fields, 11 answer destinations, fresh-session readback and closed collection. Native new-draft creation is implemented but not live accepted; broader tenants/platforms and every recovery case remain unverified. [Implementation and evidence](../docs/active-spikes/microsoft-forms.todo.md).

## Local checks
```sh
node --test tests/*.test.mjs
```
Fourteen offline checks cover specifications, targets, account/hash binding, no-replay receipts, readback and preview-path generation. Browser dependencies are reused from the selected Office provider; no credentials or browser state belong in the repository.
