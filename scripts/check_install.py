#!/usr/bin/env python3
"""Read-only install inventory for the seven dev-harness plugins.

Compares the versions declared in this repository's marketplace files with what
is registered/cached for Claude Code (~/.claude) and Codex (~/.codex).

- Never writes anything. Only reads JSON/TOML/directory names.
- Exit 1 only on a confirmed version MISMATCH, or when a plugin named in
  --require is NOT_INSTALLED/UNKNOWN in either CLI.
- The version actually loaded by a running session cannot be observed from
  disk, so `loaded` is always UNKNOWN (null in --json).
- Claude Code may register one plugin under several scopes; the plugin counts as
  MATCH when any registered entry has the expected version and MISMATCH only when
  entries exist and none matches. `enabled` is read from settings.json merged
  with settings.local.json; a missing key is reported as UNKNOWN (null), not false.
- A --require name that is not one of the marketplace plugins is an error (exit 1).
- Exit 2 when the repository marketplace files cannot be read or declare fewer than 7
  plugins (the inventory would otherwise be silently empty).

Override the homes for tests or other machines:
  HB_CLAUDE_HOME (default ~/.claude), HB_CODEX_HOME (default ~/.codex).
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
UNKNOWN = "UNKNOWN"
NOT_INSTALLED = "NOT_INSTALLED"
MATCH = "MATCH"
MISMATCH = "MISMATCH"


def read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_text(path: Path) -> Optional[str]:
    """None on any read failure (missing, unreadable, not UTF-8) — callers report UNKNOWN."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None


def cache_versions(base: Path) -> List[str]:
    if not base.is_dir():
        return []
    return sorted(entry.name for entry in base.iterdir() if entry.is_dir())


_TABLE = r"""(?:plugins|"plugins"|'plugins')"""
_KEY = r"""(?:[A-Za-z0-9_-]+|"[^"]*"|'[^']*')"""
_HEADER = re.compile(r"^\[\s*" + _TABLE + r"""\s*\.\s*(["'])(.+?)\1\s*\]\s*(#.*)?$""")
_PLUGINS_TABLE = re.compile(r"^\[\s*" + _TABLE + r"\s*\]\s*(#.*)?$")
_ANY_PLUGINS_HEADER = re.compile(r"^\[\s*" + _TABLE + r"(?![A-Za-z0-9_-])")
_INLINE = re.compile(r"""^(["'])(.+?)\1\s*=\s*\{(.*)\}\s*(#.*)?$""")
_DOTTED = re.compile(r"""^(["'])(.+?)\1\s*\.\s*([A-Za-z0-9_-]+)\s*=\s*(.*)$""")
_ENABLED = re.compile(r"""enabled\s*=\s*["']?(true|false)["']?(?![A-Za-z0-9_-])""", re.IGNORECASE)
_MULTILINE_OPEN = re.compile(r"^" + _KEY + r"(?:\s*\.\s*" + _KEY + r")*\s*=\s*(\"\"\"|''')")
_KEY_ASSIGN = re.compile(r"^" + _KEY + r"(?:\s*\.\s*" + _KEY + r")*\s*=")


def _flag(text: str) -> Optional[bool]:
    found = _ENABLED.search(text)
    return None if not found else found.group(1).lower() == "true"


def _closes(text: str, delim: str) -> bool:
    """True when `text` holds an unescaped occurrence of the multi-line delimiter.

    A backslash escapes the next character only inside basic (double-quoted) strings,
    so a backslash immediately before the closing triple quote does not terminate the
    string; literal (single-quoted) strings have no escapes at all.
    """
    start = 0
    while True:
        index = text.find(delim, start)
        if index < 0:
            return False
        if delim == "'''":
            return True
        backslashes = 0
        probe = index - 1
        while probe >= 0 and text[probe] == "\\":
            backslashes += 1
            probe -= 1
        if backslashes % 2 == 0:
            return True
        start = index + 1


