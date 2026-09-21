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


def _acceptance_block_start(relative: str) -> bool:
    """Recognize supported block starts after matching list containers."""
    if re.match(r" {0,3}(?:[-*+] +|\d{1,9}[.)] +|#{1,6} +|<!--)", relative):
        return True
    fence = re.match(r" {0,3}(`{3,}|~{3,})(.*)$", relative)
    return bool(fence and (fence.group(1)[0] != '`' or '`' not in fence.group(2)))


def _acceptance_table_separator(line: str) -> bool:
    """Use the extractor's existing two-or-more-cell separator grammar."""
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return len(cells) > 1 and all(re.fullmatch(r":?-+:?", cell) for cell in cells)


def _acceptance_table_cells(line: str) -> List[str]:
    """Split GFM cells, retaining empties; unescaped code-span pipes split too."""
    # GFM table scanning consumes backslash-pipe even after another backslash;
    # it does not apply the generic inline parser's odd/even escape parity.
    cells = re.split(r'(?<!\\)\|', line.strip(' \t'))
    # Only one optional border pipe is allowed on either side. Repeated pipes
    # represent empty cells, and an escaped trailing pipe remains cell content.
    if cells and not cells[0]:
        cells.pop(0)
    if cells and not cells[-1]:
        cells.pop()
    return [cell.strip(' \t') for cell in cells]


def _acceptance_table_start(relative: str, separator: str, container: int) -> bool:
    """Match both rows at zero to three columns within the same container."""
    indent = len(relative) - len(relative.lstrip(' '))
    if indent > 3 or '|' not in relative:
        return False
    expanded = separator.expandtabs(4)
    separator_indent = len(expanded) - len(expanded.lstrip(' '))
    # A delimiter dedented out of this container is not a table boundary.
    if not container <= separator_indent <= container + 3:
        return False
    # This stricter block-boundary grammar does not replace the extractor's
    # existing separator grammar for criteria outside comments.
    cells = _acceptance_table_cells(expanded[container:])
    return (len(cells) > 1 and all(re.fullmatch(r":?-+:?", cell) for cell in cells)
            and len(_acceptance_table_cells(relative)) == len(cells))


def _acceptance_html_boundary(relative: str) -> bool:
    """CommonMark 0.31.2 HTML types 1, 3, 4, 5 and 6 interrupt paragraphs."""
    # Type 7 (arbitrary tags, e.g. img/br/span/custom elements) cannot interrupt
    # a paragraph. Keep the type-1 and type-6 token endings distinct.
    block_tags = (r'address|article|aside|base|basefont|blockquote|body|caption|center|'
                  r'col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|'
                  r'figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|'
                  r'iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|'
                  r'option|p|param|search|section|summary|table|tbody|td|tfoot|th|'
                  r'thead|title|tr|track|ul')
    return bool(re.match(r' {0,3}(?:<\?|<![A-Za-z]|<!\[CDATA\[)', relative)
                or re.match(r' {0,3}<(?:pre|script|style|textarea)(?=[ \t>]|$)', relative, re.I | re.ASCII)
                or re.match(r' {0,3}</?(?:' + block_tags + r')(?=[ \t>]|/>|$)', relative, re.I | re.ASCII))


def _continuation_comment_end(lines: List[str], start: int,
                              list_indents: List[int]) -> Tuple[Optional[int], int]:
    """Return a paired closer, or the exclusive boundary of a failed scan."""
    if '-->' in lines[start]:
        return start, start
    for index in range(start + 1, len(lines)):
        expanded = lines[index].expandtabs(4)
        if not expanded.strip():
            return None, index
        indent = len(expanded) - len(expanded.lstrip(' '))
        container = next((level for level in reversed(list_indents) if level <= indent), 0)
        relative = expanded[container:]
        if (_acceptance_block_start(relative)
                or re.match(r' {0,3}(?:>|#{1,6} *$)', relative)
                or re.fullmatch(r' {0,3}(?:(?:\* *){3,}|(?:- *){3,}|(?:_ *){3,})', relative)
                or re.fullmatch(r' {0,3}(?:=+|-+) *', relative)
                or _acceptance_html_boundary(relative)
                or (index + 1 < len(lines)
                    and _acceptance_table_start(relative, lines[index + 1], container))):
            return None, index
        if '-->' in expanded:
            return index, index
    return None, len(lines)


