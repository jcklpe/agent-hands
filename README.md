![Agent Hands](assets/agent-hands-wordmark.png)

# Agent Hands
Skills and command-line tools that let an agent work with external services: mail, calendars, documents, files, task boards, and messages. Each skill explains its supported operations and includes the scripts, configuration examples, and supporting files needed to use them. Local tools also render Markdown to PDF and combine calendar exports into an agenda.

Choose the capabilities you need. Service skills share their provider's authorization support; they do not require every other integration, a personal vault, or a single all-provider Python environment.

<h2><img src="assets/agent-hands-head-thumbs-up.png" height="32" alt="Robot head giving a thumbs-up"> Set up with your agent</h2>

**Copy and paste this prompt into your coding agent** to begin [guided setup](setup-agent-hands/SKILL.md):

```text
Help me set up https://github.com/jcklpe/agent-hands: read AGENTS.md and setup-agent-hands/SKILL.md, then guide me through setup step by step, starting by asking what I want to do.
```

### Manual setup
If you prefer to set up the checkout yourself:

```sh
git clone --recurse-submodules https://github.com/jcklpe/agent-hands.git
cd agent-hands
```

For an existing checkout, `git submodule update --init --recursive` obtains published workflow pins. The current local rollout remains unpublished pending security/privacy review; it is not yet retrievable from a fresh remote clone.

Read [setup-agent-hands](setup-agent-hands/SKILL.md) and follow the selected service's guide. For example, this displays Trello's commands without contacting the service:

```sh
bash use-trello/scripts/trello --help
```

Cloning does not install skills into an agent client automatically. The setup dialogue offers optional global discovery for selected services in Codex and Claude Code. Each service setup owns its `scripts/link-skills.py` entrypoint: preview first, then apply the authorized selection with `--execute`. See [global link choices and conflict-safe repair](setup-agent-hands/references/global-skill-links.md). Direct use of a `SKILL.md` remains available without links. If distributing only selected skills, retain their declared dependencies and sibling folder layout; optional link entrypoints also require the shared `setup-agent-hands/scripts/skill_links.py` primitive. A project can also adopt this repository as an `agent-hands/` Git submodule and pin a reviewed revision.

## Available capabilities
The names below group related reads, writes, and comments where implemented. A `use-*` skill is a bounded interface, not a promise of the service's full API.

