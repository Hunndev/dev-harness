import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review import tdd_quality
import test_contract


class BaselineContract(unittest.TestCase):
    def design(self, baseline="RED_TO_GREEN"):
        data = test_contract.TestDesignContract().valid_design()
        data.update(schema_version="1.1", baseline=baseline)
        if baseline == "PASS_TO_PASS":
            data.pop("red_failure_kind")
        return data

    def sensitivity(self, baseline="RED_TO_GREEN"):
        data = test_contract.TestSensitivityContract().valid_sensitivity()
        data.update(schema_version="1.1", baseline=baseline)
        if baseline == "PASS_TO_PASS":
            data["red_outcome"] = "PASS"
        return data

    def test_schema_11_red_and_refactor_baselines_pass(self):
        for baseline in ("RED_TO_GREEN", "PASS_TO_PASS"):
            with self.subTest(baseline=baseline):
                self.assertEqual([], tdd_quality.validate_test_design(self.design(baseline)))
                self.assertEqual([], tdd_quality.validate_test_sensitivity(self.sensitivity(baseline)))

    def test_missing_unknown_or_unsupported_baseline_is_rejected(self):
        for factory, validator in (
            (self.design, tdd_quality.validate_test_design),
            (self.sensitivity, tdd_quality.validate_test_sensitivity),
        ):
            for change in ("missing", "unknown", "unsupported_version", "missing_version", "legacy_with_baseline"):
                data = factory()
                if change == "missing":
                    data.pop("baseline")
                elif change == "unknown":
                    data["baseline"] = "SOMETHING_ELSE"
                elif change == "unsupported_version":
                    data["schema_version"] = "9.9"
                elif change == "missing_version":
                    data.pop("schema_version")
                else:
                    data["schema_version"] = "1.0"
                with self.subTest(contract=validator.__name__, change=change):
                    self.assertIn("TDD_BASELINE_INVALID", validator(data))

    def test_refactor_forbids_a_red_failure_reason(self):
        for reason in ("bug_reproduced", None):
            data = self.design("PASS_TO_PASS")
            data["red_failure_kind"] = reason
            with self.subTest(reason=reason):
                self.assertIn("TDD_RED_REASON_INVALID", tdd_quality.validate_test_design(data))

    def test_red_baseline_still_requires_a_valid_failure_reason(self):
        data = self.design()
        data.pop("red_failure_kind")
        self.assertIn("TDD_RED_REASON_INVALID", tdd_quality.validate_test_design(data))

    def test_baseline_controls_both_outcomes(self):
        for baseline, wrong_red in (("RED_TO_GREEN", "PASS"), ("PASS_TO_PASS", "FAIL")):
            for field, value in (("red_outcome", wrong_red), ("green_outcome", "FAIL")):
                data = self.sensitivity(baseline)
                data[field] = value
                with self.subTest(baseline=baseline, field=field):
                    self.assertIn("TDD_TRANSITION_INVALID", tdd_quality.validate_test_sensitivity(data))

    def test_refactor_keeps_test_identity_and_regression_checks(self):
        data = self.sensitivity("PASS_TO_PASS")
        data["green_test_hash"] = "b" * 64
        data["regression"]["status"] = "FAIL"
        errors = tdd_quality.validate_test_sensitivity(data)
        self.assertIn("TDD_TEST_IDENTITY_CHANGED", errors)
        self.assertIn("TDD_REGRESSION_NOT_PASSING", errors)

    def test_legacy_baseline_is_red_without_mutating_input(self):
        for data, validator in (
            (test_contract.TestDesignContract().valid_design(), tdd_quality.validate_test_design),
            (test_contract.TestSensitivityContract().valid_sensitivity(), tdd_quality.validate_test_sensitivity),
        ):
            before = copy.deepcopy(data)
            self.assertEqual([], validator(data))
            self.assertEqual(before, data)
            self.assertNotIn("baseline", data)

    def test_schema_11_requires_explicit_baseline_in_both_contracts(self):
        for name in ("tdd-test-design-result", "tdd-sensitivity-result"):
            schema = json.loads((ROOT / "SHARED" / "contracts" / (name + ".schema.json")).read_text())
            with self.subTest(contract=name):
                self.assertEqual("1.2", schema["properties"]["schema_version"]["const"])
                self.assertIn("baseline", schema["required"])
                self.assertEqual(["RED_TO_GREEN", "PASS_TO_PASS"], schema["properties"]["baseline"]["enum"])

    def test_producer_docs_define_both_baselines_and_matching_contract_versions(self):
        for track in ("BE", "CM", "FE", "CHAT", "AOS", "IOS"):
            text = (ROOT / track / "commands" / "shared" / "tdd.md").read_text()
            with self.subTest(track=track):
                self.assertIn("RED_TO_GREEN", text)
                self.assertIn("PASS_TO_PASS", text)
                self.assertIn('"schema_version": "1.1"', text)
                self.assertIn('"schema_version": "1.2"', text)
                self.assertIn("red_failure_kind", text)
                self.assertIn("approved_red_revision", text)
                self.assertIn("maintenance의 refactor", text)
                self.assertIn('"schema_version": "1.0"', text)  # qa-snapshot remains 1.0


if __name__ == "__main__":
    unittest.main()
