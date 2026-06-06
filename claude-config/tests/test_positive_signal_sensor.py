"""Acceptance tests for issue #236 — `no_observed_defect_30d` positive-signal sensor (§3 / §0.6).

Host-agnostic: injected tracer results + exposure evidence, no live gh. The cardinal rule: a unit is
`no_observed_defect` ONLY with full exposure evidence + adequate tracer coverage — absence is never
silently "good".
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import positive_signal_sensor as S  # noqa: E402
import defect_tracer as DT  # noqa: E402

FULL_EXPOSURE = {
    "deployed": True,
    "tests_ran": True,
    "tests_covered_changed": True,
    "reviewer_coverage": True,
    "ci_scope": True,
}
NO_CORRECTION = {"label": DT.LABEL_NO_DEFECT, "coverage": 0.8}
FREEZE = "2026-05-01T00:00:00Z"
NOW_CLOSED = "2026-06-10T00:00:00Z"  # 40d after freeze → window closed
NOW_OPEN = "2026-05-25T00:00:00Z"  # 24d after freeze → window open


def _classify(
    tracer_result=NO_CORRECTION,
    exposure=None,
    *,
    recall_threshold=0.5,
    freeze_ts=FREEZE,
    now_ts=NOW_CLOSED,
    **kw,
):
    return S.classify_unit(
        "u1",
        tracer_result=tracer_result,
        exposure=FULL_EXPOSURE if exposure is None else exposure,
        recall_threshold=recall_threshold,
        freeze_ts=freeze_ts,
        now_ts=now_ts,
        **kw,
    )


# Required: 30d elapsed, no correction, test execution missing → unverified (not no_observed_defect) --
def test_missing_test_execution_is_unverified():
    exposure = {**FULL_EXPOSURE, "tests_ran": False}
    res = _classify(exposure=exposure)
    assert res["label"] == S.LABEL_UNVERIFIED
    assert "tests_ran" in res["missing_exposure"]


# Required: 30d elapsed, no correction, ALL six met → no_observed_defect -----------------------------
def test_all_conditions_met_is_no_observed_defect():
    res = _classify()
    assert res["label"] == S.LABEL_GOOD
    assert res["missing_exposure"] == []
    assert res["coverage_ok"] is True
    assert res["label"] == "no_observed_defect"  # exact name discipline


# Required: correction within 30d → correction_detected regardless of exposure ------------------------
def test_correction_is_terminal_regardless_of_exposure():
    corrected = {"label": DT.LABEL_OBSERVED_DEFECT, "by": [43], "coverage": 0.9}
    # even with FULL exposure, a correction wins
    res = _classify(tracer_result=corrected)
    assert res["label"] == S.LABEL_CORRECTION
    assert res["correction_by"] == [43]
    # and with NO exposure too
    res2 = _classify(tracer_result=corrected, exposure={})
    assert res2["label"] == S.LABEL_CORRECTION


# Required: tracer coverage below threshold → forces unverified even with all else --------------------
def test_low_tracer_coverage_forces_unverified():
    low = {"label": DT.LABEL_NO_DEFECT, "coverage": 0.2}
    res = _classify(
        tracer_result=low, recall_threshold=0.5
    )  # full exposure, but coverage 0.2 < 0.5
    assert res["label"] == S.LABEL_UNVERIFIED
    assert res["coverage_ok"] is False
    # threshold is configurable: lower it and the same unit qualifies
    res2 = _classify(tracer_result=low, recall_threshold=0.1)
    assert res2["label"] == S.LABEL_GOOD


# Required: 29 days elapsed (window open) → no label yet (pending) ------------------------------------
def test_window_not_closed_is_pending():
    res = _classify(now_ts=NOW_OPEN)
    assert res["label"] == S.LABEL_PENDING
    assert res["label"] not in (S.LABEL_GOOD, S.LABEL_UNVERIFIED, S.LABEL_CORRECTION)
    # exactly 30d → closed (inclusive boundary)
    boundary = S.window_closed("2026-05-01T00:00:00Z", "2026-05-31T00:00:00Z", 30)
    assert boundary is True
    assert S.window_closed("2026-05-01T00:00:00Z", "2026-05-30T00:00:00Z", 30) is False


# Required: tests-exist but not tests-ran → condition fails → unverified ------------------------------
def test_tests_exist_but_not_ran_is_unverified():
    # "tests exist" is modeled as ran=False/covered=False — existence alone is not execution
    exposure = {**FULL_EXPOSURE, "tests_ran": False, "tests_covered_changed": False}
    res = _classify(exposure=exposure)
    assert res["label"] == S.LABEL_UNVERIFIED
    # tests ran but did NOT cover changed paths → still unverified
    partial = {**FULL_EXPOSURE, "tests_covered_changed": False}
    assert _classify(exposure=partial)["label"] == S.LABEL_UNVERIFIED


# Required: reviewer coverage missing → unverified ---------------------------------------------------
def test_missing_reviewer_coverage_is_unverified():
    exposure = {**FULL_EXPOSURE, "reviewer_coverage": False}
    res = _classify(exposure=exposure)
    assert res["label"] == S.LABEL_UNVERIFIED
    assert "reviewer_coverage" in res["missing_exposure"]


# Output schema shape (AC) ---------------------------------------------------------------------------
def test_output_schema():
    res = _classify()
    for k in (
        "unit_id",
        "label",
        "exposure_evidence",
        "tracer_coverage_pct",
        "window_days",
    ):
        assert k in res, k
    assert set(res["exposure_evidence"]) == set(S.REQUIRED_EXPOSURE)
    assert res["window_days"] == 30


# Naming discipline (AC): no first_pass_correct anywhere in the new module ----------------------------
def test_no_first_pass_correct_in_source():
    src = (
        Path(__file__).resolve().parents[1] / "scripts" / "positive_signal_sensor.py"
    ).read_text()
    assert "first_pass_correct" not in src
    assert S.LABEL_GOOD == "no_observed_defect"


# Integration: full pipeline session→tracer→exposure→label -------------------------------------------
def test_integration_full_pipeline():
    prs = DT.from_gh_json(
        [
            {
                "number": 42,
                "title": "feat",
                "body": "",
                "mergedAt": "2026-04-02T00:00:00Z",
            },
            {
                "number": 43,
                "title": 'Revert "feat"',
                "body": "This reverts #42.",
                "mergedAt": "2026-04-05T00:00:00Z",
            },
            {
                "number": 44,
                "title": "chore",
                "body": "",
                "mergedAt": "2026-04-02T00:00:00Z",
            },
        ]
    )
    units = [
        {
            "unit_id": "uA",
            "pr": 42,
            "freeze_ts": "2026-04-01T00:00:00Z",
        },  # got reverted
        {
            "unit_id": "uB",
            "pr": 44,
            "freeze_ts": "2026-04-01T00:00:00Z",
        },  # clean, full exposure
        {
            "unit_id": "uC",
            "pr": 44,
            "freeze_ts": "2026-04-01T00:00:00Z",
        },  # clean, missing exposure
    ]
    exposure_by_unit = {
        "uA": FULL_EXPOSURE,
        "uB": FULL_EXPOSURE,
        "uC": {"deployed": True},
    }
    cal = DT.run_calibration(
        [{"predicted": "defect", "truth": "defect"} for _ in range(27)]
        + [{"predicted": "defect", "truth": "clean"} for _ in range(2)]
        + [{"predicted": "clean", "truth": "clean"} for _ in range(5)]
    )
    out = S.run_sensor(
        prs,
        units,
        exposure_by_unit=exposure_by_unit,
        recall_threshold=0.0,
        now_ts="2026-06-10T00:00:00Z",
        calibration=cal,
    )
    by_unit = {c["unit_id"]: c["label"] for c in out["classifications"]}
    assert by_unit["uA"] == S.LABEL_CORRECTION  # reverted within window
    assert by_unit["uB"] == S.LABEL_GOOD  # clean + full exposure
    assert by_unit["uC"] == S.LABEL_UNVERIFIED  # clean but missing exposure


# Integration: blocked calibration gate → every unit unverified (can't confirm a positive) -----------
def test_blocked_gate_makes_units_unverified():
    prs = DT.from_gh_json(
        [
            {
                "number": 44,
                "title": "chore",
                "body": "",
                "mergedAt": "2026-04-02T00:00:00Z",
            }
        ]
    )
    units = [{"unit_id": "uB", "pr": 44, "freeze_ts": "2026-04-01T00:00:00Z"}]
    out = S.run_sensor(
        prs,
        units,
        exposure_by_unit={"uB": FULL_EXPOSURE},
        recall_threshold=0.0,
        now_ts="2026-06-10T00:00:00Z",
        calibration={"passed": True},  # forged → gate blocked
    )
    assert out["anchor_emission"] == "blocked"
    assert out["classifications"][0]["label"] == S.LABEL_UNVERIFIED


# Integration: no_observed_defect emits a tk-auto-observe-consumable event ----------------------------
def test_auto_observe_event_only_for_confirmed_positive():
    good = _classify()
    ev = S.auto_observe_event(good)
    assert ev is not None
    assert ev["event"] == "positive_example"
    assert ev["source"] == "no_observed_defect_30d"
    assert ev["unit_id"] == "u1"
    # unverified / correction / pending are NOT auto-observable
    assert S.auto_observe_event(_classify(exposure={})) is None
    assert S.auto_observe_event(_classify(now_ts=NOW_OPEN)) is None
    assert (
        S.auto_observe_event(
            _classify(tracer_result={"label": DT.LABEL_OBSERVED_DEFECT})
        )
        is None
    )


# Strictness (Codex review): a positive requires an EXPLICIT confirmed no-defect tracer label ---------
def test_positive_requires_explicit_no_defect_tracer_label():
    # missing tracer label + externally supplied high coverage + full exposure → NOT good
    res = _classify(tracer_result={}, tracer_coverage_pct=0.9)
    assert res["label"] == S.LABEL_UNVERIFIED
    assert res["no_correction_confirmed"] is False
    # an indeterminate-coverage tracer label is also not a confirmation
    indet = {"label": DT.LABEL_INDETERMINATE, "coverage": 0.9}
    assert (
        _classify(tracer_result=indet, tracer_coverage_pct=0.9)["label"]
        == S.LABEL_UNVERIFIED
    )
    # an unknown label likewise
    assert _classify(tracer_result={"label": "weird"}, tracer_coverage_pct=0.9)[
        "label"
    ] == (S.LABEL_UNVERIFIED)


# Defense-in-depth (Codex review): auto-observe rejects a forged label lacking confirmation evidence --
def test_auto_observe_rejects_forged_label():
    forged = {
        "unit_id": "x",
        "label": S.LABEL_GOOD,  # claims good...
        "coverage_ok": False,  # ...but evidence absent
        "no_correction_confirmed": False,
        "missing_exposure": ["deployed"],
        "window_days": 30,
    }
    assert S.auto_observe_event(forged) is None
    # a label claiming good but with no confirmation fields at all is also rejected
    assert S.auto_observe_event({"label": S.LABEL_GOOD}) is None
    # confirmation flags present but missing_exposure ABSENT (None, not []) must still be rejected
    assert (
        S.auto_observe_event(
            {
                "label": S.LABEL_GOOD,
                "no_correction_confirmed": True,
                "coverage_ok": True,
            }
        )
        is None
    )