def parse_toml_plugins(text: str) -> Tuple[Dict[str, Optional[bool]], bool]:
    """Tolerant parser for Codex plugin entries.

    Returns (plugins, certain). `plugins` maps "name@marketplace" to True/False, or None
    when the key exists without a readable flag. `certain` is False when the file holds
    plugin configuration this parser cannot classify (a plugins header in an unknown
    form, an assignment under [plugins] it cannot read, an enabled value that is not a
    boolean, or an unterminated multi-line string); callers must then report UNKNOWN
    instead of confirming "not registered".

    Understood forms: [plugins."name@mkt"] / [plugins.'name@mkt'] / ["plugins"."name@mkt"]
    headers with optional trailing comments; enabled = true | false | "true" | 'false';
    a [plugins] (or ["plugins"]) table with inline entries "name@mkt" = { enabled = true }
    or dotted keys "name@mkt".enabled = true. Lines inside triple-quoted multi-line
    strings are skipped whatever their key looks like (bare, quoted, dotted), honouring
    backslash-escaped terminators in basic strings, so a configuration example inside
    developer_instructions is never read as a registration.
    """
    plugins: Dict[str, Optional[bool]] = {}
    current: Optional[str] = None
    in_table = False
    certain = True
    string_delim: Optional[str] = None
    for raw in text.splitlines():
        line = raw.strip()
        if string_delim is not None:
            if _closes(line, string_delim):
                string_delim = None
            continue
        if not line or line.startswith("#"):
            continue
        opened = _MULTILINE_OPEN.match(line)
        if opened:
            delim = opened.group(1)
            if not _closes(line[opened.end():], delim):
                string_delim = delim
            continue
        header = _HEADER.match(line)
        if header:
            current, in_table = header.group(2), False
            plugins.setdefault(current, None)
            continue
        if _PLUGINS_TABLE.match(line):
            current, in_table = None, True
            continue
        if line.startswith("["):
            if _ANY_PLUGINS_HEADER.match(line):
                certain = False  # a plugins header in a form we do not understand
            current, in_table = None, False
            continue
        if current is not None:
            if line.lower().startswith("enabled"):
                flag = _flag(line)
                if flag is None:
                    certain = False  # enabled present but not a boolean we can read
                else:
                    plugins[current] = flag
            continue
        if in_table:
            inline = _INLINE.match(line)
            dotted = _DOTTED.match(line)
            if inline:
                plugins[inline.group(2)] = _flag(inline.group(3))
            elif dotted:
                key, leaf, value = dotted.group(2), dotted.group(3), dotted.group(4)
                plugins.setdefault(key, None)
                if leaf.lower() == "enabled":
                    flag = _flag("enabled = " + value)
                    if flag is None:
                        certain = False
                    else:
                        plugins[key] = flag
            elif _KEY_ASSIGN.match(line):
                certain = False  # an assignment under [plugins] we could not read
    if string_delim is not None:
        certain = False  # unterminated multi-line string
    return plugins, certain


def version_status(versions: List[str], expected: str, registry_present: bool) -> str:
    if not registry_present:
        return UNKNOWN
    if not versions:
        return NOT_INSTALLED
    return MATCH if expected in versions else MISMATCH


def read_enabled_flags(home: Path) -> Optional[Dict[str, Any]]:
    """settings.json merged with settings.local.json (local wins); None if neither is readable."""
    merged: Optional[Dict[str, Any]] = None
    for filename in ("settings.json", "settings.local.json"):
        settings = read_json(home / filename)
        if isinstance(settings, dict) and isinstance(settings.get("enabledPlugins"), dict):
            merged = dict(merged or {})
            merged.update(settings["enabledPlugins"])
    return merged


def inspect_claude(home: Path, marketplace: str, name: str, expected: str) -> Dict[str, Any]:
    registry = read_json(home / "plugins" / "installed_plugins.json")
    flags = read_enabled_flags(home)
    key = "%s@%s" % (name, marketplace)
    present = isinstance(registry, dict) and isinstance(registry.get("plugins"), dict)
    versions: List[str] = []
    unreadable = False
    if present:
        entries = registry["plugins"].get(key)
        if isinstance(entries, dict):
            entries = [entries]
        if entries is None:
            entries = []
        if isinstance(entries, list):
            versions = [str(entry.get("version")) for entry in entries if isinstance(entry, dict) and entry.get("version")]
            unreadable = bool(entries) and not versions
        else:
            unreadable = True  # unknown registry shape: do not claim NOT_INSTALLED
    enabled: Optional[bool] = None
    if flags is not None and key in flags:
        enabled = bool(flags[key])
    if unreadable:
        installed, status = UNKNOWN, UNKNOWN
    else:
        installed = ",".join(versions) if versions else (NOT_INSTALLED if present else UNKNOWN)
        status = version_status(versions, expected, present)
    return {
        "installed": installed,
        "installed_all": versions,
        "enabled": enabled,
        "cached": cache_versions(home / "plugins" / "cache" / marketplace / name),
        "loaded": None,
        "status": status,
    }


def inspect_codex(home: Path, marketplace: str, name: str, expected: str) -> Dict[str, Any]:
    config = read_text(home / "config.toml")
    cached = cache_versions(home / "plugins" / "cache" / marketplace / name)
    key = "%s@%s" % (name, marketplace)
    registered: Optional[bool] = None
    enabled: Optional[bool] = None
    if config is not None:
        plugins, certain = parse_toml_plugins(config)
        if key in plugins:
            registered, enabled = True, plugins[key]
        elif certain:
            registered, enabled = False, False
        # otherwise the file holds plugin config this parser cannot read: leave UNKNOWN
    # Codex keeps no version registry; cache directories are the only version evidence.
    if cached:
        status = MATCH if expected in cached else MISMATCH
    elif config is None:
        status = UNKNOWN
    else:
        status = NOT_INSTALLED
    return {
        "registered": registered,
        "enabled": enabled,
        "cached": cached,
        "loaded": None,
        "status": status,
    }


