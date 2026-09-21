"""Execute one real provider stage and bind semantic output to a parent envelope."""

import errno
import hashlib
import json
import os
import shutil
import stat
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .adapters.claude import build_claude_command, claude_environment
from .adapters.codex import build_codex_command, codex_environment
from .process import DESCENDANT_CONTAINMENT, _utc_now, run_isolated_process
from .redaction import known_secret_values, redact_json, redact_text
from .result_validation import canonical_bytes

# One result file cannot plausibly exceed this; refusing early also bounds the read.
_MAX_RESULT_BYTES = 8 * 1024 * 1024
# The credential scan streams every stage file, so memory stays flat whatever the size;
# this caps the time one file may cost. Anything larger is reported as unscanned and
# blocks the stage rather than being quietly left behind.
_MAX_SCAN_BYTES = 64 * 1024 * 1024
# A provider does not nest its output this deep. Refusing to go further keeps the walk
# bounded without reaching any tree a real stage produces.
_MAX_SCAN_DEPTH = 32
_READ_CHUNK = 65536

# Scan verdicts for one stage file.
_HIT, _CLEAN, _GONE, _UNSCANNABLE = "HIT", "CLEAN", "GONE", "UNSCANNABLE"
# Setting a mode without dereferencing needs lchmod-style support. Where the platform
# lacks it the parent leaves the entry alone and the removal fails closed instead of
# chmod-ing whatever a link points at.
_NOFOLLOW_CHMOD = os.chmod in os.supports_follow_symlinks
# A child can pin a file in its own HOME with the user immutable/append flags, which
# survive every chmod. Only these owner-settable ones are cleared, and only inside the
# HOME this run created; system flags are never touched.
_SUPPORTS_CHFLAGS = hasattr(os, "chflags")
_LOCK_FLAGS = (
    getattr(stat, "UF_IMMUTABLE", 0) | getattr(stat, "UF_APPEND", 0)
    | getattr(stat, "UF_NOUNLINK", 0)
)
# How many free names the parent will try when a needle-bearing directory name has to
# be replaced in place. A stage that needs more than this is reported, not guessed at.
_MAX_RENAME_ATTEMPTS = 64


class _UnsafeResultPath(ValueError):
    """The child left something other than its own plain file at the result path."""


