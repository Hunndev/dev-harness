"""Parent-owned TDD execution observations, frozen baselines, and revision binding.

An external approval record is an explicit controller trust input, not proof of
cryptographic human authorship. Repository evidence cannot approve its own edits.
"""
import hashlib
import json
import os
import re
import shlex
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .gate import _argv, _load_json, run_gate_command
from .pack import ContractError, artifact_layout, repository_root, _git
from .schema_validation import validate_schema
from .snapshot import compute_source_snapshot, compute_tdd_sut_sha256
from .tdd_quality import (canonical_json_bytes, validate_test_design,
                          validate_test_sensitivity, validate_observation_pair, _valid_approval)
from .tdd_reports import prepare_report, parse_report

_DESIGN = 'tdd-test-design-result.json'
_SENSITIVITY = 'tdd-sensitivity-result.json'
_BAD_OUTPUT = re.compile(
    r'(?im)(?:\b(?:ERROR collecting|ERROR at (?:setup|teardown)|failed on setup)\b'
    r'|(?:^|\n)[^\n]*\berror: (?:cannot find|cannot convert|no such module|package .+ does not exist)'
    r'|(?:^|\n)\s*Compilation failed\b)')


def _fail(code: str) -> None:
    raise ContractError([code])


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe(path: Path, root: Optional[Path] = None, *, exists: bool = True) -> Path:
    path = Path(path).absolute()
    if '..' in path.parts or path.resolve() != path:
        _fail('TDD_PATH_INVALID')
    if root is not None:
        try:
            path.relative_to(root)
        except ValueError:
            _fail('TDD_PATH_INVALID')
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            _fail('TDD_PATH_INVALID')
    if exists and not path.is_file():
        _fail('TDD_PATH_INVALID')
    return path


def _read(path: Path) -> Dict[str, Any]:
    _safe(path)
    try:
        data = _load_json(path)
    except (OSError, UnicodeError, ValueError):
        _fail('TDD_SCHEMA_INVALID')
    if not isinstance(data, dict):
        _fail('TDD_SCHEMA_INVALID')
    return data


def _parse(raw: bytes) -> Dict[str, Any]:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    data = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
    if not isinstance(data, dict):
        raise ValueError('JSON object required')
    return data


