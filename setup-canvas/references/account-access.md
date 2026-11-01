# Account access and provider support
The command examples below identify their working directory. Private configuration lives in this setup folder beside its examples; explicit configuration overrides keep their precedence. Preserve existing credentials; do not create a parallel profile or move tokens as part of routine setup.

## Scope and dependencies
`scripts/canvas_auth.py` owns configuration parsing, account routing, the API transport, pagination, read throttling back-off, error classification and the identity check. [setup-canvas](../SKILL.md) owns onboarding; [use-canvas](../../use-canvas/SKILL.md) owns reads, exports, downloads and operation history on top of it; supported Canvas writes use its reviewed preview/execute gate. Python 3.11 or later with only its standard library. No Bash, other provider or personal workspace is required.

## Configuration contract
Two private files in the selected configuration directory, both ignored, copied from the adjacent [.env.example](../.env.example) and [canvas-accounts.example.json](../canvas-accounts.example.json) only when absent:
- `.env`: literal `CANVAS_*` assignments, one token variable per account (named by that account's `token_env`), and optionally `CANVAS_HISTORY_DIR` and `CANVAS_HISTORY_PLAIN_MONTHS` for `use-canvas`'s history. It is parsed as data, never sourced: outer quotes are stripped and an `export ` prefix is accepted, but nothing is expanded or run. Exported environment variables take precedence over file values, and an empty value counts as unset. The file cannot set `CANVAS_ENV_FILE`, `CANVAS_CONFIG_DIR`, `CANVAS_BASE_URL` or `CANVAS_API_URL`, and any other key or a malformed line is refused without echoing its value. Keep it owner-only; `check` refuses a group- or world-accessible file.
- `canvas-accounts.json`: an `accounts` array. Each entry has `alias` (letters, numbers, underscore, hyphen; unique), `base_url`, `user_id` (empty until confirmed with `whoami`), `token_env` (a `CANVAS_*` name), an optional `token_expires` (`YYYY-MM-DD`) and `courses` (course IDs to export, as strings). Optional `token_renewal` has exactly `enabled` (boolean), `lifetime_days` (2–90) and `before_days` (positive and smaller than the lifetime); absence disables renewal. Unknown fields are refused, which catches typos. See [token renewal](token-renewal.md) before enabling it.

`base_url` is the instance origin only: `https`, a host and an optional port, with no path, query, fragment or user information. The host is lower-cased and a trailing slash or port 443 dropped; institutions' own domains are fine. The token is sent only to that origin, in an `Authorization: Bearer` header, and never appears in a URL, command argument, log or error message. Account listings contain private routing metadata (instance, user ID) even though they omit tokens; do not publish them.

An exported `CANVAS_ENV_FILE` selects an explicit env file, and its directory then holds the accounts file. Otherwise an exported `CANVAS_CONFIG_DIR` selects the directory, otherwise this setup folder is used. A missing selected file or directory fails rather than falling back.

## Commands
From the collection root:
```sh
uv run --project setup-canvas python setup-canvas/scripts/canvas_auth.py accounts
uv run --project setup-canvas python setup-canvas/scripts/canvas_auth.py check example
uv run --project setup-canvas python setup-canvas/scripts/canvas_auth.py whoami example
```
`accounts` lists aliases, instances, recorded user IDs, token variable names, expiry dates and course counts, never token values. `check` makes no network request: it validates the configuration, the env file's permissions, the token's presence and the recorded expiry (warning within 14 days), and the Python and time-zone runtime. `whoami` reads `GET /api/v1/users/self` and `/api/v1/users/self/profile` and prints only the user ID, display name and time zone; with `user_id` recorded it also confirms the match. A local check is not evidence of remote access.

## Transport guarantees
- Requests go only to `base_url` and only under `/api/v1/`; dot segments, other origins, plain `http` and user information are refused before sending. Every request asks for string IDs (`Accept: application/json+canvas-string-ids`); integer IDs from a server that ignores it are converted without loss.
- Automatic redirects are disabled and the token is attached as an unredirected header. A read follows one redirect only when it stays within this instance's API; writes never follow redirects.
- Listings ask for `per_page=100` and follow the `Link` header's `rel="next"` URL as an opaque value, checked like any other URL. A refused next link, a repeated page, a non-array page or more than 200 pages fails the listing rather than returning part of it.
- Requests are sequential. A read that Canvas throttles (`429`, or `403` with "Rate Limit Exceeded") waits `Retry-After` seconds (at most 60) or 2, 4 and 8 seconds, then fails as `throttled`. A throttled write is never retried.
- Requests time out after 60 seconds without data, and an API response over 16 MiB is refused.

## Error kinds and next steps
| Kind | Meaning | Next step |
| --- | --- | --- |
| `config_missing`, `config_invalid` | A file is absent, unreadable or has a bad field or line | Create it from the example, or fix the named field. |
| `config_insecure` | The env file is accessible to other users | `chmod 600` the env file. |
| `base_url_invalid` | The instance address is not an https origin | Use the origin from the browser's address bar. |
| `token_missing` | The alias's token variable is empty | The user fills it in their editor. |
| `token_expired_local` | `token_expires` has passed | The user creates or regenerates a token. |
| `token_rejected` | Canvas refused the token (an invalid-token error, or a `401` with an authentication challenge and no permission message) | Reconnect as in the setup skill. Stops the whole run. |
| `identity_unconfirmed`, `identity_mismatch` | No `user_id` is recorded, or the token belongs to someone else | Run `whoami` and confirm; nothing proceeds on a mismatch. |
| `denied` | Canvas refused this resource for this user (`401` with a permission message, or `403`) | Stable for the role; not a sign that anything is missing. |
| `not_found` | `404` for this user | The resource is absent or hidden from this user. |
| `throttled` | Rate-limited after the bounded back-off | Wait and try later. |
| `request_rejected`, `server_error`, `http_error`, `malformed`, `too_large` | Canvas rejected the request, failed, or sent something unusable | Retry a read later; inspect before repeating a write. |
| `url_refused`, `redirect_refused`, `pagination_cycle`, `page_cap` | Canvas pointed outside its API, redirected unsafely, repeated a page or ran past the page cap | The listing is incomplete; nothing outside the instance was contacted. |
| `network_error` | No complete response arrived | Check connectivity. A write may still have landed; inspect before retrying. |
| `tz_data_missing`, `python_unsupported` | The runtime is incomplete | Install time-zone data, or use Python 3.11 or later. |

Hidden navigation and disabled-feature responses vary by institution and role. A bare `401` remains `denied` unless authentication evidence identifies a rejected token; a denial is not proof that content is absent. Selected-instance live results do not establish every hidden-resource response.

## Errors and authority
Report missing permissions, inaccessible resources and rejected tokens as they are; do not expand access, borrow another credential or fall back to browser cookies. The initial credential is established in the user's Canvas profile settings. The runtime has no OAuth command, generic token-management endpoint, in-place regeneration or deletion command. Explicitly authorized [successor-token renewal](token-renewal.md) creates only a replacement for the configured user's credential, preserving its access scopes. See Canvas's [API authentication documentation](https://developerdocs.instructure.com/services/canvas/oauth2/file.oauth), [pagination](https://canvas.instructure.com/doc/api/file.pagination.html) and [throttling](https://canvas.instructure.com/doc/api/file.throttling.html).