def _read_regular_file(path: Path, limit: int) -> bytes:
    """Read a child-owned path without ever following a link or blocking on a device.

    O_NOFOLLOW refuses a symlink outright, O_NONBLOCK keeps a FIFO from stalling the
    parent, and fstat on the already-open descriptor decides on the very object that
    was opened, so nothing can be swapped in between the check and the read.
    """
    try:
        handle = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.ENOTDIR, errno.EMLINK):
            raise _UnsafeResultPath("RESULT_PATH_NOT_REGULAR")
        raise
    try:
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise _UnsafeResultPath("RESULT_PATH_NOT_REGULAR")
        if info.st_size > limit:
            raise ValueError("RESULT_TOO_LARGE")
        os.set_blocking(handle, True)
        chunks: List[bytes] = []
        total = 0
        while True:
            chunk = os.read(handle, _READ_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ValueError("RESULT_TOO_LARGE")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(handle)


def _replace_with_canonical(path: Path, payload: bytes) -> None:
    """Publish the redacted bytes on a fresh inode; the child's file is never written."""
    temporary = path.parent / (path.name + ".parent-tmp")
    try:
        os.unlink(str(temporary))
    except OSError:
        pass
    handle = os.open(
        str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    try:
        os.fchmod(handle, 0o600)
        os.write(handle, payload)
    finally:
        os.close(handle)
    os.replace(str(temporary), str(path))


def _discard_raw_result(path: Path) -> Optional[str]:
    """Drop an unsealed result. A link here is unlinked; its target is never touched.

    Whether it went is reported: an unsealed result may still carry injected auth, so a
    removal the child defeated is a cleanup error, never a silent success.
    """
    try:
        info = os.lstat(str(path))
    except FileNotFoundError:
        return None
    except OSError:
        return "RAW_RESULT_CLEANUP_FAILED"
    if stat.S_ISDIR(info.st_mode):
        # A directory here was never read and never sealed; removing a child-owned tree
        # by name is not this step's job, so it is reported and blocks the stage.
        return "RAW_RESULT_CLEANUP_FAILED"
    try:
        os.unlink(str(path))
    except OSError:
        return "RAW_RESULT_CLEANUP_FAILED"
    return "RAW_RESULT_CLEANUP_FAILED" if os.path.lexists(str(path)) else None


def _directory_identity(path: Path) -> Optional[Tuple[int, int]]:
    """Identify the directory itself, so a delete-and-relink cannot pass unnoticed."""
    try:
        info = os.lstat(str(path))
    except OSError:
        return None
    if not stat.S_ISDIR(info.st_mode):
        return None
    return (info.st_dev, info.st_ino)


def _root_is_intact(output_root: Path, identity: Optional[Tuple[int, int]]) -> bool:
    """A stage root that is not the very directory the parent made is never trusted."""
    return identity is not None and _directory_identity(output_root) == identity


def _mark_root_tampered(envelope: Dict[str, Any]) -> None:
    """One verdict for a swapped stage root, wherever the swap was noticed."""
    envelope["status"] = "BLOCKED"
    envelope["error_code"] = "OUTPUT_ROOT_TAMPERED"


def _open_subdirectory_reporting(
    dir_fd: int, name: str, identity: int
) -> Tuple[Optional[int], Optional[int]]:
    """Open a child directory by name, refusing a link or a swapped inode.

    The errno is handed back so the caller can tell "the child locked it" from "the
    child replaced it": only the first is something the parent may undo by name, and
    chmod-ing a name whose inode no longer matches would act on the swapped object.
    """
    try:
        handle = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
    except OSError as error:
        return None, error.errno
    try:
        if os.fstat(handle).st_ino != identity:
            os.close(handle)
            return None, None
    except OSError as error:
        os.close(handle)
        return None, error.errno
    return handle, None


def _open_subdirectory(dir_fd: int, name: str, identity: int) -> Optional[int]:
    """Open a child directory without following a link, refusing a swapped inode."""
    return _open_subdirectory_reporting(dir_fd, name, identity)[0]


def _restore_entry_mode(dir_fd: int, name: str, mode: int) -> bool:
    """Set one entry's mode relative to a held descriptor, never through a link.

    follow_symlinks=False is the whole guarantee: a component the child swaps for a
    link between the lstat and this call gets its own mode set, never whatever it
    points at.
    """
    if not _NOFOLLOW_CHMOD:
        return False
    try:
        os.chmod(name, mode, dir_fd=dir_fd, follow_symlinks=False)
    except (OSError, NotImplementedError):
        return False
    return True


def _clear_locked_flags(directory: Path, dir_fd: int, name: str, flags: int) -> None:
    """Clear the owner-settable lock flags a child used to pin a file in its HOME.

    os.chflags takes no dir_fd, so the descriptor the walk already holds is compared
    against the path immediately before the call and the final component is never
    followed. A component swapped inside that window belongs to the setsid-escapee
    limit commands/evaluate.md already states, not to a new one.
    """
    if not _SUPPORTS_CHFLAGS or not flags & _LOCK_FLAGS:
        return
    try:
        probe = os.stat(str(directory))
        held = os.fstat(dir_fd)
    except OSError:
        return
    if (probe.st_dev, probe.st_ino) != (held.st_dev, held.st_ino):
        return
    try:
        os.chflags(
            os.path.join(str(directory), name), flags & ~_LOCK_FLAGS, follow_symlinks=False
        )
    except (OSError, NotImplementedError, ValueError):
        return


def _remove_home_tree(directory: Path, dir_fd: int, depth: int) -> None:
    """Empty this run's own HOME through descriptors the parent holds open.

    Whether it succeeded is not reported here: the caller decides that by asking the
    filesystem whether the HOME is still there, which is the only answer a hostile
    child cannot influence.

    Modes and lock flags are undone on the way down, because a child that can pin its
    HOME keeps the copied credential on disk. The walk is depth-capped on purpose: a
    child can nest a chain thousands of levels deep, and an unbounded recursive removal
    turns that into a RecursionError that escapes cleanup and skips every step after
    it. What the cap leaves behind is reported as a cleanup error instead.
    """
    try:
        os.fchmod(dir_fd, 0o700)
    except OSError:
        pass
    try:
        names = os.listdir(dir_fd)
    except OSError:
        return
    for name in names:
        try:
            info = os.lstat(name, dir_fd=dir_fd)
        except OSError:
            continue
        is_directory = stat.S_ISDIR(info.st_mode)
        _clear_locked_flags(directory, dir_fd, name, getattr(info, "st_flags", 0))
        _restore_entry_mode(dir_fd, name, 0o700 if is_directory else 0o600)
        if not is_directory:
            try:
                os.unlink(name, dir_fd=dir_fd)
            except OSError:
                pass
            continue
        if depth + 1 >= _MAX_SCAN_DEPTH:
            continue
        # Classified as a directory but not verifiable as the same one: it is left
        # exactly where it is, and the caller sees the HOME is still there.
        child = _open_subdirectory(dir_fd, name, info.st_ino)
        if child is None:
            continue
        try:
            _remove_home_tree(directory / name, child, depth + 1)
        finally:
            os.close(child)
        try:
            os.rmdir(name, dir_fd=dir_fd)
        except OSError:
            pass


def _remove_provider_home(provider_home: Path) -> Optional[str]:
    """Remove only this run's own HOME; report when the child managed to keep it.

    A link left in its place is unlinked, not followed. A stripped mode is restored
    first, because a child that can pin its HOME keeps the copied credential on disk.
    """
    try:
        info = os.lstat(str(provider_home))
    except FileNotFoundError:
        return None
    except OSError:
        # Readable-but-not-searchable parent, or any other refusal: the HOME may well
        # still be there with the copied credential in it. Not knowing is not "gone".
        if not _recover_directory_mode(provider_home.parent):
            return "PROVIDER_HOME_NOT_REMOVED"
        try:
            info = os.lstat(str(provider_home))
        except FileNotFoundError:
            return None
        except OSError:
            return "PROVIDER_HOME_NOT_REMOVED"
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        try:
            os.unlink(str(provider_home))
        except OSError:
            return "PROVIDER_HOME_NOT_REMOVED"
        return None
    if _SUPPORTS_CHFLAGS and getattr(info, "st_flags", 0) & _LOCK_FLAGS:
        try:
            os.chflags(
                str(provider_home), info.st_flags & ~_LOCK_FLAGS, follow_symlinks=False
            )
        except (OSError, NotImplementedError, ValueError):
            pass
    if _NOFOLLOW_CHMOD:
        try:
            os.chmod(str(provider_home), 0o700, follow_symlinks=False)
        except (OSError, NotImplementedError):
            pass
    try:
        parent_fd = os.open(str(provider_home.parent), os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        parent_fd = None
    if parent_fd is not None:
        try:
            handle = _open_subdirectory(parent_fd, provider_home.name, info.st_ino)
        finally:
            os.close(parent_fd)
        if handle is not None:
            try:
                _remove_home_tree(provider_home, handle, 0)
            finally:
                os.close(handle)
    try:
        os.rmdir(str(provider_home))
    except OSError:
        pass
    if os.path.lexists(str(provider_home)):
        return "PROVIDER_HOME_NOT_REMOVED"
    return None


def _scan_open_file(handle: int, needles: Sequence[bytes]) -> str:
    """Stream one open file for any needle, keeping memory flat and time bounded.

    Consecutive chunks overlap by one less than the longest needle, so a credential
    that straddles a read boundary is still found.
    """
    overlap = max(len(needle) for needle in needles) - 1
    os.set_blocking(handle, True)
    tail = b""
    total = 0
    while True:
        try:
            chunk = os.read(handle, _READ_CHUNK)
        except OSError:
            return _UNSCANNABLE
        if not chunk:
            return _CLEAN
        total += len(chunk)
        if total > _MAX_SCAN_BYTES:
            return _UNSCANNABLE
        window = tail + chunk
        if any(needle in window for needle in needles):
            return _HIT
        tail = window[-overlap:] if overlap else b""


def _scan_entry(dir_fd: int, name: str, needles: Sequence[bytes]) -> str:
    """Open one stage file through the held descriptor and decide on that very object."""
    try:
        handle = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd
        )
    except FileNotFoundError:
        return _GONE
    except OSError:
        return _UNSCANNABLE
    try:
        info = os.fstat(handle)
        if not stat.S_ISREG(info.st_mode):
            return _UNSCANNABLE
        if info.st_size > _MAX_SCAN_BYTES:
            return _UNSCANNABLE
        return _scan_open_file(handle, needles)
    except OSError:
        return _UNSCANNABLE
    finally:
        os.close(handle)


def _recover_directory_write(dir_fd: int) -> bool:
    """Restore owner bits on the very directory the parent already holds open.

    A child that strips its own stage directory to r-x pins whatever is inside it. The
    mode is set on the descriptor, so no name is resolved a second time and nothing
    outside the stage root can be reached by this.
    """
    try:
        os.fchmod(dir_fd, 0o700)
    except OSError:
        return False
    return True


def _recover_directory_mode(directory: Path) -> bool:
    """Restore owner bits on a directory the parent owns, through its own descriptor.

    Used where no descriptor is held yet: opening read-only still works on a directory
    a child stripped to r--, and the mode is then set on that very descriptor, so no
    name is resolved twice and nothing outside it can be reached.
    """
    try:
        handle = os.open(str(directory), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return False
    try:
        return _recover_directory_write(handle)
    finally:
        os.close(handle)


def _list_directory(dir_fd: int) -> Optional[List[str]]:
    """List through the held descriptor, undoing a stripped mode once if need be."""
    try:
        return sorted(os.listdir(dir_fd))
    except OSError:
        pass
    if not _recover_directory_write(dir_fd):
        return None
    try:
        return sorted(os.listdir(dir_fd))
    except OSError:
        return None


def _stat_entry(dir_fd: int, name: str) -> Tuple[Optional[os.stat_result], Optional[str]]:
    """lstat one entry through the held descriptor, undoing a stripped mode once.

    A directory left readable but not searchable answers listdir and refuses lstat, so
    treating every failure as "already gone" hid whatever was inside it. Only ENOENT is
    gone; anything else is retried after the parent restores its own bits on the
    descriptor it holds, and a second failure is reported rather than passed over.
    """
    for attempt in (0, 1):
        try:
            return os.lstat(name, dir_fd=dir_fd), None
        except FileNotFoundError:
            return None, _GONE
        except OSError:
            if attempt or not _recover_directory_write(dir_fd):
                return None, _UNSCANNABLE
    return None, _UNSCANNABLE


def _unlink_entry(dir_fd: int, name: str, relative: str, report: Dict[str, Any]) -> None:
    """Unlink through the held descriptor; unlink never follows the final component."""
    for attempt in (0, 1):
        try:
            os.unlink(name, dir_fd=dir_fd)
        except FileNotFoundError:
            report["notes"][relative] = _GONE
            return
        except OSError:
            # A stripped directory mode is the one failure the parent can undo, and
            # only on the directory it is already holding open.
            if attempt or not _recover_directory_write(dir_fd):
                report["unscanned"].append(relative)
                return
        else:
            report["purged"].append(relative)
            return


def _name_holds_needle(name: str, needles: Sequence[bytes]) -> bool:
    """A credential encoded in an entry name sits on disk exactly like one in bytes."""
    encoded = name.encode("utf-8", "surrogateescape")
    return any(needle in encoded for needle in needles)


def _free_redacted_name(dir_fd: int, name: str, secrets: Sequence[str]) -> Optional[str]:
    """A free name in the same directory with every known literal taken out of it."""
    base = redact_text(name, secrets)
    if not base or base == name:
        return None
    for attempt in range(_MAX_RENAME_ATTEMPTS):
        candidate = base if attempt == 0 else "{}-{}".format(base, attempt)
        try:
            os.lstat(candidate, dir_fd=dir_fd)
        except FileNotFoundError:
            return candidate
        except OSError:
            return None
    return None


def _clear_named_directory(
    dir_fd: int, name: str, relative: str, secrets: Sequence[str], report: Dict[str, Any]
) -> None:
    """Take a credential out of a directory *name* without deleting a clean subtree.

    Removing the directory is preferred, and after the walk above it is usually already
    empty. When the child left unrelated files inside, the entry is renamed in place
    instead, so the literal leaves the disk and contents that carry no credential
    survive. Both act on the descriptor the parent holds, so neither can reach outside
    the stage root; what neither can do is reported and blocks the stage.
    """
    try:
        os.rmdir(name, dir_fd=dir_fd)
    except OSError:
        pass
    else:
        report["purged"].append(relative)
        return
    replacement = _free_redacted_name(dir_fd, name, secrets)
    if replacement is None:
        report["unscanned"].append(relative)
        return
    try:
        os.rename(name, replacement, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
    except OSError:
        report["unscanned"].append(relative)
    else:
        report["renamed"].append(relative)


def _purge_directory(
    dir_fd: int, prefix: str, needles: Sequence[bytes], secrets: Sequence[str],
    report: Dict[str, Any], depth: int,
) -> None:
    """Walk one stage directory through descriptors the parent holds open.

    Every entry is judged on two counts: the bytes it stores and the name it is stored
    under. A child that cannot get a credential past the value redaction can still
    write it as a file or directory name, and that name is on disk just the same.
    """
    names = _list_directory(dir_fd)
    if names is None:
        report["unscanned"].append(prefix.rstrip("/") or ".")
        return
    for name in names:
        relative = prefix + name
        named = _name_holds_needle(name, needles)
        info, verdict = _stat_entry(dir_fd, name)
        if info is None:
            if verdict == _GONE:
                # Gone before the parent reached it: nothing is left on disk to purge.
                report["notes"][relative] = _GONE
            else:
                report["unscanned"].append(relative)
            continue
        if stat.S_ISDIR(info.st_mode):
            if depth + 1 >= _MAX_SCAN_DEPTH:
                report["unscanned"].append(relative)
                continue
            child, refusal = _open_subdirectory_reporting(dir_fd, name, info.st_ino)
            if child is None and refusal is not None:
                # A directory the child stripped of its own bits is the one case the
                # parent can undo, and only on a name resolved through this descriptor.
                # A None refusal means the inode no longer matches, so the name is left
                # alone: chmod-ing it would act on whatever was swapped in.
                _restore_entry_mode(dir_fd, name, 0o700)
                child = _open_subdirectory(dir_fd, name, info.st_ino)
            if child is None:
                # Replaced or unreadable: it is still present and not provably clean.
                report["unscanned"].append(relative)
                continue
            try:
                _purge_directory(child, relative + "/", needles, secrets, report, depth + 1)
            finally:
                os.close(child)
            if named:
                _clear_named_directory(dir_fd, name, relative, secrets, report)
        elif stat.S_ISLNK(info.st_mode):
            # The link text itself can carry the credential, and so can the link's own
            # name. Only the link is removed; whatever it points at is never opened and
            # never deleted.
            if named:
                # The name alone already decides it, so the removal never waits on a
                # read the child can make fail.
                _unlink_entry(dir_fd, name, relative, report)
                continue
            try:
                target = os.readlink(name, dir_fd=dir_fd).encode("utf-8", "surrogateescape")
            except FileNotFoundError:
                report["notes"][relative] = _GONE
                continue
            except OSError:
                # Still on disk and not provably clean: only ENOENT means gone.
                report["unscanned"].append(relative)
                continue
            if any(needle in target for needle in needles):
                _unlink_entry(dir_fd, name, relative, report)
        elif not stat.S_ISREG(info.st_mode):
            if named:
                # A socket or FIFO stores no bytes, but its name is still on disk.
                _unlink_entry(dir_fd, name, relative, report)
            else:
                report["notes"][relative] = "NOT_A_REGULAR_FILE"
        elif named:
            _unlink_entry(dir_fd, name, relative, report)
        else:
            verdict = _scan_entry(dir_fd, name, needles)
            if verdict == _HIT:
                _unlink_entry(dir_fd, name, relative, report)
            elif verdict == _GONE:
                report["notes"][relative] = _GONE
            elif verdict == _UNSCANNABLE:
                report["unscanned"].append(relative)


def _purge_secret_files(root: Path, known_secrets: Sequence[str]) -> Dict[str, Any]:
    """Delete stage files that still hold an injected credential; report paths only.

    Every name is resolved against a directory descriptor the parent opened with
    O_NOFOLLOW and verified by inode, so a component the child swaps after enumeration
    cannot redirect a read, a rename or an unlink outside the stage root. What cannot be
    proven clean is reported as unscanned and blocks the stage instead of being skipped.

    The match is the exact injected literal, in file bytes and in entry names alike. A
    value the child re-encoded is outside this scope, exactly as commands/evaluate.md
    states, and so is anything a descendant writes after leaving the process group.
    """
    secrets = [item for item in known_secrets if isinstance(item, str) and item]
    needles = [item.encode("utf-8", "surrogateescape") for item in secrets]
    report: Dict[str, Any] = {"purged": [], "unscanned": [], "renamed": [], "notes": {}}
    if not needles:
        return report
    try:
        root_fd = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        report["unscanned"].append(".")
        return report
    try:
        _purge_directory(root_fd, "", needles, secrets, report, 0)
    finally:
        os.close(root_fd)
    return report


def _guarded_cleanup(code: str, step: Any, errors: List[str]) -> Any:
    """Run one cleanup step; anything it raises becomes a reported code.

    Cleanup runs after the provider is gone, on a tree the child controlled, so the
    failure modes are not enumerable in advance — a chain nested past the interpreter's
    recursion limit raises RecursionError, not OSError. Whatever it is, it is turned
    into a BLOCKED error code so the steps after it still run.
    """
    try:
        return step()
    except Exception:
        errors.append(code)
        return None


def _redacted_paths(paths: Sequence[str], known_secrets: Sequence[str]) -> List[str]:
    """Diagnostics carry child-chosen names, so every one is redacted before sealing.

    A child that cannot get a credential past the value redaction can still encode it
    in a file or directory name; without this the parent would seal that name itself.
    """
    return [redact_text(str(item), known_secrets) for item in paths]


def _extract_claude(stdout: str) -> Dict[str, Any]:
    outer = json.loads(stdout)
    if not isinstance(outer, dict):
        # Untrusted output: an outer document that is not an object is a BLOCKED result,
        # never an AttributeError out of the stage.
        raise ValueError("CLAUDE_SEMANTIC_RESULT_MISSING")
    semantic = outer.get("structured_output")
    if semantic is None:
        semantic = outer.get("result")
    if isinstance(semantic, str):
        semantic = json.loads(semantic)
    if not isinstance(semantic, dict):
        raise ValueError("CLAUDE_SEMANTIC_RESULT_MISSING")
    return semantic


_CLAUDE_AUTH_KEYS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def _claude_temp_root() -> Path:
    """The Claude CLI writes session state here regardless of TMPDIR; it is shared."""
    return Path("/tmp/claude-{}".format(os.getuid()))


def _direct_children(root: Path) -> set:
    try:
        return {str(item) for item in root.iterdir()}
    except OSError:
        return set()


class _ProviderAuthUnusable(ValueError):
    """The auth material this parent injected cannot be read back or parsed."""


def _known_secrets(engine: str, environment: Dict[str, str], provider_home: Path) -> List[str]:
    """Collect the credentials this parent injected so they can never be echoed back."""
    if engine == "claude":
        return known_secret_values(
            [environment[key] for key in _CLAUDE_AUTH_KEYS if environment.get(key)]
        )
    try:
        auth = json.loads((provider_home / "auth.json").read_text())
    except (OSError, ValueError) as error:
        # The parent wrote this file itself. An empty inventory here is not "no
        # credentials": it is the parent not knowing which literals it just handed the
        # child, so there is nothing to redact out of the output and nothing for the
        # purge to look for. An auth failure is BLOCKED, so the stage never launches.
        raise _ProviderAuthUnusable("PROVIDER_AUTH_UNUSABLE") from error
    return known_secret_values(auth)


def _prelaunch_blocked_envelope(
    stage: str, engine: str, packet: Dict[str, str], error_code: str
) -> Dict[str, Any]:
    """A stage that never launched still owes the gate one complete BLOCKED envelope.

    The orchestrator reads `future.result()`, so raising here would surface as a
    traceback instead of a verdict. `run_isolated_process` already answers an unusable
    sandbox exactly this way; unusable injected auth is the same kind of refusal. The
    code is a fixed constant, so nothing read off the child's disk travels with it.
    """
    moment = _utc_now()
    return {
        "schema_version": "2.0", "stage": stage, "engine": engine, "provider": engine,
        "run_id": str(uuid.uuid4()), "started_at": moment, "finished_at": moment,
        "exit_code": None, "timed_out": False, "fresh_process": True,
        "session_resumed": False, "isolation_mode": "unsupported",
        "source_snapshot_before": packet["source_snapshot_id"],
        "source_snapshot_after": packet["source_snapshot_id"],
        "packet_id": packet["packet_id"], "evidence_bundle_id": packet["evidence_bundle_id"],
        "repository_mutated": False, "result_sha256": hashlib.sha256(b"").hexdigest(),
        "status": "BLOCKED", "error_code": error_code,
    }


def _ephemeral_environment(engine: str, output_root: Path) -> Dict[str, str]:
    """Create one minimal provider HOME; never expose the user's normal HOME."""
    provider_home = output_root / ".provider-home"
    temp_root = provider_home / "tmp"
    temp_root.mkdir(parents=True, exist_ok=False)
    provider_home.chmod(0o700)
    temp_root.chmod(0o700)
    overrides = dict(os.environ)
    overrides.update({
        "HOME": str(provider_home),
        "TMPDIR": str(temp_root),
        "XDG_CONFIG_HOME": str(provider_home / ".config"),
        "XDG_CACHE_HOME": str(provider_home / ".cache"),
    })
    if engine == "claude":
        environment = claude_environment(overrides)
        if not any(environment.get(key) for key in (
            "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"
        )):
            raise ValueError("CLAUDE_MINIMAL_AUTH_MISSING")
        return environment
    auth_source = Path(os.environ.get("HB_CODEX_AUTH_FILE", str(Path.home() / ".codex" / "auth.json")))
    if not auth_source.is_file():
        raise ValueError("CODEX_AUTH_FILE_MISSING")
    auth_target = provider_home / "auth.json"
    shutil.copyfile(str(auth_source), str(auth_target))
    auth_target.chmod(0o600)
    overrides["CODEX_HOME"] = str(provider_home)
    return codex_environment(overrides)


def run_provider_stage(
    engine: str,
    stage: str,
    packet: Dict[str, str],
    packet_source: Path,
    output_root: Path,
    prompt: str,
    timeout_seconds: float = 240,
    peer_output_root: Optional[Path] = None,
    model: Optional[str] = None,
    readable_roots: Optional[List[Path]] = None,
) -> Dict[str, Any]:
    """Run Claude or Codex as a fresh sibling process against one protected packet copy."""
    packet_source = Path(packet_source).resolve()
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    contracts = Path(__file__).resolve().parents[2] / "contracts"
    semantic_schema = contracts / "provider-result-base.schema.json"
    schema_data = json.loads(semantic_schema.read_text())
    claude_schema = dict(schema_data)
    claude_schema.pop("$schema", None)
    claude_schema.pop("$id", None)
    denied = [peer_output_root] if peer_output_root is not None else []
    home = Path.home()
    provider_home = output_root / ".provider-home"
    claude_temp = _claude_temp_root()
    temp_before = _direct_children(claude_temp) if engine == "claude" else set()
    result_path: Optional[Path] = None

    if engine == "claude":
        command = build_claude_command(
            prompt, json.dumps(claude_schema, separators=(",", ":")), model=model
        )
        denied.append(home / ".codex")
    elif engine == "codex":
        result_path = output_root / "semantic-result.json"
        local_schema = output_root / "provider-result.schema.json"
        local_schema.write_text(semantic_schema.read_text())
        command = build_codex_command(packet_source, local_schema, result_path, prompt, model=model)
        denied.append(home / ".claude")
    else:
        raise ValueError("unsupported engine")

    # The stage root is parent-owned. Everything cleaned up afterwards is keyed to
    # this identity, so a child that deletes or relinks it gets nothing removed.
    root_identity = _directory_identity(output_root)
    known_secrets: List[str] = []
    semantic: Dict[str, Any] = {}
    # Bound before the try because a stage refused before launch still runs the cleanup
    # block below and still builds the diagnostics: there is simply no child output.
    execution: Dict[str, Any] = {}
    # Bound before the try so the cleanup block can pass the same verdict whatever the
    # try raised; a stage that never got an envelope re-raises and never reads this.
    envelope: Dict[str, Any] = {}
    sealed_raw_result = False
    purge_report: Dict[str, Any] = {
        "purged": [], "unscanned": [], "renamed": [], "notes": {}
    }
    cleanup_errors: List[str] = []
    tampered = False
    try:
        environment = _ephemeral_environment(engine, output_root)
        known_secrets = _known_secrets(engine, environment, provider_home)
        execution = run_isolated_process(
            command, packet_source, output_root, packet, stage, engine, timeout_seconds,
            environment, denied_read_roots=[Path(item) for item in denied],
            readable_roots=[Path.home() / ".npm-global"] + ([claude_temp] if engine == "claude" else []) + list(readable_roots or []),
            writable_roots=[claude_temp] if engine == "claude" else [],
        )
        envelope = execution["envelope"]
        if not _root_is_intact(output_root, root_identity):
            _mark_root_tampered(envelope)
            tampered = True
        elif envelope["status"] == "PASS":
            try:
                if engine == "claude":
                    # Parse the raw child output first; redaction is applied to the parsed
                    # string values so it can never corrupt the JSON the parent must read.
                    semantic = redact_json(_extract_claude(str(execution["stdout"])), known_secrets)
                else:
                    raw = _read_regular_file(result_path, _MAX_RESULT_BYTES)
                    parsed = json.loads(raw.decode("utf-8"))
                    if not isinstance(parsed, dict):
                        raise ValueError("CODEX_SEMANTIC_RESULT_MISSING")
                    semantic = redact_json(parsed, known_secrets)
                    _replace_with_canonical(result_path, canonical_bytes(semantic))
                    sealed_raw_result = True
                envelope["result_sha256"] = hashlib.sha256(canonical_bytes(semantic)).hexdigest()
            except _UnsafeResultPath:
                semantic = {}
                envelope["status"] = "BLOCKED"
                envelope["error_code"] = "RESULT_PATH_UNSAFE"
            except (OSError, ValueError, json.JSONDecodeError, RecursionError):
                # A child chooses the nesting depth, and parsing, redacting and
                # canonicalising are all recursive: RecursionError is one more shape a
                # malformed result takes, not an exception the stage may leave on.
                semantic = {}
                envelope["status"] = "BLOCKED"
                envelope["error_code"] = "RESULT_MALFORMED"
    except _ProviderAuthUnusable as error:
        # Raised before `run_isolated_process`, so no child was started. The cleanup
        # block below still runs and removes this run's HOME, credential copy and all.
        envelope = _prelaunch_blocked_envelope(stage, engine, packet, str(error))
    finally:
        # Only this run's own HOME/TMPDIR is removed. The shared Claude session root
        # belongs to the parent and to other sessions; it is never deleted here, and
        # neither is anything reachable through a stage root the child swapped out.
        if tampered or not _root_is_intact(output_root, root_identity):
            # A descendant that escaped the process group outlives the wait, so it can
            # swap the root *after* the check above passed. This one then sees it first,
            # and the verdict is the same either way: the stage is BLOCKED, the result
            # read through a root the parent no longer owns is dropped, and every step
            # below is skipped so nothing is deleted through the swapped name.
            _mark_root_tampered(envelope)
            semantic = {}
            tampered = True
        else:
            # Each step is reported rather than raised, so one that a child manages to
            # break — including with an exception no caller can predict — cannot stop
            # the ones after it from running or end the stage as a traceback.
            home_error = _guarded_cleanup(
                "PROVIDER_HOME_CLEANUP_FAILED",
                lambda: _remove_provider_home(provider_home), cleanup_errors,
            )
            if home_error is not None:
                cleanup_errors.append(home_error)
            if result_path is not None and not sealed_raw_result:
                # A raw result the parent did not seal may still carry injected auth.
                raw_error = _guarded_cleanup(
                    "RAW_RESULT_CLEANUP_FAILED",
                    lambda: _discard_raw_result(result_path), cleanup_errors,
                )
                if raw_error is not None:
                    cleanup_errors.append(raw_error)
            report = _guarded_cleanup(
                "PURGE_FAILED",
                lambda: _purge_secret_files(output_root, known_secrets), cleanup_errors,
            )
            if report is not None:
                purge_report = report
            if purge_report["unscanned"]:
                cleanup_errors.append("PURGE_INCOMPLETE")
            if sealed_raw_result and result_path is not None:
                # The parent sealed this file itself from redacted bytes. Finding an
                # injected literal in it means the redaction missed a channel, and the
                # purge has just deleted the stage's only result: never a PASS.
                sealed_name = result_path.name
                if any(
                    sealed_name in purge_report[key]
                    for key in ("purged", "renamed", "unscanned")
                ):
                    cleanup_errors.append("SEALED_RESULT_PURGED")
    # Cleanup the child defeated leaves its credential on disk, so the stage cannot be
    # called clean even though the provider itself answered.
    if cleanup_errors and envelope.get("status") == "PASS":
        envelope["status"] = "BLOCKED"
        envelope["error_code"] = cleanup_errors[0]
    leftover_temp_paths = sorted(
        _direct_children(claude_temp) - temp_before
    ) if engine == "claude" else []
    return {
        "semantic": semantic,
        "envelope": envelope,
        "diagnostics": {
            "stderr_tail": redact_text(str(execution.get("stderr", "")), known_secrets)[-2000:],
            "stdout_tail": redact_text(str(execution.get("stdout", "")), known_secrets)[-2000:],
            "stdout_present": bool(execution.get("stdout")),
            # Every path below is a name the child chose, so all of them are redacted.
            "leftover_temp_paths": _redacted_paths(leftover_temp_paths, known_secrets),
            "purged_secret_files": _redacted_paths(purge_report["purged"], known_secrets),
            "renamed_secret_paths": _redacted_paths(purge_report["renamed"], known_secrets),
            "unscanned_paths": _redacted_paths(purge_report["unscanned"], known_secrets),
            "purge_notes": {
                redact_text(path, known_secrets): reason
                for path, reason in sorted(purge_report["notes"].items())
            },
            "cleanup_errors": cleanup_errors,
            # Signals the kernel refused on the way to the timeout envelope; kept so a
            # bounded BLOCKED result still says what could not be done.
            "process_signal_errors": [
                str(item) for item in (execution.get("signal_errors") or [])
            ],
            "output_root_tampered": tampered,
            # Honest scope, not a claim of full isolation: see process.DESCENDANT_CONTAINMENT.
            "provider_descendants_alive": bool(execution.get("descendants_alive")),
            "descendant_containment": DESCENDANT_CONTAINMENT,
        },
    }
