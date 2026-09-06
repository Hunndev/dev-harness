import json
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review.redaction import (
    REDACTED,
    RedactionCollisionError,
    find_secret_shaped,
    redact_json,
    redact_text,
)


class RedactJsonTests(unittest.TestCase):
    def payload(self):
        return {
            "schema_version": "2.0",
            "status": "PASS",
            "blocking": [],
            "findings": [{
                "finding_id": "F1",
                "risk": "HIGH",
                "blocking": False,
                "occurrences": 3,
                "owner": None,
                "message": "found token=abc123secret",
            }],
            "evidence_refs": ["gate:test"],
        }

    def test_redact_json_keeps_structure_and_validity(self):
        redacted = redact_json(self.payload())
        self.assertIsInstance(redacted, dict)
        json.dumps(redacted)
        self.assertEqual(set(self.payload()), set(redacted))
        self.assertEqual(
            set(self.payload()["findings"][0]), set(redacted["findings"][0])
        )
        self.assertNotIn("abc123secret", json.dumps(redacted))
        self.assertIn(REDACTED, redacted["findings"][0]["message"])
        self.assertIs(False, redacted["findings"][0]["blocking"])
        self.assertEqual(3, redacted["findings"][0]["occurrences"])
        self.assertIsNone(redacted["findings"][0]["owner"])
        self.assertEqual("2.0", redacted["schema_version"])

    def test_secret_shaped_key_values_are_redacted_wholesale(self):
        for key in ("api_key", "api-key", "password", "token", "secret", "authorization"):
            with self.subTest(key=key):
                redacted = redact_json({"outer": {key: "plain-looking-value"}})
                self.assertEqual(REDACTED, redacted["outer"][key])

    def test_json_string_value_at_end_of_string_is_redacted_without_breaking_json(self):
        redacted = redact_json({"message": "leaked api_key=sk-ant-api03-AAAABBBBCCCC"})
        self.assertNotIn("sk-ant-api03-AAAABBBBCCCC", json.dumps(redacted))
        self.assertEqual({"message"}, set(redacted))


class RedactTextTests(unittest.TestCase):
    def test_vendor_literal_prefixes_are_redacted(self):
        cases = {
            "anthropic": "sk-ant-api03-AAAABBBBCCCCDDDD",
            "openai": "sk-" + "A" * 24,
            "github_classic": "ghp_" + "B" * 22,
            "github_pat": "github_pat_" + "C" * 24,
            "slack": "xoxb-123456789012-abcdef",
            "aws": "AKIA1234567890ABCDEF",
            "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4",
            "bearer": "Bearer abcdefgh12345678",
        }
        for name, literal in cases.items():
            with self.subTest(case=name):
                out = redact_text(f"provider said {literal} at the end")
                self.assertNotIn(literal, out)
                self.assertIn(REDACTED, out)

    def test_known_secret_literal_is_redacted_anywhere(self):
        out = redact_text(
            "auth used fixture-oauth-XYZ12345 mid-sentence",
            known_secrets=["fixture-oauth-XYZ12345"],
        )
        self.assertNotIn("fixture-oauth-XYZ12345", out)
        self.assertIn(REDACTED, out)

    def test_short_known_secret_is_ignored(self):
        text = "value abc here"
        self.assertEqual(text, redact_text(text, known_secrets=["abc"]))

    def test_redaction_is_idempotent(self):
        once = redact_text("found token=abc123secret")
        self.assertEqual(once, redact_text(once))

    def test_quoted_key_value_forms_are_redacted(self):
        cases = {
            "json_compact": ('{"token":"abcdefghij"}', "abcdefghij"),
            "json_spaced": ('{"token": "abc123secret"}', "abc123secret"),
            "camel_api_key": ('"apiKey": "AIzaSyABCDEFGHIJKLMNOP"', "AIzaSyABCDEFGHIJKLMNOP"),
            "client_secret": ('"client_secret":"abcdefghijkl"', "abcdefghijkl"),
            "yaml_quoted": ('password: "hunter2"', "hunter2"),
            "assignment_quoted": ('SECRET_KEY = "django-insecure-abcdefgh"', "django-insecure-abcdefgh"),
            "env_quoted": ('DB_PASSWORD = "hunter2pass"', "hunter2pass"),
            "fat_arrow": ("password => hunter22", "hunter22"),
        }
        for name, (text, leaked) in cases.items():
            with self.subTest(case=name):
                out = redact_text(text)
                self.assertNotIn(leaked, out)
                self.assertIn(REDACTED, out)

    def test_quoted_json_stays_parseable_after_redaction(self):
        out = redact_text('{"token": "abcdefghij", "note": "keep"}')
        self.assertEqual({"token": REDACTED, "note": "keep"}, json.loads(out))

    def test_basic_authorization_credentials_are_redacted(self):
        for name, text in {
            "header": "Authorization: Basic dXNlcjpzdXBlci1zZWNyZXQtcGFzcw==",
            "lowercase": "authorization: basic YWRtaW46aHVudGVyMnBhc3N3b3Jk",
        }.items():
            with self.subTest(case=name):
                out = redact_text(text)
                self.assertNotIn("dXNlcjpzdXBlci1zZWNyZXQtcGFzcw==", out)
                self.assertNotIn("YWRtaW46aHVudGVyMnBhc3N3b3Jk", out)
                self.assertIn(REDACTED, out)


