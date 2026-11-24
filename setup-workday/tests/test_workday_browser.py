"""Synthetic page data for the Workday browser reader; no browser, network, credentials or real timesheets."""

import copy
import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import workday_browser as WB  # noqa: E402

LABEL = "GMT-06:00 Central Time (Chicago)"
ACCOUNT = {"schema_version": 1, "origin": "https://workday.example.invalid", "tenant": "exampletenant", "worker": "000$000001", "timezone": "America/Chicago", "timezone_label": LABEL, "enter_time_path": "/exampletenant/d/task/0000$00000.htmld"}
TARGET = {"tenant": "exampletenant", "worker": "000$000001", "week_start": "2026-10-26", "timezone": "America/Chicago"}
HEADERS = [h + "\nSort and filter column" for h in WB.REVIEW_HEADERS[:-1]] + ["Details"]
BLOCKS = [("10-26", "9-0", "12-0", "Mon, 10/26", "09:00 AM", "12:00 PM", "3", "10/26/2026"), ("10-30", "8-0", "14-0", "Fri, 10/30", "08:00 AM", "02:00 PM", "6", "10/30/2026"), ("11-1", "13-0", "16-0", "Sun, 11/1", "01:00 PM", "04:00 PM", "3", "11/01/2026")]


def calendar(blocks=BLOCKS, style="approved", hours=("3", "0", "0", "0", "6", "0", "3"), total="12", label="Approved"):
    # The marker's text as a background tab renders it, with the title and dates run together.
    events = [{"text": "Time Period End10/16/2026 - 10/31/2026", "title": "Time Period End", "subtitle": "10/16/2026 - 10/31/2026", "style": "non-event", "id": "", "allday": "true", "start": "10-31-0-0", "end": "10-31-0-0"}, {"text": "Synthetic Holiday", "title": "Synthetic Holiday", "subtitle": "", "style": "non-event", "id": "", "allday": "true", "start": "10-28-0-0", "end": "10-28-0-0"}]
    for i, (day, start, end, *_rest) in enumerate(blocks):
        events.append({"text": "Hours Worked", "title": "Hours Worked", "subtitle": "", "label": label, "style": style, "id": f"5773${i}", "allday": "false", "start": f"{day}-{start}", "end": f"{day}-{end}"})
    return {"range": ["Oct 26 – Nov 1, 2026"], "workers": ["selectedItem_000$000001"], "worker_labels": ["Synthetic Worker (abc123)"], "hours": [f"Hours: {h}" for h in hours], "summary": [{"label": "Example Time Entry: Example Hours", "value": total}, {"label": "Timesheet Total", "value": total}], "events": events}


def review(blocks=BLOCKS, out_reason="Out", worktags=""):
    rows = [[d, "Paid", "Hours Worked", i, o, out_reason, q, "Hours", worktags, "", ""] for (_a, _b, _c, d, i, o, q, _e) in blocks]
    return {"title": ["Review Time by Week"], "range": "Review Time by Week | October 26, 2026 - November 1, 2026 |", "headers": HEADERS, "rows": rows, "ids": [f"5773${i}" for i in range(len(rows))], "empty": not rows}


def details(blocks=BLOCKS, label=LABEL, tag="Example Class"):
    found = []
    for (_a, _b, _c, _d, i, o, q, full) in blocks:
        pairs = [("Reported Quantity", f"{q} Hours"), ("Time Entry Code", "Hours Worked"), ("In", f"{full} {i} {label}"), ("Out", f"{full} {o} {label}"), ("Out Reason", "Out"), ("Source", "User Entered"), ("Time Block Comment", "(empty)")]
        reported = f"View Time Block\n{q} Hours on {full}\nReported\nCalculated\nHistory\n" + "\n".join(f"{k}\n{k}\n\t{v}" for k, v in pairs)
        cpairs = [("Calculated Date", full), ("Calculated Time In", f"{full} {i} {label}"), ("Calculated Time Out", f"{full} {o} {label}"), ("Calculated Quantity", q), ("Time Calculation Tag", f"\t\n{tag}")]
        calculated = "View Time Block\n" + "\n".join(f"{k}\n{k}\n\t{v}" for k, v in cpairs)
        found.append({"reported": reported, "calculated": calculated})
    return found


