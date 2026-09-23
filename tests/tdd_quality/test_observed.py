import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SHARED" / "runtime"))

from hb_eval_review import tdd_quality
from hb_eval_review.schema_validation import validate_schema
import test_contract


def canonical_bytes(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


class ObservedContract(unittest.TestCase):
    def observation(self, exit_code=1):
        return {
            "argv": ["python3", "-m", "pytest", "tests/test_behavior.py"],
            "cwd": "/workspace/repo",
            "git_dir": "/workspace/repo/.git",
            "artifacts": "/workspace/artifacts/run",
            "run_id": "d" * 32,
            "test_file": "tests/test_behavior.py",
            "exit_code": exit_code,
            "selected_tests": ["tests/test_behavior.py::test_behavior"],
            "executed": 1,
            "recorded_at": "2026-09-21T03:04:05.123456Z",
            "test_file_sha256": "a" * 64,
            "source_snapshot_id": "e" * 64,
            "sut_sha256": "1" * 64,
        }

    def design(self, baseline="RED_TO_GREEN"):
        data = test_contract.TestDesignContract().valid_design()
        data.update(schema_version="1.2", baseline=baseline,
                    observed=self.observation(0 if baseline == "PASS_TO_PASS" else 1))
        if baseline == "PASS_TO_PASS":
            data.pop("red_failure_kind")
        return data

    def sensitivity(self, design):
        data = test_contract.TestSensitivityContract().valid_sensitivity()
        data.update(schema_version="1.2", baseline=design["baseline"], observed=self.observation(0))
        data["observed"]["baseline_sha256"] = hashlib.sha256(canonical_bytes(design)).hexdigest()
        # The implementation is expected to change between baseline and green.
        data["observed"]["source_snapshot_id"] = "f" * 64
        data["observed"]["sut_sha256"] = "2" * 64
        if design["baseline"] == "PASS_TO_PASS":
            data["red_outcome"] = "PASS"
        return data

    def approval(self, design, sensitivity):
        observed = design["observed"]
        record = {
            "schema_version": "1.0", "kind": "tdd-red-revision-approval",
            "repo": observed["cwd"], "git_dir": observed["git_dir"],
            "artifacts": observed["artifacts"], "run_id": observed["run_id"],
            "test_file": observed["test_file"],
            "old_sha256": observed["test_file_sha256"],
            "new_sha256": sensitivity["green_test_hash"], "revision": 1,
            "revision_line": "revision 1: tighten behavior assertion",
            "approved_by": "user", "approval_source": "user-message:2026-09-21-1",
            "recorded_at": "2026-09-21T04:00:00+00:00",
        }
        return {"record_path": "/workspace/approvals/revision.json", "record": record,
                "record_sha256": hashlib.sha256(canonical_bytes(record)).hexdigest()}

    def pair(self, design, sensitivity):
        validator = getattr(tdd_quality, "validate_observation_pair", None)
        self.assertTrue(callable(validator), "the gate needs a shared observation-pair validator")
        return validator(design, sensitivity)

    def test_both_schema_12_observations_validate_and_bind(self):
        for baseline in ("RED_TO_GREEN", "PASS_TO_PASS"):
            design = self.design(baseline)
            sensitivity = self.sensitivity(design)
            with self.subTest(baseline=baseline):
                self.assertEqual([], validate_schema(design, "tdd-test-design-result.schema.json"))
                self.assertEqual([], validate_schema(sensitivity, "tdd-sensitivity-result.schema.json"))
                self.assertEqual([], tdd_quality.validate_test_design(design))
                self.assertEqual([], tdd_quality.validate_test_sensitivity(sensitivity))
                self.assertEqual([], self.pair(design, sensitivity))

    def test_observation_required_fields_cannot_be_self_reported_or_omitted(self):
        design = self.design()
        sensitivity = self.sensitivity(design)
        for original, validator, name in (
            (design, tdd_quality.validate_test_design, "tdd-test-design-result.schema.json"),
            (sensitivity, tdd_quality.validate_test_sensitivity, "tdd-sensitivity-result.schema.json"),
        ):
            for key in [None] + list(original["observed"]):
                data = copy.deepcopy(original)
                if key is None:
                    data.pop("observed")
                else:
                    data["observed"].pop(key)
                with self.subTest(contract=name, missing=key):
                    self.assertTrue(validate_schema(data, name))
                    self.assertIn("TDD_OBSERVATION_INVALID", validator(data))

    def test_execution_count_is_exactly_the_unique_executed_selected_ids(self):
        design = self.design()
        variants = [([], 0), (["test_behavior"], 0), (["test_behavior"], True),
                    (["test_behavior"], 2), (["test_behavior", "test_behavior"], 2),
                    (["test_behavior", "test_behavior"], 1), ([""], 1), ([1], 1)]
        for ids, count in variants:
            for original, validator in ((design, tdd_quality.validate_test_design),
                                        (self.sensitivity(design), tdd_quality.validate_test_sensitivity)):
                data = copy.deepcopy(original)
                data["observed"].update(selected_tests=ids, executed=count)
                with self.subTest(ids=ids, count=count, stage=data["stage"]):
                    self.assertIn("TDD_OBSERVATION_INVALID", validator(data))

    def test_observed_shape_rejects_invalid_paths_hashes_dates_and_commands(self):
        cases = {"argv": ([], "pytest", [3]), "cwd": ("repo", ""),
                 "git_dir": (".git",), "artifacts": ("output",),
                 "run_id": ("d" * 31, "D" * 32),
                 "test_file": ("/test.py", "../test.py", "tests/../test.py", "./test.py", "tests\\test.py"),
                 "test_file_sha256": ("x" * 64,), "source_snapshot_id": ("e" * 63,),
                 "recorded_at": ("2026-02-30T00:00:00Z", "2026-09-21T00:00:00", "2026-09-21T00:00:00+09:00"),
                 "exit_code": (False, "1")}
        for key, values in cases.items():
            for value in values:
                data = self.design()
                data["observed"][key] = value
                with self.subTest(field=key, value=value):
                    self.assertIn("TDD_OBSERVATION_INVALID", tdd_quality.validate_test_design(data))

    def test_observed_exit_code_must_match_design_baseline_and_green(self):
        for baseline, wrong_exit in (("RED_TO_GREEN", 0), ("PASS_TO_PASS", 1)):
            data = self.design(baseline)
            data["observed"]["exit_code"] = wrong_exit
            with self.subTest(baseline=baseline):
                self.assertIn("TDD_OBSERVATION_INVALID", tdd_quality.validate_test_design(data))
        data = self.sensitivity(self.design())
        data["observed"]["exit_code"] = 1
        self.assertIn("TDD_OBSERVATION_INVALID", tdd_quality.validate_test_sensitivity(data))

    def test_sut_digest_is_required_and_well_formed_for_both_observed_contracts(self):
        design = self.design()
        for original, validator, name in (
            (design, tdd_quality.validate_test_design, "tdd-test-design-result.schema.json"),
            (self.sensitivity(design), tdd_quality.validate_test_sensitivity, "tdd-sensitivity-result.schema.json"),
        ):
            for value in (None, False, "", "1" * 63, "g" * 64, "A" * 64):
                data = copy.deepcopy(original)
                if value is None:
                    data["observed"].pop("sut_sha256")
                else:
                    data["observed"]["sut_sha256"] = value
                with self.subTest(stage=data["stage"], digest=value):
                    self.assertTrue(validate_schema(data, name))
                    self.assertIn("TDD_OBSERVATION_INVALID", validator(data))

    def test_green_hash_must_be_its_observed_test_file_hash(self):
        data = self.sensitivity(self.design())
        data["observed"]["test_file_sha256"] = "b" * 64
        self.assertIn("TDD_TEST_IDENTITY_CHANGED", tdd_quality.validate_test_sensitivity(data))

    def test_pair_binds_run_repository_artifacts_and_test_file(self):
        design = self.design()
        for field, value in (("run_id", "b" * 32), ("cwd", "/other/repo"),
                             ("git_dir", "/other/repo/.git"), ("artifacts", "/other/artifacts"),
                             ("test_file", "tests/other.py")):
            data = self.sensitivity(design)
            data["observed"][field] = value
            with self.subTest(field=field):
                self.assertIn("TDD_BASELINE_MISMATCH", self.pair(design, data))

    def test_pair_binds_frozen_design_digest_baseline_and_red_hash(self):
        design = self.design()
        sensitivity = self.sensitivity(design)
        for change in ("digest", "metadata", "baseline", "red_hash"):
            left, right = copy.deepcopy(design), copy.deepcopy(sensitivity)
            if change == "digest":
                right["observed"]["baseline_sha256"] = "b" * 64
            elif change == "metadata":
                left["acceptance_refs"] = ["AC-OTHER"]
            elif change == "baseline":
                right["baseline"] = "PASS_TO_PASS"
            else:
                right["red_test_hash"] = "b" * 64
            with self.subTest(change=change):
                self.assertIn("TDD_BASELINE_MISMATCH", self.pair(left, right))

    def test_green_must_execute_every_baseline_selected_id_but_may_add_ids(self):
        design = self.design()
        green = self.sensitivity(design)
        green["observed"]["selected_tests"].append("tests/test_behavior.py::test_another_behavior")
        green["observed"]["executed"] = 2
        self.assertEqual([], self.pair(design, green))
        green["observed"]["selected_tests"] = ["tests/test_behavior.py::test_another_behavior"]
        green["observed"]["executed"] = 1
        self.assertIn("TDD_TEST_IDENTITY_CHANGED", self.pair(design, green))

    def test_pair_allows_different_commands_and_implementation_snapshots(self):
        design = self.design()
        green = self.sensitivity(design)
        green["observed"]["argv"] = ["pytest", "-q", "tests/test_behavior.py"]
        green["observed"]["recorded_at"] = "2026-09-21T05:00:00+00:00"
        self.assertNotEqual(design["observed"]["source_snapshot_id"], green["observed"]["source_snapshot_id"])
        self.assertNotEqual(design["observed"]["sut_sha256"], green["observed"]["sut_sha256"])
        self.assertEqual([], self.pair(design, green))

    def test_legacy_contracts_remain_valid_without_becoming_observed_evidence(self):
        for version in ("1.0", "1.1"):
            design = test_contract.TestDesignContract().valid_design()
            sensitivity = test_contract.TestSensitivityContract().valid_sensitivity()
            for data, validator, name in ((design, tdd_quality.validate_test_design, "tdd-test-design-result.schema.json"),
                                          (sensitivity, tdd_quality.validate_test_sensitivity, "tdd-sensitivity-result.schema.json")):
                data["schema_version"] = version
                if version == "1.1":
                    data["baseline"] = "RED_TO_GREEN"
                before = copy.deepcopy(data)
                with self.subTest(version=version, stage=data["stage"]):
                    self.assertEqual([], validate_schema(data, name))
                    self.assertEqual([], validator(data))
                    self.assertEqual(before, data)
                    forged = dict(data, observed=self.observation())
                    self.assertTrue(validate_schema(forged, name))
            self.assertEqual([], self.pair(design, sensitivity))
            self.assertIn("TDD_OBSERVATION_INVALID", self.pair(self.design(), sensitivity))
            self.assertIn("TDD_OBSERVATION_INVALID", self.pair(design, self.sensitivity(self.design())))

    def test_self_reported_revision_boolean_does_not_approve_test_changes(self):
        design = self.design()
        data = self.sensitivity(design)
        data.update(green_test_hash="b" * 64, approved_red_revision=True)
        data["observed"]["test_file_sha256"] = "b" * 64
        self.assertIn("TDD_TEST_IDENTITY_CHANGED", tdd_quality.validate_test_sensitivity(data))
        self.assertIn("TDD_TEST_IDENTITY_CHANGED", self.pair(design, data))

    def test_approval_receipt_is_strict_and_binds_original_and_revised_tests(self):
        design = self.design()
        green = self.sensitivity(design)
        green.update(green_test_hash="b" * 64, approved_red_revision=True)
        green["observed"]["test_file_sha256"] = "b" * 64
        green["observed"]["approval"] = self.approval(design, green)
        self.assertEqual([], validate_schema(green, "tdd-sensitivity-result.schema.json"))
        self.assertEqual([], tdd_quality.validate_test_sensitivity(green))
        self.assertEqual([], self.pair(design, green))
        variants = [("run_id", "c" * 32), ("repo", "/other/repo"), ("git_dir", "/other/.git"),
                    ("artifacts", "/other/run"), ("test_file", "tests/other.py"),
                    ("old_sha256", "c" * 64), ("new_sha256", "c" * 64),
                    ("approved_by", "assistant"), ("approval_source", ""),
                    ("revision", 3), ("revision", True), ("revision_line", "revision 2: wrong number"),
                    ("recorded_at", "yesterday"), ("unrecognized", "field")]
        for key, value in variants:
            data = copy.deepcopy(green)
            approval = data["observed"]["approval"]
            approval["record"][key] = value
            approval["record_sha256"] = hashlib.sha256(canonical_bytes(approval["record"])).hexdigest()
            with self.subTest(field=key, value=value):
                self.assertIn("TDD_TEST_IDENTITY_CHANGED", self.pair(design, data))
        for field, value in (("record_sha256", "c" * 64), ("record_path", "approval.json"),
                             ("record_path", "/workspace/repo/approval.json"), ("extra", True)):
            data = copy.deepcopy(green)
            data["observed"]["approval"][field] = value
            with self.subTest(receipt_field=field):
                self.assertIn("TDD_TEST_IDENTITY_CHANGED", self.pair(design, data))

    def test_approved_boolean_must_match_changed_hash_and_receipt(self):
        design = self.design()
        data = self.sensitivity(design)
        data["approved_red_revision"] = True
        self.assertIn("TDD_TEST_IDENTITY_CHANGED", tdd_quality.validate_test_sensitivity(data))
        data.update(green_test_hash="b" * 64, approved_red_revision=False)
        data["observed"]["test_file_sha256"] = "b" * 64
        data["observed"]["approval"] = self.approval(design, data)
        self.assertIn("TDD_TEST_IDENTITY_CHANGED", tdd_quality.validate_test_sensitivity(data))

    def test_optional_approval_receipt_is_validated_even_when_hashes_are_unchanged(self):
        data = self.sensitivity(self.design())
        data["observed"]["approval"] = {"record": "self-reported"}
        self.assertTrue(validate_schema(data, "tdd-sensitivity-result.schema.json"))
        self.assertIn("TDD_TEST_IDENTITY_CHANGED", tdd_quality.validate_test_sensitivity(data))

    def test_canonical_design_bytes_match_frozen_utf8_serialization(self):
        design = self.design()
        design["assertions"][0]["description"] = "권한 거부"
        serializer = getattr(tdd_quality, "canonical_design_bytes", None)
        self.assertTrue(callable(serializer), "baseline and gate must share frozen JSON serialization")
        self.assertEqual(canonical_bytes(design), serializer(design))


if __name__ == "__main__":
    unittest.main()
