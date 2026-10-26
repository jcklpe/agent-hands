---
name: authorize-github
description: "Configure or diagnose GitHub CLI authentication and optional repository/project aliases for the bounded GitHub capabilities."
---
# Authorize GitHub
The installed `gh` CLI owns authentication. This provider skill owns literal configuration, repository alias resolution, local export publication, and narrow response-format helpers. Issues and Pull Requests share the same collection/Markdown shape; Discussions and Projects keep their own renderers. No use skill depends on another use skill.

## Configuration
A normal `gh auth login` uses gh's credential storage; preserve that existing route. See [official authentication](https://cli.github.com/manual/gh_auth_login) and [environment precedence](https://cli.github.com/manual/gh_help_environment). Do not switch accounts, broaden grants, or print tokens implicitly. The tool calls `gh auth status`, but does not pin an expected user identity. Inspect the intended account/host before a live operation.

Optional `.env` and `github-repos.json` live beside this file and are ignored. Adjacent examples contain synthetic fields only. `GITHUB_REPOS_PATH` overrides the JSON location; relative values resolve against `GITHUB_CONFIG_DIR` or this skill, not the caller's project. `GITHUB_ENV_FILE` selects an explicit env file, relative to cwd if not absolute; a missing selected file fails. Exported variables win. Only literal `GITHUB_REPOS_PATH`, `GH_TOKEN`, and `GH_HOST` assignments are accepted from the file; nothing is sourced/evaluated. A local `GH_TOKEN` is optional when the user chooses it over gh's account store. Keep real config owner-readable and never committed.

Repo aliases require unique simple names, owner/repo fields, optional project owner, and positive project numbers with simple export names. `issues`/`prs`/`discussions` flags are retained for aggregate legacy consumers; an explicit standalone domain export selects its own capability. The configuration is not a write allowlist. Literal `OWNER/REPO` works without any config for issue/PR/Discussion operations. Projects use an explicit configured alias; status moves target its first configured organization project.

## Commands and runtime
From the collection root:
```sh
bash authorize-github/scripts/authorize check
bash authorize-github/scripts/authorize status
bash authorize-github/scripts/authorize list-repos
```
`check` inspects local gh/jq availability and an existing alias file without network access; it does not verify credentials. `status` invokes gh's account check and may access the network. `list-repos` reads only local metadata. No token value is printed by these helpers.

Each use skill needs Bash 3.2+, gh, jq, and Python 3.11+ for Markdown rendering. With uv installed, rendering uses the selected capability's manifest/lock. `GITHUB_PYTHON` can select an existing compatible executable instead. The provider has no all-service Python environment. [setup-github](../setup-github/SKILL.md) covers onboarding.

Read failures and ambiguous targets are errors. Export retrieval/rendering completes in a private temporary directory before named output artifacts are replaced. Multi-file publication is not a transaction; interrupted replacement attempts restore the artifact currently being moved, and report retained recovery files if restoration fails. Do not treat a successful local export as proof of unlimited server history or a consistent remote snapshot.

## Offline checks
Run `bash tests/test-operations.sh` and `bash tests/test-render.sh` from this skill folder. They cover provider configuration, shared issue/PR exports and rendering, failure preservation, and interrupted publication using synthetic data. Capability-specific writes and renderers are tested beside their owning use skills.