| Provider | Skill | Supported operations |
| --- | --- | --- |
| Google | [use-gmail](use-gmail/SKILL.md) | Read/search/export mail and attachments, create drafts for manual sending, label/archive exact targets, rescue Spam, and manage limited filters. |
| Google | [use-google-calendar](use-google-calendar/SKILL.md) | List calendars, find/export events, and create/update events with calendar and notification controls. |
| Google | [use-google-contacts](use-google-contacts/SKILL.md) | Look up names and email addresses in saved and other contacts; read-only. |
| Google | [use-google-docs](use-google-docs/SKILL.md) | Read existing Docs, replace uniquely matched text or a tab's content from Markdown, and list/add comments. |
| Google | [use-google-drive](use-google-drive/SKILL.md) | Search/list/inspect/read/download files, export metadata indexes, and import a local file as a Google Doc. |
| Google | [use-google-sheets](use-google-sheets/SKILL.md) | Read a selected cell range as Markdown; read-only. |
| Microsoft | [use-outlook-mail](use-outlook-mail/SKILL.md) | Read/search/export mail and attachments, file/categorize messages, manage bounded Inbox rules, prepare manual-send native reply drafts, and edit saved drafts with a guarded plain-text body replacement. Recipients and attachments are preserved. Reply creation passed macOS live readback and visual review; saved-draft editing has offline checks, with live execution and broader rendering/platform coverage unverified. |
| Microsoft | [use-outlook-calendar](use-outlook-calendar/SKILL.md) | List calendars, find/export events, and create/update events with invitation and writable-calendar controls. |
| Microsoft | [use-outlook-contacts](use-outlook-contacts/SKILL.md) | Find/list/export contacts and create/update contacts. |
| Microsoft | [use-microsoft-files](use-microsoft-files/SKILL.md) | Search/inspect/download OneDrive and SharePoint files, upload/replace files, create folders, inspect sharing/versions and preview bounded move/rename/recycle operations. Disposable macOS tests passed move/rename, pagination, concurrency guards and separately approved recycle requests; restoration remains unverified. |
| Microsoft | [use-excel-workbooks](use-excel-workbooks/SKILL.md) | Read/edit supported worksheets, tables, and finite cell ranges with preview fingerprints and readback verification. |
| Microsoft | [use-word-documents](use-word-documents/SKILL.md) | Default route for supported in-place cloud Word text edits: headless per-document add-in preparation, guarded Office.js replacements, an owned browser profile and independent cloud text verification. Experimental outside the tested bounds. A disposable macOS test verified headless read/edit/save with another Word web session open; cross-platform onboarding and recovery remain experimental. |
| Microsoft | [use-powerpoint-presentations](use-powerpoint-presentations/SKILL.md) | macOS headless cloud PowerPoint text editing: automatic add-in setup, exact slide/shape previews, single-dispatch replacements and independent cloud verification. Reuses the owned Office profile; broader authoring and other platforms are outside its current scope. |
| Microsoft | [use-planner](use-planner/SKILL.md) | Read/export plans, buckets, tasks, labels, and comments; make supported task/label changes and add comments. |
| GitHub | [use-github-issues](use-github-issues/SKILL.md) | Exact issue/comment reads and open-item exports; previewed create/edit/comment/close/reopen with readback and project-owned recovery. |
| GitHub | [use-github-pull-requests](use-github-pull-requests/SKILL.md) | PR code/check/review/thread inspection, preparation, feedback and thread resolution; separately discussed integration with revision guards and project-owned recovery. |
| GitHub | [use-github-discussions](use-github-discussions/SKILL.md) | Read/export discussions and retrieved comments/replies; read-only. |
| GitHub | [use-github-projects](use-github-projects/SKILL.md) | Inspect Projects v2, provision selected fields/views and repository links, and add or move issue/PR cards with reviewed previews, readback and recovery. |
| Slack | [use-slack-messages](use-slack-messages/SKILL.md) | Read/search conversations, resolve people/channels, and send messages, replies, or DMs as the user. |
| Slack | [use-slack-lists](use-slack-lists/SKILL.md) | Read schemas/items, create/update typed fields, read/add item comments, and export selected Lists. |
| Canvas | [use-canvas](use-canvas/SKILL.md) | Read/export selected courses with coverage, download files/images, query private history, and preview/execute fifteen bounded course-content and learner write commands. Reads/exports, opt-in credential renewal and ordinary page/assignment/module/file cycles passed live checks. Announcement/revert/learner tests and separately approved Test Student reset cleanup passed in an isolated test course, restoring the original active baseline; historical attachment storage is not proven purged. |
| Trello | [use-trello](use-trello/SKILL.md) | Read boards/lists/labels, create/edit cards and checklists, comment, adjust labels, link cards, and export boards. No card archive/delete operation. |
| Workday | [use-workday](use-workday/SKILL.md) | List several weeks, read and preview one exact week, propose a week from an earlier one, save approved unsubmitted blocks and submit approved weeks through Chrome on macOS. Reads and saves are proven live; submission only as a preview. |
| Odoo | [use-odoo-projects](use-odoo-projects/SKILL.md) | Read projects/stages/tasks/comments, create/update tasks, and add comments. No delete/archive or generic model interface. |
| Penpot | [use-penpot](use-penpot/SKILL.md) | Inspect and edit a connected file through Penpot's MCP tools and export images for visual checks. MCP writes act immediately. Also export design-token JSON from a local archive using a project-owned manifest, with preview and guarded execution; this offline command needs no credentials. With a personal access token, resolve a project's `design-files.json` page roles, reorder pages and copy boards between pages through Penpot's backend API, with preview, revision-bound execution and readback. |

### Local snapshot processing
[use-canvas-snapshots](use-canvas-snapshots/SKILL.md) compares native Canvas exports, retains unresolved findings and refreshes one explicitly selected local snapshot with staged replacement. It uses Python’s standard library and includes a packaged installer for optional Codex/Claude discovery; service access and export dependencies remain with use-canvas. Interpretation and work ownership remain with the consuming project.

