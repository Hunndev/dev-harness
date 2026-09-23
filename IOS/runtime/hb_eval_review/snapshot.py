"""Content-bound repository, evidence, and evaluation packet identities."""

import hashlib
import json
import os
import re
import string
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

_EXCLUDED_PARTS = (".harness", "artifacts")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
# Dependency and build caches are large, machine-local, and never part of the change
# under evaluation. They apply to untracked paths only and match directory components
# only, so a tracked `dist/index.js` and a regular file named `scripts/build` both stay
# in the packet. Cache paths are dropped silently; secret material is not.
_CACHE_PARTS = frozenset({
    "node_modules", ".gradle", "build", "dist", "__pycache__", ".venv", "venv",
    "Pods", "DerivedData", ".next", ".turbo", ".cache", "target",
})
_SECRET_NAMES = frozenset({".env", "local.properties"})
_SECRET_SUFFIXES = (".jks", ".keystore", ".p12", ".pfx", ".pem", ".key")
_SECRET_PARTS = frozenset({"secrets"})
# The secret patterns are ASCII, so case folding is done with an explicit ASCII table
# instead of str.lower(): the match must not depend on the platform's locale or on
# Unicode case rules for characters outside the patterns.
_ASCII_FOLD = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


class PacketPolicyError(ValueError):
    """Refuse to build a packet: secret material, or a path the copier cannot trust."""

    def __init__(self, code: str, paths: Iterable[str]) -> None:
        self.code = code
        self.paths = sorted(paths)
        super().__init__(code)


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compute_tree_sha256(entries: Iterable[Dict[str, Any]]) -> str:
    """Hash a packet entry list the way a materialized copy is bound to its source.

    ``materialize_source_packet`` records this over the entries it copied as
    ``source_tree_sha256``; ``run`` recomputes it over a fresh snapshot's ``files`` right
    after the copy. One helper on purpose: the two sides must never hash differently.
    """
    return _digest(list(entries))


def compute_tdd_sut_sha256(manifest: Dict[str, Any], artifact_relative: Path) -> str:
    """Bind tested source entries without letting this run's own evidence self-invalidate.

    This is a view of an already verified source manifest, not a new enumerator or
    a change to packet exclusions. Paths, kinds, modes and content digests remain
    bound; only the exact current artifact directory is omitted from this view.
    """
    prefix = artifact_relative.as_posix().rstrip('/') + '/'
    return compute_tree_sha256(entry for entry in manifest['files']
                               if not entry['path'].startswith(prefix))


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=str(repo), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ).stdout


def _is_excluded(relative: Path, tracked: bool) -> bool:
    parts = relative.parts
    if len(parts) >= 4 and parts[0:2] == _EXCLUDED_PARTS and "eval-review" in parts:
        return True
    # A tracked file is part of the change under review wherever it lives; only
    # untracked content under a cache directory name is machine-local build output.
    if tracked:
        return False
    return bool(_CACHE_PARTS.intersection(parts[:-1]))


def _fold(value: str) -> str:
    return value.translate(_ASCII_FOLD)


def _is_secret_material(relative: Path) -> bool:
    """Refuse the entry when *any* component names secret material, not just the leaf.

    A leaf-only rule let `.env.local/credentials.txt` and `certs.pem/server.txt` reach
    the packet: the credential is in a file whose own name is ordinary, under a
    directory named exactly what the deny list refuses. The `secrets/` component rule
    was already whole-path; the rest now match it.
    """
    for part in relative.parts:
        folded = _fold(part)
        if folded in _SECRET_NAMES or folded in _SECRET_PARTS:
            return True
        if folded.startswith(".env."):
            return True
        # The rule is the suffix itself, so the component only has to end with one:
        # `os.path.splitext` reports no extension for `.pem` or `..pem`, and the bare
        # name test only caught `.pem`, so one extra leading dot walked past a rule
        # written to refuse `.pem` in every component. Same six suffixes, same folding;
        # nothing new is denied, and `.pemx` or `notes..pem.txt` still are not.
        if folded.endswith(_SECRET_SUFFIXES):
            return True
    return False


def _names(raw: bytes) -> set:
    return {item for item in raw.decode("utf-8", "surrogateescape").split("\0") if item}


def _allowlisted_paths(repo: Path) -> List[Tuple[Path, bool]]:
    """Tracked plus untracked-and-not-ignored paths; gitignored content never enters.

    The two lists are queried separately so each path keeps its origin: the cache
    deny-list applies to untracked build output only.
    """
    tracked = _names(_git(repo, "ls-files", "-z", "--cached"))
    others = _names(_git(repo, "ls-files", "-z", "--others", "--exclude-standard"))
    return sorted(
        ((Path(name), name in tracked) for name in tracked | others),
        key=lambda item: item[0].as_posix(),
    )


