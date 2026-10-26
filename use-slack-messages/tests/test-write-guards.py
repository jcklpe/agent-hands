import io, json, os, sys, tempfile
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import slack_messages as capability
import slack_auth as support

def main(argv):
    return capability.main(argv, load_config=False)

temporary = tempfile.TemporaryDirectory()
work = temporary.name
config = os.path.join(work, "slack-accounts.json")
with open(config, "w") as handle:
    json.dump({"accounts": [{"alias": "work", "team_id": "T1", "user_id": "U1", "token_env": "SLACK_TOKEN_TEST"}]}, handle)
os.environ["SLACK_ACCOUNTS_PATH"] = config
os.environ["SLACK_TOKEN_TEST"] = "xoxp-test"

calls = []
state = {"auth": {"ok": True, "team_id": "T1", "user_id": "U1", "team": "Test", "user": "tester"}, "posted_user": "U1"}

def fake_call(acct, method, params=None, json_body=False):
    calls.append((method, params or {}))
    if method == "auth.test":
        return state["auth"]
    if method == "conversations.info":
        return {"ok": True, "channel": {"id": params["channel"], "name": "general"}}
    if method == "users.info":
        return {"ok": True, "user": {"id": params["user"], "profile": {"real_name": "Pat Example"}}}
    if method == "chat.postMessage":
        return {"ok": True, "channel": params["channel"], "ts": "1700000000.000100", "message": {"user": state["posted_user"]}}
    if method == "chat.getPermalink":
        return {"ok": True, "permalink": "https://example.slack.com/archives/C1/p1700000000000100"}
    if method == "conversations.open":
        return {"ok": True, "channel": {"id": "D1"}}
    raise AssertionError(f"unexpected method {method}")

support.call = fake_call

def run(argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(argv)
    return code, out.getvalue()

def methods():
    return [m for m, _ in calls]

def check(condition, message):
    if not condition:
        raise SystemExit("FAIL: " + message)

# Dry run shows the plan and sends nothing.
calls.clear()
code, out = run(["post", "work", "--channel", "C1", "--text", "hello there"])
check(code == 0 and "DRY RUN" in out and "hello there" in out and "#general (C1)" in out, "post dry run should print the plan")
check("chat.postMessage" not in methods() and "auth.test" not in methods(), "dry run must not call the API to send")

# Execute checks identity first, posts, and reports the permalink.
calls.clear()
code, out = run(["post", "work", "--channel", "C1", "--text", "hello there", "--execute"])
check(code == 0 and "Permalink:" in out, "post --execute should report the permalink")
check(methods().index("auth.test") < methods().index("chat.postMessage"), "identity check must precede the send")

# Replying via a message URL targets that thread.
calls.clear()
code, out = run(["post", "work", "--url", "https://example.slack.com/archives/C9/p1700000000000100", "--text", "reply", "--execute"])
sent = [p for m, p in calls if m == "chat.postMessage"][0]
check(sent["channel"] == "C9" and sent["thread_ts"] == "1700000000.000100", "URL reply should post into that thread")

# Identity mismatch and bot tokens are refused before sending.
state["auth"] = {"ok": True, "team_id": "T1", "user_id": "U2"}
calls.clear()
code, _ = run(["post", "work", "--channel", "C1", "--text", "x", "--execute"])
check(code == 1 and "chat.postMessage" not in methods(), "identity mismatch must refuse to send")
state["auth"] = {"ok": True, "team_id": "T1", "user_id": "U1", "bot_id": "B1"}
calls.clear()
code, _ = run(["post", "work", "--channel", "C1", "--text", "x", "--execute"])
check(code == 1 and "chat.postMessage" not in methods(), "a bot token must be refused")
state["auth"] = {"ok": True, "team_id": "T1", "user_id": "U1", "team": "Test", "user": "tester"}

# A message attributed to someone else is reported as an error.
state["posted_user"] = "U9"
code, _ = run(["post", "work", "--channel", "C1", "--text", "x", "--execute"])
check(code == 1, "posted-as-another-user must fail")
state["posted_user"] = "U1"

# DM needs a user ID and opens a conversation on execute.
code, _ = run(["dm", "work", "--user", "Pat", "--text", "hi"])
check(code == 1, "dm with a name instead of an ID should fail")
calls.clear()
code, out = run(["dm", "work", "--user", "U5", "--text", "hi", "--execute"])
check(code == 0 and "conversations.open" in methods() and "Pat Example (U5)" in out, "dm should open a conversation and label the recipient")

# Empty text is refused.
code, _ = run(["post", "work", "--channel", "C1", "--text", "   "])
check(code == 1, "empty text should fail")

print("PASS: use-slack-messages migrated guards")