class SecretShapedTests(unittest.TestCase):
    def test_redacted_marker_is_not_secret_shaped(self):
        self.assertFalse(find_secret_shaped({"message": f"token={REDACTED}"}))

    def test_nested_secret_shaped_string_is_detected(self):
        self.assertTrue(
            find_secret_shaped({"findings": [{"message": "api_key=abcdefghij"}]})
        )

    def test_secret_key_with_long_value_is_detected(self):
        self.assertTrue(find_secret_shaped({"outer": {"password": "hunter2hunter2"}}))

    def test_clean_payload_is_not_secret_shaped(self):
        self.assertFalse(find_secret_shaped({"summary": "no findings", "count": 4}))

    def test_a_word_after_the_marker_is_not_a_secret(self):
        # The runtime's own redaction output must survive its own validator.
        cases = {
            "token_then_word": "token=[REDACTED] exposed in config",
            "password_then_word": "password=[REDACTED] leaked in the log",
            "quoted_marker": '{"token": "[REDACTED]", "note": "review this"}',
            "marker_at_end": "api_key=[REDACTED]",
            "marker_then_comma": "token=[REDACTED], next=value",
        }
        for name, text in cases.items():
            with self.subTest(case=name):
                self.assertFalse(find_secret_shaped({"message": text}))

    def test_content_glued_to_the_marker_is_still_a_secret(self):
        for name, text in {
            "no_separator": "token=[REDACTED]abcdefgh",
            "unterminated_marker": "token=[REDACTEDabcdefgh",
        }.items():
            with self.subTest(case=name):
                self.assertTrue(find_secret_shaped({"message": text}))

    def test_redaction_output_never_trips_the_secret_check(self):
        for name, text in {
            "sentence": "password=hunter2 exposed in config",
            "midsentence": "token=abc123secret leaked in log",
            "quoted": '{"token": "abcdefghij"} was printed',
        }.items():
            with self.subTest(case=name):
                self.assertFalse(find_secret_shaped({"message": redact_text(text)}))


