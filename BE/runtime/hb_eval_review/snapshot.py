"""Content-bound repository, evidence, and evaluation packet identities."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List

_EXCLUDED_PARTS = (".harness", "artifacts")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=str(repo), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ).stdout


def _is_excluded(relative: Path) -> bool:
    parts = relative.parts
    return len(parts) >= 4 and parts[0:2] == _EXCLUDED_PARTS and "eval-review" in parts


def _file_entry(repo: Path, path: Path) -> Dict[str, Any]:
    relative = path.relative_to(repo)
    stat = path.lstat()
    if path.is_symlink():
        content = os.readlink(str(path)).encode("utf-8", "surrogateescape")
        kind = "symlink"
    else:
        content = path.read_bytes()
        kind = "file"
    return {
        "path": relative.as_posix(),
        "kind": kind,
        "mode": stat.st_mode & 0o777,
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def compute_source_snapshot(repository: Path) -> Dict[str, Any]:
    """Bind HEAD, index state, status, and all current non-generated file contents."""
    repo = Path(repository).resolve()
    head = _git(repo, "rev-parse", "HEAD").decode().strip()
    index = _git(repo, "ls-files", "-s", "-z").decode("utf-8", "surrogateescape")
    # Index metadata distinguishes staged from unstaged content. Current file hashes
    # bind unstaged and untracked content. Raw `git status` is deliberately not
    # hashed because generated eval-review outputs must not invalidate their input.
    files: List[Dict[str, Any]] = []
    for path in sorted(repo.rglob("*"), key=lambda item: item.relative_to(repo).as_posix()):
        relative = path.relative_to(repo)
        if ".git" in relative.parts or _is_excluded(relative):
            continue
        if path.is_file() or path.is_symlink():
            files.append(_file_entry(repo, path))
    manifest = {"head": head, "index": index, "files": files}
    return {"source_snapshot_id": _digest(manifest), "manifest": manifest}


def compute_evidence_bundle_id(entries: Iterable[Dict[str, Any]]) -> str:
    """Return a deterministic ID for sanitized, hash-addressed evidence entries."""
    return _digest(list(entries))


def compute_packet_id(request: Dict[str, Any], source_snapshot_id: str, evidence_bundle_id: str) -> str:
    """Bind request/AC/exclusions to source and evidence identities."""
    return _digest(
        {
            "request": request,
            "source_snapshot_id": source_snapshot_id,
            "evidence_bundle_id": evidence_bundle_id,
        }
    )


def validate_packet_bindings(packet: Dict[str, Any], repository: Path) -> List[str]:
    """Recompute every packet identity from local source, request, and evidence bytes."""
    errors: List[str] = []
    repo = Path(repository).resolve()
    for field in ("packet_id", "source_snapshot_id", "evidence_bundle_id"):
        value = packet.get(field)
        if not isinstance(value, str) or not _HEX64.fullmatch(value):
            errors.append("PACKET_IDENTITY_FORMAT_INVALID")
    request = packet.get("request")
    entries = packet.get("evidence_entries")
    if not isinstance(request, dict):
        errors.append("PACKET_REQUEST_MISSING")
        request = {}
    if not isinstance(entries, list):
        errors.append("PACKET_EVIDENCE_ENTRIES_MISSING")
        entries = []

    try:
        actual_source = compute_source_snapshot(repo)["source_snapshot_id"]
    except (OSError, subprocess.CalledProcessError):
        errors.append("SOURCE_SNAPSHOT_UNAVAILABLE")
        actual_source = ""
    if actual_source != packet.get("source_snapshot_id"):
        errors.append("SOURCE_SNAPSHOT_MISMATCH")

    normalized_entries: List[Dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            errors.append("EVIDENCE_ENTRY_INVALID")
            continue
        entry_hash = entry.get("sha256")
        if not isinstance(entry_hash, str) or not _HEX64.fullmatch(entry_hash):
            errors.append("EVIDENCE_ENTRY_HASH_INVALID")
            continue
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            errors.append("EVIDENCE_ENTRY_PATH_ESCAPE")
            continue
        candidate = (repo / relative).resolve()
        if repo != candidate and repo not in candidate.parents:
            errors.append("EVIDENCE_ENTRY_PATH_ESCAPE")
            continue
        if not candidate.is_file() or candidate.is_symlink():
            errors.append("EVIDENCE_ENTRY_MISSING")
            continue
        actual_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
        normalized = dict(entry)
        normalized["path"] = relative.as_posix()
        normalized_entries.append(normalized)
        if actual_sha != entry.get("sha256"):
            errors.append("EVIDENCE_ENTRY_MISMATCH")

    actual_evidence = compute_evidence_bundle_id(normalized_entries)
    if actual_evidence != packet.get("evidence_bundle_id"):
        errors.append("EVIDENCE_BUNDLE_ID_MISMATCH")
    actual_packet = compute_packet_id(request, actual_source, actual_evidence)
    if actual_packet != packet.get("packet_id"):
        errors.append("PACKET_ID_MISMATCH")
    return list(dict.fromkeys(errors))
