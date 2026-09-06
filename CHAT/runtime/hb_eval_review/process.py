"""Fresh subprocess control with allowlisted environment and bounded output."""

import os
import hashlib
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .redaction import redact_text

_COMMON_ENV = (
    "HOME", "USER", "LOGNAME", "SHELL", "PATH", "TMPDIR", "LANG", "LC_ALL", "TERM", "SSL_CERT_FILE",
    "SSL_CERT_DIR", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
)
_DIAGNOSTIC_LIMIT = 65536

# What the parent can actually contain, stated plainly: the child is started in its own
# session, so every descendant it forks stays in that one process group and is reaped on
# every exit path. A descendant that calls setsid() leaves the group, and macOS has no
# cgroup-style container to fall back on, so it is out of reach. Nothing here claims
# full isolation; `descendant_containment` carries this scope into the diagnostics.
DESCENDANT_CONTAINMENT = "process-group-only"
# The reap is bounded so a stuck descendant cannot stall the stage: SIGTERM, then
# SIGKILL, each with its own deadline, polled at a fixed interval.
_REAP_TERM_SECONDS = 2.0
_REAP_KILL_SECONDS = 1.0
_REAP_POLL_SECONDS = 0.02

_MACOS_SYSTEM_READ_ROOTS = (
    Path("/System"),
    Path("/usr"),
    Path("/bin"),
    Path("/sbin"),
    Path("/Library/Developer/CommandLineTools"),
    Path("/Library/Frameworks"),
    Path("/private/etc"),
    Path("/etc"),
    Path("/dev"),
)
_DENIED_EXECUTABLES = (
    Path("/usr/bin/security"),
    Path("/usr/bin/ssh"),
    Path("/usr/bin/scp"),
    Path("/usr/bin/sftp"),
)
_DENIED_MACH_SERVICES = (
    "com.apple.securityd",
    "com.apple.securityd.xpc",
    "com.apple.security.agent",
    "com.apple.security.authhost",
)


def minimal_environment(source: Optional[Mapping[str, str]] = None, extra_keys: Optional[List[str]] = None) -> Dict[str, str]:
    """Copy only explicitly permitted operating-system and provider variables."""
    source = source or os.environ
    keys = list(_COMMON_ENV) + list(extra_keys or [])
    return {key: source[key] for key in keys if key in source}


def _diagnostics(stdout: str, stderr: str) -> Dict[str, str]:
    """Redacted, bounded copies for humans; never the payload the parent parses."""
    return {
        "stdout_tail": redact_text(stdout)[-_DIAGNOSTIC_LIMIT:],
        "stderr_tail": redact_text(stderr)[-_DIAGNOSTIC_LIMIT:],
    }


def _tree_digest(root: Path) -> str:
    """Hash path, type, mode, and bytes/link text without dereferencing symlinks."""
    digest = hashlib.sha256()
    root = Path(root).resolve()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8", "surrogateescape")
        digest.update(relative + b"\0")
        if path.is_symlink():
            digest.update(b"L\0" + os.readlink(str(path)).encode("utf-8", "surrogateescape"))
        elif path.is_file():
            digest.update(b"F\0" + str(path.stat().st_mode & 0o777).encode() + b"\0" + path.read_bytes())
        elif path.is_dir():
            digest.update(b"D\0" + str(path.stat().st_mode & 0o777).encode())
    return digest.hexdigest()


