import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from workday_core import NotDispatched, Refusal, preview, propose, read_timesheet, save_draft
from workday_journal import Journal

BINDING = {'tenant': 'example.invalid', 'worker': 'synthetic-worker', 'week_start': '2026-02-02', 'timezone': 'America/Chicago'}


def block(day='2026-02-02', start='09:00', end='12:00'):
    return {'date': day, 'start': start, 'end': end, 'breaks': [], 'time_type': 'regular', 'worktags': {'job': 'synthetic-job'}}


def empty():
    return {'schema_version': 1, 'target': copy.deepcopy(BINDING), 'revision': '0', 'status': 'empty', 'entries': [],
            'allowed_time_types': ['regular'], 'pay_periods': {f'2026-02-0{i}': 'period-a' for i in range(2, 9)},
            'service_total_minutes': 0, 'draft_save_supported': True, 'certification': ''}


def allocation():
    return {'schema_version': 1, 'target': copy.deepcopy(BINDING), 'entries': [block(), block('2026-02-03')], 'expected_total_minutes': 360}


class Fake:
    """Test-only in-memory service. Never a CLI transport."""
    supports_conditional_create = True

    def __init__(self):
        self.state, self.calls, self.reads = empty(), 0, 0
        self.fail_at, self.lose_response, self.bad_readback = None, False, False
        self.expire_after, self.change_on_read = None, None

    def read(self, binding):
        self.reads += 1
        if self.expire_after is not None and self.calls >= self.expire_after:
            raise RuntimeError('synthetic sensitive raw transport error')
        if self.reads == self.change_on_read:
            self.state['revision'] += '-changed'
        return copy.deepcopy(self.state)

    def create_draft(self, binding, entry, expected_revision):
        assert binding == self.state['target']
        assert expected_revision == self.state['revision']
        self.calls += 1
        if self.calls == self.fail_at:
            raise TimeoutError('synthetic sensitive raw transport error')
        self.state['entries'].append({'id': str(self.calls), 'status': 'draft', 'entry': copy.deepcopy(entry)})
        self.state['status'] = 'draft'
        self.state['revision'] = str(self.calls)
        self.state['service_total_minutes'] += 180
        if self.bad_readback:
            self.state['status'] = 'submitted'
        if self.lose_response:
            raise TimeoutError('synthetic sensitive raw transport error')


class WorkdayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.journal = Journal(Path(self.tmp.name) / 'private')

    def refused(self, fn, code):
        with self.assertRaises(Refusal) as exc:
            fn()
        self.assertEqual(exc.exception.code, code)

    def test_read_historical_submitted(self):
        state = empty()
        state['status'] = 'approved'
        self.assertEqual(read_timesheet(state, BINDING)['snapshot']['status'], 'approved')

    def test_target_all_dimensions(self):
        for field, value in [('tenant', 'other'), ('worker', 'other'), ('week_start', '2026-02-09'), ('timezone', 'UTC')]:
            target = dict(BINDING, **{field: value})
            self.refused(lambda: read_timesheet(empty(), target), 'TARGET_MISMATCH')

    def test_read_service_totals(self):
        state = empty()
        state['service_total_minutes'] = 5
        self.refused(lambda: read_timesheet(state, BINDING), 'TOTAL_MISMATCH')

    def test_explicit_break_and_totals(self):
        a = allocation()
        a['entries'][0]['breaks'] = [{'start': '10:00', 'end': '10:30'}]
        a['expected_total_minutes'] = 330
        p = preview(empty(), a)
        self.assertEqual(p['daily_minutes']['2026-02-02'], 150)
        self.assertEqual(p['total_minutes'], 330)

    def test_missing_break_refuses(self):
        a = allocation()
        del a['entries'][0]['breaks']
        self.refused(lambda: preview(empty(), a), 'INVALID_INPUT')

    def test_invalid_breaks(self):
        for breaks in [[{'start': '08:00', 'end': '10:00'}], [{'start': '10:00', 'end': '11:00'}, {'start': '10:30', 'end': '11:30'}]]:
            a = allocation()
            a['entries'][0]['breaks'] = breaks
            with self.assertRaises(Refusal):
                preview(empty(), a)

    def test_overlap_duplicate_and_overnight(self):
        for e in [block(), block(start='11:00', end='13:00'), block(start='22:00', end='01:00')]:
            a = allocation()
            a['entries'][1] = e
            with self.assertRaises(Refusal):
                preview(empty(), a)

    def test_unknown_fields_classification_and_wrong_date(self):
        for change in [{'selector': 'button'}, {'time_type': 'guessed'}, {'date': '2026-02-09'}]:
            a = allocation()
            a['entries'][0].update(change)
            with self.assertRaises(Refusal):
                preview(empty(), a)

    def test_dst(self):
        for monday, sunday, start, end in [('2026-03-02', '2026-03-08', '01:30', '03:30'), ('2026-10-26', '2026-11-01', '00:30', '02:30')]:
            from datetime import date, timedelta
            s, a = empty(), allocation()
            s['target']['week_start'] = a['target']['week_start'] = monday
            s['pay_periods'] = {(date.fromisoformat(monday) + timedelta(days=i)).isoformat(): 'period' for i in range(7)}
            a['entries'] = [block(sunday, start, end)]
            self.refused(lambda: preview(s, a), 'DST_UNSUPPORTED')

    def test_expected_total(self):
        a = allocation()
        a['expected_total_minutes'] = 361
        self.refused(lambda: preview(empty(), a), 'TOTAL_MISMATCH')

    def test_period_crossing_visible(self):
        s = empty()
        s['pay_periods']['2026-02-08'] = 'period-b'
        self.assertTrue(preview(s, allocation())['crosses_pay_period'])

    def test_protected_and_certification(self):
        for state in ['submitted', 'sent_for_approval', 'approved', 'denied', 'unknown']:
            s = empty()
            s['status'] = state
            self.refused(lambda: preview(s, allocation()), 'PROTECTED_STATE')
        for change in [{'draft_save_supported': False}, {'certification': 'I certify'}]:
            s = dict(empty(), **change)
            self.refused(lambda: preview(s, allocation()), 'DRAFT_UNSAFE')

    def test_exact_match_skip_and_conflict(self):
        f = Fake()
        f.create_draft(BINDING, block(), '0')
        p = preview(f.state, allocation())
        self.assertEqual(len(p['unchanged']), 1)
        self.assertEqual(len(p['additions']), 1)
        a = allocation()
        a['entries'][0]['worktags']['job'] = 'different'
        self.refused(lambda: preview(f.state, a), 'CONFLICT')

    def test_mixed_and_duplicate_records(self):
        f = Fake()
        f.create_draft(BINDING, block(), '0')
        f.state['entries'][0]['status'] = 'submitted'
        self.refused(lambda: preview(f.state, allocation()), 'PROTECTED_STATE')
        f.state['entries'].append(copy.deepcopy(f.state['entries'][0]))
        self.refused(lambda: read_timesheet(f.state, BINDING), 'DUPLICATE_RECORD')

    def test_execute_and_repeat_new_preview(self):
        f = Fake()
        p = preview(f.state, allocation())
        result = save_draft(f, p, p['plan_fingerprint'], self.journal)
        self.assertEqual(result['status'], 'saved-draft')
        self.assertFalse(result['submitted'])
        p = preview(f.state, allocation())
        self.assertEqual(save_draft(f, p, p['plan_fingerprint'], self.journal)['status'], 'unchanged')
        self.assertEqual(f.calls, 2)

    def test_no_guard_no_writes(self):
        f = Fake()
        f.supports_conditional_create = False
        p = preview(f.state, allocation())
        self.refused(lambda: save_draft(f, p, p['plan_fingerprint'], self.journal), 'UNSAFE_TRANSPORT')
        self.assertEqual(f.calls, 0)

    def test_reread_safeguard_needs_the_accounts_explicit_choice(self):
        f = Fake()
        f.supports_conditional_create = False
        f.save_safeguard = 'reread'
        p = preview(f.state, allocation())
        self.refused(lambda: save_draft(f, p, p['plan_fingerprint'], self.journal), 'UNSAFE_TRANSPORT')
        self.assertEqual(f.calls, 0)
        result = save_draft(f, p, p['plan_fingerprint'], self.journal, allow_reread=True)
        self.assertEqual((result['status'], f.calls), ('saved-draft', 2))

    def test_a_stop_before_sending_is_clean_and_clears_the_intent(self):
        f = Fake()
        p = preview(f.state, allocation())
        original = f.create_draft

        def stop_on_second(binding, entry, expected_revision):
            if f.calls == 1:
                raise NotDispatched()
            return original(binding, entry, expected_revision)

        f.create_draft = stop_on_second
        result = save_draft(f, p, p['plan_fingerprint'], self.journal)
        self.assertEqual((result['status'], result['stage'], len(result['completed']), len(result['pending'])), ('stopped', 'before-save', 1, 1))
        with self.journal.guard(BINDING):
            self.assertFalse(self.journal.pending())

    def test_an_uncertain_intent_records_when_it_was_written(self):
        f = Fake()
        f.fail_at = 1
        p = preview(f.state, allocation())
        self.assertEqual(save_draft(f, p, p['plan_fingerprint'], self.journal)['status'], 'uncertain')
        with self.journal.guard(BINDING):
            intent = self.journal.read_intent()
        self.assertEqual(intent['entry'], block())
        self.assertIn('recorded_at', intent)

    def test_plan_tamper_and_approval(self):
        f = Fake()
        p = preview(f.state, allocation())
        self.refused(lambda: save_draft(f, p, 'wrong', self.journal), 'APPROVAL_MISMATCH')
        p['total_minutes'] = 1
        self.refused(lambda: save_draft(f, p, p['plan_fingerprint'], self.journal), 'PLAN_CHANGED')
        self.assertEqual(f.calls, 0)

    def test_stale_initial(self):
        f = Fake()
        p = preview(f.state, allocation())
        f.state['revision'] = 'changed'
        self.refused(lambda: save_draft(f, p, p['plan_fingerprint'], self.journal), 'STALE_PLAN')
        self.assertEqual(f.calls, 0)

    def test_changed_between_saves_reports_partial(self):
        f = Fake()
        p = preview(f.state, allocation())
        f.change_on_read = 4
        r = save_draft(f, p, p['plan_fingerprint'], self.journal)
        self.assertEqual(r['status'], 'stopped')
        self.assertEqual(len(r['completed']), 1)
        self.assertEqual(f.calls, 1)

    def test_timeout_partial_and_durable_retry_block(self):
        f = Fake()
        f.fail_at = 2
        p = preview(f.state, allocation())
        r = save_draft(f, p, p['plan_fingerprint'], self.journal)
        self.assertEqual(r['status'], 'uncertain')
        self.assertEqual(len(r['completed']), 1)
        p = preview(f.state, allocation())
        reopened = Journal(Path(self.tmp.name) / 'private')
        self.refused(lambda: save_draft(f, p, p['plan_fingerprint'], reopened), 'RECONCILE_REQUIRED')
        self.assertEqual(f.calls, 2)

    def test_lost_response_readback_not_automatic_retry(self):
        f = Fake()
        f.lose_response = True
        p = preview(f.state, allocation())
        r = save_draft(f, p, p['plan_fingerprint'], self.journal)
        self.assertEqual(r['status'], 'uncertain')
        self.assertEqual(len(r['observed_draft']), 1)
        self.assertEqual(f.calls, 1)

    def test_expired_readback_and_wrong_status(self):
        for change in ['expire_after', 'bad_readback']:
            f = Fake()
            setattr(f, change, 1)
            p = preview(f.state, allocation())
            r = save_draft(f, p, p['plan_fingerprint'], self.journal)
            self.assertEqual(r['status'], 'uncertain')
            self.assertEqual(f.calls, 1)
            with self.journal.guard(BINDING):
                self.assertTrue(self.journal.pending())
                self.journal.clear()  # Test isolation only; no production recovery bypass exposed.

    def test_journal_lock_and_permissions(self):
        with self.journal.guard(BINDING):
            other = Journal(Path(self.tmp.name) / 'private')
            self.refused(lambda: other.guard(BINDING).__enter__(), 'TARGET_BUSY')
            self.journal.intent({'synthetic': True})
            self.assertEqual(os.stat(self.journal.path).st_mode & 0o777, 0o600)
        os.chmod(Path(self.tmp.name) / 'private', 0o755)
        self.refused(lambda: Journal(Path(self.tmp.name) / 'private'), 'PRIVATE_STORAGE_REQUIRED')

    def test_intent_failure_stops_before_mutation(self):
        f = Fake()
        p = preview(f.state, allocation())
        def fail(record):
            raise OSError('synthetic disk full')
        self.journal.intent = fail
        r = save_draft(f, p, p['plan_fingerprint'], self.journal)
        self.assertEqual(r['stage'], 'journal')
        self.assertEqual(f.calls, 0)

    def test_invalid_timezone(self):
        s = empty()
        s['target']['timezone'] = 'Not/A_Zone'
        self.refused(lambda: read_timesheet(s, s['target']), 'INVALID_TIMEZONE')

    def test_cli_rejects_missing_critical_value(self):
        cli = Path(__file__).resolve().parents[1] / 'scripts/workday'
        root = Path(self.tmp.name)
        a = allocation()
        del a['target']['timezone']
        for name, value in [('snapshot', empty()), ('allocation', a)]:
            (root / name).write_text(json.dumps(value))
        result = subprocess.run([sys.executable, str(cli), 'preview', '--snapshot', str(root / 'snapshot'), '--allocation', str(root / 'allocation')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertIn('complete documented v1 JSON contract', result.stderr)

    def test_cli_duplicate_json_key(self):
        cli = Path(__file__).resolve().parents[1] / 'scripts/workday'
        path = Path(self.tmp.name) / 'bad.json'
        path.write_text('{"target": 1, "target": 2}')
        result = subprocess.run([sys.executable, str(cli), 'preview', '--snapshot', str(path), '--allocation', str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertIn('duplicate JSON object keys', result.stderr)

    def test_journal_symlink_refused(self):
        from workday_core import digest
        victim = Path(self.tmp.name) / 'untouched'
        victim.write_text('untouched')
        lock = Path(self.tmp.name) / 'private' / (digest(BINDING) + '.lock')
        lock.symlink_to(victim)
        with self.assertRaises(OSError):
            with self.journal.guard(BINDING):
                self.fail('symlink lock accepted')
        self.assertEqual(victim.read_text(), 'untouched')

    def test_cli_failure_has_no_payload_stdout(self):
        cli = Path(__file__).resolve().parents[1] / 'scripts/workday'
        for args in [['doctor'], ['read-timesheet', '--target', 'missing-file']]:
            result = subprocess.run([sys.executable, str(cli), *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, '')
            self.assertIn('TRANSPORT_UNAVAILABLE', result.stderr)
            self.assertIn('workday_browser.py read', result.stderr)

    def earlier(self):
        source = empty()
        source['entries'] = [{'id': str(i), 'status': 'approved', 'entry': b} for i, b in enumerate([block(), block('2026-02-08', '14:00', '17:00')])]
        source['status'], source['service_total_minutes'] = 'approved', 360
        return source

    def test_propose_moves_an_earlier_weeks_blocks_to_the_same_weekdays(self):
        proposed = propose(self.earlier(), '2026-02-16')
        self.assertEqual(proposed, {'schema_version': 1, 'target': dict(BINDING, week_start='2026-02-16'), 'entries': [block('2026-02-16'), block('2026-02-22', '14:00', '17:00')], 'expected_total_minutes': 360})
        fresh = empty()
        fresh['target'] = proposed['target']
        fresh['pay_periods'] = {f'2026-02-{i}': 'period-b' for i in range(16, 23)}
        self.assertEqual(len(preview(fresh, proposed)['additions']), 2)
        self.assertEqual([e['date'] for e in propose(self.earlier(), '2026-01-26')['entries']], ['2026-01-26', '2026-02-01'])

    def test_propose_refuses_what_it_cannot_carry_over(self):
        self.refused(lambda: propose(empty(), '2026-02-16'), 'NOTHING_TO_COPY')
        self.refused(lambda: propose(self.earlier(), '2026-02-02'), 'SAME_WEEK')
        self.refused(lambda: propose(self.earlier(), '2026-02-17'), 'INVALID_WEEK')
        self.refused(lambda: propose([], '2026-02-16'), 'INVALID_INPUT')
        early = self.earlier()
        early['entries'][1]['entry'].update(start='01:00', end='04:00')
        # Sunday 8 March 2026 changes to daylight time at 2 AM.
        self.refused(lambda: propose(early, '2026-03-02'), 'DST_UNSUPPORTED')

    def test_cli_propose_writes_a_private_allocation(self):
        cli = Path(__file__).resolve().parents[1] / 'scripts/workday'
        root = Path(os.path.realpath(self.tmp.name))
        (root / 'earlier.json').write_text(json.dumps(self.earlier()))
        out = root / 'allocation.json'
        result = subprocess.run([sys.executable, str(cli), 'propose', '--snapshot', str(root / 'earlier.json'), '--week', '2026-02-16', '--out', str(out)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        shown = json.loads(result.stdout)
        self.assertEqual((shown['status'], shown['source_week'], shown['allocation']), ('proposal', '2026-02-02', json.loads(out.read_text())))
        self.assertIn('not evidence of hours worked', shown['next_action'])
        self.assertEqual(out.stat().st_mode & 0o777, 0o600)

    def test_cli_preview_and_no_execute(self):
        cli = Path(__file__).resolve().parents[1] / 'scripts/workday'
        root = Path(self.tmp.name)
        for name, value in [('snapshot', empty()), ('allocation', allocation())]:
            (root / name).write_text(json.dumps(value))
        result = subprocess.run([sys.executable, str(cli), 'preview', '--snapshot', str(root / 'snapshot'), '--allocation', str(root / 'allocation')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)['plan']
        (root / 'plan').write_text(json.dumps(plan))
        result = subprocess.run([sys.executable, str(cli), 'save-draft', '--plan', str(root / 'plan'), '--execute', '--approved-fingerprint', plan['plan_fingerprint']], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertIn('No entries were saved', result.stderr)


if __name__ == '__main__':
    unittest.main()
