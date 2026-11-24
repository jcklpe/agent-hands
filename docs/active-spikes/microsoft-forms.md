---
attention: live
tags: [microsoft, forms, cli]
---
# Microsoft Forms authoring
Add a bounded CLI for creating and verifying a Microsoft Form from a reviewed specification. The user authorized a browser-backed implementation using an owned headless Microsoft session. Normal browser profiles and tabs are outside the capability. The user-specific form content belongs outside this public repository.

Microsoft's documented Forms connector exposes form/response detail reads and a response trigger, not authoring. The Graph Forms resources concern administrative settings. Do not invent Graph endpoints or use extracted cookies or tokens to call undocumented APIs. Use the actual Forms editor and observed controls through the provider-owned browser session.

The proposed surface validates question IDs, supported types and forward-only branching before any remote mutation. Preview binds the selected account and complete specification. Apply requires the preview hash, explicit execution and a durable single-dispatch receipt. Persist a created form identity as soon as it is known; partial creation must remain inspectable without automatically making another form. Readback must inspect questions, options, required flags, branching and closed response collection. No response submission, invitations, distribution, permission changes or deletion are included.

Tasks and evidence: [work log](microsoft-forms.todo.md).

## Sources
- [Microsoft Forms connector](https://learn.microsoft.com/en-us/connectors/microsoftforms/)
- [Forms administrative settings](https://learn.microsoft.com/en-us/graph/api/resources/formssettings?view=graph-rest-beta)
- [Branching in Microsoft Forms](https://support.microsoft.com/en-us/forms/use-branching-logic-in-microsoft-forms)