def _sandbox_quote(path: Path) -> str:
    return str(Path(path).resolve()).replace("\\", "\\\\").replace('"', '\\"')


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_macos_sandbox_profile(
    protected_root: Path,
    output_root: Path,
    readable_roots: Optional[List[Path]] = None,
    writable_roots: Optional[List[Path]] = None,
    denied_read_roots: Optional[List[Path]] = None,
) -> str:
    """Build a deny-by-default Seatbelt profile for one provider process."""
    protected_root = Path(protected_root).resolve()
    output_root = Path(output_root).resolve()
    reads = list(_MACOS_SYSTEM_READ_ROOTS) + [protected_root, output_root]
    reads.extend(Path(item).resolve() for item in readable_roots or [])
    writes = [output_root]
    writes.extend(Path(item).resolve() for item in writable_roots or [])
    lines = [
        "(version 1)",
        "(deny default)",
        '(import "system.sb")',
        "(allow process*)",
        "(allow signal (target self))",
        "(allow sysctl-read)",
        "(allow mach-lookup)",
        "(allow network-outbound)",
    ]
    for root in reads:
        lines.append(f'(allow file-read* (subpath "{_sandbox_quote(root)}"))')
    ancestors = set()
    for root in reads + writes:
        parent = root.parent
        while parent != parent.parent:
            ancestors.add(parent)
            parent = parent.parent
    for parent in sorted(ancestors, key=lambda item: str(item)):
        lines.append(f'(allow file-read-metadata (literal "{_sandbox_quote(parent)}"))')
    for root in writes:
        lines.append(f'(allow file-write* (subpath "{_sandbox_quote(root)}"))')
    for root in denied_read_roots or []:
        lines.append(f'(deny file-read* (subpath "{_sandbox_quote(root)}"))')
    for executable in _DENIED_EXECUTABLES:
        lines.append(f'(deny process-exec (literal "{_sandbox_quote(executable)}"))')
    for service in _DENIED_MACH_SERVICES:
        lines.append(f'(deny mach-lookup (global-name "{service}"))')
    return "\n".join(lines)


def _process_group_is_empty(pgid: int) -> bool:
    """True only when no process remains in the group; a signal of 0 just probes it."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return False


def reap_process_group(pgid: int) -> bool:
    """Terminate everything the child left in its own group; True if any survived."""
    if pgid <= 1 or pgid == os.getpgid(0):
        return False
    for number, budget in (
        (signal.SIGTERM, _REAP_TERM_SECONDS), (signal.SIGKILL, _REAP_KILL_SECONDS)
    ):
        if _process_group_is_empty(pgid):
            return False
        try:
            os.killpg(pgid, number)
        except OSError:
            return False
        deadline = time.monotonic() + budget
        while not _process_group_is_empty(pgid):
            if time.monotonic() >= deadline:
                break
            time.sleep(_REAP_POLL_SECONDS)
    return not _process_group_is_empty(pgid)


def _decode_stream(raw: bytes) -> Tuple[str, bool]:
    """Decode child output for humans without ever raising on a hostile byte.

    The bytes belong to the child, so one byte that is not valid UTF-8 must not become
    an exception that escapes the stage. It is replaced, and the caller is told the
    stream was not decodable so the result can fail closed on its own terms.
    """
    try:
        return raw.decode("utf-8"), True
    except UnicodeDecodeError:
        return raw.decode("utf-8", "replace"), False


def _signal_group(pgid: int, number: int, errors: List[str]) -> None:
    """Signal the group, recording rather than raising when the kernel refuses.

    A group whose leader is already a zombie answers EPERM on macOS. That is a fact to
    report next to the timeout, not a traceback out of the stage.
    """
    try:
        os.killpg(pgid, number)
    except OSError as error:
        errors.append("KILLPG_" + type(error).__name__.upper())


def _drain_after_timeout(
    process: "subprocess.Popen", pgid: int, errors: List[str]
) -> Tuple[bytes, bytes]:
    """Stop the group and take what it already wrote, within a fixed budget.

    The final collection is bounded too: a descendant that left the group still holds
    the pipes, and waiting on it has no end. Partial output is what the stage gets.
    """
    _signal_group(pgid, signal.SIGTERM, errors)
    try:
        return process.communicate(timeout=_REAP_TERM_SECONDS)
    except subprocess.TimeoutExpired:
        pass
    _signal_group(pgid, signal.SIGKILL, errors)
    try:
        return process.communicate(timeout=_REAP_KILL_SECONDS)
    except subprocess.TimeoutExpired as expired:
        errors.append("OUTPUT_NOT_DRAINED")
        return expired.output or b"", expired.stderr or b""


def _collect_output(
    process: "subprocess.Popen", pgid: int, timeout_seconds: float
) -> Dict[str, Any]:
    """Collect one child's output as bytes; every failure becomes a BLOCKED result."""
    errors: List[str] = []
    timed_out = False
    try:
        raw_stdout, raw_stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            raw_stdout, raw_stderr = _drain_after_timeout(process, pgid, errors)
        except Exception as error:
            # An exception raised inside a handler is not caught by the one below it,
            # so the drain gets its own guard. The timeout still stands as the verdict.
            errors.append("DRAIN_" + type(error).__name__.upper())
            raw_stdout, raw_stderr = b"", b""
    except Exception as error:
        # The pipe itself failed. Nothing here can be trusted as output, so the stage
        # fails closed on the exception class alone; the payload is never carried.
        errors.append("COLLECT_" + type(error).__name__.upper())
        return {
            "status": "BLOCKED", "error_code": "PROCESS_OUTPUT_UNAVAILABLE",
            "exit_code": None, "stdout": "", "stderr": "", "signal_errors": errors,
        }
    stdout, stdout_ok = _decode_stream(raw_stdout or b"")
    stderr, stderr_ok = _decode_stream(raw_stderr or b"")
    if timed_out:
        status, error_code, exit_code = "BLOCKED", "PROCESS_TIMEOUT", None
    elif not (stdout_ok and stderr_ok):
        # Not valid UTF-8, so no parser downstream can read it. The stage stops on the
        # child's own output rather than guessing at a repaired payload.
        status, error_code = "BLOCKED", "PROCESS_OUTPUT_UNDECODABLE"
        exit_code = process.returncode
    elif process.returncode == 0:
        status, error_code, exit_code = "PASS", None, process.returncode
    else:
        status, error_code, exit_code = "BLOCKED", "PROCESS_NONZERO", process.returncode
    return {
        "status": status, "error_code": error_code, "exit_code": exit_code,
        "stdout": stdout, "stderr": stderr, "signal_errors": errors,
    }


