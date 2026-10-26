---
name: setup-github
description: "Install selected GitHub capabilities, establish or repair account access, choose existing profiles, and diagnose configuration or authentication. Owns the shared provider runtime used by the selected use skills."
---
# Setup GitHub
Select one or more use skills and keep this setup folder as their sibling. Its [account-access reference](references/account-access.md) describes shared provider support. Each capability runs with only this provider dependency; unrelated services and the other GitHub domains are optional. Bash 3.2+, gh, jq, and Python 3.11+ rendering are required. macOS offline execution is verified; fresh Linux/WSL onboarding is not yet verified, and native Windows needs a Bash-compatible environment.

1. Inspect existing tools and account settings. Install missing gh/jq through the appropriate package manager within setup authorization. For missing uv, follow [official installation](https://docs.astral.sh/uv/getting-started/installation/); uv can provision compatible Python. Preserve existing toolchains.
2. Run the selected `scripts/github --help` with Bash. Each use skill has its own uv manifest/lock with no third-party Python packages. `GITHUB_PYTHON` may select a compatible existing interpreter instead.
3. Preserve existing gh authentication. If absent and setup is authorized, follow [gh auth login](https://cli.github.com/manual/gh_auth_login) and let the user complete consent. Do not broaden grants, switch accounts, or acquire credentials merely because a read is denied. Auth status is not permission to write.
4. Aliases are optional for issue/PR/Discussion work: pass `OWNER/REPO`. For aliases/Projects, verify ignores and copy the tailored JSON example only if the real file is absent. Set exact owner/repository/project selections privately. No personal repository list is built in.
5. Run the provider's local `check`, then authorized account/read verification. Do not create an issue or move a project item as a setup test. Report runtime readiness, live access, and client skill discovery separately.

Do not push, create repositories, or change a project's automation as part of onboarding. Existing private snapshot/index destinations remain consumer choices.

## Account access and shared runtime
Read [account access and provider support](references/account-access.md) for configuration, account selection, initial authorization, reconnection and diagnosis. This setup skill owns the provider scripts, examples and tests that the selected use skills load. Automatic refresh, where supported, stays in that runtime; normal operations do not require rerunning setup or granting broader access. Keep credential establishment separate from permission for each service action, and preserve existing user approval within its stated scope.

## Optional global discovery
Ask whether this selected capability should be available globally and which supported local clients (Codex, Claude Code, or both) should receive it. Preserve an already stated choice; do not re-ask for granted installation scope. Select only the requested capabilities with repeated `--skill`; omission is refused for this service. Read the [shared link procedure](../setup-agent-hands/references/global-skill-links.md), inspect existing destinations, and use this owner's entrypoint from the checkout root:
```sh
python3 setup-github/scripts/link-skills.py --client codex --skill use-github-issues
```
This previews only; add `--execute` for the authorized selection. The optional linker requires Python 3.9+ without external packages and keeps provider runtimes separate. Correct links are unchanged; conflicting user files/links are preserved. An explicit previous checkout permits recoverable repair as described in the shared procedure. Verify filesystem targets and fresh client discovery separately; links do not grant account access or operation permission.