def build(**changes):
    parts = {"account": dict(ACCOUNT), "target": dict(TARGET), "calendar": calendar(), "review": review(), "details": details()} | changes
    return WB.build_snapshot(parts["account"], parts["target"], parts["calendar"], parts["review"], parts["details"])


class ParsingTests(unittest.TestCase):
    def test_calendar_ranges(self):
        self.assertEqual(WB.parse_calendar_range("Nov 23 – 29, 2026"), date(2026, 11, 23))
        self.assertEqual(WB.parse_calendar_range("Oct 26 – Nov 1, 2026"), date(2026, 10, 26))
        self.assertEqual(WB.parse_calendar_range("Dec 28, 2026 – Jan 3, 2027"), date(2026, 12, 28))
        self.assertEqual(WB.parse_calendar_range("Dec 28 – Jan 3, 2027"), date(2026, 12, 28))
        for bad in ("Nov 24 – 30, 2026", "Sometime", ""):
            with self.assertRaises(WB.Refusal):
                WB.parse_calendar_range(bad)

    def test_review_range_and_clock(self):
        self.assertEqual(WB.parse_review_range("x | October 26, 2026 - November 1, 2026 |"), (date(2026, 10, 26), date(2026, 11, 1)))
        self.assertEqual([WB.clock(t) for t in ("12:15 AM", "09:10 AM", "12:00 PM", "02:20 PM")], ["00:15", "09:10", "12:00", "14:20"])
        with self.assertRaises(WB.Refusal):
            WB.clock("13:00 PM")

    def test_details_read_labels_not_values(self):
        fields = WB.dialog_fields(details()[0]["reported"], WB.REPORTED_LABELS)
        self.assertEqual(fields["Out"], f"10/26/2026 12:00 PM {LABEL}")
        self.assertEqual(fields["Out Reason"], "Out")
        with self.assertRaisesRegex(WB.Refusal, "missing"):
            WB.dialog_fields("View Time Block\nIn\nx", WB.REPORTED_LABELS)

    def test_the_zone_label_is_matched_never_read_as_an_offset(self):
        self.assertEqual(WB.detail_time(f"10/26/2026 09:00 AM {LABEL}", LABEL), (date(2026, 10, 26), "09:00"))
        with self.assertRaises(WB.Refusal) as caught:
            WB.detail_time("10/26/2026 09:00 AM GMT-05:00 Eastern Time (New York)", LABEL)
        self.assertEqual(caught.exception.code, "TIMEZONE_MISMATCH")

    def test_pay_periods_follow_the_markers(self):
        week = date(2026, 10, 26)
        periods = WB.pay_periods(week, [(date(2026, 10, 16), date(2026, 10, 31))])
        self.assertEqual(periods["2026-10-31"], "2026-10-16..2026-10-31")
        self.assertEqual(periods["2026-11-01"], "2026-11-01..")
        self.assertEqual(set(WB.pay_periods(date(2026, 11, 2), []).values()), {"period-containing-2026-11-02"})
        with self.assertRaises(WB.Refusal):
            WB.pay_periods(week, [(date(2026, 10, 29), date(2026, 10, 30))])


