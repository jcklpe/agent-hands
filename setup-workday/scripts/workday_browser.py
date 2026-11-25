#!/usr/bin/env python3
"""Read, save and submit one Workday week at a time through Chrome, and list several weeks, producing use-workday's v1 snapshots.

Depending on the account's choice, commands connect to the user's running Chrome through Chrome's own consent flow (the user turns on remote debugging at chrome://inspect/#remote-debugging and clicks Allow when Chrome asks), or start a separate Chrome with a profile kept for Workday alone, which the user signs in to themself. With the running Chrome it finds the profile that has the configured Workday tenant open. Either way it works in a background tab that it opens and closes itself, and it never attaches to, navigates or closes the user's own tabs. It needs only the Python standard library.

Reading moves between weeks and opens read-only views: the Enter Time week calendar, Review Time by Week and each block's details, cross-checked, with a refusal for anything it cannot verify. Only save, submit-preview and submit use entry or submission controls; check-in, check-out and calculation controls are never used.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import socket
import stat
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "use-workday" / "scripts"))
from workday_core import NotDispatched, Refusal, read_timesheet, save_draft, target as check_target, verify_plan  # noqa: E402
from workday_journal import Journal, write_private  # noqa: E402
sys.path.insert(0, str(HERE))
from chrome_session import BrowserError, Chrome, devtools_port  # noqa: E402

STATE_ENV = "AGENT_HANDS_STATE_DIR"
# Status comes from the label each calendar block shows. Labels seen on a real tenant map to a status; anything else reads as unknown, which use-workday treats as protected. A style seen with its label must agree with it.
STATUS_LABELS = {"Approved": "approved", "Not Submitted": "draft", "Submitted": "submitted"}
STYLE_LABELS = {"approved": "Approved", "saved": "Not Submitted", "submitted": "Submitted"}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# Quick Add enters in/out blocks of this time-entry code; anything else is refused before Workday is touched.
SAVE_TYPES = {"Hours Worked"}
SAVE_SAFEGUARDS = {"reread"}
# A save whose outcome was lost counts as not applied only once the week still lacks it this long after the attempt.
SETTLE = timedelta(minutes=10)
MONTHS = {name: number for number, name in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
REVIEW_HEADERS = ["Date", "Status", "Type", "In", "Out", "Out Reason", "Quantity", "Units", "Worktags", "Comment", "Details"]
REPORTED_LABELS = ["Reported Quantity", "Time Entry Code", "In", "Out", "Out Reason", "Source", "Time Block Comment"]
CALCULATED_LABELS = ["Calculated Date", "Calculated Time In", "Calculated Time Out", "Calculated Quantity", "Time Calculation Tag"]
ACCOUNT_REQUIRED = {"schema_version", "origin", "tenant", "worker", "timezone", "timezone_label", "enter_time_path"}
ACCOUNT_OPTIONAL = {"time_types", "save_safeguard", "browser"}
# "everyday" connects to the user's running Chrome with an Allow click per connection; "own" starts a separate Chrome with a profile kept for Workday alone, in which the user signs in once per session.
BROWSERS = {"everyday", "own"}
SIGN_IN_MINUTES = 10
SIGN_IN_POLL_S = 1
SIGN_IN_STEADY_S = 5
CONNECT_S = 120
STEP_S = 30
MAX_WEEK_STEPS = 104
MAX_OVERVIEW_WEEKS = 26
OVERVIEW_PAUSE_S = 2


def refuse(code, remedy):
    raise Refusal(code, remedy)


# Account configuration


def state_base():
    base = Path(os.environ.get(STATE_ENV) or str(Path.home() / ".agent-hands"))
    if not base.is_absolute():
        refuse("PRIVATE_STORAGE_REQUIRED", f"Set {STATE_ENV} to an absolute private directory.")
    return base / "workday"


def account_path(explicit=None):
    return Path(explicit) if explicit else state_base() / "config" / "account.json"


def load_account(path):
    path = Path(path)
    if not path.is_file():
        refuse("ACCOUNT_MISSING", f"Create {path} from setup-workday/account.example.json with the tenant, worker, time zone and Workday time-zone label the user confirmed, then chmod 600 it.")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        refuse("PRIVATE_STORAGE_REQUIRED", f"Restrict {path} to its owner with chmod 600.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        refuse("INVALID_ACCOUNT", "The account file is not valid JSON.")
    if not isinstance(data, dict) or not ACCOUNT_REQUIRED <= set(data) or set(data) - ACCOUNT_REQUIRED - ACCOUNT_OPTIONAL or data["schema_version"] != 1:
        refuse("INVALID_ACCOUNT", "The account file needs exactly schema_version 1, origin, tenant, worker, timezone, timezone_label, enter_time_path and optionally time_types, save_safeguard and browser.")
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+", str(data["origin"])):
        refuse("INVALID_ACCOUNT", "origin must be the Workday site's https origin, without a path.")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(data["tenant"])):
        refuse("INVALID_ACCOUNT", "tenant must be the tenant name from the Workday address.")
    if not str(data["enter_time_path"]).startswith(f"/{data['tenant']}/"):
        refuse("INVALID_ACCOUNT", "enter_time_path must be the tenant's Enter My Time address path.")
    if not isinstance(data["timezone_label"], str) or not data["timezone_label"].strip():
        refuse("INVALID_ACCOUNT", "timezone_label must be Workday's label for the confirmed time zone, as a block's details show it.")
    types = data.get("time_types", [])
    if not isinstance(types, list) or not all(isinstance(t, str) and t.strip() for t in types):
        refuse("INVALID_ACCOUNT", "time_types must be a list of confirmed Workday time-entry codes.")
    if "save_safeguard" in data and data["save_safeguard"] not in SAVE_SAFEGUARDS:
        refuse("INVALID_ACCOUNT", "save_safeguard may only be \"reread\", and only when the user chose it.")
    if data.get("browser", "everyday") not in BROWSERS:
        refuse("INVALID_ACCOUNT", "browser may be \"everyday\" or \"own\".")
    check_target({"tenant": data["tenant"], "worker": data["worker"], "week_start": "2026-01-05", "timezone": data["timezone"]})
    return data


def check_binding(account, target):
    for key in ("tenant", "worker", "timezone"):
        if target[key] != account[key]:
            refuse("TARGET_MISMATCH", f"The target's {key} differs from the confirmed account; correct the target or the account file.")


# Pure parsing of what the pages show


def parse_calendar_range(text):
    match = re.fullmatch(r"([A-Z][a-z]{2}) (\d{1,2})(?:, (\d{4}))? [–-] (?:([A-Z][a-z]{2}) )?(\d{1,2}), (\d{4})", (text or "").strip())
    if not match:
        refuse("LAYOUT_CHANGED", f"Unrecognized calendar week {text!r}.")
    m1, d1, y1, m2, d2, y2 = match.groups()
    try:
        first, last = MONTHS[m1], MONTHS[m2 or m1]
        year_end = int(y2)
        year_start = int(y1) if y1 else (year_end - 1 if first > last else year_end)
        start, end = date(year_start, first, int(d1)), date(year_end, last, int(d2))
    except (KeyError, ValueError):
        refuse("LAYOUT_CHANGED", f"Unrecognized calendar week {text!r}.")
    if start.weekday() != 0 or end - start != timedelta(days=6):
        refuse("LAYOUT_CHANGED", "The calendar is not showing a Monday-to-Sunday week.")
    return start


def parse_review_range(text):
    match = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4}) - ([A-Z][a-z]+ \d{1,2}, \d{4})", text or "")
    if not match:
        refuse("LAYOUT_CHANGED", "Review Time by Week does not show its date range.")
    try:
        start, end = (datetime.strptime(part, "%B %d, %Y").date() for part in match.groups())
    except ValueError:
        refuse("LAYOUT_CHANGED", "Review Time by Week shows an unrecognized date range.")
    return start, end


def day_in_week(days, month, day):
    found = [d for d in days if d.month == month and d.day == day]
    if len(found) != 1:
        refuse("WEEK_MISMATCH", f"A block dated {month}/{day} is outside the selected week.")
    return found[0]


def stamp_parts(value):
    match = re.fullmatch(r"(\d{1,2})-(\d{1,2})-(\d{1,2})-(\d{1,2})", value or "")
    if not match:
        refuse("LAYOUT_CHANGED", f"Unrecognized block time {value!r}.")
    return [int(part) for part in match.groups()]


def clock(text):
    match = re.fullmatch(r"(\d{1,2}):(\d{2}) (AM|PM)", (text or "").strip())
    if not match:
        refuse("LAYOUT_CHANGED", f"Unrecognized time {text!r}.")
    hour, minute, half = int(match.group(1)), int(match.group(2)), match.group(3)
    if not 1 <= hour <= 12 or minute > 59:
        refuse("LAYOUT_CHANGED", f"Unrecognized time {text!r}.")
    hour = hour % 12 + (12 if half == "PM" else 0)
    return f"{hour:02d}:{minute:02d}"


def hours(text, prefix=""):
    value = (text or "").strip()
    if prefix:
        if not value.startswith(prefix):
            refuse("LAYOUT_CHANGED", f"Unrecognized hours {text!r}.")
        value = value[len(prefix):].strip()
    try:
        number = Decimal(value)
    except InvalidOperation:
        refuse("LAYOUT_CHANGED", f"Unrecognized hours {text!r}.")
    minutes = number * 60
    if minutes != minutes.to_integral_value() or minutes < 0:
        refuse("TOTAL_MISMATCH", f"{text!r} is not a whole number of minutes.")
    return int(minutes)


def minutes_between(start, end):
    (h1, m1), (h2, m2) = (map(int, start.split(":")), map(int, end.split(":")))
    return (h2 * 60 + m2) - (h1 * 60 + m1)


def parse_events(events, week_start):
    days = [week_start + timedelta(days=i) for i in range(7)]
    blocks, markers, holidays = [], [], []
    for event in events:
        if event.get("id"):
            if event.get("allday") != "false":
                refuse("UNSUPPORTED_ENTRY", "An all-day time entry is not supported; review it in Workday.")
            start, end = stamp_parts(event.get("start")), stamp_parts(event.get("end"))
            on = day_in_week(days, start[0], start[1])
            if day_in_week(days, end[0], end[1]) != on:
                refuse("UNSUPPORTED_ENTRY", "A block that crosses midnight is not supported.")
            blocks.append({"id": event["id"], "style": event.get("style") or "", "label": event.get("label") or "", "title": event.get("title") or "", "date": on, "start": f"{start[2]:02d}:{start[3]:02d}", "end": f"{end[2]:02d}:{end[3]:02d}"})
            continue
        text = event.get("text") or ""
        # A background tab can run the title and dates together, so the marker is read from its own title and subtitle; anything that mentions a time period but does not parse stops the read.
        if (event.get("title") or "").strip() == "Time Period End" or "Time Period" in text:
            marker = re.fullmatch(r"(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", (event.get("subtitle") or "").strip())
            if not marker:
                refuse("UNKNOWN_PAY_PERIOD", "A pay-period marker on the calendar could not be read.")
            markers.append(tuple(datetime.strptime(part, "%m/%d/%Y").date() for part in marker.groups()))
        elif event.get("allday") == "true":
            holidays.append(text)
        else:
            refuse("UNKNOWN_EVENT", "The calendar shows an item without an ID that is neither a holiday nor a pay-period marker.")
    return blocks, markers, holidays


def pay_periods(week_start, markers):
    """Each day's pay period from the calendar's period-end markers. A week without a marker has no period boundary inside it."""
    days = [week_start + timedelta(days=i) for i in range(7)]
    if not markers:
        return {d.isoformat(): f"period-containing-{week_start.isoformat()}" for d in days}
    markers = sorted(markers, key=lambda m: m[1])
    result = {}
    for d in days:
        inside = [m for m in markers if m[0] <= d <= m[1]]
        if inside:
            result[d.isoformat()] = f"{inside[0][0].isoformat()}..{inside[0][1].isoformat()}"
        elif d > markers[-1][1]:
            result[d.isoformat()] = f"{(markers[-1][1] + timedelta(days=1)).isoformat()}.."
        else:
            refuse("UNKNOWN_PAY_PERIOD", f"The pay period for {d.isoformat()} cannot be read from the calendar.")
    return result


def parse_review(headers, rows, week_start):
    names = [h.split("\n")[0].strip() for h in headers]
    if names != REVIEW_HEADERS:
        refuse("LAYOUT_CHANGED", "Review Time by Week's columns changed.")
    days = [week_start + timedelta(days=i) for i in range(7)]
    parsed = []
    for cells in rows:
        if len(cells) != len(names):
            refuse("LAYOUT_CHANGED", "A Review Time by Week row has an unexpected shape.")
        row = dict(zip(names, (c.strip() for c in cells)))
        match = re.fullmatch(r"[A-Z][a-z]{2}, (\d{1,2})/(\d{1,2})", row["Date"])
        if not match:
            refuse("LAYOUT_CHANGED", f"Unrecognized review date {row['Date']!r}.")
        parsed.append(row | {"date": day_in_week(days, int(match.group(1)), int(match.group(2))), "start": clock(row["In"]), "end": clock(row["Out"])})
    return parsed


def dialog_fields(text, labels):
    lines = [line.strip() for line in re.split(r"[\n\t]+", text or "") if line.strip()]
    found = {}
    for index, line in enumerate(lines):
        if line in labels and line not in found:
            # Workday repeats each label (one copy is for screen readers) before the value.
            following = [value for value in lines[index + 1:index + 3] if value != line]
            if following:
                found[line] = following[0]
    missing = [label for label in labels if label not in found]
    if missing:
        refuse("LAYOUT_CHANGED", f"Block details are missing {', '.join(missing)}.")
    return found


def detail_time(text, label):
    match = re.fullmatch(r"(\d{2}/\d{2}/\d{4}) (\d{1,2}:\d{2} (?:AM|PM)) (.+)", (text or "").strip())
    if not match:
        refuse("LAYOUT_CHANGED", f"Unrecognized block time {text!r}.")
    if match.group(3) != label:
        refuse("TIMEZONE_MISMATCH", f"Workday shows the time zone {match.group(3)!r}, not the confirmed {label!r}; correct the account file or the Workday preference.")
    return datetime.strptime(match.group(1), "%m/%d/%Y").date(), clock(match.group(2))


def summary_minutes(items, label):
    found = [item for item in items if (item.get("label") or "").strip() == label]
    if len(found) != 1:
        refuse("LAYOUT_CHANGED", f"The summary does not show exactly one {label!r}.")
    return hours(found[0].get("value"))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def calendar_revision(calendar):
    """A fingerprint of what the week calendar shows, independent of event order and of how a background tab joins text."""
    keys = ("id", "style", "allday", "start", "end", "title", "subtitle", "label")
    events = sorted(({k: e.get(k) for k in keys} for e in calendar.get("events") or []), key=lambda e: json.dumps(e, sort_keys=True))
    material = {k: calendar.get(k) for k in ("range", "workers", "hours", "summary")} | {"events": events}
    return "calendar-sha256:" + fingerprint(material)


def build_snapshot(account, target, calendar, review, details):
    """Cross-check the three views and produce a validated v1 snapshot plus observations. Refuses on any disagreement."""
    week = date.fromisoformat(target["week_start"])
    if parse_calendar_range((calendar.get("range") or [""])[0]) != week:
        refuse("WEEK_MISMATCH", "The calendar is not showing the selected week.")
    if parse_review_range(review.get("range")) != (week, week + timedelta(days=6)):
        refuse("WEEK_MISMATCH", "Review Time by Week is not showing the selected week.")
    if f"selectedItem_{account['worker']}" not in (calendar.get("workers") or []) or len(calendar.get("worker_labels") or []) != 1:
        refuse("WORKER_MISMATCH", "The calendar does not show exactly the confirmed worker.")
    blocks, markers, holidays = parse_events(calendar.get("events") or [], week)
    # An empty week's review drops the In, Out and Out Reason columns; with "No items available" there is nothing to cross-check, and any calendar block still makes the views disagree below.
    rows = [] if review.get("empty") and not review.get("rows") else parse_review(review.get("headers") or [], review.get("rows") or [], week)
    if len(details) != len(rows):
        refuse("LAYOUT_CHANGED", "Every review row needs its block details.")
    by_key = {}
    for block in blocks:
        key = (block["date"], block["start"], block["end"])
        if key in by_key:
            refuse("DUPLICATE_RECORD", "Two calendar blocks share a date and times; reconcile them in Workday.")
        by_key[key] = block
    if sorted(by_key) != sorted((r["date"], r["start"], r["end"]) for r in rows):
        refuse("VIEWS_DISAGREE", "The calendar and Review Time by Week list different blocks; read again after Workday finishes loading.")
    ids = review.get("ids") or []
    if len(ids) != len(rows) or any(by_key[(r["date"], r["start"], r["end"])]["id"] != i for r, i in zip(rows, ids)):
        refuse("VIEWS_DISAGREE", "A review row's block ID differs from the calendar's.")
    entries, observed_types, classifications, payment, comments, rounded, counted_daily = [], set(), {}, {}, [], [], {}
    for row, detail in zip(rows, details):
        block = by_key[(row["date"], row["start"], row["end"])]
        minutes = minutes_between(block["start"], block["end"])
        reported, calculated = dialog_fields(detail.get("reported"), REPORTED_LABELS), dialog_fields(detail.get("calculated"), CALCULATED_LABELS)
        if block["title"] and block["title"] != row["Type"]:
            refuse("VIEWS_DISAGREE", "A block's calendar title and review type differ.")
        if reported["Time Entry Code"] != row["Type"]:
            refuse("VIEWS_DISAGREE", "A block's details and review type differ.")
        if row["Out Reason"] != "Out" or reported["Out Reason"] != "Out":
            refuse("UNSUPPORTED_ENTRY", "A block ends with a meal, break or other out reason, which the v1 contract cannot represent yet.")
        if row["Worktags"]:
            refuse("UNSUPPORTED_ENTRY", "A block carries worktags; their exact identifiers are not read yet.")
        for field, expected in (("In", block["start"]), ("Out", block["end"])):
            if detail_time(reported[field], account["timezone_label"]) != (block["date"], expected):
                refuse("VIEWS_DISAGREE", "A block's details show different times from the calendar.")
        # Workday may round the times it counts; its details give the calculated interval, which must sit within a quarter hour of the entered one and match every quantity shown.
        (calc_day_in, calc_in), (calc_day_out, calc_out) = (detail_time(calculated[f], account["timezone_label"]) for f in ("Calculated Time In", "Calculated Time Out"))
        if calc_day_in != block["date"] or calc_day_out != block["date"]:
            refuse("VIEWS_DISAGREE", "A block's calculated time falls on another day.")
        if abs(minutes_between(block["start"], calc_in)) >= 15 or abs(minutes_between(block["end"], calc_out)) >= 15:
            refuse("VIEWS_DISAGREE", "A block's calculated times differ from its entered times by more than rounding.")
        counted = minutes_between(calc_in, calc_out)
        if row["Units"] != "Hours" or hours(row["Quantity"]) != counted or hours(calculated["Calculated Quantity"]) != counted:
            refuse("TOTAL_MISMATCH", "A block's hours disagree with its calculated in and out times.")
        if counted != minutes:
            rounded.append({"date": block["date"].isoformat(), "entered": [block["start"], block["end"]], "calculated": [calc_in, calc_out], "calculated_minutes": counted})
        counted_daily[block["date"].isoformat()] = counted_daily.get(block["date"].isoformat(), 0) + counted
        if block["style"] in STYLE_LABELS and STYLE_LABELS[block["style"]] != block["label"]:
            refuse("VIEWS_DISAGREE", "A block's status label disagrees with its calendar style.")
        status = STATUS_LABELS.get(block["label"], "unknown")
        entries.append({"id": block["id"], "status": status, "entry": {"date": block["date"].isoformat(), "start": block["start"], "end": block["end"], "breaks": [], "time_type": row["Type"], "worktags": {}}})
        observed_types.add(row["Type"])
        tag = calculated["Time Calculation Tag"]
        classifications[tag] = classifications.get(tag, 0) + counted
        payment[row["Status"]] = payment.get(row["Status"], 0) + 1
        if row["Comment"]:
            comments.append({"date": block["date"].isoformat(), "start": block["start"], "comment": row["Comment"]})
    daily = {}
    for record in entries:
        e = record["entry"]
        daily[e["date"]] = daily.get(e["date"], 0) + minutes_between(e["start"], e["end"])
    shown = calendar.get("hours") or []
    if len(shown) != 7:
        refuse("LAYOUT_CHANGED", "The calendar does not show hours for all seven days.")
    for index, text in enumerate(shown):
        if hours(text, "Hours:") != counted_daily.get((week + timedelta(days=index)).isoformat(), 0):
            refuse("TOTAL_MISMATCH", "A day's hours on the calendar disagree with its blocks.")
    total, workday_total = sum(daily.values()), sum(counted_daily.values())
    # A week with no summary at all and nothing on it has no timesheet to read, as before employment; it reads as unknown so nothing can be saved into it.
    timesheet = bool(calendar.get("summary"))
    if timesheet and summary_minutes(calendar.get("summary") or [], "Timesheet Total") != workday_total:
        refuse("TOTAL_MISMATCH", "The timesheet total disagrees with the blocks, possibly because of time off or entries this reader cannot see.")
    if not timesheet and (entries or any(hours(text, "Hours:") for text in shown)):
        refuse("LAYOUT_CHANGED", "The calendar shows time but no timesheet summary.")
    types = sorted(observed_types | set(account.get("time_types", [])))
    if not types:
        refuse("UNKNOWN_TIME_TYPES", "No time type is visible this week; add the user-confirmed time-entry codes to the account file's time_types.")
    statuses = {r["status"] for r in entries}
    week_status = "unknown" if not timesheet else "empty" if not entries else statuses.pop() if len(statuses) == 1 else "unknown"
    # The v1 contract's total must equal its entries' minutes. Where Workday rounded, the cross-check above used Workday's own figures; the snapshot keeps the entered times and their total, and the week cannot be saved into.
    saveable = account.get("save_safeguard") in SAVE_SAFEGUARDS and timesheet and not rounded
    snapshot = {
        "schema_version": 1, "target": target, "revision": calendar_revision(calendar), "status": week_status,
        "entries": entries, "allowed_time_types": types, "pay_periods": pay_periods(week, markers),
        "service_total_minutes": total, "draft_save_supported": saveable, "certification": "",
    }
    result = read_timesheet(snapshot, target)
    observations = {
        "styles": sorted({b["style"] for b in blocks}), "status_labels": sorted({b["label"] for b in blocks}), "payment_statuses": payment, "classification_minutes": classifications,
        "summary": {item.get("label"): item.get("value") for item in calendar.get("summary") or []}, "all_day_items": holidays,
        "pay_period_markers": [[s.isoformat(), e.isoformat()] for s, e in markers], "comments": comments,
        "time_types": {"observed": sorted(observed_types), "from_account": sorted(account.get("time_types", []))},
        "timesheet_shown": timesheet, "rounded_blocks": rounded, "workday_total_minutes": workday_total,
        "revision_note": "Fingerprint of the calendar as read; Workday offers no service revision through the browser.",
    }
    return snapshot, result, observations


# Browser steps, through chrome_session's single-tab DevTools client.

CALENDAR_JS = """() => {
  const t = (e) => e ? (e.innerText || '').replace(/\\s+/g, ' ').trim() : '';
  const q = (s) => [...document.querySelectorAll(s)];
  return {
    range: q('[data-automation-id=dateRangeTitle]').map(t),
    workers: q('[data-automation-id^="selectedItem_"]').map(e => e.getAttribute('data-automation-id')),
    worker_labels: q('[data-automation-id=promptOption]').map(t),
    hours: q('[data-automation-id^="hoursEntered_"]').map(t),
    summary: q('[data-automation-id=summarizedListItem]').map(e => ({label: t(e.querySelector('[data-automation-id=summarizedListItemLabel]')), value: t(e.querySelector('[data-automation-id=summarizedListItemValue]'))})),
    events: q('[data-automation-id=calendarevent]').map(e => ({text: t(e), title: t(e.querySelector('[data-automation-id=calendarAppointmentTitle]')), subtitle: t(e.querySelector('[data-automation-id=calendarAppointmentSubtitle]')), label: (() => { const parts = ['calendarAppointmentTitle', 'calendarAppointmentSubtitle', 'calendarAppointmentSubtitle2']; const leaves = [...e.querySelectorAll('*')].filter(x => x.children.length === 0 && (x.textContent || '').trim() && !parts.some(p => x.closest('[data-automation-id=' + p + ']'))); return leaves.length ? leaves[leaves.length - 1].textContent.trim() : ''; })(), style: e.getAttribute('data-automation-appointment-style'), id: e.getAttribute('data-automation-eventid'), allday: e.getAttribute('data-automation-allday'), start: e.getAttribute('data-automation-startdate'), end: e.getAttribute('data-automation-enddate')}))
  };
}"""

REVIEW_JS = """() => {
  const header = document.querySelector('[data-automation-id=pageHeader]');
  const table = [...document.querySelectorAll('table')].find(x => [...x.querySelectorAll('th')].some(h => (h.innerText || '').startsWith('Out Reason')));
  return {
    title: [...document.querySelectorAll('[data-automation-id=pageHeaderTitleText]')].map(e => (e.innerText || '').trim()),
    range: header ? header.innerText : '',
    headers: table ? [...table.querySelectorAll('th')].map(h => (h.innerText || '').trim()) : [],
    rows: table ? [...table.querySelectorAll('tbody tr')].filter(r => r.querySelectorAll('td').length >= 8).map(r => [...r.querySelectorAll('td')].map(c => (c.innerText || '').trim())) : [],
    ids: table ? [...table.querySelectorAll('tbody tr')].filter(r => r.querySelectorAll('td').length >= 8).map(r => { const e = r.lastElementChild.querySelector('[data-automation-id^="selectedItem_"]'); return e ? e.getAttribute('data-automation-id').slice('selectedItem_'.length) : ''; }) : [],
    empty: /No items available/.test(document.body.innerText || '')
  };
}"""

# The text of the smallest element around the "View Time Block" heading that contains the needle, one text node per line so it does not depend on layout; null while the dialog is closed.
DIALOG_JS = """(needle) => {
  const heads = [...document.querySelectorAll('body *')].filter(e => e.children.length === 0 && (e.textContent || '').trim() === 'View Time Block');
  for (const head of heads) {
    let node = head;
    while (node && !(node.textContent || '').includes(needle)) node = node.parentElement;
    if (node) {
      const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
      const lines = [];
      while (walker.nextNode()) { const value = walker.currentNode.textContent.trim(); if (value) lines.push(value); }
      return lines.join('\\n');
    }
  }
  return null;
}"""

# A real click's event sequence, so Workday's widgets respond as they do to the mouse.
FIRE_JS = """const fire = (el) => {
  el.scrollIntoView({block: 'center'});
  for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
    const Kind = type.startsWith('pointer') && window.PointerEvent ? PointerEvent : MouseEvent;
    el.dispatchEvent(new Kind(type, {bubbles: true, cancelable: true, view: window, button: 0}));
  }
  return true;
};"""

CLICK_JS = "(selector) => { " + FIRE_JS + " const el = document.querySelector(selector); return el ? fire(el) : false; }"

CLICK_DETAILS_JS = "(index) => { " + FIRE_JS + """ const table = [...document.querySelectorAll('table')].find(x => [...x.querySelectorAll('th')].some(h => (h.innerText || '').startsWith('Out Reason')));
  const rows = table ? [...table.querySelectorAll('tbody tr')].filter(r => r.querySelectorAll('td').length >= 8) : [];
  const button = rows[index] ? rows[index].lastElementChild.querySelector('[data-automation-id=SEARCH_ICON_charm]') : null;
  return button ? fire(button) : false; }"""

# Inside the open dialog: the Calculated tab, or the close control.
DIALOG_CLICK_JS = "(what) => { " + FIRE_JS + """ const heads = [...document.querySelectorAll('body *')].filter(e => e.children.length === 0 && (e.textContent || '').trim() === 'View Time Block');
  if (!heads.length) return false;
  let box = heads[0];
  while (box && !(box.innerText || '').includes('Time Entry Code') && !(box.innerText || '').includes('Time Calculation Tag')) box = box.parentElement;
  if (!box) return false;
  if (what === 'calculated') {
    const tab = [...box.querySelectorAll('[role=tab]')].find(e => (e.innerText || '').trim() === 'Calculated') || [...box.querySelectorAll('*')].find(e => e.children.length === 0 && (e.textContent || '').trim() === 'Calculated');
    return tab ? fire(tab) : false;
  }
  let scope = heads[0], close = null;
  for (let i = 0; i < 12 && scope && !(close = scope.querySelector('[data-automation-id=closeButton]')); i++) scope = scope.parentElement;
  return close ? fire(close) : false; }"""

DIALOG_OPEN_JS = "() => [...document.querySelectorAll('body *')].some(e => e.children.length === 0 && (e.textContent || '').trim() === 'View Time Block')"
RANGE_JS = "() => { const e = document.querySelector('[data-automation-id=dateRangeTitle]'); return e ? e.innerText.trim() : ''; }"


def summarize_week(account, week, calendar):
    """One week's hours and status from its calendar alone. It is not cross-checked against the review or block details, so it never supports a save or submission."""
    if parse_calendar_range((calendar.get("range") or [""])[0]) != week:
        refuse("WEEK_MISMATCH", "The calendar is not showing the selected week.")
    if f"selectedItem_{account['worker']}" not in (calendar.get("workers") or []) or len(calendar.get("worker_labels") or []) != 1:
        refuse("WORKER_MISMATCH", "The calendar does not show exactly the confirmed worker.")
    found = {"week_start": week.isoformat()}
    try:
        blocks, _markers, _holidays = parse_events(calendar.get("events") or [], week)
        shown = calendar.get("hours") or []
        if len(shown) != 7:
            refuse("LAYOUT_CHANGED", "The calendar does not show hours for all seven days.")
        minutes = sum(hours(text, "Hours:") for text in shown)
        timesheet = bool(calendar.get("summary"))
        if timesheet and summary_minutes(calendar["summary"], "Timesheet Total") != minutes:
            refuse("TOTAL_MISMATCH", "The timesheet total disagrees with the days' hours.")
        if bool(minutes) != bool(blocks) or (blocks and not timesheet):
            refuse("VIEWS_DISAGREE", "The calendar's hours and blocks disagree.")
    except Refusal as error:
        return found | {"status": "unreadable", "code": error.code, "remedy": "Look at this week in Workday."}
    labels = {}
    for block in blocks:
        labels[block["label"]] = labels.get(block["label"], 0) + 1
    statuses = {STATUS_LABELS.get(label, "unknown") for label in labels}
    status = "no-timesheet" if not timesheet else "empty" if not blocks else statuses.pop() if len(statuses) == 1 else "mixed"
    return found | {"status": status, "minutes": minutes, "labels": labels}


