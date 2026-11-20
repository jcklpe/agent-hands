---
attention: live
---
# Runtime file lifecycle
Make disposable outputs and persistent private state explicit during installation reconciliation. The [runtime file inventory](../runtime-files.md) owns current locations and cleanup semantics for the affected Microsoft, Office-browser and GitHub operations. Project Workflows supplies the reusable file-handling procedure; service code owns its concrete paths and recovery behavior.

Move verification downloads to private system temporary directories, preserve authentication and unresolved write records, and review retained experiment files by purpose. Existing legacy state defaults must remain accurately documented until a supported migration is implemented. Do not make a path change silently select an empty journal or another browser profile.

Scope is local file handling and review, not new service writes, credential resets or bulk cleanup. Retiring retained files needs the applicable explicit deletion approval. Broader storage migration remains a separately reviewed implementation boundary.
