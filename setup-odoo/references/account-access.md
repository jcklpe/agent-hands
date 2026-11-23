# Account access and provider support
The command examples below identify their working directory. Private configuration defaults to `~/.agent-hands/odoo/config/`; synthetic examples remain beside this skill and explicit configuration overrides keep their existing precedence. Preserve existing credentials; do not create a parallel profile or move tokens as part of routine setup.

## Scope and dependencies
Own account selection, credential lookup, JSON-2 transport, and request pacing. [use-odoo-projects](../../use-odoo-projects/SKILL.md) owns supported project/task operations; [setup-odoo](../SKILL.md) owns first-time onboarding. Runtime: Bash 3.2+, jq, curl, sed/date/mktemp and ordinary Unix file utilities. Private storage and disposable-run registration additionally require Python 3.9+ with the standard library; no unrelated provider or workspace skill is required.

## Configuration contract
Use the selected configuration directory described above. Its `.env` contains literal `ODOO_*` assignments; `odoo-accounts.json` holds an accounts array with `alias`, HTTPS `base_url`, optional `database`, and `api_key_env`. Use the adjacent [.env.example](../.env.example) and [account example](../odoo-accounts.example.json). These files are distinct because multiple account profiles need structured routing.

An exported `ODOO_CONFIG_DIR` can select another configuration directory. An exported `ODOO_ENV_FILE` selects an explicit env file; relative paths resolve against the configuration directory. A missing explicitly selected file fails instead of silently using another file. Account and request-state paths resolve there too, never against the invoking project's working directory. Existing exported variables take precedence. Use ODOO-prefixed key-variable names in the env file. Single/double outer quotes are stripped; no variable, tilde, escape, or command expansion occurs. Inline comments are not parsed. The file cannot redirect its own directory or env selection.

Real env/account files and the request timestamp are ignored. Check ignores before creating them, preserve existing values, and use owner-only permissions for credential-bearing files. Never print credentials or write them to public examples, logs, commit bodies, or shell history. Account listings contain private routing metadata even though they omit keys; do not publish them automatically.

## Diagnose narrowly
From the setup skill folder, run `bash scripts/authorize check ALIAS`. It checks local alias existence, HTTPS routing, and key presence without printing the key or making a network request. This does not prove the key is valid, API access is enabled, or writes are authorized. The next meaningful check is one authorized bounded read through the use skill.

Check the actual server response for permission, expiration, or plan restrictions. Do not expand privileges or bypass denied access through browser cookies. The client has no automatic token refresh or key-creation command; guide the user through their Odoo account's key management when needed. Odoo JSON-2 and plan constraints are described in the [official Odoo documentation](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html).

## Provider support boundary
`scripts/client.sh` exposes internal account/transport functions to declared Odoo consumers. It reads no configuration and contacts no server merely when sourced. Supported user-facing operations are bounded by the use skill's dispatcher. The default request interval is five seconds, configurable from 0 through 300; calls are not retried automatically. Timestamp pacing is not an interprocess mutex, so do not claim strict concurrent rate limiting.

## Private settings location
The default is `~/.agent-hands/odoo/config/`. Real files remain untracked; examples stay beside this skill. [Private settings selection and migration](../../setup-agent-hands/references/private-settings.md) defines the common root override, explicit preview/execution, stopped-caller requirement, Canvas renewal locking and interruption recovery. Authentication is preserved; do not move an existing store by copying selected token files or discarding pending records.

## Disposable request files
Each request creates a mode-0700 registered `odoo-work.*` directory under the OS temporary root (`TMPDIR`, the macOS user temp directory, or `/tmp` on Unix). Checkout destinations are refused, including through aliases. The request JSON and response stay in that directory; normal completion and handled termination remove this run's directory. Curl receives its credential header on stdin and reads the JSON body from a private file, without putting either value in arguments. This does not promise that the caller's original credential environment is encrypted or absent from its process.

Hard termination can leave plaintext. `bash scripts/authorize cleanup-temp` previews eligible registered runs older than 24 hours; execution with `--execute` requires separate deletion approval. There is no automatic historical cleanup. Eligibility requires owner-only registration, matching directory identity and a confirmed-absent controller; live/reused PIDs, denied liveness, symlinks and unregistered old response files are preserved. These files never contain required authentication or write-recovery state. OS purging is only a backstop.
