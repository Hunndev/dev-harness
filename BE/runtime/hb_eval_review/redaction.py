"""One definition of secret redaction for both free text and parsed JSON values."""

import re
from array import array
from typing import Any, Dict, Iterable, List, Sequence, Tuple

REDACTED = "[REDACTED]"


class RedactionCollisionError(ValueError):
    """Two distinct keys redacted to one name; the payload is refused, not merged."""


_MIN_KNOWN_SECRET = 8

# One keyword list for both substitution and detection. The value class stops at
# JSON/YAML punctuation so redacting text never eats a closing quote or bracket, and
# an optional quote on either side of the key covers `"token": "x"` as well as
# `token=x`. Structured payloads are still redacted per string value, not as text.
_SECRET_KEYWORDS = (
    r"api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token"
    r"|password|passwd|secret|token|authorization|bearer"
)
_VALUE_CLASS = r"[^\s,\"'}\]]"
# `=>` is one delimiter, so `=` is only a delimiter when no `>` follows it. Without the
# guard the alternation may give `=>` up and retry as `=`, and `>` — an ordinary value
# character — then starts a value: `token=>[REDACTED]`, this runtime's own output, reads
# as the value `>[REDAC…` and the detector flags it.
_DELIMITER = r"\s*(?::|=>|=(?!>))\s*"
# The value class stops before `]` so redacting text never eats a closing bracket. A
# whole marker is the one place a `]` belongs *inside* the value, so the value is a run
# of markers and value characters: `token=[REDACTED]` is exactly one marker and stays
# exempt, while `token=[REDACTED]abcdefgh` is a marker plus content and is replaced in
# one piece, bracket included.
_VALUE_EXPR = r"(?:\[REDACTED\]|" + _VALUE_CLASS + r")+"
_KEY_VALUE_RE = re.compile(
    r"(?i)([\"']?(?:" + _SECRET_KEYWORDS + r")[\"']?)(" + _DELIMITER + r"[\"']?)("
    + _VALUE_EXPR + r")"
)
_LITERAL_RES = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # The lookbehind is what keeps this linear: without it every offset inside a run
    # of `eyJ` is a candidate start and the scan is quadratic in the run's length. A
    # real token never begins in the middle of its own alphabet.
    re.compile(
        r"(?<![A-Za-z0-9_\-])eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"
    ),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)basic\s+[A-Za-z0-9+/=]{16,}"),
)
_SECRET_KEYS = {
    "api_key", "api-key", "apikey", "password", "passwd", "token",
    "access_token", "refresh_token", "secret", "client_secret", "authorization",
}
# The marker is exempt only when it is the whole value: `token=[REDACTED] word` is
# this runtime's own output, while `token=[REDACTED]abcdefgh` still hides content.
# The keyword alternation is the same one the substitution uses, so a key the
# substitution rewrites can never be a key the detector ignores.
_SECRET_SHAPED_RE = re.compile(
    r"(?i)[\"']?(?:" + _SECRET_KEYWORDS + r")[\"']?"
    + _DELIMITER + r"[\"']?(?!\[REDACTED\](?!" + _VALUE_CLASS + r"))" + _VALUE_CLASS + r"{6,}"
)


def _replace_key_value(match: "re.Match") -> str:
    # Only the marker standing alone as the whole value is left as it is. A prefix test
    # would let `token=[REDACTED]abcdefgh` carry the real value past the substitution,
    # which is exactly what the detector then has to catch.
    if match.group(3) == REDACTED:
        return match.group(0)
    return match.group(1) + match.group(2) + REDACTED


# JSON spells any character as an escape, so raw provider output can carry an injected
# credential that no plain search finds while a reader still reconstructs it exactly.
_JSON_ESCAPE_RE = re.compile(r'\\(?:u[0-9a-fA-F]{4}|["\\/bfnrt])')
_JSON_SHORT_ESCAPES = {
    '"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
}


def _decoded_with_offsets(text: str) -> Tuple[str, array]:
    """The text as a reader would decode it, plus each decoded character's own offset.

    The offsets are what keep the damage minimal: only the span that actually spells a
    known credential is replaced, and everything around it is handed back untouched.
    One extra entry at the end gives the exclusive bound of the last character.
    """
    pieces: List[str] = []
    offsets = array("q")
    cursor = 0
    while True:
        match = _JSON_ESCAPE_RE.search(text, cursor)
        stop = match.start() if match else len(text)
        if stop > cursor:
            pieces.append(text[cursor:stop])
            offsets.extend(range(cursor, stop))
        if match is None:
            break
        token = match.group(0)
        pieces.append(
            chr(int(token[2:], 16)) if token[1] == "u" else _JSON_SHORT_ESCAPES[token[1]]
        )
        offsets.append(match.start())
        cursor = match.end()
    offsets.append(len(text))
    return "".join(pieces), offsets


