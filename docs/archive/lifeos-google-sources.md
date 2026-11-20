---
attention: historical
---
# LifeOS Google Sources

Privacy separation (2026-11-02): consumer-specific passages and actual account-validation chronology were preserved privately before removal from this public record. Portable requirements, recorded tooling evidence and stable slugs remain; historical instructions below are not current operating guidance.

Migration note (2026-10-30): moved from `configs/docs/archive/lifeos-google-sources.md` into Agent Hands as historical service-tooling context. Original body and task states are retained apart from navigation repairs. Old LifeOS commands, paths and account observations are not current Agent Hands instructions. The original Git history stays in the configs repository; stable slugs are unchanged. Current capabilities are documented in the [Agent Hands README](../../README.md).

Status: archived. Gmail snapshots and Drive on-demand commands are implemented; representative live read/OAuth QA was recorded. Actual account selection and validation chronology are retained privately.

Companion to-do: `docs/archive/lifeos-google-sources.todo.md`.

## Purpose
Extend the original service CLI with bounded Gmail and Google Drive reads that agents can use independently of a hosted connector.

The goal is not to turn agents loose on Google accounts. The goal is a portable, platform-neutral source layer:

- secrets and tokens stay in `configs/lifeos-tools/`
- callers select generated snapshot destinations explicitly
- on-demand reads/searches return bounded terminal output
- commands remain explicit, read-only, and agent-friendly

## Project Boundary
The historical helper implementation lived in configs. Its reusable service mechanics now belong to Agent Hands; consumers own their private content and selected output locations.

Do not store OAuth credentials, OAuth tokens, account config, `.env`, or API settings inside `<private-workspace>`.

Generated snapshots use an explicitly selected caller-owned destination; a service capability does not prescribe a vault layout.

## Relationship To Existing Tools
The existing Trello and Calendar tooling gives the baseline:

- `lifeos` is the stable entrypoint.
- tools load local config at runtime, not from shell startup.
- read-only sync writes generated Markdown snapshots.
- write commands, when present, are explicit and narrow.
- real secret-bearing files are ignored beside tracked fake examples.

Gmail should follow the Calendar snapshot pattern. Drive should not.

## Account Alias Model
Google work now needs multiple accounts. Use stable local aliases rather than raw email addresses in commands:

```text
example
secondary
organization
institution
```

Aliases should be configured in ignored local config, with a tracked fake example beside it:

```text
lifeos-tools/
  google-accounts.example.json # tracked fake account setup
  google-accounts.json         # ignored real aliases, queries, token paths
```

Each account alias should have its own ignored token file. Reusing one OAuth client is fine if the scopes work, but token state must be per account.

Example ignored token files:

```text
lifeos-tools/google-example-token.json
lifeos-tools/google-secondary-token.json
lifeos-tools/google-organization-token.json
lifeos-tools/google-institution-token.json
```

Implemented local config:

- `google-accounts.example.json` is tracked with fake values.
- `google-accounts.json` is ignored and scaffolded locally for `example`, `secondary`, `organization`, and future disabled `institution`.
- `GOOGLE_ACCOUNTS_PATH` may point to the alias config; otherwise the default is `lifeos-tools/google-accounts.json`.
- Live OAuth has been completed for `personal`, `professional`, and `open-austin`.
- Live all-account Gmail sync has written snapshots to `$LIFEOS_VAULT_PATH/sources/gmail/`.

## Gmail Behavior
Gmail should produce bounded Markdown snapshots into the LifeOS vault because email context is temporal and useful for planning.

Target generated files:

```text
$LIFEOS_VAULT_PATH/sources/gmail/index.md
$LIFEOS_VAULT_PATH/sources/gmail/personal.md
$LIFEOS_VAULT_PATH/sources/gmail/professional.md
$LIFEOS_VAULT_PATH/sources/gmail/open-austin.md
```

Implemented command surface:

```sh
lifeos google accounts
lifeos google auth ALIAS
lifeos gmail sync ALIAS
lifeos gmail sync ALIAS --qa
lifeos gmail sync --all
lifeos gmail sync --all --qa
```

Default query should be conservative:

```text
in:inbox newer_than:30d
```

Default max results should be bounded:

```text
150 messages per account
```

Support per-account query overrides because each account may mean something different by "current/open loop".

Include:

- account alias
- last refreshed timestamp
- query/scope used
- message date
- sender
- recipients when available
- subject
- labels
- thread ID
- message ID
- attachment presence
- cleaned plain-text body

Bound body output. Strip/clean HTML where possible, preserve useful links, cap large message bodies, and mark truncation. Do not dump attachments.

Do not implement Gmail mutations:

- no sending
- no replying
- no archiving
- no deleting
- no labeling
- no marking read/unread

## Drive Behavior
Drive should behave like an on-demand connector, not a sync source.

Do not clone Drive into the LifeOS vault. Do not recursively index whole Drives. Do not generate giant summaries of personal Drive, Open Austin Drive, or the LifeOS folder itself.

The first useful Drive commands should let agents search, inspect, and read specific files:

```sh
lifeos drive accounts
lifeos drive search ALIAS QUERY
lifeos drive list ALIAS FOLDER_ID
lifeos drive meta ALIAS FILE_URL_OR_ID
lifeos drive read ALIAS FILE_URL_OR_ID
```

Implemented command surface:

```sh
lifeos drive accounts
lifeos drive search ALIAS QUERY [--json]
lifeos drive list ALIAS FOLDER_ID [--json]
lifeos drive meta ALIAS FILE_URL_OR_ID [--json]
lifeos drive read ALIAS FILE_URL_OR_ID [--range RANGE]
```

Default output should be readable terminal text. Add `--json` where structured output is useful for wrappers or agents.

Search/list output should include:

- account alias
- file name
- file ID
- MIME type
- modified time
- owner/organizer when available
- parent/folder/shared drive context when feasible
- web URL

Read support should be bounded and explicit:

- Google Docs: read as bounded plain text.
- Google Sheets: read spreadsheet metadata and a bounded sheet/range preview.
- PDFs, images, arbitrary binary files: metadata only for v1 unless a specific reader is added later.
- Slides, comments, rich Docs structure, and full spreadsheet extraction can wait.

Google API docs use the word "export" for reading Google-native Docs/Sheets into a usable format. In the CLI and docs, prefer user-facing words like `read` or `fetch` so this does not sound like cloning or durable Drive export.

## OAuth And Scopes
Calendar currently uses narrow read-only Calendar scopes. Gmail and Drive will require additional scopes and likely fresh tokens per alias.

Implemented aliases request the minimum read-only scopes that satisfy v1:

- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/drive.metadata.readonly`
- `https://www.googleapis.com/auth/drive.readonly`
- `https://www.googleapis.com/auth/spreadsheets.readonly`

Do not add write scopes in this spike.

## Safety Boundaries
- No auth/config files in the LifeOS vault.
- No generated Gmail QA snapshots committed to git.
- No Drive-wide clone.
- No Gmail or Drive mutations.
- No attachment dumping.
- No giant message bodies or giant Sheets by default.
- No hidden background sync or cron.

## Non-Goals
- Inbox zero automation.
- Email sending/replying.
- Drive migration, backup, or archival export.
- Recursive indexing of all Drive content.
- Full Google Docs/Sheets/Slides fidelity.
- Universal replacement for first-party Google UIs.

## Future Threads
Future ergonomics and expansion questions are preserved in `docs/lifeos-tools-v2.md` rather than left as unresolved work in this closeout doc.

## Closeout
This spike is closed. The user confirmed the tools work when used from the LifeOS agent workflow.

Future product/ergonomics choices are tracked in `docs/lifeos-tools-v2.md`.
