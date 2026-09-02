"""Fresh subprocess control with allowlisted environment and bounded output."""

import os
import hashlib
import re
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

_COMMON_ENV = (
    "HOME", "USER", "LOGNAME", "SHELL", "PATH", "TMPDIR", "LANG", "LC_ALL", "TERM", "SSL_CERT_FILE",
    "SSL_CERT_DIR", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
)
_SECRET_RE = re.compile(r"(?i)(api[_-]?key|password|secret|token)(\s*[:=]\s*)[^\s,]+")

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


def _sanitize(text: str) -> str:
    return _SECRET_RE.sub(lambda match: match.group(1) + match.group(2) + "[REDACTED]", text)[:65536]


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
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return {
            "status": "BLOCKED",
            "error_code": "PROCESS_TIMEOUT",
            "exit_code": None,
            "stdout": _sanitize(stdout),
            "stderr": _sanitize(stderr),
        }
    status = "PASS" if process.returncode == 0 else "BLOCKED"
    return {
        "status": status,
        "error_code": None if status == "PASS" else "PROCESS_NONZERO",
        "exit_code": process.returncode,
        "stdout": _sanitize(stdout),
        "stderr": _sanitize(stderr),
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
        return {"stdout": "", "stderr": "", "envelope": {
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
    status = "PASS" if result.get("status") == "PASS" and not mutated else "BLOCKED"
    error_code = "REPOSITORY_MUTATION" if mutated else result.get("error_code")
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
    return {"stdout": stdout, "stderr": result.get("stderr", ""), "envelope": envelope}