class SnapshotTests(unittest.TestCase):
    def test_a_populated_week_reads_completely(self):
        snapshot, result, observations = build()
        self.assertEqual(snapshot["status"], "approved")
        self.assertEqual(snapshot["service_total_minutes"], 720)
        self.assertEqual(snapshot["entries"][0]["entry"], {"date": "2026-10-26", "start": "09:00", "end": "12:00", "breaks": [], "time_type": "Hours Worked", "worktags": {}})
        self.assertFalse(snapshot["draft_save_supported"])
        self.assertTrue(snapshot["revision"].startswith("calendar-sha256:"))
        self.assertEqual(result["daily_minutes"], {"2026-10-26": 180, "2026-10-30": 360, "2026-11-01": 180})
        self.assertEqual(observations["classification_minutes"], {"Example Class": 720})
        self.assertEqual(observations["all_day_items"], ["Synthetic Holiday"])
        self.assertEqual(observations["payment_statuses"], {"Paid": 3})
        self.assertEqual(snapshot["pay_periods"]["2026-10-31"], "2026-10-16..2026-10-31")
        self.assertEqual(snapshot["pay_periods"]["2026-11-01"], "2026-11-01..")
        self.assertTrue(result["snapshot"]["pay_periods"] and len(set(snapshot["pay_periods"].values())) == 2)

    def test_an_empty_week_needs_confirmed_time_types(self):
        # As Workday shows an empty week: no In/Out columns at all.
        empty = dict(calendar=calendar(blocks=[], hours=("0",) * 7, total="0"), review=review(blocks=[]) | {"headers": ["Date", "Status", "Type", "Quantity", "Units", "Worktags", "Comment", "Details"]}, details=[])
        with self.assertRaisesRegex(WB.Refusal, "time_types"):
            build(**empty)
        snapshot, _, observations = build(account=ACCOUNT | {"time_types": ["Hours Worked"]}, **empty)
        self.assertEqual((snapshot["status"], snapshot["entries"], snapshot["allowed_time_types"]), ("empty", [], ["Hours Worked"]))
        self.assertEqual(observations["time_types"]["from_account"], ["Hours Worked"])
        with self.assertRaises(WB.Refusal) as caught:
            build(account=ACCOUNT | {"time_types": ["Hours Worked"]}, review=empty["review"], details=[])
        self.assertEqual(caught.exception.code, "VIEWS_DISAGREE")

    def test_status_comes_from_the_block_label(self):
        snapshot, _, observations = build(calendar=calendar(style="notsubmitted", label="Not Submitted"))
        self.assertEqual((snapshot["status"], {r["status"] for r in snapshot["entries"]}), ("draft", {"draft"}))
        self.assertEqual(observations["status_labels"], ["Not Submitted"])
        snapshot, _, _ = build(calendar=calendar(style="pending", label="Pending Review"))
        self.assertEqual(snapshot["status"], "unknown")
        self.assertEqual(build(calendar=calendar(style="saved", label="Not Submitted"))[0]["status"], "draft")
        self.assertEqual(build(calendar=calendar(style="submitted", label="Submitted"))[0]["status"], "submitted")
        for style, label in (("approved", "Submitted"), ("saved", "Approved"), ("submitted", "Not Submitted")):
            with self.assertRaises(WB.Refusal) as caught:
                build(calendar=calendar(style=style, label=label))
            self.assertEqual(caught.exception.code, "VIEWS_DISAGREE")

    def test_the_revision_follows_content_not_order_or_joined_text(self):
        first = calendar()
        shuffled = copy.deepcopy(first)
        shuffled["events"].reverse()
        for event in shuffled["events"]:
            event["text"] = event["text"].replace(" ", "")
        self.assertEqual(WB.calendar_revision(first), WB.calendar_revision(shuffled))
        changed = copy.deepcopy(first)
        changed["events"][2]["end"] = "10-26-15-0"
        self.assertNotEqual(WB.calendar_revision(first), WB.calendar_revision(changed))

    def test_saves_are_advertised_only_with_the_accounts_choice(self):
        self.assertFalse(build()[0]["draft_save_supported"])
        self.assertTrue(build(account=ACCOUNT | {"save_safeguard": "reread"})[0]["draft_save_supported"])

    def test_disagreements_and_unsupported_entries_refuse(self):
        other_worker = calendar()
        other_worker["workers"] = ["selectedItem_000$999999"]
        missing_row = review()
        missing_row["rows"] = missing_row["rows"][:-1]
        wrong_day = calendar(hours=("3", "0", "0", "0", "6", "0", "2"))
        cases = [
            ({"calendar": other_worker}, "WORKER_MISMATCH"),
            ({"review": missing_row, "details": details()[:-1]}, "VIEWS_DISAGREE"),
            ({"review": review(out_reason="Meal")}, "UNSUPPORTED_ENTRY"),
            ({"review": review() | {"ids": ["5773$9", "5773$1", "5773$2"]}}, "VIEWS_DISAGREE"),
            ({"review": review(worktags="Grant: X")}, "UNSUPPORTED_ENTRY"),
            ({"details": details(label="GMT-05:00 Eastern Time (New York)")}, "TIMEZONE_MISMATCH"),
            ({"calendar": wrong_day}, "TOTAL_MISMATCH"),
            ({"calendar": calendar(total="13")}, "TOTAL_MISMATCH"),
            ({"target": TARGET | {"week_start": "2026-11-02"}}, "WEEK_MISMATCH"),
        ]
        for changes, code in cases:
            with self.assertRaises(WB.Refusal) as caught:
                build(**changes)
            self.assertEqual(caught.exception.code, code, changes.keys())

    def test_workday_rounding_is_checked_and_blocks_saving(self):
        rounded = [("10-26", "9-0", "11-10", "Mon, 10/26", "09:00 AM", "11:10 AM", "2.25", "10/26/2026")]
        cal = calendar(blocks=rounded, hours=("2.25", "0", "0", "0", "0", "0", "0"), total="2.25")
        det = details(blocks=rounded)
        det[0]["calculated"] = det[0]["calculated"].replace("11:10 AM", "11:15 AM")
        snapshot, result, observations = build(account=ACCOUNT | {"save_safeguard": "reread"}, calendar=cal, review=review(blocks=rounded), details=det)
        self.assertEqual(snapshot["entries"][0]["entry"]["end"], "11:10")
        self.assertEqual((snapshot["service_total_minutes"], observations["workday_total_minutes"]), (130, 135))
        self.assertEqual(observations["rounded_blocks"], [{"date": "2026-10-26", "entered": ["09:00", "11:10"], "calculated": ["09:00", "11:15"], "calculated_minutes": 135}])
        self.assertFalse(snapshot["draft_save_supported"])
        far = details(blocks=rounded)
        far[0]["calculated"] = far[0]["calculated"].replace("11:10 AM", "11:30 AM")
        with self.assertRaises(WB.Refusal) as caught:
            build(calendar=cal, review=review(blocks=rounded), details=far)
        self.assertEqual(caught.exception.code, "VIEWS_DISAGREE")
        unrounded = details(blocks=rounded)
        with self.assertRaises(WB.Refusal) as caught:
            build(calendar=cal, review=review(blocks=rounded), details=unrounded)
        self.assertEqual(caught.exception.code, "TOTAL_MISMATCH")

    def test_a_week_without_a_timesheet_reads_as_unknown(self):
        cal = calendar(blocks=[], hours=("0",) * 7, total="0")
        cal["summary"] = []
        snapshot, _, observations = build(account=ACCOUNT | {"time_types": ["Hours Worked"], "save_safeguard": "reread"}, calendar=cal, review=review(blocks=[]) | {"headers": []}, details=[])
        self.assertEqual((snapshot["status"], snapshot["draft_save_supported"], observations["timesheet_shown"]), ("unknown", False, False))
        cal["hours"][1] = "Hours: 3"
        with self.assertRaises(WB.Refusal) as caught:
            build(account=ACCOUNT | {"time_types": ["Hours Worked"]}, calendar=cal, review=review(blocks=[]) | {"headers": []}, details=[])
        self.assertEqual(caught.exception.code, "TOTAL_MISMATCH")

    def test_entries_the_contract_cannot_hold_refuse(self):
        overnight = calendar()
        overnight["events"][2]["end"] = "10-28-1-0"
        allday = calendar()
        allday["events"][2]["allday"] = "true"
        unknown = calendar()
        unknown["events"].append({"text": "Something", "title": "", "style": "x", "id": "", "allday": "false", "start": "10-27-9-0", "end": "10-27-10-0"})
        garbled = calendar()
        garbled["events"][0]["subtitle"] = "sometime"
        for cal, code in ((overnight, "UNSUPPORTED_ENTRY"), (allday, "UNSUPPORTED_ENTRY"), (unknown, "UNKNOWN_EVENT"), (garbled, "UNKNOWN_PAY_PERIOD")):
            with self.assertRaises(WB.Refusal) as caught:
                build(calendar=cal)
            self.assertEqual(caught.exception.code, code)


