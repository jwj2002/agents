"""Acceptance tests for issue #233 — precision-tiered defect tracer (telemetry-validation §2.2).

Runs against SIMULATED PR payloads (the shape `gh pr list --json ...` returns) — host-agnostic, no
live `gh` calls. Precision≫recall: the tracer must NEVER false-accuse a clean PR.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import defect_tracer as T  # noqa: E402


def _pr(
    number, *, title="", body="", merged_at="2026-06-01T00:00:00Z", files=None, **extra
):
    return {
        "number": number,
        "title": title,
        "body": body,
        "merged_at": merged_at,
        "files": files or [],
        **extra,
    }


# AC1 / required-test: explicit revert → correction_or_defect (NOT a bare 'defect'), HIGH tier ------
def test_revert_pr_is_correction_or_defect_high():
    pr = _pr(99, title='Revert "feat: add widget"', body="This reverts #42.")
    c = T.classify_pr(pr)
    assert c is not None
    assert c["label"] == T.LABEL_CORRECTION
    assert c["label"] != "defect"  # never the bare/standalone defect label
    assert c["tier"] == T.TIER_HIGH
    assert 42 in c["references"]


# AC3 / required-test: same-file edit within window → NOISE hint only, never a defect label ---------
def test_same_file_within_window_is_noise_only():
    original = _pr(42, files=["a.py", "b.py"], merged_at="2026-06-01T00:00:00Z")
    churn = _pr(
        50, files=["a.py"], merged_at="2026-06-10T00:00:00Z"
    )  # 9 days later, shared file
    hint = T.same_file_noise_hint(churn, [original], window_days=14)
    assert hint["tier"] == T.TIER_NOISE
    assert hint["is_defect_label"] is False
    assert hint["label"] is None
    assert 42 in hint["noise_refs"]
    # and the churn PR, classified by its own text, is NOT a correction event
    assert T.classify_pr(churn) is None


# AC2 / required-test: "fixes regression from #PR" → MEDIUM tier correction --------------------------
def test_regression_fix_is_medium():
    pr = _pr(
        60,
        title="fix: nav crash",
        body="Fixes regression from #42 introduced last week.",
    )
    c = T.classify_pr(pr)
    assert c is not None
    assert c["label"] == T.LABEL_CORRECTION
    assert c["tier"] == T.TIER_MEDIUM
    assert 42 in c["references"]
    # revert takes precedence over regression when both appear
    both = _pr(61, body="This reverts #7. Fixes regression from #8.")
    assert T.classify_pr(both)["tier"] == T.TIER_HIGH


# Precision hardening: prose mentioning the verb + a distant #N must NOT classify (no false accuse) -
def test_clause_spanning_mentions_do_not_false_classify():
    # the #N belongs to a different clause — a loose regex would contaminate the anchor here
    assert (
        T.classify_pr(_pr(80, body="Do not revert anything; see #42 for context."))
        is None
    )
    assert T.classify_pr(_pr(81, body="No regression here, closes #42.")) is None
    assert (
        T.classify_pr(
            _pr(82, body="This avoids a future revert of the parser. Ref #42.")
        )
        is None
    )
    # but the canonical GitHub forms still classify (bare #N is same-repo shorthand)
    assert T.classify_pr(_pr(83, body="Reverts #42"))["tier"] == T.TIER_HIGH
    assert (
        T.classify_pr(_pr(84, body="regression introduced in #42"))["tier"]
        == T.TIER_MEDIUM
    )


# Precision hardening (Codex F2/F3): ADJACENT negation inverts the signal — must not classify --------
def test_adjacent_negation_does_not_classify():
    assert (
        T.classify_pr(_pr(85, body="Do not revert #42 under any circumstances."))
        is None
    )
    assert T.classify_pr(_pr(86, body="Prevents regression from #42.")) is None
    assert T.classify_pr(_pr(87, body="No regression in #42.")) is None
    # a quoted ORIGINAL title carrying an issue number must not be mined as the revert target
    assert T.classify_pr(_pr(88, title='Revert "Fix login #42"', body="")) is None


# Precision hardening (Codex re-review F2): repo-qualified #N only honored when local repo confirmed --
def test_cross_repo_reference_dropped():
    pr = _pr(90, body="Reverts otherorg/otherrepo#42")
    # repo known and mismatched → reference dropped (no local target marked)
    assert T.classify_pr(pr, repo="jwj2002/agents") is None
    # repo UNKNOWN (None) → repo-qualified ref cannot be confirmed local → also dropped
    assert T.classify_pr(pr) is None
    assert T.classify_pr(_pr(92, body="Reverts owner/agents#42")) is None
    # same repo → kept
    same = _pr(91, body="Reverts jwj2002/agents#42")
    assert 42 in T.classify_pr(same, repo="jwj2002/agents")["references"]


# Precision hardening (Codex re-review F3): negation anywhere in the clause is caught, not just nearby -
def test_long_distance_clause_negation():
    assert (
        T.classify_pr(_pr(93, body="Do not under any circumstances revert #42."))
        is None
    )
    assert (
        T.classify_pr(
            _pr(94, body="This does not appear to be caused by a regression from #42.")
        )
        is None
    )
    # a negation in a PRIOR sentence must NOT bleed into a clean revert clause
    assert (
        T.classify_pr(_pr(95, body="We will not merge yet. This reverts #42."))["tier"]
        == T.TIER_HIGH
    )


# AC5 / required-test: no revert/regression signal → no_observed_defect WITH coverage annotation ----
def test_no_signal_is_no_observed_defect_with_coverage():
    target = _pr(42)
    lab = T.label_target(
        target, correction_events=[], coverage=0.6, recall_threshold=0.5
    )
    assert lab["label"] == T.LABEL_NO_DEFECT
    assert lab["coverage"] == 0.6
    assert lab["metric_admissible"] is True  # 0.6 >= 0.5 threshold
    # below threshold → positive label withheld from targets AND a DISTINCT label (Codex F5) so a
    # naive consumer cannot read absence-of-defect as "clean"
    withheld = T.label_target(
        target, correction_events=[], coverage=0.2, recall_threshold=0.5
    )
    assert withheld["metric_admissible"] is False
    assert withheld["label"] == T.LABEL_INDETERMINATE
    assert withheld["label"] != T.LABEL_NO_DEFECT
    assert "withheld" in withheld["note"]


# AC4 / required-test: three windows; fast vs slow bug; boundary edge -------------------------------
def test_three_window_cumulative_and_boundary():
    target = _pr(42, merged_at="2026-06-01T00:00:00Z")
    # a FAST correction at lag 5d → observed in all three windows (7/14/30)
    fast = T.classify_pr(
        _pr(43, body="This reverts #42.", merged_at="2026-06-06T00:00:00Z")
    )
    lab_fast = T.label_target(target, [fast])
    assert lab_fast["label"] == T.LABEL_OBSERVED_DEFECT
    assert lab_fast["per_window"][7]["observed"] is True
    assert lab_fast["per_window"][30]["observed"] is True

    # a SLOW correction at lag 20d → observed in 30d ONLY, absent from 7d and 14d
    slow = T.classify_pr(
        _pr(44, body="This reverts #42.", merged_at="2026-06-21T00:00:00Z")
    )
    lab_slow = T.label_target(target, [slow])
    assert lab_slow["per_window"][7]["observed"] is False
    assert lab_slow["per_window"][14]["observed"] is False
    assert lab_slow["per_window"][30]["observed"] is True
    assert lab_slow["label"] == T.LABEL_OBSERVED_DEFECT  # observed in ≥1 window

    # BOUNDARY: a correction at exactly lag 7d is INCLUSIVE in the 7d window
    edge = T.classify_pr(
        _pr(45, body="This reverts #42.", merged_at="2026-06-08T00:00:00Z")
    )
    assert T.label_target(target, [edge])["per_window"][7]["observed"] is True


# AC6 / required-test: calibration precision 0.85 → emission BLOCKED --------------------------------
def _seeded(tp, fp, tn):
    """tp predicted-defect&true-defect, fp predicted-defect&true-clean, tn predicted-clean&true-clean."""
    cases = []
    cases += [{"predicted": "defect", "truth": "defect"} for _ in range(tp)]
    cases += [{"predicted": "defect", "truth": "clean"} for _ in range(fp)]
    cases += [{"predicted": "clean", "truth": "clean"} for _ in range(tn)]
    return cases


def test_calibration_below_gate_blocks_emission():
    res = T.run_calibration(
        _seeded(tp=17, fp=3, tn=10), round_ts="2026-06-06T00:00:00Z"
    )  # 0.85
    assert res["precision"] == pytest.approx(0.85)
    assert res["passed"] is False
    assert res["anchor_emission"] == "blocked"
    assert res["reason"] == "precision_below_gate"


# AC7 / required-test: calibration precision 0.92 → emission ALLOWED --------------------------------
def test_calibration_at_or_above_gate_allows_emission():
    res = T.run_calibration(
        _seeded(tp=23, fp=2, tn=5), round_ts="2026-06-06T00:00:00Z"
    )  # 0.92
    assert res["precision"] == pytest.approx(0.92)
    assert res["passed"] is True
    assert res["anchor_emission"] == "allowed"


# AC8 / required-test: sample < 30 → calibration rejected (insufficient sample) ---------------------
def test_calibration_insufficient_sample_rejected():
    res = T.run_calibration(
        _seeded(tp=15, fp=0, tn=5)
    )  # 20 cases, perfect precision but too few
    assert res["passed"] is False
    assert res["reason"] == "insufficient_sample"
    assert res["sample_size"] == 20
    assert res["anchor_emission"] == "blocked"


# AC6 (recall): CI-failure signal updates coverage, does NOT mark the PR individually defective ------
def test_recall_signal_estimates_coverage_not_individual_defect():
    prs = [
        _pr(42, ci_failed=True),
        _pr(43),
    ]  # 42 had a CI failure, no revert references it
    cands = T.recall_candidates(prs)
    assert [c["number"] for c in cands] == [42]
    assert cands[0]["label"] is None  # NOT an observed_defect label
    # the CI-failed PR, with no correction event referencing it, stays no_observed_defect
    lab = T.label_target(_pr(42, ci_failed=True), correction_events=[], coverage=0.5)
    assert lab["label"] == T.LABEL_NO_DEFECT
    # coverage estimate reflects the candidate as a missed-defect denominator
    cov = T.estimate_coverage(high_precision_count=1, recall_candidate_count=1)
    assert cov["coverage"] == pytest.approx(0.5)
    assert cov["method"] == "signal_lower_bound"
    # audit sample is the gold estimate when present
    audit_cov = T.estimate_coverage(
        high_precision_count=1,
        recall_candidate_count=99,
        audit={"true_defects_found": 10, "tracer_caught": 7},
    )
    assert audit_cov["coverage"] == pytest.approx(0.7)
    assert audit_cov["method"] == "audit_sample"


# AC integration: end-to-end gh pull → labeled output with coverage; calibration gate honored --------
def test_end_to_end_from_gh_json_with_calibration_gate():
    gh_payload = [
        {
            "number": 42,
            "title": "feat: nav",
            "body": "",
            "mergedAt": "2026-06-01T00:00:00Z",
            "files": [{"path": "nav.py"}],
            "labels": [{"name": "feature"}],
        },
        {
            "number": 43,
            "title": 'Revert "feat: nav"',
            "body": "This reverts #42.",
            "mergedAt": "2026-06-03T00:00:00Z",
            "files": [{"path": "nav.py"}],
            "labels": [],
        },
        {
            "number": 44,
            "title": "chore: docs",
            "body": "",
            "mergedAt": "2026-06-04T00:00:00Z",
            "files": [{"path": "README.md"}],
            "labels": [],
        },
    ]
    prs = T.from_gh_json(gh_payload)
    assert prs[0]["merged_at"] == "2026-06-01T00:00:00Z"  # camelCase normalized
    assert prs[0]["files"] == ["nav.py"]

    # gate OPEN: a REAL calibration result that authorizes emission
    passed = T.run_calibration(_seeded(tp=23, fp=2, tn=5))  # precision 0.92, n=30
    assert T.calibration_authorizes_emission(passed) is True
    out = T.trace_prs(prs, calibration=passed, recall_threshold=0.0)
    assert out["anchor_emission"] == "allowed"
    by_num = {l_["number"]: l_ for l_ in out["labels"]}
    assert (
        by_num[42]["label"] == T.LABEL_OBSERVED_DEFECT
    )  # reverted by #43 within window
    assert by_num[42]["by"] == [43]
    assert by_num[44]["label"] == T.LABEL_NO_DEFECT
    assert "coverage" in out and out["coverage"]["coverage"] >= 0

    # gate CLOSED: calibration failed → NO anchor labels emitted
    blocked = T.run_calibration(_seeded(tp=17, fp=3, tn=10))  # precision 0.85
    out2 = T.trace_prs(prs, calibration=blocked)
    assert out2["anchor_emission"] == "blocked"
    assert out2["labels"] == []


# Calibration-gate bypass (Codex F1): a FORGED calibration object must NOT open the anchor gate -------
def test_forged_calibration_cannot_emit_anchors():
    prs = T.from_gh_json(
        [{"number": 1, "title": "x", "body": "", "mergedAt": "2026-06-01T00:00:00Z"}]
    )
    forged = {
        "passed": True,
        "anchor_emission": "allowed",
    }  # no real seeded round behind it
    assert T.calibration_authorizes_emission(forged) is False
    out = T.trace_prs(prs, calibration=forged)
    assert out["anchor_emission"] == "blocked"
    assert out["labels"] == []
    # also reject a passed-but-undersized round, and a non-dict
    undersized = {
        "passed": True,
        "anchor_emission": "allowed",
        "sample_size": 5,
        "precision": 1.0,
    }
    assert T.calibration_authorizes_emission(undersized) is False
    assert T.calibration_authorizes_emission(None) is False


# Anchor safety (Codex F4): a PR cannot label ITSELF and same-timestamp corrections don't count -------
def test_self_reference_and_same_timestamp_do_not_label():
    # a PR whose body references its OWN number must not mark itself defective
    self_ref = T.classify_pr(
        _pr(42, body="This reverts #42.", merged_at="2026-06-01T00:00:00Z")
    )
    assert (
        T.label_target(_pr(42, merged_at="2026-06-01T00:00:00Z"), [self_ref])["label"]
        != T.LABEL_OBSERVED_DEFECT
    )
    # a correction merged at the SAME timestamp as the target is not "strictly after" → not counted
    target = _pr(50, merged_at="2026-06-01T00:00:00Z")
    same_ts = T.classify_pr(
        _pr(51, body="This reverts #50.", merged_at="2026-06-01T00:00:00Z")
    )
    assert T.label_target(target, [same_ts])["label"] != T.LABEL_OBSERVED_DEFECT
    # one second later DOES count
    later = T.classify_pr(
        _pr(52, body="This reverts #50.", merged_at="2026-06-01T00:00:01Z")
    )
    assert T.label_target(target, [later])["label"] == T.LABEL_OBSERVED_DEFECT


# Edge: squash-merge PR — commit lineage NOT used; only PR-level #N signals matter ------------------
def test_squash_merge_commit_revert_is_unmapped():
    # GitHub's squash revert body references a commit SHA, not a PR number.
    pr = _pr(70, title='Revert "feat: x"', body="This reverts commit deadbeefcafe1234.")
    c = T.classify_pr(pr)
    assert c is not None
    assert c["evidence"] == "commit_revert_unmapped"
    assert c["references"] == []  # no PR-level target → labels nothing
    assert c["label"] is None
    # it is excluded from the correction index (cannot mark any target defective)
    assert T.build_correction_index([pr]) == []
    # so a target PR is NOT falsely accused by a commit-only revert
    target = _pr(42)
    assert (
        T.label_target(target, T.build_correction_index([pr]))["label"]
        != T.LABEL_OBSERVED_DEFECT
    )


# Calibration logging: round is persisted as an audit record ---------------------------------------
def test_calibration_round_is_logged(tmp_path):
    res = T.run_calibration(_seeded(tp=23, fp=2, tn=5), round_ts="2026-06-06T00:00:00Z")
    sink = tmp_path / "calib.jsonl"
    rec = T.log_calibration(res, sink)
    assert rec["event"] == "calibration_round"
    assert rec["precision"] == pytest.approx(0.92)
    lines = sink.read_text().strip().splitlines()
    assert len(lines) == 1


# Calibration end-to-end via classify (seeded PRs, not pre-labeled predictions) --------------------
def test_calibration_classifies_seeded_prs():
    # 30 cases: 25 seeded reverts (true defects the tracer should catch) + 5 clean PRs
    cases = [
        {"pr": _pr(i, body=f"This reverts #{i - 1}."), "truth": "defect"}
        for i in range(100, 125)
    ]
    cases += [
        {"pr": _pr(i, title="feat: clean"), "truth": "clean"} for i in range(200, 205)
    ]
    res = T.run_calibration(cases)
    assert res["sample_size"] == 30
    assert res["precision"] == pytest.approx(
        1.0
    )  # every predicted-defect is a true defect
    assert res["anchor_emission"] == "allowed"
    # and that real round authorizes emission via the evidence-based gate
    assert T.calibration_authorizes_emission(res) is True


# Gate integrity (Codex re-review F2): the BLOCKED output carries NO anchor-bearing data --------------
def test_blocked_output_withholds_correction_events():
    prs = T.from_gh_json(
        [
            {
                "number": 42,
                "title": "feat",
                "body": "",
                "mergedAt": "2026-06-01T00:00:00Z",
            },
            {
                "number": 43,
                "title": 'Revert "feat"',
                "body": "This reverts #42.",
                "mergedAt": "2026-06-03T00:00:00Z",
            },
        ]
    )
    out = T.trace_prs(prs, calibration={"passed": True})  # forged → blocked
    assert out["anchor_emission"] == "blocked"
    assert out["labels"] == []
    # the anchor-bearing lists must be ABSENT — only non-label counts survive
    assert "correction_events" not in out
    assert "recall_candidates" not in out
    assert out["correction_event_count"] == 1


# Gate integrity (Codex re-review F1): forged evidence cannot fake the confusion matrix ---------------
def test_evidence_based_gate_rejects_inconsistent_counts():
    # claims precision 1.0 but supplies counts that recompute below the gate
    sneaky = {
        "anchor_emission": "allowed",
        "passed": True,
        "precision": 1.0,
        "sample_size": 30,
        "tp": 17,
        "fp": 5,
    }  # 17/22 = 0.77 < 0.9
    assert T.calibration_authorizes_emission(sneaky) is False
    # counts exceeding the sample are rejected
    impossible = {"anchor_emission": "allowed", "tp": 40, "fp": 0, "sample_size": 30}
    assert T.calibration_authorizes_emission(impossible) is False


# Consistency (Codex re-review F5): below-threshold per-window entries are NOT labeled clean -----------
def test_below_threshold_per_window_not_clean():
    lab = T.label_target(
        _pr(42), correction_events=[], coverage=0.2, recall_threshold=0.5
    )
    assert lab["label"] == T.LABEL_INDETERMINATE
    for w in T.WINDOWS_DAYS:
        assert lab["per_window"][w]["label"] == T.LABEL_INDETERMINATE
        assert lab["per_window"][w]["label"] != T.LABEL_NO_DEFECT


# Gate integrity (Codex round 3): bool/negative counts cannot forge a passing matrix -----------------
def test_gate_rejects_bool_and_negative_counts():
    # bool is an int subclass — must be rejected
    assert (
        T.calibration_authorizes_emission(
            {"anchor_emission": "allowed", "tp": True, "fp": False, "sample_size": 30}
        )
        is False
    )
    # negative fp recomputes a passing precision — must be rejected
    assert (
        T.calibration_authorizes_emission(
            {"anchor_emission": "allowed", "tp": 30, "fp": -29, "sample_size": 30}
        )
        is False
    )


# Precision (Codex round 3): prospective/discussed reverts are NOT correction events -----------------
def test_prospective_revert_not_classified():
    assert T.classify_pr(_pr(96, body="Adds a tool to revert #42 if needed.")) is None
    assert T.classify_pr(_pr(97, body="Option considered: revert #42.")) is None
    assert T.classify_pr(_pr(98, body="Please revert #42 when ready.")) is None
    # accomplished tense still classifies
    assert T.classify_pr(_pr(99, body="This reverts #42."))["tier"] == T.TIER_HIGH
    assert T.classify_pr(_pr(100, body="Reverted #42."))["tier"] == T.TIER_HIGH


# Production gate (Codex round 3): authorization comes from the persisted, fresh audit log -----------
def test_authorized_from_log(tmp_path):
    log = tmp_path / "calib.jsonl"
    # no log yet → not authorized
    assert T.authorized_from_log(log)["authorized"] is False
    assert T.authorized_from_log(log)["reason"] == "no_calibration_logged"
    # log a real passing round
    T.log_calibration(
        T.run_calibration(_seeded(tp=27, fp=2, tn=5), round_ts="2026-06-01T00:00:00Z"),
        log,
    )
    fresh = T.authorized_from_log(log, now_ts=T._parse_ts("2026-06-15T00:00:00Z"))
    assert fresh["authorized"] is True
    # the same round 200 days later is STALE (quarterly cadence) → not authorized
    stale = T.authorized_from_log(log, now_ts=T._parse_ts("2026-12-20T00:00:00Z"))
    assert stale["authorized"] is False
    assert stale["reason"] == "calibration_stale"


def test_trace_prs_uses_calibration_log(tmp_path):
    log = tmp_path / "calib.jsonl"
    prs = T.from_gh_json(
        [
            {
                "number": 42,
                "title": "feat",
                "body": "",
                "mergedAt": "2026-06-01T00:00:00Z",
            },
            {
                "number": 43,
                "title": 'Revert "feat"',
                "body": "This reverts #42.",
                "mergedAt": "2026-06-03T00:00:00Z",
            },
        ]
    )
    # no logged calibration → blocked even though no dict was forged
    out_blocked = T.trace_prs(prs, calibration_log_path=log)
    assert out_blocked["anchor_emission"] == "blocked"
    assert out_blocked["reason"] == "no_calibration_logged"
    # after a real logged round → allowed
    T.log_calibration(
        T.run_calibration(_seeded(tp=27, fp=2, tn=5), round_ts="2026-06-01T00:00:00Z"),
        log,
    )
    out_ok = T.trace_prs(
        prs,
        calibration_log_path=log,
        now_ts=T._parse_ts("2026-06-10T00:00:00Z"),
        recall_threshold=0.0,
    )
    assert out_ok["anchor_emission"] == "allowed"
    assert {lbl["number"]: lbl["label"] for lbl in out_ok["labels"]}[
        42
    ] == T.LABEL_OBSERVED_DEFECT


# Gate integrity (Codex round 4): freshness is FAIL-CLOSED, not fail-open ----------------------------
def test_freshness_fails_closed(tmp_path):
    log = tmp_path / "calib.jsonl"
    # a passing round WITHOUT a timestamp cannot be confirmed fresh → not authorized
    rnd = T.run_calibration(_seeded(tp=27, fp=2, tn=5))  # round_ts defaults to None
    T.log_calibration(rnd, log)
    res = T.authorized_from_log(log, now_ts=T._parse_ts("2026-06-10T00:00:00Z"))
    assert res["authorized"] is False
    assert res["reason"] == "calibration_no_timestamp"


def test_freshness_omitted_now_does_not_fail_open(tmp_path):
    # an ancient round must be rejected even when now_ts is omitted (defaults to wall clock, not skip)
    log = tmp_path / "calib.jsonl"
    T.log_calibration(
        T.run_calibration(_seeded(tp=27, fp=2, tn=5), round_ts="2000-01-01T00:00:00Z"),
        log,
    )
    res = T.authorized_from_log(log)  # no now_ts → uses wall clock → ancient → stale
    assert res["authorized"] is False
    assert res["reason"] == "calibration_stale"


def test_future_timestamp_rejected(tmp_path):
    log = tmp_path / "calib.jsonl"
    T.log_calibration(
        T.run_calibration(_seeded(tp=27, fp=2, tn=5), round_ts="2099-01-01T00:00:00Z"),
        log,
    )
    res = T.authorized_from_log(log, now_ts=T._parse_ts("2026-06-10T00:00:00Z"))
    assert res["authorized"] is False
    assert res["reason"] == "calibration_future_timestamp"
