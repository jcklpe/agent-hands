# Account access and provider support
The command examples below identify their working directory. Private configuration defaults to `~/.agent-hands/github-settings/config/`; synthetic examples remain beside this skill and explicit configuration overrides keep their existing precedence. Preserve existing credentials; do not create a parallel profile or move tokens as part of routine setup.

The installed `gh` CLI owns authentication. This provider skill owns literal configuration, repository alias resolution, local export publication, narrow response-format helpers and shared collaboration identity/transport/recovery. Issues and Pull Requests share the same collection/Markdown shape; Discussions and Projects keep their own renderers. No use skill depends on another use skill.

## Configuration
A normal `gh auth login` uses gh's credential storage; preserve that existing route. See [official authentication](https://cli.github.com/manual/gh_auth_login) and [environment precedence](https://cli.github.com/manual/gh_help_environment). Do not switch accounts, broaden grants, or print tokens implicitly. Legacy export readiness uses `gh auth status`; exact issue/PR collaboration additionally establishes and checks the effective user identity. Inspect the intended account/host before a live operation.

Optional `.env` and `github-repos.json` live in the selected configuration directory and are ignored. Adjacent examples contain synthetic fields only. `GITHUB_REPOS_PATH` overrides the JSON location; relative values resolve against the selected configuration directory, not the caller's project. `GITHUB_ENV_FILE` selects an explicit env file, relative to cwd if not absolute; a missing selected file fails. Exported variables win. Only literal `GITHUB_REPOS_PATH`, `GH_TOKEN`, `GH_HOST` and `GITHUB_EXPECTED_ACTOR` assignments are accepted from the file; nothing is sourced/evaluated. A local `GH_TOKEN` is optional when the user chooses it over gh's account store. Keep real config owner-readable and never committed.

Exact issue/PR operations use the [collaboration runtime contract](collaboration.md). They establish the effective actor through a real `/user` request under gh's environment precedence, bind the repository ID, and require the expected actor for execution. Their recovery journals belong to the operated project's ignored private state, separate from setup credentials. Bulk exports and other GitHub domains keep their existing contracts.

Repo aliases require unique simple names, owner/repo fields, optional project owner, and positive project numbers with simple export names. `issues`/`prs`/`discussions` flags are retained for aggregate legacy consumers; an explicit standalone domain export selects its own capability. The configuration is not a write allowlist. Literal `OWNER/REPO` works without any config for issue/PR/Discussion operations. Projects use an explicit configured alias; status moves target its first configured organization project.

## Commands and runtime
From the collection root:
```sh
bash setup-github/scripts/authorize check
bash setup-github/scripts/authorize status
bash setup-github/scripts/authorize list-repos
```
`check` inspects local gh/jq availability and an existing alias file without network access; it does not verify credentials. `status` invokes gh's account check and may access the network. `list-repos` reads only local metadata. No token value is printed by these helpers.

Each use skill needs Bash 3.2+, gh, jq, and Python 3.11+ for Markdown rendering. With uv installed, rendering uses the selected capability's manifest/lock. `GITHUB_PYTHON` can select an existing compatible executable instead. The provider has no all-service Python environment. [setup-github](../SKILL.md) covers onboarding.

Read failures and ambiguous targets are errors. Export retrieval/rendering completes in a private temporary directory before named output artifacts are replaced. Multi-file publication is not a transaction; interrupted replacement attempts restore the artifact currently being moved, and report retained recovery files if restoration fails. Do not treat a successful local export as proof of unlimited server history or a consistent remote snapshot.

## Offline checks
Run `bash tests/test-operations.sh` and `bash tests/test-render.sh` from the setup skill folder. They cover provider configuration, shared issue/PR exports and rendering, failure preservation, and interrupted publication using synthetic data. Capability-specific writes and renderers are tested beside their owning use skills.

Collaboration write receipts and their OS lock default to `~/.agent-hands/github/HOST_OWNER_REPO/`, separate from this configuration and gh authentication. These private records contain actor/target IDs, operation fingerprints and verification outcomes, not Git commits. Preserve uncertain operations; see [journal selection and migration](collaboration.md).

## Private settings location
The default is `~/.agent-hands/github-settings/config/`. Real files remain untracked; examples stay beside this skill. [Private settings selection and migration](../../setup-agent-hands/references/private-settings.md) defines the common root override, explicit preview/execution, stopped-caller requirement, Canvas renewal locking and interruption recovery. Authentication is preserved; do not move an existing store by copying selected token files or discarding pending records.

## Local export publication recovery
Export staging and original-output backups live in mode-0700 `~/.agent-hands/github-exports/RUN/`, separate from configuration, gh authentication and remote-write journals. Each run records the explicit destination, controller, artifact hashes and publication status in `publication.json`. New/previous artifacts can contain private repository text. Publication requires one filesystem and refuses overlapping unresolved exports, symlinks, unsafe names and legacy `.github-export.*` staging at the destination. A failed retrieval leaves the old output unchanged. Multi-artifact publication is not atomic; completed earlier artifacts can coexist with an interrupted later artifact.

From this setup folder, `python3 scripts/export_state.py inspect /absolute/private/RUN` reads the exact run without resending requests. `reconcile` independently fingerprints outputs and updates only local classification. For an absent controller and an exact inspected hash, `restore RUN --execute --hash SHA256` restores only missing targets whose retained preimages still match. It never replaces existing content. A concurrent file/directory appearing at the target makes publication/restoration fail rather than overwrite it. An interrupted directory reservation can leave an empty target requiring separate inspection; originals and the operation record remain private and protected. A partial run stays blocked until reconciled or explicitly reviewed; recovery does not rerun retrieval or publication.

The EXIT handler classifies retrieval failure and retains recovery. Resolved runs older than seven days with an absent controller are eligible for explicit `retire RUN` preview; `--execute --hash SHA256` requires separate itemized deletion consent and removes only that exact unchanged run. Unresolved records never age out. No background retirement or historical sweep runs. `legacy /absolute/output` inventories old `.github-export.*` folders without moving, deleting or assuming their contents are disposable; those unregistered originals need owner review before action.
