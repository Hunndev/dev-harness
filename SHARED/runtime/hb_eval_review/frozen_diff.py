"""Build diff evidence from captured bytes, never from a mutable working tree."""
import hashlib
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .snapshot import PacketPolicyError, _is_excluded, _is_secret_material


_SHA = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})\Z')


def _environment() -> Dict[str, str]:
    # Plumbing must use this repository's objects, and the standalone diff must not
    # inherit injected configuration, alternate indexes, diff helpers or attributes.
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_SYSTEM=os.devnull,
               GIT_CONFIG_GLOBAL=os.devnull, GIT_ATTR_NOSYSTEM='1',
               GIT_NO_REPLACE_OBJECTS='1', GIT_NO_LAZY_FETCH='1',
               GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
    return env


def _git(repo: Path, *args: str, input_data: bytes = None) -> bytes:
    result = subprocess.run(
        ['git', '-c', 'core.fsmonitor=false', '-c', 'core.attributesFile=' + os.devnull,
         *args], cwd=str(repo), env=_environment(), input=input_data,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise PacketPolicyError('DIFF_UNAVAILABLE', [])
    return result.stdout


def _untracked_names(repo: Path) -> bytes:
    # Enumerate with the same complete config/environment interpretation as
    # snapshot's ls-files. Copying selected keys loses other ignore semantics
    # (case folding, Unicode precomposition, and future Git settings).
    # This names-only command does not run diff/textconv/clean filters. Its one
    # executable hook, fsmonitor, is disabled by a command-line override that
    # wins over global/includes and command-scope environment configuration.
    # Public pack/run reject these six redirects before reaching this helper.
    # Keep its pre-existing repository/index isolation for direct internal calls;
    # no ignore/configuration keys are selected or reconstructed here.
    env = dict(os.environ)
    for key in ('GIT_DIR', 'GIT_COMMON_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE',
                'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES'):
        env.pop(key, None)
    # Object reads and the final diff still use the isolated _environment().
    result = subprocess.run(
        ['git', '-c', 'core.fsmonitor=false', 'ls-files', '-z', '--others', '--exclude-standard'],
        cwd=str(repo), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise PacketPolicyError('DIFF_UNAVAILABLE', [])
    return result.stdout


def _relative(value: str) -> Path:
    path = Path(value)
    if (not value or path.is_absolute() or '..' in path.parts or '.git' in path.parts
            or path.as_posix() != value or path == Path('.')):
        raise PacketPolicyError('PACKET_PATH_UNSAFE', [value])
    return path


def _artifact(path: Path) -> bool:
    return path.parts[:2] == ('.harness', 'artifacts')


def _capture(root_fd: int, relative: Path) -> Tuple[bytes, str, Any]:
    """Read a leaf once through no-follow directory descriptors.

    A replaced parent cannot redirect this read outside the repository. An open
    regular-file descriptor also pins the inode while its captured bytes are checked
    against the supplied snapshot. Symlinks contribute link text, never target bytes.
    """
    parent_fd = os.dup(root_fd)
    try:
        for part in relative.parts[:-1]:
            try:
                child_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                   dir_fd=parent_fd)
            except OSError:
                raise PacketPolicyError('PACKET_PATH_UNSAFE', [relative.as_posix()])
            os.close(parent_fd)
            parent_fd = child_fd
        leaf = relative.name
        before = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(before.st_mode):
            data = os.readlink(leaf, dir_fd=parent_fd).encode('utf-8', 'surrogateescape')
            return data, 'symlink', None
        if not stat.S_ISREG(before.st_mode):
            raise PacketPolicyError('PACKET_PATH_UNSAFE', [relative.as_posix()])
        descriptor = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=parent_fd)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise PacketPolicyError('PACKET_PATH_UNSAFE', [relative.as_posix()])
            with os.fdopen(descriptor, 'rb', closefd=False) as stream:
                data = stream.read()
            after = os.fstat(descriptor)
            if (opened.st_mode & 0o777) != (after.st_mode & 0o777):
                raise PacketPolicyError('DIFF_SOURCE_MISMATCH', [relative.as_posix()])
            return data, 'file', opened.st_mode & 0o777
        finally:
            os.close(descriptor)
    except OSError:
        raise PacketPolicyError('DIFF_SOURCE_MISMATCH', [relative.as_posix()])
    finally:
        os.close(parent_fd)


