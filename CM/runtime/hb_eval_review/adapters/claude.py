"""Claude Code fresh read-only adapter contract."""

import os
from typing import Dict, List, Mapping, Optional

from ..process import minimal_environment

_CLAUDE_AUTH = ["CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"]


def claude_environment(source: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Allow Claude auth but exclude Codex-specific state and unrelated secrets."""
    return minimal_environment(source or os.environ, _CLAUDE_AUTH)


def build_claude_command(packet_prompt: str, schema_json: str, model: Optional[str] = None) -> List[str]:
    """Build a fresh, non-persistent, structured, read-only Claude invocation."""
    command = [
        "claude", "-p", packet_prompt,
        "--no-session-persistence",
        "--output-format", "json",
        "--json-schema", schema_json,
        "--permission-mode", "plan",
        "--allowedTools", "Read,Glob,Grep",
        "--safe-mode",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--mcp-config", '{"mcpServers":{}}',
    ]
    if model:
        command.extend(["--model", model])
    return command