class MarkerSplicingTests(unittest.TestCase):
    """R4-02: the marker exempts a value only when it *is* the marker.

    A child that writes `authorization=[REDACTED]abcdefgh` got the prefix exemption in
    the substitution and the missing keyword in the detector, so the same string passed
    both layers untouched. One keyword list now serves both.
    """

    def test_content_glued_to_the_marker_is_still_redacted(self):
        for name, text in {
            "token": "token=[REDACTED]abcdefgh",
            "authorization": "authorization=[REDACTED]abcdefgh",
            "bearer": "bearer=[REDACTED]abcdefgh",
            "unterminated": "token=[REDACTEDabcdefgh",
        }.items():
            with self.subTest(case=name):
                out = redact_text(text)
                self.assertNotIn("abcdefgh", out)
                self.assertIn(REDACTED, out)

    def test_the_marker_alone_is_still_left_as_it_is(self):
        for name, text in {
            "bare": "token=[REDACTED]",
            "then_word": "token=[REDACTED] exposed in config",
            "then_comma": "token=[REDACTED], next=value",
            "quoted": '{"token": "[REDACTED]", "note": "keep"}',
        }.items():
            with self.subTest(case=name):
                self.assertEqual(text, redact_text(text))

    def test_every_redacted_keyword_is_also_a_detected_keyword(self):
        keywords = (
            "api_key", "api-key", "secret_key", "client_secret", "access_token",
            "refresh_token", "password", "passwd", "secret", "token",
            "authorization", "bearer",
        )
        for keyword in keywords:
            with self.subTest(keyword=keyword):
                plain = keyword + "=plainvalue123"
                self.assertTrue(find_secret_shaped({"message": plain}))
                self.assertTrue(
                    find_secret_shaped({"message": keyword + "=[REDACTED]abcdefgh"})
                )
                # What the substitution produced must not then trip the detector.
                self.assertFalse(
                    find_secret_shaped({"message": redact_text(plain)})
                )


class DelimiterParsingTests(unittest.TestCase):
    """R6-b: `=>` is one delimiter, never an `=` with `>` starting the value.

    The alternation used to be free to give up `=>` and retry as `=`, and the detector
    then read `token=>[REDACTED]` as the key `token`, the delimiter `=`, and the value
    `>[REDAC…` — six value characters, so the runtime flagged its own redaction output
    as secret-shaped. Each delimiter is pinned on all three behaviours: a plain value
    is redacted, the marker standing alone stays exempt, and content glued to the
    marker is still caught.
    """

    DELIMITERS = ("=", ":", "=>")

    def test_a_plain_value_is_redacted_after_every_delimiter(self):
        for delimiter in self.DELIMITERS:
            with self.subTest(delimiter=delimiter):
                out = redact_text("token" + delimiter + "abcdefgh")
                self.assertEqual("token" + delimiter + REDACTED, out)
                self.assertNotIn("abcdefgh", out)

    def test_the_marker_alone_is_exempt_after_every_delimiter(self):
        for delimiter in self.DELIMITERS:
            for suffix in ("", " rest", ", next=value", "\n"):
                text = "token" + delimiter + REDACTED + suffix
                with self.subTest(delimiter=delimiter, suffix=suffix):
                    self.assertEqual(text, redact_text(text))
                    self.assertFalse(find_secret_shaped({"message": text}))

    def test_content_glued_to_the_marker_is_caught_after_every_delimiter(self):
        for delimiter in self.DELIMITERS:
            for value in (REDACTED + "abcdefgh", REDACTED * 2 + "abcdefgh"):
                text = "token" + delimiter + value
                with self.subTest(delimiter=delimiter, value=value):
                    self.assertTrue(find_secret_shaped({"message": text}))
                    out = redact_text(text)
                    self.assertEqual("token" + delimiter + REDACTED, out)
                    self.assertNotIn("abcdefgh", out)

    def test_redaction_output_survives_its_own_validator_and_a_second_pass(self):
        for delimiter in self.DELIMITERS:
            for value in ("abcdefgh", REDACTED + "abcdefgh", REDACTED, "sk-ant-abcdefghij12345"):
                with self.subTest(delimiter=delimiter, value=value):
                    out = redact_text("token" + delimiter + value)
                    self.assertFalse(find_secret_shaped({"message": out}))
                    self.assertEqual(out, redact_text(out))

    def test_a_delimiter_with_no_value_is_left_alone(self):
        # `token=>` at the end of a line has no value to redact; rewriting it as
        # `token=[REDACTED]` would invent one out of the delimiter's own `>`.
        for text in ("token=>", "token=> ", "token:", "token="):
            with self.subTest(text=text):
                self.assertEqual(text, redact_text(text))


