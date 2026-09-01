"""Codex fresh adapter; the parent process owns the enforced read-only boundary."""

import os
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from ..process import minimal_environment


def codex_environment(source: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Allow Codex-owned state while excluding every Claude auth variable."""
    return minimal_environment(source or os.environ, ["CODEX_HOME"])


def build_codex_command(
    repository: Path, schema_path: Path, result_path: Path, prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> List[str]:
    """Build an ephemeral Codex invocation inside the parent's macOS/container sandbox.

    Codex's own read-only sandbox cannot be nested inside macOS sandbox-exec
    (sandbox_apply exits 71). The outer parent sandbox still denies protected
    source writes and peer-output reads, then detects mutation by tree digest.
    """
    command = [
        "codex", "exec",
        "--ephemeral",
        "--sandbox", "danger-full-access",
        "--skip-git-repo-check",
        "--cd", str(repository),
        "--output-schema", str(schema_path),
        "--output-last-message", str(result_path),
    ]
    if model:
        command.extend(["--model", model])
    command.append(prompt if prompt is not None else "-")
    return command
