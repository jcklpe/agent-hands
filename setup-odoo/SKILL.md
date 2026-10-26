---
name: setup-odoo
description: "Install selected Odoo capabilities, establish or repair account access, choose existing profiles, and diagnose configuration or authentication. Owns the shared provider runtime used by the selected use skills."
---

# Setup Odoo
Read [account access and provider support](references/account-access.md) for the configuration contract. Ordinary Odoo use does not require repeating onboarding.

1. Check Bash, jq, and curl. Use the user's operating-system package manager for missing tools within the authorized setup scope; do not install unrelated providers or a Python environment. The current launcher requires a Unix-like Bash environment. On Windows, select an existing WSL/Bash environment deliberately; native Windows is not yet a supported route.
2. Confirm the intended Odoo instance supports JSON-2 and the account has the needed API access. Follow the [official Odoo API/key instructions](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html). Do not infer external API entitlement from a working browser session, broaden access automatically, or request secrets in chat.
3. In the selected private configuration directory from the account-access reference, verify `.env`, `odoo-accounts.json`, and `odoo-last-request` are ignored. Copy `.env.example` and `odoo-accounts.example.json` only when their real destinations do not exist. Apply owner-only file permissions. Have the user put the key in the indicated local env entry and account routing in the JSON file; preserve existing profiles.
4. From this setup folder, run `bash scripts/authorize check ALIAS`. State that this verifies configuration, not service access.
5. When a service read is authorized, use `bash ../use-odoo-projects/scripts/odoo projects list ALIAS --json` from this setup folder. Stop after one relevant bounded result or a concrete access error. Do not perform a test write, rotate keys, or change permissions as an onboarding side effect.

Report which dependencies/configuration are ready, which reads succeeded, and any remaining platform or entitlement gap without revealing credential values. Repeated setup must preserve existing files and unrelated accounts.

## Account access and shared runtime
Read [account access and provider support](references/account-access.md) for configuration, account selection, initial authorization, reconnection and diagnosis. This setup skill owns the provider scripts, examples and tests that the selected use skills load. Automatic refresh, where supported, stays in that runtime; normal operations do not require rerunning setup or granting broader access. Keep credential establishment separate from permission for each service action, and preserve existing user approval within its stated scope.