def build_rows(claude_home: Path, codex_home: Path) -> Dict[str, Any]:
    claude_mkt = read_json(REPO / ".claude-plugin" / "marketplace.json") or {}
    codex_mkt = read_json(REPO / ".agents" / "plugins" / "marketplace.json") or {}
    codex_versions = {p.get("name"): p.get("version") for p in codex_mkt.get("plugins", [])}
    rows: List[Dict[str, Any]] = []
    for plugin in claude_mkt.get("plugins", []):
        name, expected = plugin.get("name"), plugin.get("version")
        if not name or not expected:
            continue
        row = {
            "plugin": name,
            "expected": expected,
            "claude": inspect_claude(claude_home, claude_mkt.get("name", ""), name, expected),
            "codex": inspect_codex(codex_home, codex_mkt.get("name", ""), name, expected),
        }
        if codex_versions.get(name) not in (None, expected):
            row["note"] = "codex marketplace declares %s" % codex_versions.get(name)
        rows.append(row)
    return {
        "repo": str(REPO),
        "claude_home": str(claude_home),
        "codex_home": str(codex_home),
        "claude_marketplace": claude_mkt.get("name", ""),
        "codex_marketplace": codex_mkt.get("name", ""),
        "rows": rows,
    }


def show(value: Any) -> str:
    return UNKNOWN if value is None else str(value)


def render_table(report: Dict[str, Any]) -> str:
    header = ("plugin", "expected", "claude installed", "enabled", "claude cached", "codex cached", "enabled", "loaded", "status claude/codex")
    lines = [list(header)]
    for row in report["rows"]:
        c, x = row["claude"], row["codex"]
        lines.append([
            row["plugin"], row["expected"], show(c["installed"]), show(c["enabled"]), ",".join(c["cached"]) or "-",
            ",".join(x["cached"]) or "-", show(x["enabled"]), "%s/%s" % (show(c["loaded"]), show(x["loaded"])),
            "%s/%s" % (c["status"], x["status"]),
        ])
    widths = [max(len(line[i]) for line in lines) for i in range(len(header))]
    out = []
    for index, line in enumerate(lines):
        out.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(line)).rstrip())
        if index == 0:
            out.append("  ".join("-" * w for w in widths))
    for row in report["rows"]:
        if row.get("note"):
            out.append("note %s: %s" % (row["plugin"], row["note"]))
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only plugin install inventory (repo vs Claude Code vs Codex).")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--require", default="", help="comma-separated plugins that must be installed in both CLIs")
    args = parser.parse_args(argv)

    claude_home = Path(os.environ.get("HB_CLAUDE_HOME", "~/.claude")).expanduser()
    codex_home = Path(os.environ.get("HB_CODEX_HOME", "~/.codex")).expanduser()
    report = build_rows(claude_home, codex_home)
    if not report["claude_marketplace"] or not report["codex_marketplace"] or len(report["rows"]) < 7:
        sys.stderr.write(
            "check-install: cannot read the repository marketplace files (%s/.claude-plugin/marketplace.json, "
            ".agents/plugins/marketplace.json) or fewer than 7 plugins declared (%d) — run from a dev-harness checkout\n"
            % (REPO, len(report["rows"]))
        )
        return 2

    required = [item.strip() for item in args.require.split(",") if item.strip()]
    known = {row["plugin"] for row in report["rows"]}
    required_unknown = [item for item in required if item not in known]
    mismatches = [row["plugin"] for row in report["rows"] if MISMATCH in (row["claude"]["status"], row["codex"]["status"])]
    required_missing = [
        row["plugin"] for row in report["rows"]
        if row["plugin"] in required and any(status in (NOT_INSTALLED, UNKNOWN) for status in (row["claude"]["status"], row["codex"]["status"]))
    ]
    exit_code = 1 if (mismatches or required_missing or required_unknown) else 0
    report.update({
        "required": required, "required_missing": required_missing, "required_unknown": required_unknown,
        "mismatches": mismatches, "exit_code": exit_code,
    })

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("repo marketplace: %s (claude) / %s (codex)" % (report["claude_marketplace"], report["codex_marketplace"]))
        print("claude home: %s\ncodex home:  %s" % (report["claude_home"], report["codex_home"]))
        print(render_table(report))
        print("loaded = UNKNOWN: the version a running session actually loaded cannot be read from disk.")
        if mismatches:
            print("MISMATCH: %s" % ", ".join(mismatches))
        if required_missing:
            print("REQUIRED but missing/unknown: %s" % ", ".join(required_missing))
        if required_unknown:
            print("REQUIRED name not in marketplace: %s" % ", ".join(required_unknown))
        print("exit %d" % exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
