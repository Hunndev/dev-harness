"""Build content-bound packets and freeze their independently bound evidence."""
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .frozen_diff import build_frozen_diff
from .gate import validate_gate_file
from .schema_validation import validate_schema
from .snapshot import (PacketPolicyError, compute_evidence_bundle_id,
                       compute_packet_id, compute_source_snapshot, _is_secret_material)

DIFF_PROMPT_LIMIT = 65536
TDD_NAMES = ('tdd-test-design-result.json', 'tdd-sensitivity-result.json')


class ContractError(ValueError):
    def __init__(self, errors: List[str], paths: Optional[List[str]] = None,
                 variables: Optional[List[str]] = None):
        self.errors = list(dict.fromkeys(errors))
        self.paths = paths or []
        self.variables = variables or []
        super().__init__(','.join(self.errors))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(['git', *args], cwd=str(repo), check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def reject_git_redirect_environment() -> None:
    """Fail closed on exported repository/index/object redirection without changing env."""
    keys = ("GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
            "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")
    present = sorted(key for key in keys if key in os.environ)
    if present:
        raise ContractError(["GIT_REDIRECT_ENV_UNSUPPORTED"], variables=present)


def repository_root(repo: Path) -> Path:
    reject_git_redirect_environment()
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
    if _is_secret_material(path):
        raise PacketPolicyError('PACKET_SECRET_MATERIAL_PRESENT', [relative])
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


def _diff(repo: Path, base_sha: str, snapshot: Optional[Dict[str, Any]] = None) -> bytes:
    return build_frozen_diff(repo, base_sha, snapshot or compute_source_snapshot(repo))


def _command_doc(stage: str) -> str:
    package = Path(__file__).resolve().parents[2]
    for path in (package / 'commands' / (stage + '.md'),
                 package / 'commands' / 'shared' / (stage + '.md')):
        if path.is_file():
            return path.read_text(encoding='utf-8')
    raise ContractError(['PROMPT_TEMPLATE_MISSING'])


def _acceptance_lines(text: str) -> List[str]:
    """Hide comments/fences while retaining line boundaries for table headers."""
    visible: List[str] = []
    in_comment = False
    fence_character: Optional[str] = None
    fence_size = 0
    fence_container = 0
    list_indents: List[int] = []
    for raw_line in text.splitlines():
        expanded = raw_line.expandtabs(4)
        indent = len(expanded) - len(expanded.lstrip(' '))
        if fence_character is not None:
            # An unclosed list fence ends when its containing item ends.
            if expanded.strip() and indent < fence_container:
                fence_character = None
            else:
                relative = expanded[fence_container:]
                if re.fullmatch(r" {0,3}" + re.escape(fence_character)
                                + "{" + str(fence_size) + r",}[ \t]*", relative):
                    fence_character = None
                visible.append('')
                continue
        # Comments in literal fenced content never affect subsequent Markdown.
        line = raw_line
        uncommented = ''
        while line:
            if in_comment:
                end = line.find('-->')
                if end < 0:
                    line = ''
                else:
                    line = line[end + 3:]
                    in_comment = False
            else:
                start = line.find('<!--')
                if start < 0:
                    uncommented += line
                    break
                uncommented += line[:start]
                line = line[start + 4:]
                in_comment = True
        line = uncommented
        expanded = line.expandtabs(4)
        indent = len(expanded) - len(expanded.lstrip(' '))
        if expanded.strip():
            while list_indents and indent < list_indents[-1]:
                list_indents.pop()
        container = list_indents[-1] if list_indents else 0
        relative = expanded[container:]
        # CommonMark fence indentation is measured after list container prefixes.
        marker = re.match(r" {0,3}(?:[-*+]|\d{1,9}[.)])( +)", relative)
        while marker:
            padding = len(marker.group(1))
            width = marker.end() if padding <= 4 else marker.end() - padding + 1
            container += width
            list_indents.append(container)
            relative = expanded[container:]
            marker = re.match(r" {0,3}(?:[-*+]|\d{1,9}[.)])( +)", relative)
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", relative)
        if fence and (fence.group(1)[0] != '`' or '`' not in fence.group(2)):
            fence_character, fence_size = fence.group(1)[0], len(fence.group(1))
            fence_container = container
            visible.append('')
        else:
            visible.append(line)
    return visible


def _acceptance(text: str) -> List[str]:
    """Collect actual list/table criteria, excluding examples and empty seed rows."""
    result: List[str] = []
    heading_level: Optional[int] = None
    table = False
    list_prefix = r"\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?"
    identifier = r"AC[-_][A-Za-z0-9_-]+(?=\s|[:：.)|-]|$)"
    lines = _acceptance_lines(text)
    separators = set()
    for index, line in enumerate(lines):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) > 1 and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            separators.add(index)
    for index, line in enumerate(lines):
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.+)", line)
        if heading:
            table = False
            level = len(heading.group(1))
            if re.search(r"acceptance|완료\s*기준|수용\s*기준", heading.group(2), re.I):
                heading_level = level
            elif heading_level is not None and level <= heading_level:
                heading_level = None
            continue
        # Delay classifying a possible header until its following separator is known.
        if "|" in line and index + 1 in separators:
            table = True
            continue
        if table and index in separators:
            continue
        if not line.strip() or "|" not in line:
            table = False
        list_item = re.match(r"^" + list_prefix + identifier, line, re.I)
        explicit = (list_item
                    or re.match(r"^\s*\|\s*" + identifier, line, re.I)
                    or (table and re.match(r"^\s*" + identifier, line, re.I)))
        heading_item = heading_level is not None and re.match(r"^" + list_prefix + r"\S", line)
        if explicit or heading_item:
            if explicit:
                wording = line[explicit.end():].strip()
                # The criterion can share the ID cell or occupy the next cell;
                # evidence/lens columns cannot fill an empty criterion placeholder.
                if wording.startswith('|'):
                    wording = wording[1:].lstrip()
                wording = re.sub(r"^(?:[:：)]\s*|[.-]\s+)", '', wording)
                criterion_wording = wording if list_item else wording.split('|', 1)[0]
                if criterion_wording.strip() == '...':
                    continue
            criterion = line.strip().strip("|").strip()
            if criterion not in result:
                result.append(criterion)
    return result


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
    declared_type = declared.group(1).lower() if declared else None
    if issue_type and declared_type and issue_type != declared_type:
        raise ContractError(['ISSUE_TYPE_CONFLICT'])
    issue_type = issue_type or declared_type or ('hotfix' if request_source == 'hotfix-reproduction.md' else 'bug')
    gate_path = artifacts / 'eval-review' / 'gate-result.json'
    errors = validate_gate_file(gate_path, repo, track=track, issue_type=issue_type)
    if errors:
        raise ContractError(errors)
    snapshot = compute_source_snapshot(repo)
    snapshot_id = snapshot['source_snapshot_id']
    gate = json.loads(gate_path.read_bytes())
    if gate.get('source_snapshot_id') != snapshot_id:
        raise ContractError(['GATE_STALE'])
    base_sha = _git(repo, 'merge-base', base_ref, 'HEAD').decode().strip()
    diff = _diff(repo, base_sha, snapshot)
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
                                           track=track, issue_type=issue_type, artifacts=artifacts)
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
    errors = validate_packet_schema(packet) or validate_gate_binding(packet)
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
    """Validate the complete catalog before any untrusted evidence path is read.

    Digests bind bytes, not purpose: a caller can recompute all public hashes. The
    required six paths therefore come from the packet's one artifact identity,
    never from whichever entries the caller happened to supply.
    """
    request = packet.get("request", {})
    entries = packet.get("evidence_entries", [])
    if not isinstance(request, dict) or not isinstance(entries, list):
        return ["PACKET_SCHEMA_INVALID"]
    artifact_name = request.get("artifacts")
    if not isinstance(artifact_name, str):
        return ["ARTIFACT_EVIDENCE_MISMATCH"]
    artifact = Path(artifact_name)
    parts = artifact.parts
    if (artifact.is_absolute() or len(parts) != 4 or parts[:2] != (".harness", "artifacts")
            or parts[2] not in ("feature", "maintenance", "hotfix")
            or parts[2] != request.get("track") or parts[3] != request.get("identifier")
            or artifact.as_posix() != artifact_name or ".." in parts):
        return ["ARTIFACT_EVIDENCE_MISMATCH"]
    kind = request.get("issue_type")
    if kind not in ("feature", "bug", "refactor", "hotfix", "performance"):
        return ["ARTIFACT_EVIDENCE_MISMATCH"]
    logs = ("hotfix-red-log.txt", "hotfix-green-log.txt") if kind == "hotfix" or parts[2] == "hotfix" else ("tdd-baseline-log.txt", "tdd-green-log.txt")
    expected = {name: (artifact / name).as_posix() for name in (*logs, *TDD_NAMES)}
    expected.update({name: (artifact / "eval-review" / name).as_posix()
                     for name in ("gate-result.json", "diff.patch")})
    if any(_is_secret_material(Path(path)) for path in expected.values()):
        return ["PACKET_SECRET_MATERIAL_PRESENT"]
    paths = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            return ["PACKET_SCHEMA_INVALID"]
        name = Path(entry["path"]).name
        if name not in expected:
            return ["EVIDENCE_ENTRY_UNEXPECTED"]
        if entry["path"] != expected[name]:
            return ["ARTIFACT_EVIDENCE_MISMATCH"]
        paths.append(entry["path"])
    if len(paths) != len(set(paths)):
        return ["EVIDENCE_ENTRY_DUPLICATE"]
    missing = set(expected.values()) - set(paths)
    if missing:
        if expected["gate-result.json"] in missing:
            return ["GATE_EVIDENCE_MISSING"]
        if expected["diff.patch"] in missing:
            return ["DIFF_EVIDENCE_MISSING"]
        return ["TDD_EVIDENCE_MISSING"]
    digests = request.get("evidence_digests")
    if not isinstance(digests, dict) or set(digests) != set(expected):
        return ["EVIDENCE_DIGESTS_INVALID"]
    gate = request.get("gate")
    if (not isinstance(gate, dict) or gate.get("status") != "PASS"
            or gate.get("path") != expected["gate-result.json"]):
        return ["GATE_EVIDENCE_MISSING"]
    for entry in entries:
        name = Path(entry["path"]).name
        if digests[name] != entry.get("sha256"):
            return ["DIFF_EVIDENCE_MISSING" if name == "diff.patch" else "GATE_EVIDENCE_MISSING"]
        if name == "gate-result.json" and gate.get("sha256") != entry.get("sha256"):
            return ["GATE_EVIDENCE_MISSING"]
    return []
