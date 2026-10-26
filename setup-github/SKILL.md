---
name: setup-github
description: "Install selected GitHub Issues, Pull Requests, Discussions, or Projects capabilities and configure gh authentication or repository aliases as needed."
---
# Setup GitHub
Select one or more use skills and keep [authorize-github](../authorize-github/SKILL.md) as their sibling. Each capability runs with only this provider dependency; unrelated services and the other GitHub domains are optional. Bash 3.2+, gh, jq, and Python 3.11+ rendering are required. macOS offline execution is verified; fresh Linux/WSL onboarding is not yet verified, and native Windows needs a Bash-compatible environment.

1. Inspect existing tools and account settings. Install missing gh/jq through the appropriate package manager within setup authorization. For missing uv, follow [official installation](https://docs.astral.sh/uv/getting-started/installation/); uv can provision compatible Python. Preserve existing toolchains.
2. Run the selected `scripts/github --help` with Bash. Each use skill has its own uv manifest/lock with no third-party Python packages. `GITHUB_PYTHON` may select a compatible existing interpreter instead.
3. Preserve existing gh authentication. If absent and setup is authorized, follow [gh auth login](https://cli.github.com/manual/gh_auth_login) and let the user complete consent. Do not broaden grants, switch accounts, or acquire credentials merely because a read is denied. Auth status is not permission to write.
4. Aliases are optional for issue/PR/Discussion work: pass `OWNER/REPO`. For aliases/Projects, verify ignores and copy the tailored JSON example only if the real file is absent. Set exact owner/repository/project selections privately. No personal repository list is built in.
5. Run the provider's local `check`, then authorized account/read verification. Do not create an issue or move a project item as a setup test. Report runtime readiness, live access, and client skill discovery separately.

Do not push, create repositories, or change a project's automation as part of onboarding. Existing private snapshot/index destinations remain consumer choices.