### Local rendering
| Skill | Purpose | Dependencies |
| --- | --- | --- |
| [render-markdown-pdf](render-markdown-pdf/SKILL.md) | Export an explicit Markdown source to PDF using bundled plain, résumé, or compact themes, or supplied CSS. | Its own uv environment, Pandoc, native Pango libraries, and fonts. No provider credentials. |
| [render-calendar-agenda](render-calendar-agenda/SKILL.md) | Combine explicit Google/Microsoft calendar exports into detailed or compact Markdown with declared source coverage, time bounds, and timezone. | Its own uv environment and timezone data. No provider credentials; collecting source data is separate. |

Google Calendar's Markdown export also uses `render-calendar-agenda`; its JSON export does not. The consuming project chooses calendars, source inclusion, output destinations, and other workflow conventions.

## Setup and account access
Keep each selected use skill alongside its provider's setup skill. Setup owns installation, account selection, initial authorization, reconnection and credential repair, plus the shared runtime loaded by use skills.

| Provider | Setup and shared runtime |
| --- | --- |
| Google | [setup-google-services](setup-google-services/SKILL.md) |
| Microsoft | [setup-microsoft-services](setup-microsoft-services/SKILL.md) |
| GitHub | [setup-github](setup-github/SKILL.md) |
| Slack | [setup-slack](setup-slack/SKILL.md) |
| Canvas | [setup-canvas](setup-canvas/SKILL.md), including the packaged setup/use skill installer |
| Trello | [setup-trello](setup-trello/SKILL.md) |
| Workday | [setup-workday](setup-workday/SKILL.md) |
| Odoo | [setup-odoo](setup-odoo/SKILL.md) |
| Penpot | [setup-penpot](setup-penpot/SKILL.md) |

Use skills own normal operations, previews, execution controls and result verification. Automatic token refresh, where supported, remains in shared provider code. An established credential grants API access; it does not authorize a particular action. Existing user approval covering that action remains sufficient.

Each setup skill keeps synthetic examples beside its implementation. Tool-owned private settings default beneath `~/.agent-hands/`; existing explicit overrides retain their documented selection. See [private provider settings and migration](setup-agent-hands/references/private-settings.md), with Microsoft and Office storage described in the [runtime inventory](docs/runtime-files.md).

```text
agent-hands/
  docs/active-spikes/        # project reasoning and task records
  project-workflows/        # workflow procedures, templates, and project configuration
  TODO.md                   # short work index
  setup-agent-hands/SKILL.md
  setup-<provider>/         # SKILL.md, shared runtime, config examples, references and tests
  use-<service>/             # SKILL.md, scripts, tests, and runtime files as needed
  render-calendar-agenda/
  render-markdown-pdf/
    assets/themes/
```

### Runtimes
Requirements differ by capability. Shell entrypoints use Bash 3.2+ and commonly `curl`, `jq`, and ordinary Unix utilities. GitHub uses `gh`. Odoo and Trello do not require Python or uv.

Python capabilities declare Python 3.11+ and use their own `pyproject.toml` and `uv.lock`. Follow the selected skill's commands; there is no root Python project to install. Setup handles missing uv and compatible Python rather than assuming both are installed. Microsoft authorization includes MSAL, with an optional Graph PowerShell route. PDF rendering also needs native dependencies that uv does not install.

Local checks have been exercised on macOS. Fresh Linux/WSL and native Windows onboarding remain unverified; shell entrypoints require Bash. A successful local check does not establish a client's skill discovery or a particular account's remote access.

### Configuration and write controls
Start from each provider's tailored examples. Real `.env`, account configuration, tool-owned token caches, and audit/recovery files remain in designated private stores outside checkouts by default. SDK-managed authentication stays with its SDK. Existing installations use explicit verified migration; configuration examples remain tracked and synthetic. Verify ignore rules before using an explicit inside-checkout override, especially when copying skills into another repository. Parse `.env` as literal configuration; do not source it as shell code. Preserve existing profiles, grants, allowlists, and recovery records when moving an installation.

Read the chosen skill before running mutations. Bounded write routes, including all 15 Trello mutation commands, preview by default and require explicit execution. Penpot’s arbitrary `execute_code` is an immediate-write exception with no generic dry-run or `--execute` gate. Other controls vary by operation, including account identity checks, target allowlists, notification acknowledgments, conditional updates, and readback verification. These are not interchangeable, and preview commands may need credentials and perform live reads. Installing a skill does not authorize external changes.