def _redact_escaped_literals(text: str, literals: Sequence[str]) -> str:
    """Replace any span that decodes to an injected credential, escapes included."""
    if "\\" not in text or not literals:
        return text
    decoded, offsets = _decoded_with_offsets(text)
    spans: List[Tuple[int, int]] = []
    for literal in literals:
        start = decoded.find(literal)
        while start != -1:
            spans.append((start, start + len(literal)))
            start = decoded.find(literal, start + len(literal))
    if not spans:
        return text
    spans.sort()
    merged: List[Tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    out: List[str] = []
    cursor = 0
    for start, end in merged:
        out.append(text[cursor:offsets[start]])
        out.append(REDACTED)
        cursor = offsets[end]
    out.append(text[cursor:])
    return "".join(out)


def redact_text(text: str, known_secrets: Sequence[str] = ()) -> str:
    """Redact known injected literals, vendor-shaped literals, then key=value pairs."""
    if not isinstance(text, str):
        return text
    literals = [
        item for item in known_secrets
        if isinstance(item, str) and len(item) >= _MIN_KNOWN_SECRET
    ]
    for literal in literals:
        text = text.replace(literal, REDACTED)
    text = _redact_escaped_literals(text, literals)
    for pattern in _LITERAL_RES:
        text = pattern.sub(REDACTED, text)
    return _KEY_VALUE_RE.sub(_replace_key_value, text)


def redact_json(value: Any, known_secrets: Sequence[str] = ()) -> Any:
    """Redact string values *and* string keys; non-strings keep their type.

    A child that cannot get a credential past the value redaction can still put it in
    the key, and the sealed result then carries it verbatim. Redacting the key can
    collapse two distinct keys into one name: that is refused rather than silently
    merged, because dropping one of them would change the model-owned payload.

    The refusal does not ask whether the two values agree. Equal values are a property
    of one payload, not a licence to drop a name the model wrote, and the parent has no
    way to tell which of the two the reader was meant to see. A key that merely carries
    a credential is a different thing entirely: the literal leaves the name, the name
    stays distinct from its neighbours, and nothing is merged.
    """
    if isinstance(value, dict):
        result: Dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in _SECRET_KEYS:
                redacted_item: Any = REDACTED
            else:
                redacted_item = redact_json(item, known_secrets)
            redacted_key = redact_text(key, known_secrets) if isinstance(key, str) else key
            if redacted_key in result:
                raise RedactionCollisionError("REDACTION_KEY_COLLISION")
            result[redacted_key] = redacted_item
        return result
    if isinstance(value, list):
        return [redact_json(item, known_secrets) for item in value]
    if isinstance(value, str):
        return redact_text(value, known_secrets)
    return value


def _text_is_secret_shaped(text: str) -> bool:
    # The marker is skipped by the pattern itself. Deleting it first would splice the
    # following word into the value position and flag the runtime's own output.
    return bool(_SECRET_SHAPED_RE.search(text))


def find_secret_shaped(value: Any) -> bool:
    """Report secret-shaped content in any string value; the redaction marker is exempt."""
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                isinstance(key, str) and key.lower() in _SECRET_KEYS
                and isinstance(item, str) and item != REDACTED and len(item) >= 6
            ):
                return True
            if find_secret_shaped(item):
                return True
        return False
    if isinstance(value, list):
        return any(find_secret_shaped(item) for item in value)
    if isinstance(value, str):
        return _text_is_secret_shaped(value)
    return False


def known_secret_values(*sources: Iterable[Any]) -> List[str]:
    """Collect string leaves long enough to be treated as injected credentials."""
    collected: List[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for value in item.values():
                walk(value)
        elif isinstance(item, (list, tuple)):
            for value in item:
                walk(value)
        elif isinstance(item, str) and len(item) >= _MIN_KNOWN_SECRET:
            collected.append(item)

    for source in sources:
        walk(source)
    return sorted(set(collected), key=len, reverse=True)