def _write(path: Path, content: bytes, *, frozen: bool = False) -> None:
    _safe(path, exists=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.tdd-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(content)
        os.chmod(temporary, 0o444 if frozen else 0o600)
        os.replace(temporary, str(path))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _load_baseline(state: Path, out: Path, design_path: Optional[Path] = None):
    try:
        active_path = state / 'active.json'
        active = _read(active_path)
        run_id = active.get('run_id')
        if not isinstance(run_id, str) or not re.fullmatch(r'[0-9a-f]{32}', run_id):
            _fail('TDD_OBSERVATION_INVALID')
        frozen_path = state / (run_id + '.json')
        baseline = _read(frozen_path)
        content = frozen_path.read_bytes()
        if (_sha(content) != active.get('baseline_sha256')
                or content != canonical_json_bytes(baseline)
                or baseline.get('schema_version') != '1.2'
                or baseline.get('observed', {}).get('run_id') != run_id
                or validate_schema(baseline, 'tdd-test-design-result.schema.json')
                or validate_test_design(baseline)):
            _fail('TDD_OBSERVATION_INVALID')
        current_design = _safe(out / _DESIGN)
        if current_design.read_bytes() != content:
            _fail('TDD_OBSERVATION_INVALID')
        if design_path is not None and _safe(design_path) != current_design:
            _fail('TDD_OBSERVATION_INVALID')
        guard = {path: path.read_bytes() for path in (active_path, frozen_path, current_design)}
        return active, baseline, guard
    except ContractError:
        _fail('TDD_OBSERVATION_INVALID')


def _approval(path: Optional[Path], baseline: Dict[str, Any], context: Dict[str, str],
              current_hash: str):
    if path is None:
        _fail('TDD_TEST_IDENTITY_CHANGED')
    try:
        path = _safe(path)
        repo = Path(context['cwd'])
        if path == repo or repo in path.parents:
            _fail('TDD_TEST_IDENTITY_CHANGED')
        raw = path.read_bytes()
        record = _parse(raw)
        before = baseline['observed']
        expected = {
            'schema_version': '1.0', 'kind': 'tdd-red-revision-approval',
            'repo': context['cwd'], 'git_dir': context['git_dir'],
            'artifacts': context['artifacts'], 'test_file': context['test_file'],
            'run_id': before['run_id'], 'old_sha256': before['test_file_sha256'],
            'new_sha256': current_hash, 'approved_by': 'user',
        }
        if any(record.get(key) != value for key, value in expected.items()):
            _fail('TDD_TEST_IDENTITY_CHANGED')
        revision = record.get('revision')
        if type(revision) is not int or revision not in (1, 2):
            _fail('TDD_TEST_IDENTITY_CHANGED')
        if not isinstance(record.get('approval_source'), str) or not record['approval_source'].strip():
            _fail('TDD_TEST_IDENTITY_CHANGED')
        revision_path = _safe(Path(context['artifacts']) / 'tdd-red-revisions.md', repo)
        revision_bytes = revision_path.read_bytes()
        revisions = revision_bytes.decode('utf-8').splitlines()
        if (len(revisions) != revision or any(not re.fullmatch(r'revision ' + str(index) + r': .+', line)
                for index, line in enumerate(revisions, 1))
                or record.get('revision_line') != revisions[-1]):
            _fail('TDD_TEST_IDENTITY_CHANGED')
        receipt = {'record_path': str(path), 'record_sha256': _sha(canonical_json_bytes(record)),
                   'record': record}
        if not _valid_approval({'observed': dict(context, run_id=before['run_id'], approval=receipt),
                                'red_test_hash': before['test_file_sha256'], 'green_test_hash': current_hash}):
            _fail('TDD_TEST_IDENTITY_CHANGED')
        return receipt, {path: raw, revision_path: revision_bytes}
    except (ContractError, OSError, UnicodeError, KeyError, TypeError, ValueError):
        _fail('TDD_TEST_IDENTITY_CHANGED')


def _sensitivity_metadata(document, baseline_kind, baseline):
    # Metadata can be the five semantic fields or an earlier complete evidence
    # document. A declared BLOCKED status/foreign schema is never upgraded to PASS.
    semantic = {'tier', 'test_id', 'high_risk', 'mutation', 'regression'}
    derived = {'schema_version', 'baseline', 'stage', 'status', 'red_test_hash', 'green_test_hash',
               'red_outcome', 'green_outcome', 'approved_red_revision', 'observed'}
    if (not semantic <= document.keys() or not document.keys() <= semantic | derived
            or ('schema_version' in document and document['schema_version'] not in ('1.0', '1.1', '1.2'))
            or ('stage' in document and document['stage'] != 'tdd-sensitivity')
            or ('status' in document and document['status'] != 'PASS')):
        _fail('TDD_SCHEMA_INVALID')
    metadata = {key: document[key] for key in semantic}
    candidate = dict(metadata, schema_version='1.1', baseline=baseline_kind,
                     stage='tdd-sensitivity', status='PASS',
                     red_test_hash=baseline['observed']['test_file_sha256'],
                     green_test_hash=baseline['observed']['test_file_sha256'],
                     red_outcome='PASS' if baseline_kind == 'PASS_TO_PASS' else 'FAIL',
                     green_outcome='PASS', approved_red_revision=False)
    errors = validate_test_sensitivity(candidate)
    if validate_schema(candidate, 'tdd-sensitivity-result.schema.json'):
        errors.append('TDD_SCHEMA_INVALID')
    if errors:
        raise ContractError(errors)
    return metadata


def _bound_case(case: Dict[str, Any], test: Path, repo: Path, text: str) -> bool:
    reported = case.get('file')
    if reported:
        candidate = Path(reported)
        if not candidate.is_absolute():
            candidate = repo / candidate
        return candidate.resolve() == test
    classname = case.get('classname') or ''
    if test.suffix == '.py':
        module = test.relative_to(repo).with_suffix('').as_posix().replace('/', '.')
        return classname == module or classname.startswith(module + '.')
    if test.suffix in ('.java', '.kt', '.swift', '.m', '.mm'):
        names = re.findall(r'\b(?:class|struct|interface)\s+(\w+)', text)
        package = re.search(r'^\s*package\s+([\w.]+)', text, re.MULTILINE)
        for name in names:
            full = (package.group(1) + '.' if package else '') + name
            if classname in (full, name) or classname.startswith(full + '$'):
                return True
            # xcresult identifiers include the target before the source class.
            if name in str(case.get('id', '')).split('/')[:-1]:
                return True
    return False


def _observe(command: str, repo: Path, test: Path, track: str, phase: str,
             baseline_kind: str):
    try:
        argv = _argv(command)
    except ValueError:
        _fail('TDD_COMMAND_INVALID')
    with tempfile.TemporaryDirectory(prefix='hb-tdd-report-') as temporary:
        try:
            plan = prepare_report(argv, Path(temporary).resolve())
            row = run_gate_command(shlex.join(plan['argv']), repo, track=track, capture_output=True)
            for extraction, output in zip(plan.get('report_commands', []), plan.get('report_json_paths', [])):
                extracted = run_gate_command(shlex.join(extraction), repo, track=track, capture_output=True)
                if extracted['exit_code'] != 0:
                    _fail('TDD_RED_REASON_INVALID' if phase == 'red' else 'TDD_TRANSITION_INVALID')
                _write(output, extracted['stdout'].encode('utf-8'))
            cases = parse_report(plan, repo)
        except ValueError as error:
            if isinstance(error, ContractError):
                raise
            code = str(error)
            _fail(code if code.startswith('TDD_') else 'TDD_RED_REASON_INVALID')
        bad = any(case['outcome'] == 'ERROR' or (case['outcome'] == 'FAIL' and not case['assertion'])
                  for case in cases)
        bad = (bad or row.get('execution_error') is not None or row['exit_code'] < 0
               or bool(_BAD_OUTPUT.search(row['stdout'] + '\n' + row['stderr'])))
        text = test.read_text(encoding='utf-8', errors='replace')
        selected = [case for case in cases if _bound_case(case, test, repo, text)
                    and case['outcome'] in ('PASS', 'FAIL')]
        ids = sorted(case['id'] for case in selected)
        if len(ids) != len(set(ids)):
            bad = True
        error_code = 'TDD_RED_REASON_INVALID' if phase == 'red' else 'TDD_TRANSITION_INVALID'
        if bad or not ids:
            return row, ids, False, error_code
        if phase == 'red' and baseline_kind == 'RED_TO_GREEN':
            valid = row['exit_code'] != 0 and any(case['outcome'] == 'FAIL' for case in selected)
        else:
            valid = row['exit_code'] == 0 and all(case['outcome'] == 'PASS' for case in selected)
        return row, ids, valid, error_code


def tdd_check(phase: str, repo: Path, test_file: Path, command: str, design_path: Path,
              out: Path, *, issue_type: Optional[str] = None,
              sensitivity_path: Optional[Path] = None, approval_path: Optional[Path] = None):
    # Validate the command before even a repository-inspection subprocess runs.
    try:
        _argv(command)
    except ValueError:
        _fail('TDD_COMMAND_INVALID')
    repo = repository_root(repo)
    out = _safe(out, repo, exists=False)
    track, _, out = artifact_layout(repo, out)
    test = _safe(test_file if test_file.is_absolute() else repo / test_file, repo)
    if '.harness' in test.relative_to(repo).parts or '.git' in test.relative_to(repo).parts:
        _fail('TDD_PATH_INVALID')
    git_dir = str(Path(_git(repo, 'rev-parse', '--absolute-git-dir').decode().strip()).resolve())
    context = {'cwd': str(repo), 'git_dir': git_dir, 'artifacts': str(out),
               'test_file': test.relative_to(repo).as_posix()}
    baseline_kind = 'PASS_TO_PASS' if track == 'maintenance' and issue_type == 'refactor' else 'RED_TO_GREEN'
    if issue_type == 'refactor' and track != 'maintenance':
        _fail('TDD_BASELINE_INVALID')
    state = _safe(out / 'eval-review/tdd-check', repo, exists=False)
    state.mkdir(parents=True, exist_ok=True)
    lock = state / '.lock'
    try:
        lock.mkdir()
    except FileExistsError:
        _fail('TDD_BASELINE_BUSY')
    try:
        return _check_locked(phase, repo, test, command, design_path, out, track,
                             issue_type, baseline_kind, context, state, sensitivity_path, approval_path)
    finally:
        lock.rmdir()


def _check_locked(phase, repo, test, command, design_path, out, track, issue_type,
                  baseline_kind, context, state, sensitivity_path, approval_path):
    before_hash = _sha(test.read_bytes())
    guard = {}
    receipt = None
    baseline = None
    if (state / 'active.json').exists():
        active, baseline, guard = _load_baseline(state, out, design_path if phase == 'green' else None)
        previous = baseline['observed']
        if any(previous.get(key) != value for key, value in context.items()):
            _fail('TDD_OBSERVATION_INVALID')
        if active.get('issue_type') != issue_type or baseline['baseline'] != baseline_kind:
            _fail('TDD_BASELINE_MISMATCH')
        if phase == 'red' or previous['test_file_sha256'] != before_hash:
            if phase == 'red' and approval_path is None:
                _fail('TDD_BASELINE_IMMUTABLE')
            receipt, approval_guard = _approval(approval_path, baseline, context, before_hash)
            guard.update(approval_guard)
    elif phase == 'green':
        _fail('TDD_OBSERVATION_INVALID')

    if phase == 'red':
        document = _read(design_path)
        if document.get('schema_version') not in ('1.0', '1.1') or document.get('observed') is not None:
            _fail('TDD_SCHEMA_INVALID')
        if validate_schema(document, 'tdd-test-design-result.schema.json') or validate_test_design(document):
            _fail('TDD_SCHEMA_INVALID')
        if document.get('status') != 'PASS':
            _fail('TDD_EVIDENCE_MISSING')
        if document.get('baseline', 'RED_TO_GREEN') != baseline_kind:
            _fail('TDD_BASELINE_INVALID')
        run_id = uuid.uuid4().hex
    else:
        document = _read(sensitivity_path or out / _SENSITIVITY)
        run_id = baseline['observed']['run_id']
        if document.get('test_id') != baseline['test_id'] or document.get('tier') != baseline['tier']:
            _fail('TDD_OBSERVATION_INVALID')
        document = _sensitivity_metadata(document, baseline_kind, baseline)
        # A failed refresh must not leave an earlier successful Green consumable.
        # This run's artifact bytes are deliberately outside the SUT-only view.
        previous_green = out / _SENSITIVITY
        if previous_green.exists():
            blocked = _read(previous_green)
            blocked['status'] = 'BLOCKED'
            _write(previous_green, canonical_json_bytes(blocked), frozen=True)
    source_snapshot = compute_source_snapshot(repo)
    source = source_snapshot['source_snapshot_id']
    row, ids, valid, failure = _observe(command, repo, test, track, phase, baseline_kind)
    after_hash = _sha(test.read_bytes())
    if before_hash != after_hash:
        _fail('TDD_TEST_IDENTITY_CHANGED')
    if any(not path.is_file() or path.read_bytes() != content for path, content in guard.items()):
        _fail('TDD_OBSERVATION_INVALID')
    if compute_source_snapshot(repo)['source_snapshot_id'] != source:
        _fail('TDD_SOURCE_CHANGED')
    log_name = ('hotfix-red-log.txt' if phase == 'red' else 'hotfix-green-log.txt') if (
        issue_type == 'hotfix' or track == 'hotfix') else ('tdd-baseline-log.txt' if phase == 'red' else 'tdd-green-log.txt')
    _write(out / log_name, (row['stdout'] + '\n' + row['stderr']).encode('utf-8'))
    if not valid:
        _fail(failure)
    if phase == 'green' and not set(baseline['observed']['selected_tests']).issubset(ids):
        _fail('TDD_TRANSITION_INVALID')
    observed = dict(context, argv=row['command'], exit_code=row['exit_code'], selected_tests=ids,
                    executed=len(ids), recorded_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                    test_file_sha256=before_hash, run_id=run_id, source_snapshot_id=source,
                    sut_sha256=compute_tdd_sut_sha256(source_snapshot['manifest'], out.relative_to(repo)))
    document = dict(document, schema_version='1.2', baseline=baseline_kind, observed=observed, status='PASS')
    if phase == 'red':
        filename = _DESIGN
        document['stage'] = 'tdd-test-design'
        errors = validate_test_design(document)
    else:
        filename = _SENSITIVITY
        observed['baseline_sha256'] = _sha(canonical_json_bytes(baseline))
        if receipt is not None:
            observed['approval'] = receipt
        document.update(stage='tdd-sensitivity', red_test_hash=baseline['observed']['test_file_sha256'],
                        green_test_hash=before_hash, red_outcome='PASS' if baseline_kind == 'PASS_TO_PASS' else 'FAIL',
                        green_outcome='PASS', approved_red_revision=receipt is not None)
        errors = validate_test_sensitivity(document) + validate_observation_pair(baseline, document)
    if validate_schema(document, filename.replace('.json', '.schema.json')):
        errors.append('TDD_SCHEMA_INVALID')
    if errors:
        raise ContractError(errors)
    content = canonical_json_bytes(document)
    if phase == 'red':
        frozen = state / (run_id + '.json')
        if frozen.exists():
            _fail('TDD_BASELINE_IMMUTABLE')
        _write(frozen, content, frozen=True)
        _write(out / filename, content, frozen=True)
        _write(state / 'active.json', canonical_json_bytes({
            'run_id': run_id, 'baseline_sha256': _sha(content), 'issue_type': issue_type,
        }), frozen=True)
    else:
        _write(out / filename, content, frozen=True)
    return {'status': 'PASS', 'phase': phase, 'run_id': run_id, 'path': str(out / filename),
            'executed': observed['executed'], 'selected_tests': ids}