def _release(process: "subprocess.Popen") -> None:
    """Close the parent's pipe ends and collect the leader, bounded either way."""
    for pipe in (process.stdout, process.stderr, process.stdin):
        if pipe is not None:
            try:
                pipe.close()
            except OSError:
                pass
    try:
        process.wait(timeout=_REAP_TERM_SECONDS + _REAP_KILL_SECONDS)
    except (subprocess.TimeoutExpired, OSError):
        pass


def run_read_only_process(
    command: List[str], cwd: Path, timeout_seconds: float, env: Optional[Mapping[str, str]] = None
) -> Dict[str, object]:
    """Run one bounded child process. CLI-level read-only flags belong in command."""
    child_env = dict(env) if env is not None else minimal_environment()
    process = subprocess.Popen(
        command,
        cwd=str(Path(cwd).resolve()),
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    # start_new_session makes the child the leader of its own group, so its pid is the
    # group id every descendant inherits.
    pgid = process.pid
    try:
        collected = _collect_output(process, pgid, timeout_seconds)
    finally:
        # A clean exit is not the end of the stage, and neither is a timeout or a
        # failure on the pipes: a worker the child left behind would go on writing into
        # the output root after the parent has sealed and purged it. commands/evaluate.md
        # promises this reap on every path, so it lives here and not on the returns.
        survivors = reap_process_group(pgid)
        _release(process)
    stdout = str(collected["stdout"])
    stderr = str(collected["stderr"])
    return {
        "status": collected["status"],
        "error_code": collected["error_code"],
        "exit_code": collected["exit_code"],
        "stdout": stdout,
        "stderr": stderr,
        "diagnostics": _diagnostics(stdout, stderr),
        "descendants_alive": survivors,
        "descendant_containment": DESCENDANT_CONTAINMENT,
        "signal_errors": collected["signal_errors"],
    }


def run_isolated_process(
    command: List[str], protected_root: Path, output_root: Path, packet: Dict[str, str],
    stage: str, engine: str, timeout_seconds: float,
    env: Optional[Mapping[str, str]] = None,
    denied_read_roots: Optional[List[Path]] = None,
    readable_roots: Optional[List[Path]] = None,
    writable_roots: Optional[List[Path]] = None,
) -> Dict[str, Any]:
    """Run one child under an OS-enforced source write barrier and emit parent facts."""
    protected_root = Path(protected_root).resolve()
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if output_root == protected_root or protected_root in output_root.parents:
        raise ValueError("output_root must be outside protected_root")
    run_id = str(uuid.uuid4())
    started = _utc_now()
    before = _tree_digest(protected_root)
    isolation_mode = "unsupported"
    wrapped = list(command)
    if sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").exists():
        profile = build_macos_sandbox_profile(
            protected_root,
            output_root,
            readable_roots=readable_roots,
            writable_roots=writable_roots,
            denied_read_roots=denied_read_roots,
        )
        wrapped = ["/usr/bin/sandbox-exec", "-p", profile, "--"] + wrapped
        isolation_mode = "macos-sandbox-exec"
    else:
        finished = _utc_now()
        empty_hash = hashlib.sha256(b"").hexdigest()
        return {"stdout": "", "stderr": "", "diagnostics": {},
                "descendants_alive": False, "signal_errors": [],
                "descendant_containment": DESCENDANT_CONTAINMENT, "envelope": {
            "schema_version": "2.0", "stage": stage, "engine": engine, "provider": engine,
            "run_id": run_id, "started_at": started, "finished_at": finished,
            "exit_code": None, "timed_out": False, "fresh_process": True,
            "session_resumed": False, "isolation_mode": isolation_mode,
            "source_snapshot_before": packet["source_snapshot_id"],
            "source_snapshot_after": packet["source_snapshot_id"],
            "packet_id": packet["packet_id"], "evidence_bundle_id": packet["evidence_bundle_id"],
            "repository_mutated": False, "result_sha256": empty_hash,
            "status": "BLOCKED", "error_code": "ISOLATION_UNAVAILABLE",
        }}

    result = run_read_only_process(wrapped, protected_root, timeout_seconds, env)
    after = _tree_digest(protected_root)
    mutated = before != after
    stdout = str(result.get("stdout", ""))
    timed_out = result.get("error_code") == "PROCESS_TIMEOUT"
    # A descendant still running owns a write handle into the output root, so the stage
    # cannot be called clean even when the child itself exited zero.
    descendants_alive = bool(result.get("descendants_alive"))
    status = (
        "PASS" if result.get("status") == "PASS" and not mutated and not descendants_alive
        else "BLOCKED"
    )
    error_code = "REPOSITORY_MUTATION" if mutated else (
        result.get("error_code")
        or ("PROVIDER_DESCENDANTS_ALIVE" if descendants_alive else None)
    )
    envelope = {
        "schema_version": "2.0", "stage": stage, "engine": engine, "provider": engine,
        "run_id": run_id, "started_at": started, "finished_at": _utc_now(),
        "exit_code": result.get("exit_code"), "timed_out": timed_out,
        "fresh_process": True, "session_resumed": False, "isolation_mode": isolation_mode,
        "source_snapshot_before": packet["source_snapshot_id"],
        "source_snapshot_after": packet["source_snapshot_id"] if not mutated else "MUTATED:" + after,
        "packet_id": packet["packet_id"], "evidence_bundle_id": packet["evidence_bundle_id"],
        "repository_mutated": mutated, "result_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
        "status": status, "error_code": error_code,
    }
    return {
        "stdout": stdout, "stderr": result.get("stderr", ""),
        "diagnostics": result.get("diagnostics", {}),
        "descendants_alive": descendants_alive,
        "descendant_containment": result.get(
            "descendant_containment", DESCENDANT_CONTAINMENT
        ),
        "signal_errors": list(result.get("signal_errors") or []),
        "envelope": envelope,
    }