class ProfileTests(unittest.TestCase):
    def test_the_profile_with_the_tenant_open_is_selected_from_urls_only(self):
        pages = [{"url": "https://workday.example.invalid/exampletenant/d/home.htmld", "browserContextId": "mine"}, {"url": "https://mail.example/", "browserContextId": "mine"}, {"url": "https://workday.example.invalid/othertenant/d/home.htmld", "browserContextId": "other"}]
        self.assertEqual(WB.select_context(pages, ACCOUNT), "mine")
        with self.assertRaisesRegex(WB.Refusal, "Open Workday"):
            WB.select_context(pages[1:], ACCOUNT)
        with self.assertRaisesRegex(WB.Refusal, "more than one"):
            WB.select_context(pages + [{"url": "https://workday.example.invalid/exampletenant/d/x", "browserContextId": "third"}], ACCOUNT)


class FakeTab:
    """Stands in for chrome_session.Tab: shows a calendar week and moves it when the week arrows are clicked."""

    def __init__(self, week):
        self.week, self.clicks = week, []

    def label(self):
        last = date.fromordinal(self.week.toordinal() + 6)
        return f"{self.week.strftime('%b')} {self.week.day} – {last.strftime('%b') + ' ' if last.month != self.week.month else ''}{last.day}, {last.year}"

    def evaluate(self, script, arg=None, timeout=30):
        if script == WB.RANGE_JS:
            return self.label()
        if script == WB.CLICK_JS:
            forward = "nextMonthButton" in arg
            self.clicks.append("next" if forward else "prev")
            self.week = date.fromordinal(self.week.toordinal() + (7 if forward else -7))
            return True
        raise AssertionError(script)

    def wait_for(self, script, arg=None, timeout=30):
        return True


