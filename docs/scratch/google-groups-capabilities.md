---
status: captured
---
# Google Groups capabilities
Explore adding Google Groups support to Agent Hands. Evaluate existing maintained MCP integrations and their actual membership-operation coverage before building a custom CLI; prefer reuse where suitable and reserve custom tooling for a demonstrated gap. Keep functioning CLI capabilities available.

The current Agent Hands Google capabilities do not cover Groups membership. Useful operations include inspecting current members and roles, reading pending join requests and invitations, approving an ordinary member request, and inviting an exact recipient without duplicating an existing membership or invitation. Verify the signed-in account, Workspace organization, target group, recipient, and intended role before any write; distinguish ordinary members from managers and owners.

Use safe write previews that show the exact target, role, recipient, and notification effects, then verify the result and distinguish a submitted invitation from accepted membership. Evaluate least-privilege scopes and approved authentication without creating credentials or expanding grants merely to unblock an operation. Account for groups that expose private discussions or shared resources, and require explicit confirmation for sensitive access or broader roles. Capture only for now; no integration has been selected, installed, authorized, or implemented.
