"""Materialize a content-verified, symlink-safe source packet."""

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List

from .snapshot import PacketPolicyError, iter_packet_entries


def _entry(root: Path, path: Path) -> Dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    stat = path.lstat()
    if path.is_symlink():
        # A symlink's own mode is platform noise: os.symlink applies the umask, Linux
        # ignores link modes entirely, and lchmod is not portable. Carrying it would
        # make an identical copy compare unequal under umask 077, so the identity is the
        # link text alone. The link is still never dereferenced, here or in the copier.
        return {
            "path": relative, "kind": "symlink", "mode": None,
            "sha256": hashlib.sha256(
                os.readlink(str(path)).encode("utf-8", "surrogateescape")
            ).hexdigest(),
        }
    return {
        "path": relative, "kind": "file", "mode": stat.st_mode & 0o777,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _wrap(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"schema_version": "1.0", "tree_sha256": hashlib.sha256(payload).hexdigest(), "entries": entries}


def _manifest(source: Path) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
        if ".git" in path.relative_to(source).parts:
            continue
        if path.is_file() or path.is_symlink():
            entries.append(_entry(source, path))
    return _wrap(entries)


def materialize_source_packet(source: Path, packet: Path) -> Dict[str, Any]:
    """Copy source without dereferencing symlinks, verify content, then remove write bits."""
    source = Path(source).resolve()
    packet = Path(packet).resolve()
    destination = packet / "source"
    if destination.exists():
        raise FileExistsError(str(destination))
    packet.mkdir(parents=True, exist_ok=True)
    # One enumerator decides what a packet contains; nothing outside it is ever copied.
    before = _wrap(iter_packet_entries(source))
    destination.mkdir(parents=True)
    for entry in before["entries"]:
        target = destination / entry["path"]
        # Second, independent barrier: an entry whose parent resolves outside the
        # destination would be written through a link this loop just created.
        resolved_parent = target.parent.resolve()
        if resolved_parent != destination and destination not in resolved_parent.parents:
            shutil.rmtree(str(destination))
            raise PacketPolicyError("PACKET_PATH_UNSAFE", [entry["path"]])
        target.parent.mkdir(parents=True, exist_ok=True)
        origin = source / entry["path"]
        if entry["kind"] == "symlink":
            os.symlink(os.readlink(str(origin)), str(target))
        else:
            shutil.copy2(str(origin), str(target), follow_symlinks=False)
    copied = _manifest(destination)
    if before["entries"] != copied["entries"]:
        shutil.rmtree(str(destination))
        raise RuntimeError("SOURCE_CHANGED_OR_COPY_MISMATCH")
    for path in sorted(destination.rglob("*"), reverse=True):
        if path.is_symlink():
            continue
        if path.is_dir():
            path.chmod(0o555)
        else:
            path.chmod(0o444)
    destination.chmod(0o555)
    final = _manifest(destination)
    manifest = {"schema_version": "1.0", "source_tree_sha256": before["tree_sha256"], "materialized": final}
    (packet / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return manifest


def verify_materialized_packet(packet: Path, manifest: Dict[str, Any]) -> bool:
    """Verify all materialized bytes, link text, paths, and enforced modes."""
    return _manifest(Path(packet).resolve() / "source") == manifest.get("materialized")


def remove_materialized_packet(packet: Path) -> None:
    """Restore owner write bits only for controlled cleanup, then remove the packet."""
    packet = Path(packet).resolve()
    if not packet.exists():
        return
    for path in sorted(packet.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_symlink():
            continue
        try:
            path.chmod(0o700 if path.is_dir() else 0o600)
        except FileNotFoundError:
            pass
    packet.chmod(0o700)
    shutil.rmtree(str(packet))