def overview_weeks(first, last):
    """The Mondays of every week from the one holding the first date to the one holding the last."""
    try:
        start, end = date.fromisoformat(first), date.fromisoformat(last)
    except (TypeError, ValueError):
        refuse("INVALID_INPUT", "Give --from and --to as YYYY-MM-DD.")
    start, end = start - timedelta(days=start.weekday()), end - timedelta(days=end.weekday())
    if end < start or (end - start).days // 7 >= MAX_OVERVIEW_WEEKS:
        refuse("INVALID_INPUT", f"Choose between one and {MAX_OVERVIEW_WEEKS} weeks, earliest first.")
    return [start + timedelta(days=7 * i) for i in range((end - start).days // 7 + 1)]


def stable(tab, script, arg=None, tries=20):
    """Evaluate until two reads 750 ms apart agree, so a half-rendered view is never read."""
    previous = None
    for _ in range(tries):
        current = tab.evaluate(script, arg)
        if current is not None and current == previous:
            return current
        previous = current
        time.sleep(0.75)
    refuse("PAGE_UNSETTLED", "Workday kept changing while being read; try again when it has finished loading.")


def select_context(pages, account):
    """The browser context (Chrome profile) of the user's open Workday tabs for this tenant; only URLs are compared, nothing is attached."""
    prefix = f"{account['origin']}/{account['tenant']}/"
    contexts = {p.get("browserContextId") for p in pages if (p.get("url") or "").startswith(prefix)}
    if not contexts:
        refuse("WORKDAY_TAB_MISSING", "Open Workday for the configured tenant in the Chrome profile to use, signed in, then run again.")
    if len(contexts) > 1:
        refuse("PROFILE_AMBIGUOUS", "Workday is open in more than one Chrome profile; close it in all but the one to use.")
    return contexts.pop()


def click(tab, selector, what):
    if not tab.evaluate(CLICK_JS, selector):
        refuse("LAYOUT_CHANGED", f"Workday's {what} control is missing.")


def open_calendar(tab, account):
    prefix = f"{account['origin']}/{account['tenant']}/"
    try:
        tab.wait_for("() => !!document.querySelector('[data-automation-id=dateRangeTitle]') && !!document.querySelector('[data-automation-id=calendarevent], [data-automation-id^=\"hoursEntered_\"]')", timeout=STEP_S)
    except BrowserError:
        if not (tab.url() or "").startswith(prefix):
            refuse("SIGN_IN_REQUIRED", sign_in_remedy(account))
        refuse("LAYOUT_CHANGED", "Enter My Time did not show its week calendar.")
    if not (tab.url() or "").startswith(prefix):
        refuse("SIGN_IN_REQUIRED", sign_in_remedy(account))


def sign_in_remedy(account):
    if account.get("browser") == "own":
        return "Workday has signed this session out. Run session stop, then session start, so the user can sign in again."
    return "Workday asked for sign-in. Sign in to Workday in that Chrome profile yourself, then run again."


# Workday's own Chrome profile


def profile_path():
    return state_base() / "chrome-profile"


@contextlib.contextmanager
def own_profile():
    """The tool's own Chrome profile directory, locked to one user of it at a time. It holds a Workday sign-in, so it stays owner-only and outside Git checkouts."""
    path = profile_path()
    for part in (path, *path.parents):
        if (part / ".git").exists():
            refuse("PRIVATE_STORAGE_REQUIRED", "Keep Workday's Chrome profile outside Git checkouts.")
    private_directory(path.parent)
    private_directory(path)
    fd = os.open(path.with_name("chrome-profile.lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            refuse("PROFILE_IN_USE", "Another Workday command or session is using Workday's own Chrome profile; wait for it or stop the session first.")
        yield path
    finally:
        os.close(fd)


def wait_for_sign_in(chrome, account, minutes):
    """Wait while the user signs in themself in the window just opened, then confirm the account. Until a Workday page has settled it looks only at tab addresses."""
    signed_in = f"{account['origin']}/{account['tenant']}/d/"
    deadline, since, last = time.monotonic() + minutes * 60, None, None
    try:
        while time.monotonic() < deadline:
            urls = sorted(p.get("url") or "" for p in chrome.pages())
            if not urls:
                refuse("SIGN_IN_CANCELLED", "The sign-in window was closed before Workday opened; nothing was changed.")
            current = next((u for u in urls if u.startswith(signed_in)), None)
            if current != last or current is None:
                since, last = time.monotonic(), current
            elif time.monotonic() - since >= SIGN_IN_STEADY_S:
                if confirm_signed_in(chrome, account):
                    return
                last = None
            time.sleep(SIGN_IN_POLL_S)
    except BrowserError:
        refuse("SIGN_IN_CANCELLED", "Chrome closed before Workday opened; nothing was changed.")
    refuse("SIGN_IN_TIMED_OUT", f"Workday did not open within {minutes} minutes; start the session again when the user is ready to sign in.")


def confirm_signed_in(chrome, account):
    """Open Enter My Time in a separate tab and check it shows the confirmed worker. False while Workday still wants a sign-in."""
    tab = chrome.open_tab(account["origin"] + account["enter_time_path"])
    try:
        open_calendar(tab, account)
        workers = stable(tab, CALENDAR_JS)["workers"]
    except Refusal as error:
        if error.code == "SIGN_IN_REQUIRED":
            return False
        raise
    finally:
        with contextlib.suppress(BrowserError):
            tab.close()
    if f"selectedItem_{account['worker']}" not in workers:
        refuse("WORKER_MISMATCH", "Workday is signed in as a different worker; start the session again and sign in to the confirmed account.")
    return True


def go_to_week(tab, week_start):
    current = parse_calendar_range(tab.evaluate(RANGE_JS))
    steps = (week_start - current).days // 7
    if abs(steps) > MAX_WEEK_STEPS:
        refuse("WEEK_OUT_OF_RANGE", "Read weeks within two years of today.")
    button = "nextMonthButton" if steps > 0 else "prevMonthButton"
    for _ in range(abs(steps)):
        before = tab.evaluate(RANGE_JS)
        click(tab, f"[data-automation-id=calendarToolbar] [data-automation-id={button}]", "week arrow")
        tab.wait_for("(b) => { const e = document.querySelector('[data-automation-id=dateRangeTitle]'); return !!e && e.innerText.trim() !== b; }", before, timeout=STEP_S)
    if parse_calendar_range(tab.evaluate(RANGE_JS)) != week_start:
        refuse("WEEK_MISMATCH", "The calendar did not reach the selected week.")


def open_review(tab):
    click(tab, '[data-automation-id=calendarToolbar] button[title="Actions"]', "Actions")
    tab.wait_for("() => !!document.querySelector('[data-automation-id=dropdown-option][data-automation-label=\"Review Time by Week\"]')", timeout=STEP_S)
    click(tab, '[data-automation-id=dropdown-option][data-automation-label="Review Time by Week"]', "Review Time by Week")
    tab.wait_for("() => [...document.querySelectorAll('[data-automation-id=pageHeaderTitleText]')].some(e => e.innerText.trim() === 'Review Time by Week')", timeout=STEP_S)
    tab.wait_for("() => /No items available/.test(document.body.innerText) || [...document.querySelectorAll('th')].some(h => (h.innerText || '').startsWith('Out Reason'))", timeout=STEP_S)


def read_details(tab, index):
    if not tab.evaluate(CLICK_DETAILS_JS, index):
        refuse("LAYOUT_CHANGED", "A review row has no Details control.")
    tab.wait_for(DIALOG_JS, "Time Entry Code", timeout=STEP_S)
    reported = stable(tab, DIALOG_JS, "Time Entry Code")
    if not tab.evaluate(DIALOG_CLICK_JS, "calculated"):
        refuse("LAYOUT_CHANGED", "A block's details have no Calculated tab.")
    tab.wait_for(DIALOG_JS, "Time Calculation Tag", timeout=STEP_S)
    calculated = stable(tab, DIALOG_JS, "Time Calculation Tag")
    if not tab.evaluate(DIALOG_CLICK_JS, "close"):
        refuse("LAYOUT_CHANGED", "A block's details have no close control; the reader stopped without changing anything.")
    try:
        tab.wait_for("() => !(" + DIALOG_OPEN_JS + ")()", timeout=10)
    except BrowserError:
        refuse("LAYOUT_CHANGED", "A block's details did not close; the reader stopped without changing anything.")
    return {"reported": reported, "calculated": calculated}


QA_PRELUDE = FIRE_JS + """
const qa = () => [...document.querySelectorAll('[role=dialog], [data-automation-id=popUpDialog]')].find(d => (d.textContent || '').includes('Quick Add'));
const fieldLabel = (el) => { let n = el; for (let i = 0; i < 8 && n; i++) { const l = n.querySelector && n.querySelector('[data-automation-id=formLabel]'); if (l) return (l.textContent || '').trim(); n = n.parentElement; } return null; };
const lines = (root) => { const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT); const out = []; while (w.nextNode()) { const v = w.currentNode.textContent.trim(); if (v) out.push(v); } return out; };
const timeInput = (label) => { const d = qa(); return d ? [...d.querySelectorAll('input[type=text]')].find(i => fieldLabel(i) === label) : null; };
"""

QA_STATE_JS = "() => { " + QA_PRELUDE + """ const d = qa(); if (!d) return null;
  return {lines: lines(d),
    workers: [...d.querySelectorAll('[data-automation-id^="selectedItem_"]')].map(e => e.getAttribute('data-automation-id')),
    selected: [...d.querySelectorAll('[data-automation-id=selectedItem]')].map(e => (e.textContent || '').trim()),
    times: [...d.querySelectorAll('input[type=text]')].filter(i => ['In', 'Out'].includes(fieldLabel(i))).map(i => [fieldLabel(i), i.value]),
    days: [...d.querySelectorAll('input[type=checkbox]')].map(i => [fieldLabel(i), i.checked]),
    buttons: [...d.querySelectorAll('button')].map(b => b.getAttribute('title') || (b.textContent || '').trim()).filter(Boolean)}; }"""

QA_BUTTON_JS = "(title) => { " + QA_PRELUDE + " const d = qa(); const b = d ? [...d.querySelectorAll('button')].find(x => x.getAttribute('title') === title) : null; return b ? fire(b) : false; }"
QA_FOCUS_JS = "(label) => { " + QA_PRELUDE + " const i = timeInput(label); if (!i) return false; i.focus(); i.select(); return document.activeElement === i; }"
QA_SET_JS = "(args) => { " + QA_PRELUDE + """ const i = timeInput(args[0]); if (!i) return false;
  if (i.value !== args[1]) { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(i, args[1]); i.dispatchEvent(new Event('input', {bubbles: true})); }
  i.dispatchEvent(new Event('change', {bubbles: true})); i.blur(); i.dispatchEvent(new FocusEvent('focusout', {bubbles: true})); return true; }"""
QA_DAY_JS = "(day) => { " + QA_PRELUDE + " const d = qa(); const box = d ? [...d.querySelectorAll('input[type=checkbox]')].find(i => fieldLabel(i) === day) : null; if (!box) return false; if (!box.checked) fire(box); return box.checked; }"
QA_OPEN_JS = "() => { " + QA_PRELUDE + " return !!qa(); }"
QA_STEP2_JS = "() => { " + QA_PRELUDE + " const d = qa(); return !!d && d.querySelectorAll('input[type=checkbox]').length === 7 && !!timeInput('In') && !!timeInput('Out'); }"
QA_DONE_JS = "() => { " + QA_PRELUDE + " return !qa() && !!document.querySelector('[data-automation-id=dateRangeTitle]'); }"
DISCARD_JS = "() => { " + FIRE_JS + " const b = [...document.querySelectorAll('button')].find(x => (x.textContent || '').trim() === 'Discard'); return b ? fire(b) : false; }"


def twelve_hour(value):
    hour, minute = (int(part) for part in value.split(":"))
    return f"{hour % 12 or 12}:{minute:02d} {'AM' if hour < 12 else 'PM'}"


def field_value(lines, label):
    """The value after a form label, skipping the repeated copy of the label."""
    for index, line in enumerate(lines):
        if line == label:
            following = [value for value in lines[index + 1:index + 3] if value != label]
            return following[0] if following else None
    return None


def check_saveable(entry, week_start):
    if entry.get("time_type") not in SAVE_TYPES:
        refuse("UNSUPPORTED_ENTRY", f"Saving supports {', '.join(sorted(SAVE_TYPES))} blocks only.")
    if entry.get("breaks"):
        refuse("UNSUPPORTED_ENTRY", "Saving a block with breaks is not supported; enter it as separate blocks.")
    if entry.get("worktags"):
        refuse("UNSUPPORTED_ENTRY", "Saving worktags is not supported.")
    if any(int(value.split(":")[1]) % 15 for value in (entry["start"], entry["end"])):
        refuse("UNSUPPORTED_ENTRY", "Saving supports quarter-hour times only; Workday rounds other times, so the saved block could not be verified exactly.")
    day = date.fromisoformat(entry["date"])
    if not 0 <= (day - week_start).days <= 6:
        refuse("WEEK_MISMATCH", "An entry falls outside the selected week.")
    return WEEKDAYS[(day - week_start).days]


def check_quick_add_start(state, account, week_start):
    if f"selectedItem_{account['worker']}" not in state["workers"]:
        refuse("WORKER_MISMATCH", "Quick Add is not set to the confirmed worker.")
    dates = (field_value(state["lines"], "Start Date"), field_value(state["lines"], "End Date"))
    if dates != (week_start.strftime("%m/%d/%Y"), (week_start + timedelta(days=6)).strftime("%m/%d/%Y")):
        refuse("WEEK_MISMATCH", "Quick Add is not set to the selected week.")
    if state["selected"] != ["Hours Worked"]:
        refuse("UNSUPPORTED_ENTRY", "Quick Add did not start with Hours Worked as the only time type.")


def check_quick_add_ready(state, entry, day):
    if "Hours Worked" not in (field_value(state["lines"], "Time Type") or ""):
        refuse("UNSUPPORTED_ENTRY", "Quick Add's time type changed before saving.")
    if field_value(state["lines"], "Out Reason") != "Out":
        refuse("UNSUPPORTED_ENTRY", "Quick Add's out reason is not Out.")
    times = dict(state["times"])
    try:
        shown = (clock(times.get("In")), clock(times.get("Out")))
    except Refusal:
        refuse("LAYOUT_CHANGED", "Workday did not accept the in and out times as entered.")
    if shown != (entry["start"], entry["end"]):
        refuse("LAYOUT_CHANGED", "Workday shows different in and out times from the plan.")
    ticked = [name for name, checked in state["days"] if checked]
    if [name for name, _ in state["days"]] != WEEKDAYS or ticked != [day]:
        refuse("LAYOUT_CHANGED", "Quick Add does not have exactly the planned day ticked.")


SUBMIT_PANEL_JS = """() => {
  const has = (e) => { const t = e.textContent || ''; return t.includes('certify time for approval') && t.includes('Timesheet Total') && [...e.querySelectorAll('button')].some(b => (b.textContent || '').trim() === 'Submit'); };
  const boxes = [...document.querySelectorAll('body *')].filter(has);
  if (!boxes.length) return null;
  const box = boxes.reduce((a, b) => (a.querySelectorAll('*').length <= b.querySelectorAll('*').length ? a : b));
  const walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
  const lines = [];
  while (walker.nextNode()) { const v = walker.currentNode.textContent.trim(); if (v) lines.push(v); }
  return {lines, comments: [...box.querySelectorAll('textarea, input[type=text]')].map(x => x.value), buttons: [...box.querySelectorAll('button')].map(b => (b.textContent || '').trim()).filter(Boolean)};
}"""

SUBMIT_CLICK_JS = "(label) => { " + FIRE_JS + """ const has = (e) => { const t = e.textContent || ''; return t.includes('certify time for approval') && t.includes('Timesheet Total') && [...e.querySelectorAll('button')].some(b => (b.textContent || '').trim() === 'Submit'); };
  const boxes = [...document.querySelectorAll('body *')].filter(has);
  if (!boxes.length) return false;
  const box = boxes.reduce((a, b) => (a.querySelectorAll('*').length <= b.querySelectorAll('*').length ? a : b));
  const button = [...box.querySelectorAll('button')].find(b => (b.textContent || '').trim() === label);
  return button ? fire(button) : false; }"""

REVIEW_BUTTON_JS = "() => { " + FIRE_JS + " const b = [...document.querySelectorAll('button')].filter(x => (x.textContent || '').trim() === 'Review'); return b.length === 1 ? fire(b[0]) : false; }"
SUBMIT_OPEN_JS = "() => !!(" + SUBMIT_PANEL_JS + ")()"


def parse_long_range(text):
    match = re.fullmatch(r"([A-Z][a-z]+) (\d{1,2})(?:, (\d{4}))? – (?:([A-Z][a-z]+) )?(\d{1,2}), (\d{4})", text)
    if not match:
        refuse("LAYOUT_CHANGED", f"Unrecognized submission range {text!r}.")
    m1, d1, y1, m2, d2, y2 = match.groups()
    try:
        first = datetime.strptime(m1, "%B").month
        last = datetime.strptime(m2 or m1, "%B").month
    except ValueError:
        refuse("LAYOUT_CHANGED", f"Unrecognized submission range {text!r}.")
    year_end = int(y2)
    year_start = int(y1) if y1 else (year_end - 1 if first > last else year_end)
    return date(year_start, first, int(d1)), date(year_end, last, int(d2))


def parse_submit_panel(panel):
    """The range, hours, total and certification Workday's Submit Time panel shows, from its text in document order."""
    if not panel:
        refuse("LAYOUT_CHANGED", "The Submit Time panel did not open.")
    text = re.sub(r"\s+", " ", " ".join(panel["lines"]))
    certification = re.search(r"(I certify .*?) Following date range will be submitted for approval\.", text)
    ranged = re.search(r"([A-Z][a-z]+ \d{1,2}(?:, \d{4})? – (?:[A-Z][a-z]+ )?\d{1,2}, \d{4}) : ([\d.]+) Hours", text)
    total = re.search(r"Timesheet Total ([\d.]+)", text)
    if not certification or not ranged or not total:
        refuse("LAYOUT_CHANGED", "The Submit Time panel does not show its certification, range and total as expected.")
    start, end = parse_long_range(ranged.group(1))
    return {"certification": certification.group(1), "range": [start.isoformat(), end.isoformat()], "range_minutes": hours(ranged.group(2)), "timesheet_total_minutes": hours(total.group(1)), "comments": panel.get("comments", [])}


def submit_plan(target, snapshot, result, observations, panel):
    week = date.fromisoformat(target["week_start"])
    entries = snapshot["entries"]
    if not entries or snapshot["status"] != "draft" or any(r["status"] != "draft" for r in entries):
        refuse("NOT_SUBMITTABLE", "Only a week whose blocks are all unsubmitted drafts can be submitted.")
    if not observations.get("timesheet_shown") or observations.get("rounded_blocks"):
        refuse("NOT_SUBMITTABLE", "This week has no timesheet or rounded blocks the tool cannot verify; submit it in Workday yourself if it is right.")
    if panel["range"] != [week.isoformat(), (week + timedelta(days=6)).isoformat()]:
        refuse("PANEL_MISMATCH", "The Submit Time panel names a different week.")
    if panel["range_minutes"] != snapshot["service_total_minutes"] or panel["timesheet_total_minutes"] != snapshot["service_total_minutes"]:
        refuse("PANEL_MISMATCH", "The Submit Time panel's hours differ from the week's blocks.")
    if any(c.strip() for c in panel["comments"]):
        refuse("PANEL_MISMATCH", "The Submit Time panel already has a comment; clear it in Workday first.")
    plan = {"schema_version": 1, "operation": "submit-week", "target": target, "snapshot_fingerprint": result["fingerprint"],
            "entries": entries, "total_minutes": snapshot["service_total_minutes"], "range": panel["range"],
            "certification": panel["certification"], "submittable_from": (week + timedelta(days=6)).isoformat()}
    plan["plan_fingerprint"] = fingerprint(plan)
    return plan


def check_submit_plan(plan, approved):
    if not isinstance(plan, dict) or plan.get("operation") != "submit-week":
        refuse("INVALID_INPUT", "Pass the plan from submit-preview.")
    body = {k: v for k, v in plan.items() if k != "plan_fingerprint"}
    if fingerprint(body) != plan.get("plan_fingerprint"):
        refuse("PLAN_CHANGED", "The submission plan was edited; run submit-preview again.")
    if approved != plan["plan_fingerprint"]:
        refuse("APPROVAL_MISMATCH", "Approve the exact plan_fingerprint shown by submit-preview.")


def week_over(account, plan, today=None):
    today = today or datetime.now(ZoneInfo(account["timezone"])).date()
    return today >= date.fromisoformat(plan["submittable_from"])


class Session:
    """One connection and one background tab, of the user's running Chrome or of Workday's own Chrome as the account chooses, for reads and, when the account allows it, saves.

    As a use-workday transport it declares the re-read safeguard: no atomic revision guard exists in Workday's pages, so each save is preceded by a fresh full read and a last calendar check, relies on Workday refusing overlapping times, and is followed by a full read.
    """

    save_safeguard = "reread"
    supports_conditional_create = False

    def __init__(self, account, sign_in_minutes=SIGN_IN_MINUTES, announce=lambda value: None):
        self.account, self.tab, self.profile = account, None, contextlib.ExitStack()
        own = account.get("browser") == "own"
        try:
            if own:
                self.chrome = Chrome.launch(self.profile.enter_context(own_profile()), account["origin"] + account["enter_time_path"])
            else:
                self.chrome = Chrome.connect(CONNECT_S)
        except BrowserError as error:
            self.profile.close()
            if own:
                refuse("BROWSER_NOT_STARTED", f"{error}.")
            refuse("BROWSER_NOT_CONNECTED", f"{error}. Keep Chrome open with remote debugging on at chrome://inspect/#remote-debugging, run again and click Allow when Chrome asks.")
        try:
            context = None
            if own:
                announce({"status": "waiting-for-sign-in", "minutes": sign_in_minutes, "next_action": "Sign in to Workday in the Chrome window that opened."})
                wait_for_sign_in(self.chrome, account, sign_in_minutes)
                self.chrome.minimize()
            else:
                context = select_context(self.chrome.pages(), account)
            self.tab = self.chrome.open_tab("about:blank", context)
        except BrowserError as error:
            self.close()
            refuse("BROWSER_STEP_FAILED", f"Opening a tab failed ({error}); nothing was changed in Workday.")
        except Refusal:
            self.close()
            raise
        self.observations = None

    def close(self):
        if self.tab is not None:
            try:
                self.tab.close()
            except BrowserError:
                pass
            self.tab = None
        self.chrome.close()
        self.profile.close()

    def show_week(self, week):
        """Load Enter My Time afresh and move to the week, so the page reflects Workday's current data."""
        self.tab.evaluate("() => { window.__agentHandsStale = true; return true; }")
        self.tab.navigate(self.account["origin"] + self.account["enter_time_path"])
        try:
            self.tab.wait_for("() => !window.__agentHandsStale", timeout=STEP_S)
        except BrowserError:
            refuse("BROWSER_STEP_FAILED", "Enter My Time did not load.")
        open_calendar(self.tab, self.account)
        go_to_week(self.tab, week)

    def read(self, binding):
        target = check_target(binding)
        stage = "calendar"
        try:
            self.show_week(date.fromisoformat(target["week_start"]))
            calendar = stable(self.tab, CALENDAR_JS)
            stage = "review"
            open_review(self.tab)
            review = stable(self.tab, REVIEW_JS)
            if review["rows"] and review["empty"]:
                refuse("LAYOUT_CHANGED", "Review Time by Week shows rows and 'No items available' at once.")
            stage = "details"
            details = [read_details(self.tab, i) for i in range(len(review["rows"]))]
        except BrowserError as error:
            refuse("BROWSER_STEP_FAILED", f"The {stage} step failed ({error}); nothing was changed in Workday. Run again once the page is idle.")
        snapshot, result, self.observations = build_snapshot(self.account, target, calendar, review, details)
        self.result = result
        return snapshot

    def overview(self, weeks):
        """Each week's calendar, read twice a pause apart so a week still loading is never reported; stops at the first that will not settle."""
        found = []
        try:
            self.show_week(weeks[0])
            for week in weeks:
                go_to_week(self.tab, week)
                calendar = stable(self.tab, CALENDAR_JS)
                for _ in range(5):
                    time.sleep(OVERVIEW_PAUSE_S)
                    again = stable(self.tab, CALENDAR_JS)
                    if again == calendar:
                        break
                    calendar = again
                else:
                    refuse("PAGE_UNSETTLED", "Workday kept changing while being read; try again when it has finished loading.")
                found.append(summarize_week(self.account, week, calendar))
        except BrowserError as error:
            refuse("BROWSER_STEP_FAILED", f"The overview stopped ({error}); nothing was changed in Workday. Run again once the page is idle.")
        return found

    def cancel_quick_add(self):
        """Close an unsent Quick Add, confirming Workday's Discard Changes prompt; the tab is closed afterwards in any case."""
        try:
            if self.tab.evaluate(QA_OPEN_JS):
                self.tab.evaluate(QA_BUTTON_JS, "Cancel")
                time.sleep(1)
                self.tab.evaluate(DISCARD_JS)
                self.tab.wait_for("() => !(" + QA_OPEN_JS + ")()", timeout=10)
        except BrowserError:
            pass

    def open_submit_panel(self, week):
        self.show_week(week)
        if not self.tab.evaluate(REVIEW_BUTTON_JS):
            refuse("LAYOUT_CHANGED", "Enter Time shows no single Review button for this week.")
        self.tab.wait_for(SUBMIT_OPEN_JS, timeout=STEP_S)
        return parse_submit_panel(stable(self.tab, SUBMIT_PANEL_JS))

    def close_submit_panel(self):
        """Cancel the panel without submitting, confirming Workday's Discard Changes prompt if it asks."""
        try:
            if self.tab.evaluate(SUBMIT_OPEN_JS):
                self.tab.evaluate(SUBMIT_CLICK_JS, "Cancel")
                time.sleep(1)
                self.tab.evaluate(DISCARD_JS)
                self.tab.wait_for("() => !(" + SUBMIT_OPEN_JS + ")()", timeout=10)
        except BrowserError:
            pass

    def preview_submission(self, binding):
        snapshot = self.read(binding)
        result, observations = self.result, self.observations
        week = date.fromisoformat(binding["week_start"])
        try:
            panel = self.open_submit_panel(week)
        except BrowserError as error:
            self.close_submit_panel()
            refuse("BROWSER_STEP_FAILED", f"Opening Submit Time failed ({error}); nothing was submitted.")
        except Refusal:
            self.close_submit_panel()
            raise
        self.close_submit_panel()
        return submit_plan(snapshot["target"], snapshot, result, observations, panel)

    def submit_week(self, plan):
        """Submit after a fresh read and panel match the approved plan; only the Submit click and after are uncertain."""
        target = plan["target"]
        week = date.fromisoformat(target["week_start"])
        snapshot = self.read(target)
        if self.result["fingerprint"] != plan["snapshot_fingerprint"]:
            refuse("STALE_PLAN", "The week changed since the preview; run submit-preview again.")
        try:
            panel = self.open_submit_panel(week)
            if submit_plan(snapshot["target"], snapshot, self.result, self.observations, panel) != plan:
                self.close_submit_panel()
                refuse("PANEL_CHANGED", "The Submit Time panel or its certification differs from the approved preview; nothing was submitted.")
        except BrowserError as error:
            self.close_submit_panel()
            refuse("BROWSER_STEP_FAILED", f"Opening Submit Time failed ({error}); nothing was submitted.")
        return True

    def press_submit(self):
        if not self.tab.evaluate(SUBMIT_CLICK_JS, "Submit"):
            raise BrowserError("The Submit button is missing")
        self.tab.wait_for("() => !(" + SUBMIT_OPEN_JS + ")()", timeout=STEP_S)

    def create_draft(self, binding, entry, expected_revision):
        week = date.fromisoformat(binding["week_start"])
        sent = False
        try:
            day = check_saveable(entry, week)
            self.show_week(week)
            if calendar_revision(stable(self.tab, CALENDAR_JS)) != expected_revision:
                raise NotDispatched()
            click(self.tab, '[data-automation-id=calendarToolbar] button[title="Actions"]', "Actions")
            self.tab.wait_for("() => !!document.querySelector('[data-automation-id=dropdown-option][data-automation-label=\"Quick Add\"]')", timeout=STEP_S)
            click(self.tab, '[data-automation-id=dropdown-option][data-automation-label="Quick Add"]', "Quick Add")
            self.tab.wait_for("() => { " + QA_PRELUDE + " const d = qa(); return !!d && [...d.querySelectorAll('button')].some(b => b.getAttribute('title') === 'Next'); }", timeout=STEP_S)
            check_quick_add_start(stable(self.tab, QA_STATE_JS), self.account, week)
            if not self.tab.evaluate(QA_BUTTON_JS, "Next"):
                refuse("LAYOUT_CHANGED", "Quick Add has no Next button.")
            self.tab.wait_for(QA_STEP2_JS, timeout=STEP_S)
            for label, value in (("In", entry["start"]), ("Out", entry["end"])):
                text = twelve_hour(value)
                if self.tab.evaluate(QA_FOCUS_JS, label):
                    self.tab.insert_text(text)
                self.tab.evaluate(QA_SET_JS, [label, text])
            if not self.tab.evaluate(QA_DAY_JS, day):
                refuse("LAYOUT_CHANGED", f"Quick Add's {day} box could not be ticked.")
            check_quick_add_ready(stable(self.tab, QA_STATE_JS), entry, day)
            # From here the request may reach Workday, so any failure is uncertain rather than a clean stop.
            sent = True
            if not self.tab.evaluate(QA_BUTTON_JS, "OK"):
                raise BrowserError("Quick Add has no OK button")
            self.tab.wait_for(QA_DONE_JS, timeout=STEP_S)
        except NotDispatched:
            self.cancel_quick_add()
            raise
        except (Refusal, BrowserError):
            if not sent:
                self.cancel_quick_add()
                raise NotDispatched()
            raise RuntimeError("The save's outcome is unknown")


def read_week(account, target, session=None):
    own = session is None
    session = session or Session(account)
    try:
        snapshot = session.read(target)
        return snapshot, session.result, session.observations
    finally:
        if own:
            session.close()


def journal_dir():
    return state_base() / "journal"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(account, plan, approved, session=None):
    if account.get("save_safeguard") not in SAVE_SAFEGUARDS:
        refuse("SAVES_NOT_ENABLED", "Saving needs the user's explicit choice of the re-read safeguard in the account file ('save_safeguard': 'reread').")
    verify_plan(plan)
    target = check_target(plan["target"])
    check_binding(account, target)
    week = date.fromisoformat(target["week_start"])
    for entry in plan["additions"]:
        check_saveable(entry, week)
    journal = Journal(journal_dir())
    own = session is None
    session = session or Session(account)
    try:
        return save_draft(session, plan, approved, journal, allow_reread=True)
    finally:
        if own:
            session.close()


def submit(account, plan, approved, session=None):
    check_submit_plan(plan, approved)
    target = check_target(plan["target"])
    check_binding(account, target)
    if not week_over(account, plan):
        refuse("WEEK_NOT_OVER", f"This week can be submitted from {plan['submittable_from']}, once its hours have been worked.")
    journal = Journal(journal_dir())
    own = session is None
    session = session or Session(account)
    try:
        with journal.guard(target):
            if journal.pending():
                refuse("RECONCILE_REQUIRED", "Reconcile the outstanding operation for this week first.")
            session.submit_week(plan)
            journal.intent({"kind": "submit", "target": target, "plan_fingerprint": plan["plan_fingerprint"], "entries": plan["entries"], "recorded_at": datetime.now(timezone.utc).isoformat()})
            try:
                session.press_submit()
                after = session.read(target)
            except (Refusal, BrowserError):
                return {"status": "uncertain", "target": target, "next_action": "Run reconcile for this week; do not submit again until it settles."}
            ids = {r["id"] for r in plan["entries"]}
            got = {r["id"]: r for r in after["entries"]}
            if set(got) != ids or any(got[r["id"]]["entry"] != r["entry"] or got[r["id"]]["status"] != "submitted" for r in plan["entries"]):
                return {"status": "uncertain", "target": target, "next_action": "The week did not read back as submitted exactly; run reconcile and inspect it in Workday."}
            journal.clear()
            return {"status": "submitted", "target": target, "range": plan["range"], "total_minutes": plan["total_minutes"], "entries": len(plan["entries"])}
    finally:
        if own:
            session.close()


def settle_submission(intent, snapshot, now):
    planned = {r["id"]: r["entry"] for r in intent["entries"]}
    got = {r["id"]: r for r in snapshot["entries"] if r["id"] in planned}
    if set(got) == set(planned) and all(got[i]["entry"] == planned[i] for i in planned):
        statuses = {got[i]["status"] for i in planned}
        if statuses <= {"submitted", "sent_for_approval", "approved"}:
            return "landed"
        if statuses == {"draft"}:
            return "not-applied" if now - datetime.fromisoformat(intent["recorded_at"]) >= SETTLE else "wait"
    return "present-not-draft"


def settle_outcome(intent, snapshot, now):
    """What a fresh read says about an uncertain save: landed, not applied after the settling time, or still unresolved."""
    drafts = [r["entry"] for r in snapshot["entries"] if r["status"] == "draft"]
    if intent["entry"] in drafts:
        return "landed"
    if intent["entry"] in [r["entry"] for r in snapshot["entries"]]:
        return "present-not-draft"
    recorded = datetime.fromisoformat(intent["recorded_at"])
    return "not-applied" if now - recorded >= SETTLE else "wait"


def reconcile(account, target, session=None):
    journal = Journal(journal_dir())
    with journal.guard(target):
        if not journal.pending():
            return {"status": "nothing-pending", "target": target}
        intent = journal.read_intent()
        own = session is None
        session = session or Session(account)
        try:
            snapshot = session.read(target)
        finally:
            if own:
                session.close()
        outcome = (settle_submission if intent.get("kind") == "submit" else settle_outcome)(intent, snapshot, datetime.now(timezone.utc))
        if outcome in ("landed", "not-applied"):
            journal.clear()
        result = {"status": outcome, "target": target} | ({"entries": len(intent["entries"])} if intent.get("kind") == "submit" else {"entry": intent["entry"]})
        if outcome == "wait":
            result["retry_after"] = (datetime.fromisoformat(intent["recorded_at"]) + SETTLE).isoformat()
        if outcome == "present-not-draft":
            result["next_action"] = "The week matches neither the planned outcome nor its starting state; inspect it in Workday before deciding."
        return result


# Signing in again costs the user more than another Allow click, so a session in the own profile waits longer.
SESSION_IDLE_MINUTES = {"everyday": 20, "own": 60}
SESSION_REPLY_SECONDS = 1800
MAX_MESSAGE = 4_000_000


def perform(account, request, session=None):
    """Run one bounded command and return its output and exit status. A given session is reused and left open."""
    command = request.get("command")
    if command == "save":
        result = save(account, request["plan"], request["approved_fingerprint"], session)
        return result, {"saved-draft": 0, "unchanged": 0, "stopped": 2}.get(result.get("status"), 3)
    if command == "submit":
        result = submit(account, request["plan"], request["approved_fingerprint"], session)
        return result, 0 if result["status"] == "submitted" else 3
    if command == "overview":
        weeks = overview_weeks(request["from"], request["to"])
        own = session is None
        session = session or Session(account)
        try:
            return {"status": "ok", "source": "workday-calendar-only", "weeks": session.overview(weeks)}, 0
        finally:
            if own:
                session.close()
    if command not in ("read", "reconcile", "submit-preview"):
        refuse("INVALID_INPUT", "Unknown command.")
    target = check_target(request["target"])
    check_binding(account, target)
    if command == "reconcile":
        result = reconcile(account, target, session)
        return result, 0 if result["status"] in ("nothing-pending", "landed", "not-applied") else 2
    if command == "submit-preview":
        own = session is None
        session = session or Session(account)
        try:
            plan = session.preview_submission(target)
        finally:
            if own:
                session.close()
        return {"plan": plan, "ready_to_submit": week_over(account, plan)}, 0
    snapshot, result, observations = read_week(account, target, session)
    return {"status": "ok", "source": "workday-browser", "read": result, "observations": observations, "snapshot": snapshot}, 0


def session_path():
    return state_base() / "session.sock"


def private_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        refuse("PRIVATE_STORAGE_REQUIRED", f"{path} must be an owner-only directory (mode 0700).")


def read_message(conn):
    data = b""
    while not data.endswith(b"\n"):
        chunk = conn.recv(65536)
        if not chunk:
            break
        data += chunk
        if len(data) > MAX_MESSAGE:
            raise ValueError("message too large")
    return json.loads(data.decode("utf-8"))


def send_message(conn, value):
    conn.sendall((json.dumps(value) + "\n").encode("utf-8"))


def through_session(request):
    """Send a command to a running session; None when no session is running, so the caller connects itself."""
    path = session_path()
    if not path.exists():
        return None
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(SESSION_REPLY_SECONDS)
    try:
        conn.connect(str(path))
    except OSError:
        conn.close()
        return None
    with conn:
        send_message(conn, request)
        return read_message(conn)


def alive(session):
    try:
        session.chrome.call("Browser.getVersion", timeout=5)
        tab = getattr(session, "tab", None)
        return tab is None or any(p["targetId"] == tab.target for p in session.chrome.pages())
    except BrowserError:
        return False


def handle(account, account_file, session, request):
    if not isinstance(request, dict) or request.get("account") != account_file:
        return {"ok": False, "code": "SESSION_ACCOUNT_MISMATCH", "remedy": "This session serves a different account file; stop it or use the same --account.", "exit": 2}
    command = request.get("command")
    if command == "status":
        return {"ok": True, "result": {"status": "running"}, "exit": 0}
    if command == "stop":
        return {"ok": True, "result": {"status": "stopped"}, "exit": 0, "stop": True}
    try:
        result, code = perform(account, request, session)
        return {"ok": True, "result": result, "exit": code}
    except Refusal as error:
        return {"ok": False, "code": error.code, "remedy": error.remedy, "exit": 2}
    except (KeyError, TypeError, ValueError, OSError):
        return {"ok": False, "code": "INVALID_INPUT", "remedy": "The request did not match the command's inputs.", "exit": 2}


def announce_json(value):
    print(json.dumps(value), flush=True)


def serve(account, account_file, idle_minutes, make_session=None, announce=announce_json):
    """Hold one Chrome connection and answer the bounded commands over an owner-only Unix socket until idle, stopped or disconnected."""
    path = session_path()
    private_directory(path.parent)
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            refuse("PRIVATE_STORAGE_REQUIRED", f"{path} exists and is not this user's session socket.")
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            probe.connect(str(path))
            refuse("SESSION_RUNNING", "A Workday session is already running; use it or stop it first.")
        except OSError:
            path.unlink()
        finally:
            probe.close()
    session = (make_session or Session)(account)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    reason = "idle"
    try:
        previous = os.umask(0o177)
        try:
            server.bind(str(path))
        finally:
            os.umask(previous)
        os.chmod(path, 0o600)
        # A command that finds the queue full would be refused and connect to Chrome by itself.
        server.listen(16)
        server.settimeout(1.0)
        announce({"status": "ready", "idle_minutes": idle_minutes})
        last = time.monotonic()
        while time.monotonic() - last < idle_minutes * 60:
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            with conn:
                conn.settimeout(60)
                try:
                    request = read_message(conn)
                except (OSError, ValueError):
                    continue
                reply = handle(account, account_file, session, request)
                try:
                    send_message(conn, reply)
                except OSError:
                    pass
            last = time.monotonic()
            if reply.get("stop"):
                reason = "stopped"
                break
            if not alive(session):
                reason = "chrome-disconnected"
                break
    finally:
        server.close()
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        session.close()
        announce({"status": "ended", "reason": reason})
    return 0


def week_choice(parser):
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--week", help="Monday of the week, YYYY-MM-DD, for the confirmed account")
    choice.add_argument("--target", help="use-workday target JSON")


def chosen_target(account, args):
    if args.target:
        return load_json(args.target)
    return {"tenant": account["tenant"], "worker": account["worker"], "week_start": args.week, "timezone": account["timezone"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Validate the account file and runtime without contacting Chrome or Workday")
    check.add_argument("--account")
    read = sub.add_parser("read", help="Read one complete week from the signed-in Chrome")
    week_choice(read)
    read.add_argument("--account")
    read.add_argument("--out", help="Write the snapshot here, owner-only and outside Git checkouts")
    write = sub.add_parser("save", help="Save a reviewed use-workday plan's additions as unsubmitted blocks")
    write.add_argument("--plan", required=True, help="The plan object from use-workday preview")
    write.add_argument("--approved-fingerprint", required=True, help="The plan_fingerprint the user approved")
    write.add_argument("--account")
    settle = sub.add_parser("reconcile", help="Settle an uncertain save from a fresh read")
    week_choice(settle)
    settle.add_argument("--account")
    look = sub.add_parser("submit-preview", help="Read a week and its Submit Time panel, then cancel without submitting")
    week_choice(look)
    several = sub.add_parser("overview", help="List several weeks' hours and statuses from the calendar, read-only")
    several.add_argument("--from", dest="first", required=True, help="A date in the first week, YYYY-MM-DD")
    several.add_argument("--to", dest="last", help="A date in the last week; today when omitted")
    several.add_argument("--account")
    look.add_argument("--out", help="Write the submission plan here, owner-only and outside Git checkouts")
    look.add_argument("--account")
    send = sub.add_parser("submit", help="Submit a week exactly as an approved submit-preview showed it")
    send.add_argument("--plan", required=True)
    send.add_argument("--approved-fingerprint", required=True)
    send.add_argument("--account")
    hold = sub.add_parser("session", help="Hold one Chrome connection for several commands")
    hold.add_argument("action", choices=["start", "status", "stop"])
    hold.add_argument("--idle-minutes", type=int, help="End after this long without a command; 20 with the everyday Chrome and 60 with the own profile when omitted")
    hold.add_argument("--sign-in-minutes", type=int, default=SIGN_IN_MINUTES, help="With the own profile, how long to wait for the user to sign in")
    hold.add_argument("--account")
    args = parser.parse_args(argv)
    try:
        account = load_account(account_path(args.account))
        if args.command == "check" and account.get("browser") == "own":
            print(json.dumps({"status": "ok", "account": "valid", "browser": "own", "profile_exists": profile_path().is_dir()}, indent=2))
            return 0
        if args.command == "check":
            try:
                devtools_port()
                debugging = "on"
            except BrowserError:
                debugging = "off; turn it on at chrome://inspect/#remote-debugging"
            print(json.dumps({"status": "ok", "account": "valid", "browser": "everyday", "chrome_remote_debugging": debugging}, indent=2))
            return 0
        account_file = str(account_path(args.account).resolve())
        if args.command == "session":
            if args.action == "start":
                idle = SESSION_IDLE_MINUTES[account.get("browser", "everyday")] if args.idle_minutes is None else args.idle_minutes
                if not 1 <= idle <= 240 or not 1 <= args.sign_in_minutes <= 60:
                    refuse("INVALID_INPUT", "--idle-minutes must be between 1 and 240, and --sign-in-minutes between 1 and 60.")
                return serve(account, account_file, idle, make_session=lambda a: Session(a, args.sign_in_minutes, announce_json))
            reply = through_session({"command": args.action, "account": account_file})
            print(json.dumps(reply["result"] if reply and reply.get("ok") else {"status": "not-running"} if reply is None else reply, indent=2))
            return 0 if reply is None or reply.get("ok") else 2
        if args.command in ("save", "submit"):
            request = {"command": args.command, "plan": load_json(args.plan), "approved_fingerprint": args.approved_fingerprint}
        elif args.command == "overview":
            request = {"command": "overview", "from": args.first, "to": args.last or datetime.now(ZoneInfo(account["timezone"])).date().isoformat()}
        else:
            request = {"command": args.command, "target": chosen_target(account, args)}
        reply = through_session(dict(request, account=account_file))
        if reply is None and account.get("browser") == "own":
            refuse("SESSION_REQUIRED", "Workday's own Chrome profile stays signed in only while its Chrome is open. Run session start in the background, have the user sign in there, and run this again once it reports ready.")
        elif reply is None:
            result, code = perform(account, request)
        elif not reply.get("ok"):
            refuse(reply.get("code", "SESSION_FAILED"), reply.get("remedy", "The running session could not complete the command."))
        else:
            result, code = reply["result"], reply["exit"]
        if args.command == "read":
            snapshot = result.pop("snapshot")
            if args.out:
                write_private(args.out, snapshot)
        if args.command == "submit-preview" and args.out:
            write_private(args.out, result["plan"])
        print(json.dumps(result, sort_keys=True, indent=2))
        return code
    except Refusal as error:
        print(json.dumps({"status": "blocked", "code": error.code, "remedy": error.remedy}), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"status": "blocked", "code": "INVALID_INPUT", "remedy": "Supply a readable target file matching the v1 contract. Nothing was read from Workday."}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
