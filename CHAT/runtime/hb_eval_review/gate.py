"""Execute deterministic checks and validate their actual, source-bound evidence."""

import hashlib
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .process import minimal_environment
from .redaction import redact_json, redact_text
from .schema_validation import validate_schema
from .snapshot import PacketPolicyError, compute_source_snapshot
from .tdd_quality import effective_baseline, validate_test_design, validate_test_sensitivity

_TDD_NAMES = ('tdd-test-design-result.json', 'tdd-sensitivity-result.json')
_TRACKS = {'feature', 'maintenance', 'hotfix'}
_TAIL_LIMIT = 65536
# These are test/build configuration, rather than provider authentication. Feature,
# maintenance and hotfix can each target any of the six supported language stacks.
_TEST_ENV = (
    'DJANGO_SETTINGS_MODULE', 'PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV',
    'JAVA_HOME', 'ANDROID_HOME', 'ANDROID_SDK_ROOT', 'GRADLE_USER_HOME',
    'DEVELOPER_DIR', 'SDKROOT', 'NODE_ENV', 'CI', 'TZ',
)


def _argv(command: str) -> List[str]:
    if not isinstance(command, str) or '\n' in command or '\r' in command:
        raise ValueError('GATE_COMMAND_INVALID')
    lexer = shlex.shlex(command, posix=True, punctuation_chars='|&;<>()')
    lexer.whitespace_split = True
    lexer.commenters = ''
    try:
        argv = list(lexer)
    except ValueError as error:
        raise ValueError('GATE_COMMAND_INVALID') from error
    if not argv or any(token and all(char in '|&;<>()' for char in token) for token in argv):
        raise ValueError('GATE_COMMAND_INVALID')
    if any('`' in token for token in argv):
        raise ValueError('GATE_COMMAND_INVALID')
    return argv


def gate_environment(source: Optional[Mapping[str, str]] = None, *, track: str) -> Dict[str, str]:
    """Permit test configuration for the three supported development tracks."""
    if track not in _TRACKS:
        raise ValueError('GATE_TRACK_INVALID')
    source = os.environ if source is None else source
    keys = minimal_environment(source, extra_keys=list(_TEST_ENV))
    return keys


def run_gate_command(command: str, repo: Path, *, track: str,
                     timeout_seconds: float = 600.0) -> Dict[str, Any]:
    """Run one argv without a shell; hash the complete redacted stdout before tailing."""
    argv = _argv(command)
    started = time.monotonic()
    try:
        process = subprocess.run(argv, cwd=str(repo), env=gate_environment(track=track),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=timeout_seconds, check=False)
        stdout, stderr, exit_code = process.stdout, process.stderr, process.returncode
    except subprocess.TimeoutExpired as error:
        stdout, stderr, exit_code = error.stdout or b'', error.stderr or b'', 124
        stderr += b'\nGate command timed out.'
    except OSError as error:
        stdout, stderr, exit_code = b'', str(error).encode('utf-8', 'replace'), 127
    clean_stdout = redact_text(stdout.decode('utf-8', 'replace'))
    clean_stderr = redact_text(stderr.decode('utf-8', 'replace'))
    return redact_json({
        'name': Path(argv[0]).name, 'command': argv, 'exit_code': exit_code,
        'duration_ms': max(0, int((time.monotonic() - started) * 1000)),
        'stdout_tail': clean_stdout[-_TAIL_LIMIT:], 'stderr_tail': clean_stderr[-_TAIL_LIMIT:],
        'stdout_sha256': hashlib.sha256(clean_stdout.encode('utf-8')).hexdigest(),
    })


