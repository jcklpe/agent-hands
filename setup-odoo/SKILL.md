---
name: setup-odoo
description: "Set up the Odoo capability for a new user or machine: check shell tools, obtain account routing and a user-managed API key, create ignored configuration from tailored examples, and verify one bounded read."
---

# Setup Odoo
Read [authorize-odoo](../authorize-odoo/SKILL.md) for the configuration contract. Ordinary Odoo use does not require repeating onboarding.

1. Check Bash, jq, and curl. Use the user's operating-system package manager for missing tools within the authorized setup scope; do not install unrelated providers or a Python environment. The current launcher requires a Unix-like Bash environment. On Windows, select an existing WSL/Bash environment deliberately; native Windows is not yet a supported route.
2. Confirm the intended Odoo instance supports JSON-2 and the account has the needed API access. Follow the [official Odoo API/key instructions](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html). Do not infer external API entitlement from a working browser session, broaden access automatically, or request secrets in chat.
3. In the authorization folder, verify `.env`, `odoo-accounts.json`, and `odoo-last-request` are ignored. Copy `.env.example` and `odoo-accounts.example.json` only when their real destinations do not exist. Apply owner-only file permissions. Have the user put the key in the indicated local env entry and account routing in the JSON file; preserve existing profiles.
4. Run the authorization skill's local `check ALIAS`. State that this verifies configuration, not service access.
5. When a service read is authorized, use `bash ../use-odoo-projects/scripts/odoo projects list ALIAS --json` from this authorization folder. Stop after one relevant bounded result or a concrete access error. Do not perform a test write, rotate keys, or change permissions as an onboarding side effect.

Report which dependencies/configuration are ready, which reads succeeded, and any remaining platform or entitlement gap without revealing credential values. Repeated setup must preserve existing files and unrelated accounts.
