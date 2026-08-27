"""Execute one real provider stage and bind semantic output to a parent envelope."""

import hashlib
import json
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


def run_provider_stage(
    engine: str,
    stage: str,
    packet: Dict[str, str],
    packet_source: Path,
    output_root: Path,
    prompt: str,
    timeout_seconds: float = 240,
    peer_output_root: Optional[Path] = None,
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

    if engine == "claude":
        command = build_claude_command(prompt, json.dumps(claude_schema, separators=(",", ":")))
        environment = claude_environment()
        denied.append(home / ".codex")
    elif engine == "codex":
        result_path = output_root / "semantic-result.json"
        command = build_codex_command(packet_source, semantic_schema, result_path, prompt)
        environment = codex_environment()
        denied.append(home / ".claude")
    else:
        raise ValueError("unsupported engine")

    execution = run_isolated_process(
        command, packet_source, output_root, packet, stage, engine, timeout_seconds,
        environment, denied_read_roots=[Path(item) for item in denied],
    )
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
