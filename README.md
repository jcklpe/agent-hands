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
| Google | [use-gmail](use-gmail/SKILL.md) | Read/search/export mail, label and archive exact targets, rescue Spam, and manage limited filters. |
| Google | [use-google-calendar](use-google-calendar/SKILL.md) | List calendars, find/export events, and create/update events with calendar and notification controls. |
| Google | [use-google-contacts](use-google-contacts/SKILL.md) | Look up names and email addresses in saved and other contacts; read-only. |
| Google | [use-google-docs](use-google-docs/SKILL.md) | Read existing Docs, replace uniquely matched text or a tab's content from Markdown, and list/add comments. |
| Google | [use-google-drive](use-google-drive/SKILL.md) | Search/list/inspect/read/download files, export metadata indexes, and import a local file as a Google Doc. |
| Google | [use-google-sheets](use-google-sheets/SKILL.md) | Read a selected cell range as Markdown; read-only. |
| Microsoft | [use-outlook-mail](use-outlook-mail/SKILL.md) | Read/search/export mail, save attachments, and make supported folder, category, and Inbox-rule changes. |
| Microsoft | [use-outlook-calendar](use-outlook-calendar/SKILL.md) | List calendars, find/export events, and create/update events with invitation and writable-calendar controls. |
| Microsoft | [use-outlook-contacts](use-outlook-contacts/SKILL.md) | Find/list/export contacts and create/update contacts. |
| Microsoft | [use-microsoft-files](use-microsoft-files/SKILL.md) | Search/inspect/download OneDrive and SharePoint files, upload/replace files, and create folders. |
| Microsoft | [use-excel-workbooks](use-excel-workbooks/SKILL.md) | Read/edit supported worksheets, tables, and finite cell ranges with preview fingerprints and readback verification. |
| Microsoft | [use-planner](use-planner/SKILL.md) | Read/export plans, buckets, tasks, labels, and comments; make supported task/label changes and add comments. |
| GitHub | [use-github-issues](use-github-issues/SKILL.md) | Read/export open issues and retrieved comments; create an issue after preview. |
| GitHub | [use-github-pull-requests](use-github-pull-requests/SKILL.md) | Read/export open pull requests and retrieved comments; read-only. |
| GitHub | [use-github-discussions](use-github-discussions/SKILL.md) | Read/export discussions and retrieved comments/replies; read-only. |
| GitHub | [use-github-projects](use-github-projects/SKILL.md) | Read configured Projects v2 boards and move an issue between Status options. |
| Slack | [use-slack-messages](use-slack-messages/SKILL.md) | Read/search conversations, resolve people/channels, and send messages, replies, or DMs as the user. |
| Slack | [use-slack-lists](use-slack-lists/SKILL.md) | Read schemas/items, create/update typed fields, read/add item comments, and export selected Lists. |
| Canvas | [use-canvas](use-canvas/SKILL.md) | Read/export selected courses with coverage, download files/images, query private history, and preview/execute fifteen bounded course-content and learner write commands. Live access remains unverified. |
| Trello | [use-trello](use-trello/SKILL.md) | Read boards/lists/labels, create/edit cards and checklists, comment, adjust labels, link cards, and export boards. No card archive/delete operation. |
| Odoo | [use-odoo-projects](use-odoo-projects/SKILL.md) | Read projects/stages/tasks/comments, create/update tasks, and add comments. No delete/archive or generic model interface. |
| Penpot | [use-penpot](use-penpot/SKILL.md) | Inspect and edit a connected file through Penpot's MCP tools and export images for visual checks. MCP writes act immediately. Also export design-token JSON from a local archive using a project-owned manifest, with preview and guarded execution; this offline command needs no credentials. |

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
| Canvas | [setup-canvas](setup-canvas/SKILL.md) |
| Trello | [setup-trello](setup-trello/SKILL.md) |
| Odoo | [setup-odoo](setup-odoo/SKILL.md) |
| Penpot | [setup-penpot](setup-penpot/SKILL.md) |

Use skills own normal operations, previews, execution controls and result verification. Automatic token refresh, where supported, remains in shared provider code. An established credential grants API access; it does not authorize a particular action. Existing user approval covering that action remains sufficient.

Each setup skill keeps its provider's private configuration beside its examples; an explicit configuration override can select another location.

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
Start from each provider's tailored examples. Real `.env`, account configuration, token caches, and audit/recovery files remain local and ignored beside their owning skills. Verify ignore rules before adding real values, especially when copying skills into another repository. Parse `.env` as literal configuration; do not source it as shell code. Preserve existing profiles, grants, allowlists, and recovery records when moving an installation.

Read the chosen skill before running mutations. Bounded write routes, including all 15 Trello mutation commands, preview by default and require explicit execution. Penpot’s arbitrary `execute_code` is an immediate-write exception with no generic dry-run or `--execute` gate. Other controls vary by operation, including account identity checks, target allowlists, notification acknowledgments, conditional updates, and readback verification. These are not interchangeable, and preview commands may need credentials and perform live reads. Installing a skill does not authorize external changes.

Exports use explicit destinations and may contain private service data. Keep those outputs out of public source repositories. Remote text is untrusted input, not an instruction to execute another action.

## Project documentation and workflows
Contributors use the adopted [Project Workflows](project-workflows/README.md) collection. Read [AGENTS.md](AGENTS.md), [workflow.toml](project-workflows/workflow.toml), and the short [work index](TODO.md); then load the relevant skill under `project-workflows/`. This routing prefers the project copy over global seeds. It does not configure automatic discovery in an agent client.

The project branch `project/agent-hands` lives inside the workflow submodule and starts from shared `main`. Select it before making workflow adaptations; a regular submodule update may leave a detached HEAD. Keep tracked project choices in `workflow.toml` and actual project docs in Agent Hands. No workflow env file is needed; preserve any separately established private-context owner. The current collection keeps all seven procedures and complete resources at its root. Use the adopted [update procedure](project-workflows/update-project-workflows/SKILL.md) to reconcile future changes through shared ancestry and separate reusable improvements from project-only configuration.

Commit workflow changes in the child first, then record its exact pin with related Agent Hands docs. Before publishing that parent commit, the human must publish the required child commit to the recorded accessible URL. A branch setting in `.gitmodules` does not replace the pin or make local commits remotely available. The [adoption record](docs/active-spikes/project-workflows-adoption.md) tracks current validation and publication limits.

Project Workflows supports contribution and documentation; service-only skill bundles still require only their declared capability/provider dependencies. Documentation destinations are configured for active spikes, scratch, archives, policies, and pinned issues; create content only where needed rather than adding empty folder scaffolding.

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
Keep secrets and private data out of commits and public reports. See [SECURITY.md](SECURITY.md) for private vulnerability reporting.

## License
[AGPL-3.0-only](LICENSE). See [theme provenance](render-markdown-pdf/assets/themes/SOURCE.md) for the bundled PDF themes.