def _gitlink_paths(repo: Path) -> set:
    """Index entries recorded with the gitlink mode: a nested repository, not content.

    `git ls-files` reports a gitlink under its own path, but the working-tree entry is a
    directory, so the file/symlink filter below dropped it silently and every byte inside
    the nested repository stayed out of the snapshot. Reading through it would mean
    implementing recursive submodule enumeration, so the packet refuses the layout.
    """
    raw = _git(repo, "ls-files", "-s", "-z").decode("utf-8", "surrogateescape")
    paths = set()
    for record in raw.split("\0"):
        if not record:
            continue
        meta, _, name = record.partition("\t")
        if meta.split(" ", 1)[0] == "160000":
            paths.add(name)
    return paths


def _untracked_repository_paths(repo: Path) -> set:
    """Untracked names git reports as a directory: a repository it refused to descend into.

    `git ls-files --others` lists files, with one exception — an embedded repository comes
    back as the single name `nested/`, trailing slash and all, because git stops at the
    boundary. That entry is a directory, so the file/symlink filter dropped it and two
    different inner working trees produced one identical snapshot. It is the same boundary
    a gitlink names, reached without an index entry.
    """
    names = _names(_git(repo, "ls-files", "-z", "--others", "--exclude-standard"))
    return {name.rstrip("/") for name in names if name.endswith("/")}


def _has_symlinked_parent(repo: Path, relative: Path) -> bool:
    """True when any directory component of the entry is itself a link.

    Git does not produce this layout on its own, but a stale index entry under a
    directory that has since become a symlink would let a copier write through it.
    """
    prefix = Path()
    for part in relative.parts[:-1]:
        prefix = prefix / part
        if (repo / prefix).is_symlink():
            return True
    return False


def iter_packet_entries(repository: Path) -> List[Dict[str, Any]]:
    """The single enumerator both the snapshot and the materialized packet are built from."""
    repo = Path(repository).resolve()
    gitlinks = _gitlink_paths(repo)
    embedded = _untracked_repository_paths(repo)
    candidates: List[Path] = []
    unsafe: List[str] = []
    nested: List[str] = []
    inner: List[str] = []
    for relative, tracked in _allowlisted_paths(repo):
        if ".git" in relative.parts or _is_excluded(relative, tracked):
            continue
        if relative.as_posix() in gitlinks:
            # Initialized, dirty or absent, the entry is a repository boundary this
            # enumerator cannot see past; it blocks instead of enumerating nothing.
            nested.append(relative.as_posix())
            continue
        if relative.as_posix() in embedded:
            inner.append(relative.as_posix())
            continue
        if _has_symlinked_parent(repo, relative):
            unsafe.append(relative.as_posix())
            continue
        path = repo / relative
        if not (path.is_symlink() or path.is_file()):
            continue
        candidates.append(relative)
    if unsafe:
        raise PacketPolicyError("PACKET_PATH_UNSAFE", unsafe)
    if nested:
        raise PacketPolicyError("PACKET_GITLINK_UNSUPPORTED", nested)
    if inner:
        # Reported under its own code: this one has no index entry, so an operator
        # reading the refusal is not sent looking for a gitlink that does not exist.
        raise PacketPolicyError("PACKET_EMBEDDED_REPOSITORY_UNSUPPORTED", inner)
    secrets = [relative.as_posix() for relative in candidates if _is_secret_material(relative)]
    if secrets:
        raise PacketPolicyError("PACKET_SECRET_MATERIAL_PRESENT", secrets)
    return [_file_entry(repo, repo / relative) for relative in candidates]


def _file_entry(repo: Path, path: Path) -> Dict[str, Any]:
    relative = path.relative_to(repo)
    if path.is_symlink():
        # Symlink modes are not portable and not preserved by any copier, so the entry
        # is bound to the link text only. `materialize._entry` must agree exactly.
        return {
            "path": relative.as_posix(),
            "kind": "symlink",
            "mode": None,
            "sha256": hashlib.sha256(
                os.readlink(str(path)).encode("utf-8", "surrogateescape")
            ).hexdigest(),
        }
    return {
        "path": relative.as_posix(),
        "kind": "file",
        "mode": path.lstat().st_mode & 0o777,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def compute_source_snapshot(repository: Path) -> Dict[str, Any]:
    """Bind HEAD, index state, status, and all current non-generated file contents."""
    repo = Path(repository).resolve()
    head = _git(repo, "rev-parse", "HEAD").decode().strip()
    index = _git(repo, "ls-files", "-s", "-z").decode("utf-8", "surrogateescape")
    # Index metadata distinguishes staged from unstaged content. Current file hashes
    # bind unstaged and untracked content. Raw `git status` is deliberately not
    # hashed because generated eval-review outputs must not invalidate their input.
    manifest = {"head": head, "index": index, "files": iter_packet_entries(repo)}
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
    except PacketPolicyError as error:
        errors.append(error.code)
        actual_source = ""
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
