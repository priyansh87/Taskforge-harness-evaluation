import pytest
from parse_trajectory import classify, validate_row

def test_validate_row_success():
    # Reward 1.0, no failure_category
    row = {
        "task_id": "bug-01",
        "reward": 1.0,
        "failure_category": None,
        "verifier_result": {
            "fail_to_pass": True,
            "pass_to_pass": True,
            "tests_passed": 1902,
            "tests_total": 1902
        }
    }
    # Should not raise an error
    validate_row(row)

    # Reward < 1.0, with failure_category
    row2 = {
        "task_id": "bug-01",
        "reward": 0.9995,
        "failure_category": "incomplete_fix",
        "verifier_result": {
            "fail_to_pass": False,
            "pass_to_pass": True,
            "tests_passed": 1901,
            "tests_total": 1902
        }
    }
    # Should not raise an error
    validate_row(row2)

def test_validate_row_contradictions():
    # Contradiction: Reward 1.0 but has failure_category
    row = {
        "task_id": "bug-01",
        "reward": 1.0,
        "failure_category": "incomplete_fix",
        "verifier_result": {
            "fail_to_pass": True,
            "pass_to_pass": True,
            "tests_passed": 1902,
            "tests_total": 1902
        }
    }
    with pytest.raises(ValueError, match="fully passing run cannot have a failure_category"):
        validate_row(row)

    # Contradiction: Reward < 1.0 but failure_category is None
    row2 = {
        "task_id": "bug-01",
        "reward": 0.9,
        "failure_category": None,
        "verifier_result": {
            "fail_to_pass": False,
            "pass_to_pass": True,
            "tests_passed": 1700,
            "tests_total": 1902
        }
    }
    with pytest.raises(ValueError, match="failing run must have a failure_category"):
        validate_row(row2)

    # Contradiction: Out of range reward
    row3 = {
        "task_id": "bug-01",
        "reward": 1.5,
        "failure_category": None,
        "verifier_result": {
            "fail_to_pass": True,
            "pass_to_pass": True,
            "tests_passed": 1902,
            "tests_total": 1902
        }
    }
    with pytest.raises(ValueError, match="reward out of range"):
        validate_row(row3)

def test_classify_logic():
    gold_files = {"arrow/arrow.py"}
    
    # 1. Fully passing run
    assert classify(
        fail_to_pass_now_passes=True,
        pass_to_pass_all_still_pass=True,
        trajectory=[],
        edited_files=set(),
        gold_files=gold_files
    ) is None

    # 2. Regression introduced
    assert classify(
        fail_to_pass_now_passes=True,
        pass_to_pass_all_still_pass=False,
        trajectory=[],
        edited_files=set(),
        gold_files=gold_files
    ) == "regression_introduced"

    # 3. Didn't verify (no pytest run in last 2 actions)
    trajectory = [
        {"action": "edit_file", "target": "arrow/arrow.py"},
        {"action": "declare_done"}
    ]
    assert classify(
        fail_to_pass_now_passes=False,
        pass_to_pass_all_still_pass=True,
        trajectory=trajectory,
        edited_files={"arrow/arrow.py"},
        gold_files=gold_files
    ) == "didnt_verify"

    # 4. Misdiagnosis (edited wrong files or no files)
    trajectory_mis = [
        {"action": "run_command", "cmd": "pytest tests/ -q"},
        {"action": "edit_file", "target": "arrow/util.py"},
        {"action": "run_command", "cmd": "pytest tests/ -q"}
    ]
    assert classify(
        fail_to_pass_now_passes=False,
        pass_to_pass_all_still_pass=True,
        trajectory=trajectory_mis,
        edited_files={"arrow/util.py"},
        gold_files=gold_files
    ) == "misdiagnosis"

    # 5. Incomplete fix (edited right file, ran tests, but still failing)
    trajectory_inc = [
        {"action": "run_command", "cmd": "pytest tests/ -q"},
        {"action": "edit_file", "target": "arrow/arrow.py"},
        {"action": "run_command", "cmd": "pytest tests/ -q"}
    ]
    assert classify(
        fail_to_pass_now_passes=False,
        pass_to_pass_all_still_pass=True,
        trajectory=trajectory_inc,
        edited_files={"arrow/arrow.py"},
        gold_files=gold_files
    ) == "incomplete_fix"

def test_append_run_validation_failure(tmp_path):
    from parse_trajectory import append_run
    # Contradictory old record: reward 1.0 but has failure_category
    row = {
        "task_id": "bug-01",
        "reward": 1.0,
        "failure_category": "incomplete_fix",
        "verifier_result": {
            "fail_to_pass": True,
            "pass_to_pass": True,
            "tests_passed": 1902,
            "tests_total": 1902
        }
    }
    temp_file = tmp_path / "runs.jsonl"
    with pytest.raises(ValueError):
        append_run(row, path=str(temp_file))
