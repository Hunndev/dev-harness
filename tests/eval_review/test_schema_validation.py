import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review.schema_validation import validate_schema


class SchemaValidationTests(unittest.TestCase):
    def validate_with(self, data, schema):
        with patch("hb_eval_review.schema_validation._load_schema", return_value=schema):
            return validate_schema(data, "fixture.schema.json")

    def test_required_and_nested_types_reject_bool_as_integer(self):
        schema = {"type": "object", "required": ["commands"], "additionalProperties": False,
                  "properties": {"commands": {"type": "array", "minItems": 1,
                      "items": {"type": "object", "required": ["exit_code"],
                                "properties": {"exit_code": {"type": "integer", "minimum": 0}}}}}}
        self.assertEqual([], self.validate_with({"commands": [{"exit_code": 0}]}, schema))
        for data in ({}, {"commands": []}, {"commands": [{"exit_code": True}]},
                     {"commands": [{"exit_code": -1}]}, {"commands": [None]},
                     {"commands": [{"exit_code": 0}], "extra": True}):
            with self.subTest(data=data):
                self.assertTrue(self.validate_with(data, schema))

    def test_const_and_enum_do_not_confuse_booleans_with_numbers(self):
        for schema in ({"const": False}, {"enum": [False]}):
            self.assertEqual([], self.validate_with(False, schema))
            self.assertTrue(self.validate_with(0, schema))
        self.assertTrue(self.validate_with({"x": 0}, {"const": {"x": False}}))

    def test_string_constraints(self):
        schema = {"type": "string", "minLength": 2, "pattern": "^[a-f]+$"}
        self.assertEqual([], self.validate_with("abc", schema))
        for value in ("", "a", "az", 123):
            self.assertTrue(self.validate_with(value, schema))

    def test_allof_conditionals_and_not_enforce_baseline_contract(self):
        schema = {"type": "object", "required": ["baseline", "before"], "allOf": [{
            "if": {"properties": {"baseline": {"const": "PASS_TO_PASS"}}},
            "then": {"properties": {"before": {"const": "PASS"}},
                     "not": {"required": ["failure_reason"]}},
            "else": {"properties": {"before": {"const": "FAIL"}},
                     "required": ["failure_reason"]}}]}
        self.assertEqual([], self.validate_with({"baseline": "PASS_TO_PASS", "before": "PASS"}, schema))
        self.assertEqual([], self.validate_with({"baseline": "RED_TO_GREEN", "before": "FAIL", "failure_reason": "bug"}, schema))
        for data in ({"baseline": "PASS_TO_PASS", "before": "FAIL"},
                     {"baseline": "PASS_TO_PASS", "before": "PASS", "failure_reason": "bug"},
                     {"baseline": "RED_TO_GREEN", "before": "FAIL"}):
            self.assertTrue(self.validate_with(data, schema))

    def test_unsupported_keyword_fails_even_in_an_unselected_branch(self):
        schema = {"if": {"const": "yes"}, "then": {}, "else": {"oneOf": [{"type": "string"}]}}
        errors = self.validate_with("yes", schema)
        self.assertTrue(any(error.startswith("SCHEMA_UNSUPPORTED:") for error in errors), errors)

    def test_unavailable_and_path_escape_schema_fail_closed(self):
        self.assertTrue(validate_schema({}, "missing.schema.json"))
        self.assertTrue(validate_schema({}, "../../contracts/packet.schema.json"))

    def test_legacy_sensitivity_stays_fail_to_pass_and_disallows_baseline(self):
        data = {"schema_version": "1.0", "stage": "tdd-sensitivity", "tier": "T1", "status": "PASS",
                "test_id": "test_behavior", "red_test_hash": "a" * 64, "green_test_hash": "a" * 64,
                "red_outcome": "FAIL", "green_outcome": "PASS", "approved_red_revision": False,
                "high_risk": False, "mutation": {"required": False, "performed": False, "outcome": "NOT_REQUIRED"},
                "regression": {"status": "PASS"}}
        self.assertEqual([], validate_schema(data, "tdd-sensitivity-result.schema.json"))
        changed = copy.deepcopy(data)
        changed["red_outcome"] = "PASS"
        self.assertTrue(validate_schema(changed, "tdd-sensitivity-result.schema.json"))
        changed = copy.deepcopy(data)
        changed["baseline"] = "RED_TO_GREEN"
        self.assertTrue(validate_schema(changed, "tdd-sensitivity-result.schema.json"))


if __name__ == "__main__":
    unittest.main()
