"""Bounded offline contract and draft-save state machine; no service transport."""
import copy
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class Refusal(Exception):
    def __init__(self, code, remedy):
        self.code, self.remedy = code, remedy
        super().__init__(remedy)


def require(ok, code='INVALID_INPUT', remedy='Supply the complete documented v1 JSON contract.'):
    if not ok:
        raise Refusal(code, remedy)


def fields(value, names):
    require(isinstance(value, dict) and set(value) == set(names.split()))


def label(value):
    require(isinstance(value, str) and 0 < len(value) <= 200 and not any(ord(c) < 32 for c in value))
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def iso(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value))
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise Refusal('INVALID_DATE', 'Supply a valid exact ISO calendar date.')


def target(value):
    fields(value, 'tenant worker week_start timezone')
    for v in value.values():
        label(v)
    require(iso(value['week_start']).weekday() == 0, 'INVALID_WEEK', 'Supply the Monday week-start date.')
    try:
        ZoneInfo(value['timezone'])
    except (ValueError, ZoneInfoNotFoundError):
        raise Refusal('INVALID_TIMEZONE', 'Supply a known IANA timezone; install system timezone data if missing.')
    return copy.deepcopy(value)


def minute(value):
    require(isinstance(value, str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value))
    h, m = map(int, value.split(':'))
    return h * 60 + m


def entry(value, binding, types):
    fields(value, 'date start end breaks time_type worktags')
    d = iso(value['date'])
    start, end = minute(value['start']), minute(value['end'])
    require(iso(binding['week_start']) <= d < iso(binding['week_start']) + timedelta(days=7), 'WRONG_WEEK', 'Use entries within the exact selected week.')
    require(start < end, 'OVERNIGHT_UNSUPPORTED', 'Split overnight work into separately verified supported dates; do not infer times.')
    zone = ZoneInfo(binding['timezone'])
    # Reject any ambiguous/nonexistent minute or offset change in the whole block, including breaks.
    offsets = set()
    for m in range(start, end + 1):
        naive = datetime.combine(d, datetime.min.time()) + timedelta(minutes=m)
        a, b = naive.replace(tzinfo=zone, fold=0), naive.replace(tzinfo=zone, fold=1)
        require(a.utcoffset() == b.utcoffset() and a.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == naive,
                'DST_UNSUPPORTED', 'Use a separately verified allocation outside DST transitions.')
        offsets.add(a.utcoffset())
    require(len(offsets) == 1, 'DST_UNSUPPORTED', 'Use a separately verified allocation outside DST transitions.')
    require(value['time_type'] in types, 'UNKNOWN_CLASSIFICATION', 'Read the allowed time classifications for this exact target.')
    require(isinstance(value['worktags'], dict))
    for k, v in value['worktags'].items():
        label(k)
        label(v)
    require(isinstance(value['breaks'], list))
    intervals = []
    for br in value['breaks']:
        fields(br, 'start end')
        a, b = minute(br['start']), minute(br['end'])
        require(start <= a < b <= end, 'INVALID_BREAK', 'Supply explicit unpaid breaks within the work block.')
        intervals.append((a, b))
    intervals.sort()
    require(all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:])), 'OVERLAP', 'Remove overlapping breaks.')
    minutes = end - start - sum(b - a for a, b in intervals)
    require(minutes > 0, 'INVALID_BREAK', 'Work blocks must contain positive paid minutes.')
    result = copy.deepcopy(value)
    result['breaks'].sort(key=lambda b: (b['start'], b['end']))
    return result, minutes


def entries(values, binding, types):
    require(isinstance(values, list) and len(values) <= 100)
    parsed = [entry(e, binding, types) for e in values]
    parsed.sort(key=lambda item: (item[0]['date'], item[0]['start'], item[0]['end']))
    for (a, _), (b, _) in zip(parsed, parsed[1:]):
        require(a['date'] != b['date'] or a['end'] <= b['start'], 'OVERLAP', 'Remove duplicate or overlapping work blocks, including break spans.')
    totals = {}
    for e, minutes in parsed:
        totals[e['date']] = totals.get(e['date'], 0) + minutes
    return [e for e, _ in parsed], totals


STATUSES = {'empty', 'draft', 'submitted', 'sent_for_approval', 'approved', 'denied', 'unknown'}


