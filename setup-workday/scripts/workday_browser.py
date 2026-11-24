#!/usr/bin/env python3
"""Read one complete Workday week from the user's signed-in Chrome into use-workday's v1 snapshot.

The command connects to the user's running Chrome through Chrome's own consent flow: the user turns on remote debugging at chrome://inspect/#remote-debugging and clicks Allow when Chrome asks. It finds the Chrome profile that has the configured Workday tenant open and reads in a background tab that it opens and closes itself; it never attaches to, navigates or closes the user's own tabs. It needs only the Python standard library. It reads the Enter Time week calendar, Review Time by Week and each block's read-only details, cross-checks them, and refuses anything it cannot verify. It only moves between weeks and opens read-only views; it never uses entry, check-in or check-out, calculation or submission controls, and it writes nothing to Workday.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import sys
import time
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "use-workday" / "scripts"))
from workday_core import Refusal, read_timesheet, target as check_target  # noqa: E402
sys.path.insert(0, str(HERE))
from chrome_session import BrowserError, Chrome, devtools_port  # noqa: E402

STATE_ENV = "AGENT_HANDS_STATE_DIR"
# Only styles seen on a real tenant map to a status. Anything else reads as unknown, which use-workday treats as protected.
STYLE_STATUS = {"approved": "approved"}
MONTHS = {name: number for number, name in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
REVIEW_HEADERS = ["Date", "Status", "Type", "In", "Out", "Out Reason", "Quantity", "Units", "Worktags", "Comment", "Details"]
REPORTED_LABELS = ["Reported Quantity", "Time Entry Code", "In", "Out", "Out Reason", "Source", "Time Block Comment"]
CALCULATED_LABELS = ["Calculated Date", "Calculated Time In", "Calculated Time Out", "Calculated Quantity", "Time Calculation Tag"]
ACCOUNT_REQUIRED = {"schema_version", "origin", "tenant", "worker", "timezone", "timezone_label", "enter_time_path"}
ACCOUNT_OPTIONAL = {"time_types"}
CONNECT_S = 120
STEP_S = 30
MAX_WEEK_STEPS = 104


def refuse(code, remedy):
    raise Refusal(code, remedy)


# Account configuration


def account_path(explicit=None):
    if explicit:
        return Path(explicit)
    base = Path(os.environ.get(STATE_ENV) or str(Path.home() / ".agent-hands"))
    if not base.is_absolute():
        refuse("PRIVATE_STORAGE_REQUIRED", f"Set {STATE_ENV} to an absolute private directory.")
    return base / "workday" / "config" / "account.json"


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
        refuse("INVALID_ACCOUNT", "The account file needs exactly schema_version 1, origin, tenant, worker, timezone, timezone_label, enter_time_path and optionally time_types.")
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
            blocks.append({"id": event["id"], "style": event.get("style") or "", "title": event.get("title") or "", "date": on, "start": f"{start[2]:02d}:{start[3]:02d}", "end": f"{end[2]:02d}:{end[3]:02d}"})
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
    entries, observed_types, classifications, payment, comments = [], set(), {}, {}, []
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
        if row["Units"] != "Hours" or hours(row["Quantity"]) != minutes or hours(calculated["Calculated Quantity"]) != minutes:
            refuse("TOTAL_MISMATCH", "A block's hours disagree with its in and out times.")
        for field, expected in (("In", block["start"]), ("Out", block["end"]), ("Calculated Time In", block["start"]), ("Calculated Time Out", block["end"])):
            if detail_time(reported.get(field) or calculated.get(field), account["timezone_label"]) != (block["date"], expected):
                refuse("VIEWS_DISAGREE", "A block's details show different times from the calendar.")
        status = STYLE_STATUS.get(block["style"], "unknown")
        entries.append({"id": block["id"], "status": status, "entry": {"date": block["date"].isoformat(), "start": block["start"], "end": block["end"], "breaks": [], "time_type": row["Type"], "worktags": {}}})
        observed_types.add(row["Type"])
        tag = calculated["Time Calculation Tag"]
        classifications[tag] = classifications.get(tag, 0) + minutes
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
        if hours(text, "Hours:") != daily.get((week + timedelta(days=index)).isoformat(), 0):
            refuse("TOTAL_MISMATCH", "A day's hours on the calendar disagree with its blocks.")
    total = sum(daily.values())
    if summary_minutes(calendar.get("summary") or [], "Timesheet Total") != total:
        refuse("TOTAL_MISMATCH", "The timesheet total disagrees with the blocks, possibly because of time off or entries this reader cannot see.")
    types = sorted(observed_types | set(account.get("time_types", [])))
    if not types:
        refuse("UNKNOWN_TIME_TYPES", "No time type is visible this week; add the user-confirmed time-entry codes to the account file's time_types.")
    statuses = {r["status"] for r in entries}
    week_status = "empty" if not entries else statuses.pop() if len(statuses) == 1 else "unknown"
    raw = {"calendar": calendar, "review": review, "details": details}
    snapshot = {
        "schema_version": 1, "target": target, "revision": "content-sha256:" + fingerprint(raw), "status": week_status,
        "entries": entries, "allowed_time_types": types, "pay_periods": pay_periods(week, markers),
        "service_total_minutes": total, "draft_save_supported": False, "certification": "",
    }
    result = read_timesheet(snapshot, target)
    observations = {
        "styles": sorted({b["style"] for b in blocks}), "payment_statuses": payment, "classification_minutes": classifications,
        "summary": {item.get("label"): item.get("value") for item in calendar.get("summary") or []}, "holidays": holidays,
        "pay_period_markers": [[s.isoformat(), e.isoformat()] for s, e in markers], "comments": comments,
        "time_types": {"observed": sorted(observed_types), "from_account": sorted(account.get("time_types", []))},
        "revision_note": "Content fingerprint of this read; Workday offers no service revision through the browser.",
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
    events: q('[data-automation-id=calendarevent]').map(e => ({text: t(e), title: t(e.querySelector('[data-automation-id=calendarAppointmentTitle]')), subtitle: t(e.querySelector('[data-automation-id=calendarAppointmentSubtitle]')), style: e.getAttribute('data-automation-appointment-style'), id: e.getAttribute('data-automation-eventid'), allday: e.getAttribute('data-automation-allday'), start: e.getAttribute('data-automation-startdate'), end: e.getAttribute('data-automation-enddate')}))
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
            refuse("SIGN_IN_REQUIRED", "Workday asked for sign-in. Sign in to Workday in that Chrome profile yourself, then run again.")
        refuse("LAYOUT_CHANGED", "Enter My Time did not show its week calendar.")
    if not (tab.url() or "").startswith(prefix):
        refuse("SIGN_IN_REQUIRED", "Workday asked for sign-in. Sign in to Workday in that Chrome profile yourself, then run again.")


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


def read_week(account, target):
    week = date.fromisoformat(target["week_start"])
    try:
        chrome = Chrome.connect(CONNECT_S)
    except BrowserError as error:
        refuse("BROWSER_NOT_CONNECTED", f"{error}. Keep Chrome open with remote debugging on at chrome://inspect/#remote-debugging, run again and click Allow when Chrome asks.")
    tab, stage = None, "select-profile"
    try:
        context = select_context(chrome.pages(), account)
        stage = "open-tab"
        tab = chrome.open_tab(account["origin"] + account["enter_time_path"], context)
        stage = "calendar"
        open_calendar(tab, account)
        go_to_week(tab, week)
        calendar = stable(tab, CALENDAR_JS)
        stage = "review"
        open_review(tab)
        review = stable(tab, REVIEW_JS)
        if review["rows"] and review["empty"]:
            refuse("LAYOUT_CHANGED", "Review Time by Week shows rows and 'No items available' at once.")
        stage = "details"
        details = [read_details(tab, i) for i in range(len(review["rows"]))]
        return calendar, review, details
    except BrowserError as error:
        refuse("BROWSER_STEP_FAILED", f"The {stage} step failed ({error}); nothing was changed in Workday. Run again once the page is idle.")
    finally:
        if tab is not None:
            try:
                tab.close()
            except BrowserError:
                pass
        chrome.close()


def write_private(path, value):
    path = Path(path).resolve()
    for part in (path.parent, *path.parent.parents):
        if (part / ".git").exists():
            refuse("PRIVATE_STORAGE_REQUIRED", "Write snapshots outside Git checkouts.")
    pending = path.with_name(f".{path.name}.{uuid.uuid4().hex}")
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(value, out, sort_keys=True, indent=2)
        out.flush()
        os.fsync(out.fileno())
    os.replace(pending, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Validate the account file and runtime without contacting Chrome or Workday")
    check.add_argument("--account")
    read = sub.add_parser("read", help="Read one complete week from the signed-in Chrome")
    read.add_argument("--target", required=True, help="use-workday target JSON")
    read.add_argument("--account")
    read.add_argument("--out", help="Write the snapshot here, owner-only and outside Git checkouts")
    args = parser.parse_args(argv)
    try:
        account = load_account(account_path(args.account))
        if args.command == "check":
            try:
                devtools_port()
                debugging = "on"
            except BrowserError:
                debugging = "off; turn it on at chrome://inspect/#remote-debugging"
            print(json.dumps({"status": "ok", "account": "valid", "chrome_remote_debugging": debugging}, indent=2))
            return 0
        target = check_target(json.loads(Path(args.target).read_text(encoding="utf-8")))
        check_binding(account, target)
        calendar, review, details = read_week(account, target)
        snapshot, result, observations = build_snapshot(account, target, calendar, review, details)
        if args.out:
            write_private(args.out, snapshot)
        print(json.dumps({"status": "ok", "source": "workday-browser", "read": result, "observations": observations}, sort_keys=True, indent=2))
        return 0
    except Refusal as error:
        print(json.dumps({"status": "blocked", "code": error.code, "remedy": error.remedy}), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"status": "blocked", "code": "INVALID_INPUT", "remedy": "Supply a readable target file matching the v1 contract. Nothing was read from Workday."}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