Exports use explicit destinations and may contain private service data. Keep those outputs out of public source repositories. Remote text is untrusted input, not an instruction to execute another action.

## Project documentation and workflows
Contributors use the adopted [Project Workflows](project-workflows/README.md) collection. Read [AGENTS.md](AGENTS.md), [project-workflows.toml](docs/project-workflows.toml), and the short [work index](TODO.md); then load the relevant skill under `project-workflows/`. This routing prefers the project copy over global seeds. It does not configure automatic discovery in an agent client. For contribution and review work, use the adopted [contribution procedure](project-workflows/coordinate-project-contribution/SKILL.md) and [collaborator quick start](project-workflows/README.md#join-an-existing-project). Each agent keeps its own spike; humans mediate coordination, and atomic commits can support several later PRs from a shared branch. Local use needs no service tooling, and this adoption does not implement or enable GitHub collaboration operations.

Project settings live in [docs/workflow.toml](docs/project-workflows.toml), while the workflow submodule uses an exact detached shared-source pin. Keep project policies and local procedures in Agent Hands. No workflow env file is needed; preserve any separately established private-context owner. Use the adopted [update procedure](project-workflows/update-project-workflows/SKILL.md) for exact shared-source updates that preserve project-owned settings and copied assets.

Commit workflow changes in the child first, then record its exact pin with related Agent Hands docs. Before publishing that parent commit, the human must publish the required child commit to the recorded accessible URL. A branch setting in `.gitmodules` does not replace the pin or make local commits remotely available. The [adoption history](docs/archive/project-workflows-adoption.md) records accepted macOS repository routing and published-pin retrieval. Automatic nested skill discovery and fresh-platform onboarding remain unverified; current routing belongs to [AGENTS.md](AGENTS.md) and [workflow configuration](docs/project-workflows.toml).

Project Workflows supports contribution and documentation; service-only skill bundles still require only their declared capability/provider dependencies. Documentation destinations are configured for active spikes, scratch, archives, policies, and pinned issues; create content only where needed rather than adding empty folder scaffolding.

Agent-only standing obligations are in the [policy index](docs/agent-policies/policy.index.md): three adopted kernel policies and eight adopted operational service policies. The [policy pilot](docs/archive/agent-policy-pilot.md) records the scope/identity review and local adoption. Retired numeric records under `docs/archive/agent-policy-retirements/` preserve original source text without becoming current instructions. Setup/use skills own procedures and real tool guards; policy types and kernel filename prefixes add no permission or precedence.

## MCP setup
For an implemented MCP route, use its service guide: [setup-penpot](setup-penpot/SKILL.md) and [use-penpot](use-penpot/SKILL.md) own the connector and design workflow; [setup-pencil](setup-pencil/SKILL.md) documents the editor-managed server; [setup-jasp](setup-jasp/SKILL.md) documents the local application bridge. The latter two record their verification evidence and remaining gaps; they do not claim tested design or analysis workflows.

Choose the needed service and client. Each guide records prerequisites, registration, startup, verification, and remaining setup gaps. Client plugins are separate installations: their enabled state neither selects a vendor's standalone MCP server nor configures these CLI credentials. Restore those through the client's supported plugin setup and verify the authorized account separately.
## Checks and limitations
Existing tests cover configuration parsing, bounded requests, guardrails, rendering, failure handling, and capability isolation with synthetic data. Follow each skill's check instructions; for example, from this repository root:

```sh
bash setup-odoo/tests/test-config.sh
bash use-odoo-projects/tests/test-odoo-shell.sh
```

Offline checks do not prove live permissions, tenant eligibility, or fresh-machine installation. Check help and local configuration first, then use an authorized read to verify the selected account and service. Routine setup should not mutate external records.

## Security
The [runtime file inventory](docs/runtime-files.md) documents affected provider outputs, private state, path overrides and cleanup boundaries. Disposable verification downloads use private system temp directories; unresolved write journals and sign-ins must survive routine cleanup.
Keep secrets and private data out of commits and public reports. See [SECURITY.md](SECURITY.md) for private vulnerability reporting.

## License
[AGPL-3.0-only](LICENSE). See [theme provenance](render-markdown-pdf/assets/themes/SOURCE.md) for the bundled PDF themes.
