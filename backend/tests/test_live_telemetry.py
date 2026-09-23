"""Live telemetry shows only claims the demo can defend."""
from types import SimpleNamespace

import pytest

from app.core.session_manager import SessionManager, UNVALIDATED_TELEMETRY_OFF


def fake_engine(reps):
    counter = SimpleNamespace(machine=SimpleNamespace(reps=reps))
    return SimpleNamespace(
        current_risk_result={"risk_label": "SAFE", "risk_level": 0, "confidence": 0.9, "mode": "temporal"},
        current_fatigue_status={"fatigue_score": 100.0, "alert_level": "green", "lifts_completed": 0},
        current_injury_risk={"combined_iri": 0.0, "category": "LOW"},
        current_features={}, current_user=None, frame_times=[], current_exercise_status={"rep_count": len(reps)},
        current_corrections=[], feedback_message="", using_iri_v2=True, current_camera_id=0,
        voice_enabled=False, speaker=None, arduino_connected=False, arduino=None, mirror_mode=False,
        calibration_mode=False, using_temporal=True, process_every_n=1, frame_count=1,
        live_squat=SimpleNamespace(counter=counter),
    )


def rep(duration, rom, trunk=5.0):
    return {"duration_seconds": duration, "rom_degrees": rom, "max_trunk_lean": trunk}


def telemetry(reps):
    manager = SessionManager.__new__(SessionManager)
    manager.engine = fake_engine(reps)
    return manager._collect_telemetry()


def test_unvalidated_model_fields_are_not_sent():
    tel = telemetry([])
    for key, value in UNVALIDATED_TELEMETRY_OFF.items():
        assert tel[key] == value
    assert tel["confidence"] is None and tel["injury_risk"] is None and tel["using_temporal"] is False
    assert tel["validated_claims_only"] is True


def test_fatigue_is_empty_until_enough_reps_not_100():
    tel = telemetry([rep(1.0, 60)] * 2)
    assert tel["fatigue_score"] is None
    assert tel["fatigue_alert"] == "INSUFFICIENT_REPS"
    assert tel["lifts_completed"] == 2


def test_fatigue_rises_with_slower_shallower_reps():
    steady = telemetry([rep(1.0, 60)] * 10)
    assert steady["fatigue_score"] == 0.0 and steady["fatigue_alert"] == "STABLE"
    tired = telemetry([rep(1.0, 60)] * 3 + [rep(1.8, 40, 15.0)] * 5)
    assert tired["fatigue_score"] > 35 and tired["fatigue_alert"] == "ELEVATED"


def test_shoulder_tilt_and_lateral_lean_correction():
    engine = pytest.importorskip("app.core.liftguard_engine")

    def body(ls, rs):
        points = [(0.0, 0.0, 0.0)] * 33
        points[11], points[12] = ls, rs
        points[23], points[24] = (560, 500, 0), (720, 500, 0)
        return points

    level = body((540, 200, 0), (740, 212, 0))  # 12 px over 200 px at 720p: old rule fired
    assert engine.shoulder_tilt_deg(level) < 5
    assert engine.shoulder_tilt_deg(body((540, 200, 0), (740, 260, 0))) > 15
    assert engine.shoulder_tilt_deg(body((630, 200, 0), (650, 205, 0))) is None  # side view

    corrector = engine.FormCorrector()
    base = {"spine_flexion": 5, "hip_hinge_angle": 170, "stability_index": 0.9, "stance_width": 0.3}

    def ids(feats):
        return {c["id"] for c in corrector.get_corrections(feats, {"risk_level": 1}, {})}

    assert "lateral_lean" not in ids({**base, "spine_lateral_tilt": 0.4, "shoulder_tilt_deg": 3.0})
    assert "lateral_lean" in ids({**base, "spine_lateral_tilt": 0.4, "shoulder_tilt_deg": 16.0})
    assert "lateral_lean" not in ids({**base, "spine_lateral_tilt": 0.4, "shoulder_tilt_deg": None})


def report_for(reps):
    manager = SessionManager.__new__(SessionManager)
    engine = fake_engine(reps)
    engine.current_exercise_status = {"rep_count": len(reps), "calibration_mode": "CALIBRATED",
                                      "rep_gates": {"rejected_feet_moved": 1, "rejected_hip_drop": 0}}
    engine.exercise_tracker = SimpleNamespace(get_session_summary=lambda: {"total_reps": 0, "exercise": "Unknown"})
    engine.fatigue_engine = SimpleNamespace(get_session_report=lambda: {"final_fatigue_score": 100.0})
    engine._session_peak_risk, engine._session_iri_history, engine._session_spine_history = 0, [0.1, 0.2], [5.0]
    engine.injury_predictor = SimpleNamespace(get_session_report=lambda: {"iri_stats": {}})
    engine.uncertainty_manager = SimpleNamespace(get_uncertainty_summary=lambda: {"mean": 0.1})
    manager.engine = engine
    return manager.get_session_report()


def full_rep(duration, rom, flags=()):
    return {**rep(duration, rom), "min_knee_angle": 180 - rom, "form_flags": list(flags)}


def test_session_report_uses_live_counter_not_legacy_tracker():
    report = report_for([full_rep(1.0, 60)] * 12 + [full_rep(1.0, 60, ["LIMITED_DEPTH"])] * 3)
    ex = report["exercise"]
    assert ex["total_reps"] == 15 and ex["exercise"] == "Squat"
    assert ex["reps_with_form_flags"] == 3
    assert ex["avg_rep_seconds"] == 1.0 and ex["rejected_candidates"] == 1
    assert all(not isinstance(v, (dict, list)) for v in ex.values())  # renders as key/value rows
    assert report["fatigue"]["status"] == "STABLE" and report["fatigue"]["score"] == 0.0
    assert "final_fatigue_score" not in report["fatigue"]


def test_session_report_drops_unvalidated_fields():
    report = report_for([])
    assert report["exercise"]["total_reps"] == 0
    assert report["fatigue"]["status"] == "INSUFFICIENT_REPS" and report["fatigue"]["score"] is None
    assert report["iri_history"] == [] and "iri" not in report and "uncertainty" not in report
    assert report["using_temporal"] is False and report["using_iri_v2"] is False
