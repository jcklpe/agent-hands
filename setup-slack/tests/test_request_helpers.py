import io, json, os, sys, tempfile
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import slack_auth as support
temporary = tempfile.TemporaryDirectory()
work = temporary.name
config = os.path.join(work, "slack-accounts.json")
with open(config, "w") as handle:
    json.dump({"accounts": [{"alias": "work", "team_id": "T1", "user_id": "U1", "token_env": "SLACK_TOKEN_TEST"}]}, handle)
os.environ["SLACK_ACCOUNTS_PATH"] = config
os.environ["SLACK_TOKEN_TEST"] = "xoxp-test"

def check(condition, message):
    if not condition:
        raise SystemExit("FAIL: " + message)

# URL parsing.
check(support.parse_message_url("https://x.slack.com/archives/C1/p1700000000000100?thread_ts=1699999999.000200&cid=C1") == ("C1", "1699999999.000200"), "thread_ts from URL")

# Paging fails loudly past the cap.
def endless(acct, method, params=None, json_body=False):
    return {"ok": True, "channels": [{"id": "C1"}], "response_metadata": {"next_cursor": "more"}}
support.call = endless
try:
    support.paged(support.account("work"), "conversations.list", {}, "channels", max_pages=3)
    raise SystemExit("FAIL: runaway paging should raise")
except support.SlackError:
    pass

print("PASS: Slack URL and bounded paging helpers")