def snapshot(value, expected):
    fields(value, 'schema_version target revision status entries allowed_time_types pay_periods service_total_minutes draft_save_supported certification')
    require(type(value['schema_version']) is int and value['schema_version'] == 1)
    require(target(value['target']) == target(expected), 'TARGET_MISMATCH', 'Re-read the exact tenant, worker, week and timezone.')
    label(value['revision'])
    require(value['status'] in STATUSES)
    require(type(value['draft_save_supported']) is bool and isinstance(value['certification'], str))
    types = value['allowed_time_types']
    require(isinstance(types, list) and len(types) > 0 and all(isinstance(t, str) for t in types))
    for t in types:
        label(t)
    require(len(types) == len(set(types)))
    periods = value['pay_periods']
    require(isinstance(periods, dict))
    days = {(iso(expected['week_start']) + timedelta(days=i)).isoformat() for i in range(7)}
    require(set(periods) == days, 'UNKNOWN_PAY_PERIOD', 'Read the payroll period for every date in the selected week.')
    for p in periods.values():
        label(p)
    require(isinstance(value['entries'], list))
    ids, raw = [], []
    for record in value['entries']:
        fields(record, 'id status entry')
        ids.append(label(record['id']))
        require(record['status'] in STATUSES - {'empty'})
        raw.append(record['entry'])
    require(len(ids) == len(set(ids)), 'DUPLICATE_RECORD', 'Reconcile duplicate service record IDs before proceeding.')
    _, totals = entries(raw, expected, types)
    total = sum(totals.values())
    require(type(value['service_total_minutes']) is int and value['service_total_minutes'] == total,
            'TOTAL_MISMATCH', 'Reconcile service-calculated minutes and classifications before proceeding.')
    require(value['status'] != 'empty' or not raw, 'STATUS_MISMATCH', 'Re-read the service submission state.')
    result = copy.deepcopy(value)
    result['entries'] = sorted(result['entries'], key=lambda r: r['id'])
    for r in result['entries']:
        r['entry'], _ = entry(r['entry'], expected, types)
    result['allowed_time_types'] = sorted(types)
    return result


def read_timesheet(value, expected):
    state = snapshot(value, expected)
    _, totals = entries([r['entry'] for r in state['entries']], expected, state['allowed_time_types'])
    return {'schema_version': 1, 'operation': 'read-timesheet', 'source': 'offline-snapshot',
            'snapshot': state, 'daily_minutes': totals, 'fingerprint': digest(state)}


def preview(value, allocation):
    fields(allocation, 'schema_version target entries expected_total_minutes')
    require(type(allocation['schema_version']) is int and allocation['schema_version'] == 1)
    expected = target(allocation['target'])
    state = snapshot(value, expected)
    require(state['status'] in {'empty', 'draft'} and all(r['status'] == 'draft' for r in state['entries']),
            'PROTECTED_STATE', 'Do not change submitted, approved, denied or unknown records; resolve their state separately.')
    require(state['draft_save_supported'] and state['certification'] == '', 'DRAFT_UNSAFE', 'Verify a save-only operation that neither submits nor certifies.')
    wanted, totals = entries(allocation['entries'], expected, state['allowed_time_types'])
    require(type(allocation['expected_total_minutes']) is int and sum(totals.values()) == allocation['expected_total_minutes'],
            'TOTAL_MISMATCH', 'Supply exact blocks and explicit breaks matching the intended weekly minutes.')
    existing = [r['entry'] for r in state['entries']]
    require(all(e in wanted for e in existing), 'CONFLICT', 'Existing entries differ from the full desired week; review them without overwriting or deleting.')
    additions = [e for e in wanted if e not in existing]
    plan = {'schema_version': 1, 'operation': 'save-draft', 'target': expected,
            'base_fingerprint': digest(state), 'allocation': dict(allocation, entries=wanted),
            'additions': additions, 'unchanged': existing, 'daily_minutes': totals,
            'total_minutes': sum(totals.values()), 'pay_periods': state['pay_periods'],
            'crosses_pay_period': len(set(state['pay_periods'].values())) > 1}
    plan['plan_fingerprint'] = digest(plan)
    return plan