class WeekNavigationTests(unittest.TestCase):
    def test_moves_one_week_at_a_time_and_checks_arrival(self):
        tab = FakeTab(date(2026, 11, 23))
        WB.go_to_week(tab, date(2026, 10, 26))
        self.assertEqual(tab.clicks, ["prev"] * 4)
        WB.go_to_week(tab, date(2027, 1, 4))
        self.assertEqual(tab.clicks[4:], ["next"] * 10)
        with self.assertRaisesRegex(WB.Refusal, "two years"):
            WB.go_to_week(tab, date(2030, 1, 7))


class OverviewTests(unittest.TestCase):
    WEEK = date(2026, 10, 26)

    def test_statuses_hours_and_labels(self):
        self.assertEqual(WB.summarize_week(ACCOUNT, self.WEEK, calendar()), {"week_start": "2026-10-26", "status": "approved", "minutes": 720, "labels": {"Approved": 3}})
        self.assertEqual(WB.summarize_week(ACCOUNT, self.WEEK, calendar(style="saved", label="Not Submitted"))["status"], "draft")
        self.assertEqual(WB.summarize_week(ACCOUNT, self.WEEK, calendar(style="odd", label="Sent Back"))["status"], "unknown")
        mixed = calendar()
        mixed["events"][-1]["label"] = "Not Submitted"
        self.assertEqual(WB.summarize_week(ACCOUNT, self.WEEK, mixed)["status"], "mixed")
        empty = calendar(blocks=[], hours=("0",) * 7, total="0")
        self.assertEqual(WB.summarize_week(ACCOUNT, self.WEEK, empty), {"week_start": "2026-10-26", "status": "empty", "minutes": 0, "labels": {}})
        empty["summary"] = []
        self.assertEqual(WB.summarize_week(ACCOUNT, self.WEEK, empty)["status"], "no-timesheet")

    def test_a_week_that_does_not_add_up_is_unreadable_not_guessed(self):
        all_day = calendar()
        all_day["events"][-1]["allday"] = "true"
        no_summary = calendar()
        no_summary["summary"] = []
        half_loaded = calendar(blocks=[])
        for shown, code in ((calendar(total="13"), "TOTAL_MISMATCH"), (all_day, "UNSUPPORTED_ENTRY"), (no_summary, "VIEWS_DISAGREE"), (half_loaded, "VIEWS_DISAGREE")):
            week = WB.summarize_week(ACCOUNT, self.WEEK, shown)
            self.assertEqual((week["status"], week["code"]), ("unreadable", code))
            self.assertNotIn("minutes", week)

    def test_another_week_or_worker_stops_the_overview(self):
        for shown, week, code in ((calendar(), date(2026, 11, 2), "WEEK_MISMATCH"), (calendar() | {"workers": ["selectedItem_000$000002"]}, self.WEEK, "WORKER_MISMATCH")):
            with self.assertRaises(WB.Refusal) as caught:
                WB.summarize_week(ACCOUNT, week, shown)
            self.assertEqual(caught.exception.code, code)

    def test_weeks_cover_the_dates_given(self):
        self.assertEqual(WB.overview_weeks("2026-10-28", "2026-11-09"), [date(2026, 10, 26), date(2026, 11, 2), date(2026, 11, 9)])
        self.assertEqual(WB.overview_weeks("2026-10-28", "2026-10-26"), [date(2026, 10, 26)])
        for first, last in (("2026-11-09", "2026-10-28"), ("2026-01-01", "2026-12-31"), ("soon", "2026-10-28"), (None, "2026-10-28")):
            with self.assertRaises(WB.Refusal):
                WB.overview_weeks(first, last)

    def test_a_week_still_loading_is_read_again_until_it_holds(self):
        session = WB.Session.__new__(WB.Session)
        session.account, session.tab = ACCOUNT, None
        loading, loaded = calendar(blocks=[], hours=("0",) * 7, total="0"), calendar()
        reads = iter([loading, loaded, loaded])
        with patch.object(WB.Session, "show_week"), patch.object(WB, "go_to_week"), patch.object(WB, "stable", lambda tab, script, arg=None: next(reads)), patch.object(WB.time, "sleep", lambda s: None):
            self.assertEqual(session.overview([self.WEEK])[0]["status"], "approved")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(os.path.realpath(self.dir.name))
        # Never route through a real running session on this machine.
        env = patch.dict(os.environ, {WB.STATE_ENV: str(self.root)})
        env.start()
        self.addCleanup(env.stop)

    def write_account(self, value, mode=0o600):
        path = self.root / "account.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        path.chmod(mode)
        return path

    def test_account_rules(self):
        self.assertEqual(WB.load_account(self.write_account(ACCOUNT))["tenant"], "exampletenant")
        for value, mode, code in ((ACCOUNT, 0o644, "PRIVATE_STORAGE_REQUIRED"), (ACCOUNT | {"extra": 1}, 0o600, "INVALID_ACCOUNT"), (ACCOUNT | {"save_safeguard": "none"}, 0o600, "INVALID_ACCOUNT"), (ACCOUNT | {"browser": "word"}, 0o600, "INVALID_ACCOUNT"), (ACCOUNT | {"enter_time_path": "/elsewhere/x"}, 0o600, "INVALID_ACCOUNT"), (ACCOUNT | {"origin": "http://x"}, 0o600, "INVALID_ACCOUNT")):
            with self.assertRaises(WB.Refusal) as caught:
                WB.load_account(self.write_account(value, mode))
            self.assertEqual(caught.exception.code, code)
        with self.assertRaises(WB.Refusal) as caught:
            WB.check_binding(ACCOUNT, TARGET | {"worker": "000$000002"})
        self.assertEqual(caught.exception.code, "TARGET_MISMATCH")

    def test_snapshots_are_owner_only_and_never_written_into_a_checkout(self):
        out = self.root / "week.json"
        WB.write_private(out, {"ok": True})
        self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)
        (self.root / "repo" / ".git").mkdir(parents=True)
        with self.assertRaises(WB.Refusal):
            WB.write_private(self.root / "repo" / "week.json", {})

    def test_a_week_can_be_named_instead_of_a_target_file(self):
        account = self.write_account(ACCOUNT)
        seen = []

        def perform(account_, request, session=None):
            seen.append(request)
            return {"status": "ok"}, 0

        with patch.object(WB, "perform", perform), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(WB.main(["reconcile", "--week", "2026-10-26", "--account", str(account)]), 0)
            self.assertEqual(WB.main(["overview", "--from", "2026-10-26", "--to", "2026-11-09", "--account", str(account)]), 0)
            with self.assertRaises(SystemExit):
                WB.main(["read", "--account", str(account)])
        self.assertEqual(seen, [{"command": "reconcile", "target": TARGET}, {"command": "overview", "from": "2026-10-26", "to": "2026-11-09"}])

    def test_cli_reports_refusals_without_stdout_payload(self):
        account = self.write_account(ACCOUNT)
        target = self.root / "target.json"
        target.write_text(json.dumps(TARGET | {"worker": "000$000002"}), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = WB.main(["read", "--target", str(target), "--account", str(account)])
        self.assertEqual((code, out.getvalue()), (2, ""))
        self.assertEqual(json.loads(err.getvalue())["code"], "TARGET_MISMATCH")
        with patch.object(WB, "read_week", return_value=build()):
            target.write_text(json.dumps(TARGET), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = WB.main(["read", "--target", str(target), "--account", str(account), "--out", str(self.root / "snap.json")])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(json.loads(out.getvalue())["read"]["snapshot"]["service_total_minutes"], 720)
        self.assertEqual(json.loads((self.root / "snap.json").read_text())["status"], "approved")


if __name__ == "__main__":
    unittest.main()