class RedactionPerformanceTests(unittest.TestCase):
    """R4-04: the JWT pattern retried every offset of a run of its own prefix."""

    SCRIPT = (
        "import sys, time\n"
        "sys.path.insert(0, {runtime!r})\n"
        "from hb_eval_review.redaction import redact_text\n"
        "payload = 'eyJ' * 350000\n"
        "start = time.monotonic()\n"
        "out = redact_text(payload)\n"
        "print(int(out == payload), round(time.monotonic() - start, 3))\n"
    )

    def test_a_megabyte_of_jwt_prefixes_is_redacted_in_bounded_time(self):
        # Out of process on purpose: a backtracking pattern stays inside one C call
        # where no in-process timer can interrupt it, so the bound must be a deadline.
        done = subprocess.run(
            [sys.executable, "-c", self.SCRIPT.format(runtime=str(ROOT / "SHARED" / "runtime"))],
            timeout=15, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        self.assertEqual(0, done.returncode, done.stdout)
        unchanged, elapsed = done.stdout.split()
        self.assertEqual("1", unchanged)
        self.assertLess(float(elapsed), 5.0, "quadratic backtracking: " + elapsed)

    def test_a_hundred_kilobytes_of_token_bodies_is_redacted_in_bounded_time(self):
        hostile = "eyJ" + "A" * 100000
        start = time.monotonic()
        redact_text(hostile)
        self.assertLess(time.monotonic() - start, 2.0)

    def test_a_megabyte_of_escape_sequences_is_redacted_in_bounded_time(self):
        # The escape-aware pass decodes the whole text once; it must stay linear, or a
        # child could stall the parent with an all-escapes stdout instead of a JWT run.
        hostile = "\\u0041" * 175000
        start = time.monotonic()
        out = redact_text(hostile, ["fixture-oauth-XYZ12345"])
        self.assertEqual(hostile, out)
        self.assertLess(time.monotonic() - start, 5.0)

    def test_real_tokens_are_still_redacted_after_the_pattern_change(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4"
        for name, text in {
            "alone": jwt,
            "in_sentence": "provider said " + jwt + " at the end",
            "after_quote": '{"jwt":"' + jwt + '"}',
            "after_space": "token " + jwt,
        }.items():
            with self.subTest(case=name):
                out = redact_text(text)
                self.assertNotIn(jwt, out)
                self.assertIn(REDACTED, out)


class JsonKeyRedactionTests(unittest.TestCase):
    """SEC-2 (un-deferred): a credential in a JSON *key* is on disk like any other."""

    LITERAL = "fixture-oauth-XYZ12345"
    OTHER = "fixture-apikey-QRS67890"

    def test_a_known_secret_in_a_key_is_redacted(self):
        out = redact_json({"evidence-" + self.LITERAL: "clean"}, [self.LITERAL])
        self.assertNotIn(self.LITERAL, json.dumps(out))
        self.assertIn("evidence-" + REDACTED, out)

    def test_a_vendor_literal_in_a_key_is_redacted(self):
        out = redact_json({"sk-ant-api03-AAAABBBBCCCC": 1})
        self.assertNotIn("sk-ant-api03-AAAABBBBCCCC", json.dumps(out))

    def test_a_key_in_a_nested_structure_is_redacted(self):
        out = redact_json(
            {"findings": [{"refs": {self.LITERAL: [{"deep-" + self.LITERAL: 1}]}}]},
            [self.LITERAL],
        )
        self.assertNotIn(self.LITERAL, json.dumps(out))

    def test_a_clean_key_is_left_exactly_as_it_is(self):
        payload = {"finding_id": "F1", "message": "clean", "count": 2}
        self.assertEqual(payload, redact_json(payload, [self.LITERAL]))

    def test_two_keys_that_collapse_to_one_fail_closed(self):
        with self.assertRaises(RedactionCollisionError):
            redact_json({"k-" + self.LITERAL: 1, "k-" + self.OTHER: 2},
                        [self.LITERAL, self.OTHER])

    def test_two_keys_that_collapse_to_one_fail_closed_even_on_equal_values(self):
        # Equal values used to buy an exemption, and the payload silently came back
        # with one key where the model had written two. Whether the values match is a
        # coincidence of this payload, not evidence that dropping a key is safe: the
        # parent cannot tell which of the two names the reader was meant to see.
        with self.assertRaises(RedactionCollisionError):
            redact_json({"k-" + self.LITERAL: 1, "k-" + self.OTHER: 1},
                        [self.LITERAL, self.OTHER])

    def test_the_marker_as_a_key_collides_with_a_key_that_redacts_to_it(self):
        for values in (("a", "b"), ("a", "a")):
            with self.subTest(values=values):
                with self.assertRaises(RedactionCollisionError):
                    redact_json({REDACTED: values[0], self.LITERAL: values[1]},
                                [self.LITERAL])

    def test_literal_keys_that_stay_distinct_are_both_kept(self):
        # R6 (g) order A/B: the prefixes survive redaction, so these two never collapse.
        # Refusing them would throw away a payload that lost nothing and hid nothing.
        for payload in (
            {"p-" + self.LITERAL: "1", "q-" + self.LITERAL: "2"},
            {"q-" + self.LITERAL: "2", "p-" + self.LITERAL: "1"},
        ):
            with self.subTest(payload=sorted(payload)):
                out = redact_json(payload, [self.LITERAL])
                self.assertEqual({"p-" + REDACTED: "1", "q-" + REDACTED: "2"}, out)
                self.assertNotIn(self.LITERAL, json.dumps(out))


class EscapedLiteralRedactionTests(unittest.TestCase):
    r"""SEC-6 (un-deferred): raw diagnostics can spell a literal out in \uXXXX escapes."""

    LITERAL = "fixture-oauth-XYZ12345"

    def escaped(self, text):
        return "".join("\\u%04x" % ord(character) for character in text)

    def test_a_fully_escaped_known_secret_is_redacted(self):
        payload = "child printed " + self.escaped(self.LITERAL) + " to stdout"
        out = redact_text(payload, [self.LITERAL])
        self.assertNotIn(self.escaped(self.LITERAL), out)
        self.assertIn(REDACTED, out)

    def test_a_partially_escaped_known_secret_is_redacted(self):
        spliced = "\\u0066ixture-oauth-XYZ1234\\u0035"
        out = redact_text("saw " + spliced + " here", [self.LITERAL])
        self.assertNotIn(spliced, out)
        self.assertIn(REDACTED, out)

    def test_a_json_two_character_escape_cannot_rebuild_a_literal(self):
        literal = 'fixture/oauth"XYZ12345'
        text = 'fixture\\/oauth\\"XYZ12345'
        out = redact_text("value " + text, [literal])
        self.assertNotIn(text, out)
        self.assertIn(REDACTED, out)

    def test_an_escaped_literal_inside_a_json_document_is_redacted_in_place(self):
        document = '{"stdout":"' + self.escaped(self.LITERAL) + '","note":"keep"}'
        out = redact_text(document, [self.LITERAL])
        self.assertEqual({"stdout": REDACTED, "note": "keep"}, json.loads(out))

    def test_ordinary_text_with_escapes_is_left_alone(self):
        for name, text in {
            "windows_path": "C:\\\\Users\\\\build\\\\out.log",
            "accent": "caf\\u00e9 and na\\u00efve",
            "newline_escape": "line one\\nline two",
            "no_backslash": "a plain sentence with no escapes",
        }.items():
            with self.subTest(case=name):
                self.assertEqual(text, redact_text(text, [self.LITERAL]))


if __name__ == "__main__":
    unittest.main()