def verify_plan(plan):
    fields(plan, 'schema_version operation target base_fingerprint allocation additions unchanged daily_minutes total_minutes pay_periods crosses_pay_period plan_fingerprint')
    body = {k: v for k, v in plan.items() if k != 'plan_fingerprint'}
    require(digest(body) == plan['plan_fingerprint'], 'PLAN_CHANGED', 'Generate and review a new preview.')


def save_draft(transport, plan, approved_fingerprint, journal):
    """Internal adapter contract. Production transport is deliberately not supplied.

    journal.guard(target) must serialize processes and persist intent before a mutation.
    transport.create_draft must atomically guard expected_revision or refuse support.
    A timeout never triggers an automatic retry, even when readback finds the entry.
    """
    verify_plan(plan)
    require(getattr(transport, 'supports_conditional_create', False) is True, 'UNSAFE_TRANSPORT', 'Use a verified atomic revision guard; browser preflight alone cannot prevent concurrent edits.')
    require(approved_fingerprint == plan['plan_fingerprint'], 'APPROVAL_MISMATCH', 'Review and explicitly authorize the exact plan fingerprint.')
    binding = target(plan['target'])
    completed = []
    with journal.guard(binding):
        require(not journal.pending(), 'RECONCILE_REQUIRED', 'Reconcile the previous uncertain operation with a fresh authoritative read before a new preview.')
        state = snapshot(transport.read(binding), binding)
        require(preview(state, plan['allocation']) == plan, 'STALE_PLAN', 'Read the current week and review a new preview.')
        for index, proposed in enumerate(plan['additions']):
            try:
                current = snapshot(transport.read(binding), binding)
                require(current == state, 'STALE_PLAN', 'The week changed during execution; reconcile completed entries and preview again.')
            except Exception:
                return {'status': 'stopped', 'stage': 'preflight', 'target': binding,
                        'completed': completed, 'pending': plan['additions'][len(completed):],
                        'next_action': 'Re-read and reconcile the changed or unavailable week, then preview again.'}
            expected_entries = [r['entry'] for r in state['entries']] + [proposed]
            try:
                journal.intent({'target': binding, 'plan_fingerprint': plan['plan_fingerprint'],
                                'entry': proposed, 'completed': completed})
            except Exception:
                return {'status': 'stopped', 'stage': 'journal', 'target': binding,
                        'completed': completed, 'pending': plan['additions'][len(completed):],
                        'next_action': 'Repair private durable storage and reconcile any intent before a new preview.'}
            try:
                transport.create_draft(binding, proposed, expected_revision=state['revision'])
                after = snapshot(transport.read(binding), binding)
                require(after['status'] == 'draft' and all(r['status'] == 'draft' for r in after['entries']), 'READBACK_FAILED', 'Verify draft-only status before further work.')
                require(after['allowed_time_types'] == state['allowed_time_types'] and after['pay_periods'] == state['pay_periods'] and after['certification'] == '' and after['draft_save_supported'], 'READBACK_FAILED', 'Reconcile changed classifications, periods or save semantics.')
                observed = [r['entry'] for r in after['entries']]
                require(sorted(map(digest, observed)) == sorted(map(digest, expected_entries)), 'READBACK_FAILED', 'Reconcile all saved entries before further work.')
                require(all(r in after['entries'] for r in state['entries']), 'READBACK_FAILED', 'Existing service records changed; reconcile before further work.')
                completed.append(proposed)
                journal.clear()
                state = after
            except Exception:
                # Do not expose raw transport errors: they can contain tokens or full pages.
                observed_saved = []
                try:
                    observed_state = snapshot(transport.read(binding), binding)
                    observed_saved = [r['entry'] for r in observed_state['entries'] if r['entry'] == proposed and r['status'] == 'draft']
                except Exception:
                    pass
                return {'status': 'uncertain', 'stage': 'save-or-readback', 'target': binding,
                        'completed': completed, 'attempted': proposed, 'observed_draft': observed_saved,
                        'pending': plan['additions'][index + 1:],
                        'next_action': 'Reconcile the journal with an authoritative read; do not retry automatically.'}
        return {'status': 'saved-draft' if completed else 'unchanged', 'target': binding,
                'completed': completed, 'total_minutes': state['service_total_minutes'],
                'fingerprint': digest(state), 'submitted': False}