def _write_copy(root: Path, relative: Path, data: bytes, kind: str, mode: Any,
                expected_sha: str) -> None:
    parent = root
    for part in relative.parts[:-1]:
        parent = parent / part
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise PacketPolicyError('PACKET_PATH_UNSAFE', [relative.as_posix()])
        parent.mkdir(exist_ok=True)
    destination = parent / relative.name
    if destination.exists() or destination.is_symlink():
        raise PacketPolicyError('PACKET_PATH_UNSAFE', [relative.as_posix()])
    if kind == 'symlink':
        try:
            destination.symlink_to(data.decode('utf-8', 'surrogateescape'))
        except ValueError:
            raise PacketPolicyError('PACKET_PATH_UNSAFE', [relative.as_posix()])
        copied = os.readlink(str(destination)).encode('utf-8', 'surrogateescape')
    else:
        destination.write_bytes(data)
        # Verify the actual copy before chmod; a source mode without read bits must
        # not prevent the copy check itself from reporting a meaningful mismatch.
        copied = destination.read_bytes()
        destination.chmod(mode)
    if hashlib.sha256(copied).hexdigest() != expected_sha:
        raise PacketPolicyError('DIFF_SOURCE_MISMATCH', [relative.as_posix()])


def _copy_current(repo: Path, destination: Path, snapshot: Dict[str, Any]) -> None:
    entries = snapshot['manifest']['files']
    names = set()
    root_fd = os.open(str(repo), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for entry in entries:
            relative = _relative(entry['path'])
            if entry['path'] in names:
                raise PacketPolicyError('PACKET_PATH_UNSAFE', [entry['path']])
            names.add(entry['path'])
            if _artifact(relative):
                continue
            data, kind, mode = _capture(root_fd, relative)
            if (kind != entry['kind'] or mode != entry['mode']
                    or hashlib.sha256(data).hexdigest() != entry['sha256']):
                raise PacketPolicyError('DIFF_SOURCE_MISMATCH', [entry['path']])
            _write_copy(destination, relative, data, kind, mode, entry['sha256'])
        # Preserve the former diff's scope: Git-visible untracked cache files are
        # omitted by source snapshots, but full diff evidence included them. They
        # get one frozen read and a verified copy, bound by the diff/packet digest;
        # they do not acquire a source-snapshot/Gate binding that does not exist.
        raw_names = _untracked_names(repo)
        for raw in sorted(filter(None, raw_names.split(b'\0'))):
            name = raw.decode('utf-8', 'surrogateescape')
            if name in names:
                continue
            # Artifact outputs never enter diff evidence, including Git's special
            # directory marker for a nested repository inside those outputs.
            if _artifact(Path(name)):
                continue
            if name.endswith('/'):
                raise PacketPolicyError('PACKET_EMBEDDED_REPOSITORY_UNSUPPORTED', [name.rstrip('/')])
            relative = _relative(name)
            if not _is_excluded(relative, tracked=False):
                raise PacketPolicyError('DIFF_SOURCE_MISMATCH', [name])
            if _is_secret_material(relative):
                raise PacketPolicyError('PACKET_SECRET_MATERIAL_PRESENT', [name])
            data, kind, mode = _capture(root_fd, relative)
            _write_copy(destination, relative, data, kind, mode, hashlib.sha256(data).hexdigest())
    finally:
        os.close(root_fd)


def _copy_base(repo: Path, destination: Path, base_sha: str) -> None:
    if not isinstance(base_sha, str) or not _SHA.fullmatch(base_sha):
        raise PacketPolicyError('DIFF_BASE_INVALID', [])
    entries: List[Tuple[Path, str, str]] = []
    for record in filter(None, _git(repo, 'ls-tree', '-r', '-z', '--full-tree', base_sha).split(b'\0')):
        metadata, name = record.split(b'\t', 1)
        mode, kind, object_id = metadata.decode('ascii').split(' ')
        relative = _relative(name.decode('utf-8', 'surrogateescape'))
        if _artifact(relative):
            continue
        if mode == '160000':
            raise PacketPolicyError('PACKET_GITLINK_UNSUPPORTED', [relative.as_posix()])
        if kind != 'blob' or mode not in ('100644', '100755', '120000') or not _SHA.fullmatch(object_id):
            raise PacketPolicyError('PACKET_PATH_UNSAFE', [relative.as_posix()])
        entries.append((relative, mode, object_id))
    if not entries:
        return
    # Raw object reads do not invoke clean/smudge or textconv, unlike a checkout.
    raw = _git(repo, 'cat-file', '--batch', input_data=''.join(item[2] + '\n' for item in entries).encode('ascii'))
    offset = 0
    for relative, mode, object_id in entries:
        end = raw.find(b'\n', offset)
        header = raw[offset:end].split(b' ')
        if end < 0 or len(header) != 3 or header[0] != object_id.encode('ascii') or header[1] != b'blob':
            raise PacketPolicyError('DIFF_UNAVAILABLE', [relative.as_posix()])
        size = int(header[2])
        start = end + 1
        data = raw[start:start + size]
        offset = start + size + 1
        if len(data) != size or raw[start + size:offset] != b'\n':
            raise PacketPolicyError('DIFF_UNAVAILABLE', [relative.as_posix()])
        _write_copy(destination, relative, data, 'symlink' if mode == '120000' else 'file',
                    None if mode == '120000' else int(mode, 8) & 0o777, hashlib.sha256(data).hexdigest())
    if offset != len(raw):
        raise PacketPolicyError('DIFF_UNAVAILABLE', [])


def _normalize_headers(diff: bytes) -> bytes:
    """Fix no-index's equal-side add/delete headers without touching diff payloads.

    Comparing relative directories `a` and `b` with --no-prefix already gives the
    correct normal headers and Git's own quoting. A new/deleted file alone uses its
    existing side twice (b/path b/path or a/path a/path); normalize only that exact
    duplicate header. Added body lines always start '+', including literal headers.
    """
    result = []
    for line in diff.splitlines(keepends=True):
        match = re.fullmatch(rb'diff --git (.+) \1\n', line)
        if match:
            name = match.group(1)
            if name.startswith(b'a/'):
                line = b'diff --git ' + name + b' b/' + name[2:] + b'\n'
            elif name.startswith(b'b/'):
                line = b'diff --git a/' + name[2:] + b' ' + name + b'\n'
            elif name.startswith(b'"a/'):
                line = b'diff --git ' + name + b' "b/' + name[3:] + b'\n'
            elif name.startswith(b'"b/'):
                line = b'diff --git "a/' + name[3:] + b' ' + name + b'\n'
        result.append(line)
    return b''.join(result)


def build_frozen_diff(repo: Path, base_sha: str, snapshot: Dict[str, Any]) -> bytes:
    """Compare a fixed commit with frozen current bytes checked against `snapshot`.

    The caller supplies the snapshot already bound to its Gate/source identity. This
    function never writes to that repository, follows external links, or lets Git diff
    consume live working files. Artifact outputs are excluded on both comparison sides.
    """
    repo = Path(repo).resolve()
    try:
        with tempfile.TemporaryDirectory(prefix='hb-frozen-diff-') as temporary:
            root = Path(temporary)
            before, after = root / 'a', root / 'b'
            before.mkdir(); after.mkdir()
            _copy_current(repo, after, snapshot)
            _copy_base(repo, before, base_sha)
            result = subprocess.run(
                ['git', '-c', 'core.attributesFile=' + os.devnull, 'diff', '--no-index',
                 '--binary', '--no-ext-diff', '--no-textconv', '--no-renames', '--no-color',
                 '--no-prefix', '--', 'a', 'b'], cwd=str(root), env=_environment(),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode not in (0, 1):
                raise PacketPolicyError('DIFF_UNAVAILABLE', [])
            return _normalize_headers(result.stdout)
    except OSError:
        raise PacketPolicyError('DIFF_UNAVAILABLE', [])