def _without_inline_comments(wording: str) -> str:
    """Ignore closed comments for placeholder comparison, keeping code spans literal."""
    visible: List[str] = []
    cursor = 0
    while cursor < len(wording):
        if wording[cursor] == '\\':
            visible.append(wording[cursor:cursor + 2])
            cursor += 2
            continue
        if wording[cursor] == '`':
            opening = re.match(r'`+', wording[cursor:]).group()
            end = cursor + len(opening)
            for closing in re.finditer(r'`+', wording[end:]):
                if closing.group() == opening:
                    end += closing.end()
                    break
            visible.append(wording[cursor:end])
            cursor = end
            continue
        if wording.startswith('<!--', cursor):
            # Empty <!--> and <!---> comments have an overlapping closer.
            end = wording.find('-->', cursor)
            if end >= 0:
                cursor = end + 3
                continue
        visible.append(wording[cursor])
        cursor += 1
    return ''.join(visible)


def _acceptance_lines(text: str) -> List[str]:
    """Hide block examples, preserving line boundaries and literal inline text.

    This is a criterion extractor, not a complete Markdown renderer. In particular,
    plain indented criterion lists following prose without a blank remain supported.
    Such paragraphs may contain paired indented example fences or inline comments;
    their closing markers end only those spans, not subsequent compatible criteria.
    """
    visible: List[str] = []
    in_comment = False
    fence_character: Optional[str] = None
    fence_size = 0
    fence_container = 0
    list_indents: List[int] = []
    indented_text: Optional[int] = None
    table_comment_code = False
    indented_fence_marker: Optional[Tuple[str, int, int]] = None
    continuation_comment_end: Optional[int] = None
    failed_comment_scan: Optional[Tuple[Tuple[int, ...], int]] = None
    table_context: Optional[Tuple[int, ...]] = None
    previous_blank = True
    lines = text.splitlines()
    for index, raw_line in enumerate(lines):
        previous_table_context = table_context
        table_context = None
        expanded = raw_line.expandtabs(4)
        indent = len(expanded) - len(expanded.lstrip(' '))
        blank = not expanded.strip()
        if continuation_comment_end is not None and index <= continuation_comment_end:
            visible.append('')
            previous_blank = blank
            continue
        continuation_comment_end = None
        if fence_character is not None:
            # An unclosed list fence ends when its containing item ends.
            if not blank and indent < fence_container:
                fence_character = None
            else:
                relative = expanded[fence_container:]
                if re.fullmatch(r" {0,3}" + re.escape(fence_character)
                                + "{" + str(fence_size) + r",}[ \t]*", relative):
                    fence_character = None
                visible.append('')
                previous_blank = blank
                continue
        if in_comment:
            # Type-2 HTML blocks include their complete closing line.
            in_comment = '-->' not in expanded
            visible.append('')
            previous_blank = blank
            continue
        if indented_text is not None:
            if blank or indent >= indented_text:
                # Only no-blank compatibility examples have a closing fence.
                # A delimiter inside blank-start indented code remains code.
                if blank:
                    indented_fence_marker = None
                if indented_fence_marker is not None:
                    character, size, opening_indent = indented_fence_marker
                    # Compatibility delimiters may be at most three columns
                    # deeper than their opener; deeper delimiter text is example.
                    if (indent <= opening_indent + 3
                            and re.fullmatch(r' *' + re.escape(character) + '{' + str(size)
                                             + r',} *', expanded[indented_text:])):
                        indented_text = None
                        indented_fence_marker = None
                if table_comment_code and '-->' in expanded:
                    indented_text = None
                    table_comment_code = False
                visible.append('')
                previous_blank = blank
                continue
            indented_text = None
            table_comment_code = False
            indented_fence_marker = None
        if blank:
            visible.append('')
            previous_blank = True
            continue
        # A lazy paragraph continuation does not end the enclosing list item.
        # Explicit block/list starts, or a blank separator, do end dedented items.
        outer_container = next((level for level in reversed(list_indents) if level <= indent), 0)
        block_start = _acceptance_block_start(expanded[outer_container:])
        if list_indents and indent < list_indents[-1] and not previous_blank and not block_start:
            visible.append(raw_line)
            continue
        while list_indents and indent < list_indents[-1]:
            list_indents.pop()
        container = list_indents[-1] if list_indents else 0
        relative = expanded[container:]
        # Fence/comment indentation is relative to every enclosing list marker.
        marker = re.match(r" {0,3}(?:[-*+]|\d{1,9}[.)])( +)", relative)
        while marker:
            padding = len(marker.group(1))
            width = marker.end() if padding <= 4 else marker.end() - padding + 1
            container += width
            list_indents.append(container)
            relative = expanded[container:]
            marker = re.match(r" {0,3}(?:[-*+]|\d{1,9}[.)])( +)", relative)
        context = tuple(list_indents)
        after_table = previous_table_context is not None and previous_table_context == context
        table_row = not (_acceptance_block_start(relative)
                         or re.match(r' {0,3}>', relative)
                         or _acceptance_html_boundary(relative))
        if (table_row and index + 1 < len(lines)
                and _acceptance_table_start(relative, lines[index + 1], container)):
            table_context = context
        elif table_row and after_table and indent - container <= 3 and '|' in relative:
            # Track only a table actually opened by a matching header/delimiter;
            # an isolated pipe paragraph never gains table context.
            table_context = context
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", relative)
        indented_fence = re.match(r"^ {4,}(`{3,}|~{3,})(.*)$", relative)
        indented_comment = re.match(r'^ {4,}<!--', relative)
        if fence and (fence.group(1)[0] != '`' or '`' not in fence.group(2)):
            fence_character, fence_size = fence.group(1)[0], len(fence.group(1))
            fence_container = container
            visible.append('')
        elif re.match(r"^ {0,3}<!--", relative):
            # Inline/code-span markers are literal; even <!--> closes on this line.
            in_comment = '-->' not in relative
            visible.append('')
        elif not previous_blank and not after_table and indented_comment:
            # Unlike a type-2 block, an inline comment cannot cross a paragraph
            # boundary. An unmatched candidate remains literal compatibility text.
            if '-->' in expanded:
                continuation_comment_end = index
            elif (failed_comment_scan is not None and failed_comment_scan[0] == context
                  and index < failed_comment_scan[1]):
                continuation_comment_end = None
            else:
                continuation_comment_end, stop = _continuation_comment_end(lines, index, list_indents)
                if continuation_comment_end is None:
                    # Reuse only this context's failed interior; process the
                    # boundary itself and candidates beyond it normally.
                    failed_comment_scan = (context, stop)
            visible.append('' if continuation_comment_end is not None else raw_line)
        elif len(relative) - len(relative.lstrip(' ')) >= 4 and (
                previous_blank or (after_table and indented_comment) or (indented_fence and (
                    indented_fence.group(1)[0] != '`' or '`' not in indented_fence.group(2)))):
            # A blank starts indented code. Without a blank, remember the paired
            # example fence so compatible criteria can resume after its closer.
            # An indented comment after an actual table is code too; ordinary
            # indented criteria retain the extractor's compatibility behavior.
            indented_text = container + 4
            if after_table and indented_comment:
                # Include the closing line, then resume compatible criteria.
                # A nonblank dedent ends this region first; blanks stay inside.
                table_comment_code = '-->' not in expanded
                if not table_comment_code:
                    indented_text = None
            if not previous_blank and indented_fence:
                indented_fence_marker = (indented_fence.group(1)[0], len(indented_fence.group(1)), indent)
            visible.append('')
        else:
            visible.append(raw_line)
        previous_blank = False
    return visible


def _acceptance(text: str) -> List[str]:
    """Collect actual list/table criteria, excluding examples and empty seed rows."""
    result: List[str] = []
    heading_level: Optional[int] = None
    table = False
    table_delimiter: Optional[int] = None
    list_prefix = r"\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?"
    identifier = r"AC[-_][A-Za-z0-9_-]+(?=\s|[:：.)|-]|$)"
    lines = _acceptance_lines(text)
    separators = set()
    for index, line in enumerate(lines):
        if _acceptance_table_separator(line):
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
        if not table and "|" in line and index + 1 in separators:
            table = True
            table_delimiter = index + 1
            continue
        if table and index == table_delimiter:
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
            else:
                criterion_wording = re.sub(r"^" + list_prefix, '', line).strip()
            if _without_inline_comments(criterion_wording).strip() == '...':
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
                                           source_manifest=snapshot['manifest'],
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
