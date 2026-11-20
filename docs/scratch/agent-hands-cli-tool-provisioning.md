---
status: captured
---
# Agent Hands CLI tool provisioning
Have the selected Agent Hands setup routines provision the terminal tools their capabilities need, across supported platforms, so a fresh machine does not need a manual tool round after setup.

What the capabilities need: `uv` (each Python capability's locked environment), `gh` (GitHub domains), `jq` and `curl` (Bash services such as Trello, Odoo and GitHub), `shasum` (Trello mutation previews), and Pandoc with `--sandbox` plus native Pango and fonts (Markdown-to-PDF rendering).

Gaps noticed while setting up a WSL (Ubuntu) machine on 2026-10-27:
- `gh` is not installed by any script; `brew-installs.sh` covers `uv`, `jq`, `pandoc` and `weasyprint`, and `dnf-installs.sh` covers Fedora.
- The Linux/WSL path depends on Homebrew. On a WSL machine without Homebrew or passwordless `sudo`, user-level installs into `~/.local/bin` worked: uv's official installer (with `UV_NO_MODIFY_PATH=1`, since the shell rc files are links into configs) and the checksummed `gh` and Pandoc release tarballs. Ubuntu already had Pango and DejaVu fonts. There is no `apt` path.
- Native Windows only gets Tabby setup from `windows-tabby.ps1`; Git, `gh`, `uv` and Pandoc are not provisioned, and Windows PowerShell 5.1's `New-Item -ItemType SymbolicLink` needs elevation even with Developer Mode, while Python's `os.symlink` does not.
- `symlinks.sh` and the Agent Hands linkers have no Windows counterpart in the install scripts; Windows skill links were made by hand with the same selection.

## Ownership and relevance review
Moved from configs scratch on 2026-11-02. The installer filenames above refer to the containing configs repository; portable runtime setup belongs to Agent Hands. The observations remain useful: configs still has no `gh` provisioning, its Linux/WSL installer depends on Homebrew, and its native Windows entrypoint configures Tabby and fonts rather than these CLI dependencies.

[Setup Agent Hands](../../setup-agent-hands/SKILL.md) already owns selected-capability runtime setup, including missing uv, and [selective skill installation](../archive/selective-skill-installation.md) implements shared Python linkers. Those linkers handle client discovery rather than runtime installation; fresh Windows/Linux discovery remains unverified. Keep the original manual Windows-link observation as dated evidence, not a claim that Agent Hands has no linker. This remains captured work, with no implementation started by this move.

## Deferred from the completed distribution migration
This note owns the unresolved selected-runtime installation and supported-platform prerequisite questions. Maintained client linking behavior lives in [Optional global skill links](../../setup-agent-hands/references/global-skill-links.md), and Windows/Linux validation is [parked separately](skill-installation-windows-linux-validation.md); provider-specific live access remains with its setup/use record. Closing the cross-collection migration does not implement or validate these captured gaps.
