# Optional global skill links
Global links make selected skills discoverable by a local agent client. They do not install dependencies, authenticate an account, register MCP servers/plugins, or authorize service writes. Direct use of a checked-out `SKILL.md` remains available without global installation.

## Choose before installing
Ask whether global discovery is wanted and which local clients should receive the selected service. Support here is limited to Codex and Claude Code. Ask which capabilities are wanted for Google, Microsoft, GitHub and Slack; their scripts refuse an omitted selection. Single-capability services include their setup/use pair; Pencil and JASP include only their existing setup guide. The setup dialogue itself is optional, not a dependency automatically linked for every service.

Inspect the user's existing discovery locations before selecting a destination. New installs use Codex's documented `$HOME/.agents/skills` and Claude Code's `$HOME/.claude/skills`. A verified existing/custom location can be selected with `--skills-dir /absolute/path`, with exactly one `--client`. For example, an existing Codex installation using `$HOME/.codex/skills` can retain that location explicitly; do not silently move its links or install duplicate skill names elsewhere. A discovery directory that is itself a symlink is refused: inspect it and select the verified real directory explicitly. Other client formats and cloud skill uploads are outside this installer.

Source: [Codex local discovery and symlinks](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills), [Claude Code personal skills](https://code.claude.com/docs/en/skills#choose-where-skills-load), checked 2026-10-26. Filesystem validation does not prove a particular client version discovered the skills; inspect its catalogue in a fresh session.

## Preview and apply
The optional installer needs Python 3.9+ and only its standard library. Use a compatible available interpreter; do not install Python merely for optional discovery without setup authorization. Bash-only service commands retain their existing runtime requirements. Keep the checkout at a stable path with `setup-agent-hands/scripts/skill_links.py` present: service-owned entrypoints import this shared primitive. No provider configuration is loaded.

From the checkout root, preview a selected GitHub capability:
```sh
python3 setup-github/scripts/link-skills.py --client codex --skill use-github-issues
```
After the user has authorized this client and selection, apply it by adding `--execute` to the same command. Repeat `--client` for both supported clients and `--skill` for multiple capabilities within that service. The JSON output lists exact source/destination pairs and create/unchanged/repair/conflict actions. Default invocation performs no writes, including no creation of discovery directories. `--help` lists the owner's accepted capabilities. There is no all-services default or force flag.

Single-capability services do not need `--skill`:
```sh
python3 setup-trello/scripts/link-skills.py --client claude
```
Standalone renderer scripts link only their renderer. Selecting Google Calendar also includes `render-calendar-agenda`, its Markdown export dependency; no other provider is pulled in. The dialogue can be installed alone with `python3 setup-agent-hands/scripts/link-skills.py --client codex` if explicitly wanted.

## Conflicts and repair
The complete selection is checked before any links are changed. Correct links, including equivalent relative links, remain untouched. Existing files, directories and unrelated or broken links block the selection; inspect them with the user rather than overwriting or renaming their material automatically.

When the checkout moved, pass `--repair-from` with its exact previous absolute location. Only a link to that previous checkout's same selected skill path qualifies. Preview first, then use `--execute` under the authorized repair scope. Each replaced link is moved into a unique `.agent-hands-link-recovery-*` directory beside the discovery directory, with a `recovery.json` manifest. The manifest records the original link text, saved link, new target and destination; relative link text is restored at its original destination, not interpreted from the recovery directory. No credential files are copied or inspected.

Installation checks state again before applying. Exclusive link creation refuses a path that appeared concurrently. A repair or filesystem failure can leave a partial installation; output identifies completed destinations and saved links. Inspect those before retrying; there is no automatic rollback and no transaction across multiple paths. Avoid concurrent edits to the selected discovery directory. To undo a repair, inspect the manifest, remove only a replacement link still pointing to the recorded new target, and move the saved link back only when its destination is absent. Stop if the destination changed. Keep recovery until verification is complete.

Removing selection from a future invocation does not uninstall previously installed skills. Existing clients and other services are preserved. Moving or deleting the checkout later breaks its links; use an explicit repair when its location changes.
