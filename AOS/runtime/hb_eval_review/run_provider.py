"""Execute one real provider stage and bind semantic output to a parent envelope."""

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from .adapters.claude import build_claude_command, claude_environment
from .adapters.codex import build_codex_command, codex_environment
from .process import run_isolated_process


def _canonical(value: Dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _extract_claude(stdout: str) -> Dict[str, Any]:
    outer = json.loads(stdout)
    semantic = outer.get("structured_output")
    if semantic is None:
        semantic = outer.get("result")
    if isinstance(semantic, str):
        semantic = json.loads(semantic)
    if not isinstance(semantic, dict):
        raise ValueError("CLAUDE_SEMANTIC_RESULT_MISSING")
    return semantic


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

    try:
        environment = _ephemeral_environment(engine, output_root)
        execution = run_isolated_process(
            command, packet_source, output_root, packet, stage, engine, timeout_seconds,
            environment, denied_read_roots=[Path(item) for item in denied],
            readable_roots=[Path.home() / ".npm-global"],
        )
    finally:
        if provider_home.exists():
            shutil.rmtree(str(provider_home))
    envelope = execution["envelope"]
    semantic: Dict[str, Any] = {}
    if envelope["status"] == "PASS":
        try:
            if engine == "claude":
                semantic = _extract_claude(str(execution["stdout"]))
            else:
                result_path = output_root / "semantic-result.json"
                semantic = json.loads(result_path.read_text())
                if not isinstance(semantic, dict):
                    raise ValueError("CODEX_SEMANTIC_RESULT_MISSING")
            envelope["result_sha256"] = hashlib.sha256(_canonical(semantic)).hexdigest()
        except (OSError, ValueError, json.JSONDecodeError):
            envelope["status"] = "BLOCKED"
            envelope["error_code"] = "RESULT_MALFORMED"
    return {
        "semantic": semantic,
        "envelope": envelope,
        "diagnostics": {
            "stderr_tail": str(execution.get("stderr", ""))[-2000:],
            "stdout_tail": str(execution.get("stdout", ""))[-2000:],
            "stdout_present": bool(execution.get("stdout")),
        },
    }
