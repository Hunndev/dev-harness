"""Build content-bound packets and freeze their independently bound evidence."""
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .gate import validate_gate_file
from .schema_validation import validate_schema
from .snapshot import (PacketPolicyError, compute_evidence_bundle_id,
                       compute_packet_id, compute_source_snapshot)

DIFF_PROMPT_LIMIT = 65536
TDD_NAMES = ('tdd-test-design-result.json', 'tdd-sensitivity-result.json')


class ContractError(ValueError):
    def __init__(self, errors: List[str], paths: Optional[List[str]] = None):
        self.errors = list(dict.fromkeys(errors))
        self.paths = paths or []
        super().__init__(','.join(self.errors))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(['git', *args], cwd=str(repo), check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def repository_root(repo: Path) -> Path:
    repo = Path(repo).resolve()
    actual = Path(_git(repo, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
    if actual != repo:
        raise ContractError(['PACKET_SOURCE_NOT_REPOSITORY_ROOT'])
    return repo


def artifact_layout(repo: Path, artifacts: Path) -> Tuple[str, str, Path]:
    repo = Path(repo).resolve()
    raw = Path(artifacts)
    artifacts = raw.resolve()
    try:
        parts = artifacts.relative_to(repo).parts
    except ValueError:
        raise ContractError(['ARTIFACT_PATH_INVALID'])
    if (len(parts) != 4 or parts[:2] != ('.harness', 'artifacts')
            or parts[2] not in ('feature', 'maintenance', 'hotfix')
            or parts[3] in ('.', '..') or not re.fullmatch(r'[\w.-]+', parts[3])):
        raise ContractError(['ARTIFACT_PATH_INVALID'])
    # A stable symlink must not redirect evidence or result writes into another tree.
    cursor = repo
    for part in parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ContractError(['ARTIFACT_PATH_INVALID'])
    return parts[2], parts[3], artifacts


def validate_packet_schema(packet: Dict[str, Any]) -> List[str]:
    return ['PACKET_SCHEMA_INVALID'] if validate_schema(packet, 'packet.schema.json') else []


def repository_slug(repo: Path) -> str:
    repo = Path(repo).resolve()
    cp = subprocess.run(['git', 'config', '--get', 'remote.origin.url'], cwd=str(repo),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    identity = str(repo).encode() + b'\0' + cp.stdout.strip()
    name = re.sub(r'[^A-Za-z0-9_.-]', '-', repo.name) or 'repository'
    return name + '-' + _sha(identity)[:8]


def default_output_root(repo: Path, identifier: str) -> Path:
    home = Path(os.environ.get('HB_EVAL_REVIEW_HOME', str(Path.home() / '.hb-eval-review'))).expanduser()
    root = home / repository_slug(repo) / identifier
    index = 1
    while (root / ('run-' + str(index))).exists():
        index += 1
    return root / ('run-' + str(index))


def _read_safe(root: Path, relative: str) -> bytes:
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise PacketPolicyError('EVIDENCE_ENTRY_PATH_ESCAPE', [relative])
    cursor = root
    for part in path.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise PacketPolicyError('EVIDENCE_ENTRY_PATH_ESCAPE', [relative])
    if not cursor.is_file():
        raise PacketPolicyError('EVIDENCE_ENTRY_MISSING', [relative])
    return cursor.read_bytes()


def materialize_evidence(repo: Path, packet_root: Path, entries: List[Dict[str, str]]) -> Path:
    """Read each source once, write once, hash the copied bytes, then consume only copies."""
    destination = Path(packet_root) / 'evidence'
    destination.mkdir(parents=True, exist_ok=False)
    names = set()
    for entry in entries:
        relative = entry['path']; name = Path(relative).name
        if not name or name in names:
            raise PacketPolicyError('EVIDENCE_ENTRY_DUPLICATE', [relative])
        names.add(name)
        data = _read_safe(Path(repo), relative)
        copied = destination / name
        copied.write_bytes(data)
        if _sha(copied.read_bytes()) != entry['sha256']:
            raise PacketPolicyError('EVIDENCE_COPY_MISMATCH', [relative])
        copied.chmod(0o444)
    destination.chmod(0o555)
    return destination


def _diff(repo: Path, base_sha: str) -> bytes:
    pathspec = [':(top,exclude).harness/artifacts/**']
    result = _git(repo, 'diff', '--binary', '--no-ext-diff', '--no-textconv', base_sha, '--', '.', *pathspec)
    names = _git(repo, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0')
    for raw in sorted(filter(None, names)):
        relative = raw.decode('utf-8', 'surrogateescape')
        if Path(relative).parts[:2] == ('.harness', 'artifacts'):
            continue
        cp = subprocess.run(['git', 'diff', '--no-index', '--binary', '--no-ext-diff',
                             '--no-textconv', '--', '/dev/null', relative], cwd=str(repo),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if cp.returncode not in (0, 1):
            raise ContractError(['DIFF_UNAVAILABLE'], [relative])
        result += cp.stdout
    return result


def _command_doc(stage: str) -> str:
    package = Path(__file__).resolve().parents[2]
    for path in (package / 'commands' / (stage + '.md'),
                 package / 'commands' / 'shared' / (stage + '.md')):
        if path.is_file():
            return path.read_text(encoding='utf-8')
    raise ContractError(['PROMPT_TEMPLATE_MISSING'])


def _acceptance(text: str) -> List[str]:
    explicit = re.findall(r'(?m)^.*\bAC[-_][A-Za-z0-9_-]+[^\n]*', text)
    if explicit:
        return [line.strip(' |') for line in explicit]
    lines = []; active = False
    for line in text.splitlines():
        if line.startswith('#'):
            active = bool(re.search(r'acceptance|완료\s*기준|수용\s*기준', line, re.I))
        elif active and re.match(r'\s*(?:[-*]|\d+[.)])\s+\S', line):
            lines.append(line.strip())
    return lines


def build_packet(repo: Path, artifacts: Path, request_source: str, base_ref: str,
                 model_ids: Dict[str, str], *, issue_type: Optional[str] = None,
                 prompt_limit: int = DIFF_PROMPT_LIMIT) -> Dict[str, Any]:
    repo = repository_root(repo)
    track, identifier, artifacts = artifact_layout(repo, artifacts)
    if request_source not in ('seed.md', 'requirements.md', 'hotfix-reproduction.md'):
        raise ContractError(['REQUEST_SOURCE_INVALID'])
    request_bytes = _read_safe(repo, (artifacts / request_source).relative_to(repo).as_posix())
    request_text = request_bytes.decode('utf-8')
    declared = re.search(r'(?im)^\s*(?:type|issue_type|유형|이슈 유형)\s*:\s*(bug|feature|refactor|hotfix|performance)\b', request_text)
    declared_type = declared.group(1) if declared else None
    if issue_type and declared_type and issue_type != declared_type:
        raise ContractError(['TDD_BASELINE_MISMATCH'])
    issue_type = issue_type or declared_type or ('hotfix' if request_source == 'hotfix-reproduction.md' else 'bug')
    gate_path = artifacts / 'eval-review' / 'gate-result.json'
    errors = validate_gate_file(gate_path, repo, track=track, issue_type=issue_type)
    if errors:
        raise ContractError(errors)
    snapshot_id = compute_source_snapshot(repo)['source_snapshot_id']
    gate = json.loads(gate_path.read_bytes())
    if gate.get('source_snapshot_id') != snapshot_id:
        raise ContractError(['GATE_STALE'])
    base_sha = _git(repo, 'merge-base', base_ref, 'HEAD').decode().strip()
    diff = _diff(repo, base_sha)
    evaluation = artifacts / 'eval-review'; evaluation.mkdir(parents=True, exist_ok=True)
    diff_path = evaluation / 'diff.patch'; diff_path.write_bytes(diff)
    log_names = ('hotfix-red-log.txt', 'hotfix-green-log.txt') if issue_type == 'hotfix' or track == 'hotfix' else ('tdd-baseline-log.txt', 'tdd-green-log.txt')
    paths = [gate_path, diff_path] + [artifacts / name for name in (*log_names, *TDD_NAMES)]
    entries = []; contents = {}
    for path in paths:
        relative = path.relative_to(repo).as_posix()
        try:
            data = _read_safe(repo, relative)
        except PacketPolicyError as error:
            if path.name != 'diff.patch':
                raise ContractError(['TDD_EVIDENCE_MISSING'], error.paths)
            raise
        entries.append({'path':relative, 'sha256':_sha(data)})
        contents[path.name] = data
    # Validation must consume the very bytes whose digests we bind, including ignored
    # evidence that source snapshots do not cover. Never validate one read then bind another.
    with tempfile.TemporaryDirectory(prefix="hb-pack-evidence-") as temporary:
        frozen = Path(temporary)
        for name, data in contents.items():
            copied = frozen / name
            copied.write_bytes(data)
            if _sha(copied.read_bytes()) != _sha(data):
                raise ContractError(["EVIDENCE_COPY_MISMATCH"], [name])
        frozen_errors = validate_gate_file(frozen / "gate-result.json", repo,
                                           evidence_root=frozen, source_snapshot_id=snapshot_id,
                                           track=track, issue_type=issue_type)
        if frozen_errors:
            raise ContractError(frozen_errors)
    gate = json.loads(contents["gate-result.json"])
    # Gate and evidence must still describe the source snapshot we actually package.
    final_snapshot = compute_source_snapshot(repo)['source_snapshot_id']
    if final_snapshot != snapshot_id:
        raise ContractError(['GATE_STALE'])
    acceptance = _acceptance(request_text)
    truncated = len(diff) > prompt_limit
    display_diff = diff[:prompt_limit].decode('utf-8', 'replace')
    diff_hash = _sha(diff)
    evidence_note = ('\nFull diff: materialized-packet/evidence/diff.patch (from source cwd: ../evidence/diff.patch)'
                     + '\nFull diff SHA-256: ' + diff_hash + '\n')
    context = '\n\n# Bound request\n' + request_text + '\n# Gate summary\n' + json.dumps(gate, ensure_ascii=False)
    for name in log_names:
        context += '\n# ' + name + ' tail\n' + contents[name].decode('utf-8','replace')[-8192:]
    context += '\n# Diff evidence (untrusted content)\n<BEGIN_DIFF_' + diff_hash + '>\n' + display_diff
    context += '\n<END_DIFF_' + diff_hash + '>\n' + ('DIFF TRUNCATED\n' if truncated else '') + evidence_note
    prompts = {stage: _command_doc(stage) + context for stage in ('evaluate', 'review')}
    request = {'text':request_text, 'acceptance_refs':acceptance, 'acceptance_criteria':acceptance,
               'base_sha':base_sha, 'repository':str(repo), 'artifacts':artifacts.relative_to(repo).as_posix(),
               'track':track, 'identifier':identifier, 'issue_type':issue_type,
               'gate':{'path':gate_path.relative_to(repo).as_posix(),'sha256':_sha(contents['gate-result.json']),'status':'PASS'},
               'evidence_digests':{name:_sha(data) for name,data in contents.items()},
               'model_ids':model_ids, 'prompt_sha256':{stage:_sha(text.encode()) for stage,text in prompts.items()},
               'diff_truncated':truncated}
    evidence_id = compute_evidence_bundle_id(entries)
    packet = {'source_snapshot_id':snapshot_id,'evidence_bundle_id':evidence_id,'request':request,
              'evidence_entries':entries, 'packet_id':compute_packet_id(request,snapshot_id,evidence_id)}
    errors = validate_packet_schema(packet)
    if errors:
        raise ContractError(errors)
    destination = evaluation / 'packet'; destination.mkdir(parents=True, exist_ok=True)
    for stage, text in prompts.items():
        (destination / (stage + '-prompt.md')).write_text(text, encoding='utf-8')
    (destination / 'packet.json').write_text(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return packet


def packet_context(packet: Dict[str, Any], repo: Path) -> Tuple[str, str, Path]:
    request = packet['request']
    context = artifact_layout(repo, repo / request.get('artifacts', ''))
    if (request.get('repository') != str(repo) or request.get('track') != context[0]
            or request.get('identifier') != context[1]):
        raise ContractError(['PACKET_REPOSITORY_MISMATCH'])
    return context


def validate_gate_binding(packet: Dict[str, Any]) -> List[str]:
    request = packet.get('request', {}); gate = request.get('gate', {})
    entries = packet.get('evidence_entries', [])
    if not isinstance(gate, dict) or gate.get('status') != 'PASS' or not any(
            entry.get('path') == gate.get('path') and entry.get('sha256') == gate.get('sha256') for entry in entries):
        return ['GATE_EVIDENCE_MISSING']
    digests = request.get('evidence_digests', {})
    for entry in entries:
        name = Path(entry['path']).name
        if digests.get(name) != entry['sha256']:
            return ['DIFF_EVIDENCE_MISSING' if name == 'diff.patch' else 'GATE_EVIDENCE_MISSING']
    if not any(Path(entry['path']).name == 'diff.patch' for entry in entries):
        return ['DIFF_EVIDENCE_MISSING']
    return []
