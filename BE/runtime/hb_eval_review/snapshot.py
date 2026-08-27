"""Content-bound repository, evidence, and evaluation packet identities."""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List

_EXCLUDED_PARTS = (".harness", "artifacts")


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