def _safe_relative_file(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if '..' in relative.parts:
        return False
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return False
    return path.is_file()


def _artifacts_from_gate(path: Path, repo: Path) -> Optional[Path]:
    try:
        parts = path.relative_to(repo).parts
    except ValueError:
        return None
    if (len(parts) != 6 or parts[:2] != ('.harness', 'artifacts')
            or parts[2] not in _TRACKS or not parts[3] or parts[3] in ('.', '..')
            or parts[4:] != ('eval-review', 'gate-result.json')):
        return None
    return repo.joinpath(*parts[:4])


def _load_json(path: Path) -> Any:
    # Duplicate keys otherwise let a consumer and a producer disagree on one status.
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('duplicate JSON key')
            value[key] = item
        return value
    return json.loads(path.read_bytes().decode('utf-8'), object_pairs_hook=unique)


def _tdd_errors(refs: Any, repo: Path, *, track: Optional[str], issue_type: Optional[str],
                evidence_root: Optional[Path] = None, artifacts: Optional[Path] = None) -> List[str]:
    errors: List[str] = []
    documents = []
    if not isinstance(refs, list) or len(refs) != 2:
        return ['TDD_EVIDENCE_MISSING']
    expected = []
    for name in _TDD_NAMES:
        matches = [value for value in refs if isinstance(value, str) and Path(value).name == name]
        if len(matches) != 1:
            return ['TDD_EVIDENCE_MISSING']
        relative = Path(matches[0])
        parts = relative.parts
        if (relative.is_absolute() or '..' in parts or len(parts) != 5
                or parts[:2] != ('.harness', 'artifacts') or parts[2] != track
                or parts[2] not in _TRACKS):
            return ['TDD_EVIDENCE_MISSING']
        expected.append(relative)
    if expected[0].parent != expected[1].parent:
        return ['TDD_EVIDENCE_MISSING']
    if artifacts is not None and expected[0].parent != artifacts.relative_to(repo):
        return ['TDD_EVIDENCE_MISSING']
    for relative in expected:
        root = evidence_root if evidence_root is not None else repo
        path = root / relative.name if evidence_root is not None else root / relative
        if not _safe_relative_file(path, root):
            return ['TDD_EVIDENCE_MISSING']
        try:
            document = _load_json(path)
        except (OSError, UnicodeError, ValueError):
            return ['TDD_EVIDENCE_MISSING']
        if not isinstance(document, dict) or document.get('status') != 'PASS':
            return ['TDD_EVIDENCE_MISSING']
        documents.append(document)
    baselines = [effective_baseline(document) for document in documents]
    if None in baselines:
        errors.append('TDD_BASELINE_INVALID')
    elif baselines[0] != baselines[1]:
        errors.append('TDD_BASELINE_MISMATCH')
    if 'PASS_TO_PASS' in baselines and (track != 'maintenance' or issue_type != 'refactor'):
        errors.append('TDD_BASELINE_INVALID')
    for document, name, validator in zip(documents, _TDD_NAMES,
                                         (validate_test_design, validate_test_sensitivity)):
        if validate_schema(document, name.replace('.json', '.schema.json')):
            errors.append('TDD_SCHEMA_INVALID')
        try:
            # Preserve meaningful TDD codes even when the same enum/const value is
            # rejected by its schema. Shape errors remain schema failures, not crashes.
            errors.extend(validator(document))
        except (AttributeError, TypeError):
            errors.append('TDD_SCHEMA_INVALID')
    return list(dict.fromkeys(errors))


def validate_gate_file(path: Path, repo: Path, *, evidence_root: Optional[Path] = None,
                       source_snapshot_id: Optional[str] = None,
                       track: Optional[str] = None, issue_type: Optional[str] = None) -> List[str]:
    """Read real Gate/TDD bytes, using frozen evidence exclusively when supplied.

    A caller supplying the original source ID has already performed source-copy
    validation. It must not cause this consumer to hash the live tree again.
    """
    repo = Path(repo).absolute()
    path = Path(path).absolute()
    root = Path(evidence_root).absolute() if evidence_root is not None else repo
    artifacts = _artifacts_from_gate(path, repo) if evidence_root is None else None
    if not _safe_relative_file(path, root) or (evidence_root is None and artifacts is None):
        return ['GATE_EVIDENCE_MISSING']
    if evidence_root is not None and path != root / 'gate-result.json':
        return ['GATE_EVIDENCE_MISSING']
    if artifacts is not None:
        actual_track = artifacts.parts[-2]
        if track is not None and track != actual_track:
            return ['GATE_TRACK_INVALID']
        track = actual_track
    try:
        data = _load_json(path)
    except (OSError, UnicodeError, ValueError):
        return ['GATE_SCHEMA_INVALID']
    if not isinstance(data, dict):
        return ['GATE_SCHEMA_INVALID']
    errors = ['GATE_SCHEMA_INVALID'] if validate_schema(data, 'gate-result.schema.json') else []
    commands = data.get('commands')
    if (data.get('status') != 'PASS' or not isinstance(commands, list) or not commands
            or any(not isinstance(item, dict) or type(item.get('exit_code')) is not int
                   or item['exit_code'] != 0 for item in commands)):
        errors.append('GATE_NOT_PASSED')
    if source_snapshot_id is None:
        try:
            source_snapshot_id = compute_source_snapshot(repo)['source_snapshot_id']
        except PacketPolicyError as error:
            errors.append(error.code)
        except (OSError, subprocess.CalledProcessError, ValueError):
            errors.append('SOURCE_SNAPSHOT_UNAVAILABLE')
    if data.get('source_snapshot_id') != source_snapshot_id:
        errors.append('GATE_STALE')
    errors.extend(_tdd_errors(data.get('tdd_evidence'), repo, track=track,
                             issue_type=issue_type, evidence_root=root if evidence_root is not None else None,
                             artifacts=artifacts))
    return list(dict.fromkeys(errors))


def generate_gate(repo: Path, commands: Sequence[str], out: Path, *,
                  issue_type: Optional[str] = None) -> Dict[str, Any]:
    """Execute all checks and write a source-bound Gate in the excluded output path."""
    repo = Path(repo).absolute()
    out = Path(out).absolute()
    artifacts = _artifacts_from_gate(out, repo)
    if artifacts is None:
        raise ValueError('GATE_PATH_INVALID')
    cursor = repo
    for part in out.relative_to(repo).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError('GATE_PATH_INVALID')
    track = artifacts.parts[-2]
    before = compute_source_snapshot(repo)['source_snapshot_id']
    refs = [(artifacts / name).relative_to(repo).as_posix() for name in _TDD_NAMES]
    errors: List[str] = []
    rows: List[Dict[str, Any]] = []
    try:
        if not commands or isinstance(commands, str):
            raise ValueError('GATE_COMMAND_INVALID')
        for command in commands:
            _argv(command)
    except ValueError:
        errors.append('GATE_COMMAND_INVALID')
    if not errors:
        rows = [run_gate_command(command, repo, track=track) for command in commands]
        if any(row['exit_code'] != 0 for row in rows):
            errors.append('GATE_NOT_PASSED')
    try:
        after = compute_source_snapshot(repo)['source_snapshot_id']
        if after != before:
            errors.append('GATE_SOURCE_CHANGED')
    except PacketPolicyError as error:
        errors.append(error.code)
    except (OSError, subprocess.CalledProcessError, ValueError):
        errors.append('SOURCE_SNAPSHOT_UNAVAILABLE')
    errors.extend(_tdd_errors(refs, repo, track=track, issue_type=issue_type, artifacts=artifacts))
    result = {
        'schema_version': '1.1', 'stage': 'gate', 'status': 'BLOCKED' if errors else 'PASS',
        'source_snapshot_id': before, 'commands': rows, 'tdd_evidence': refs,
    }
    if errors:
        result['errors'] = list(dict.fromkeys(errors))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    return result
