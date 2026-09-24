"""Auto-detect wiring: recognizer -> RecognizerGate -> feed.set_mode, on synthetic streams.

The trained model is not in the repo (see docs/MOVEMENT_MODES.md), so these
tests use scripted recognizers and a tiny hand-built forest in the same .npz
format. They check the plumbing and the switching rules, not accuracy.
"""
from types import SimpleNamespace

import numpy as np
import pytest

from app.video_analysis import auto_mode
from app.video_analysis.auto_mode import AutoModeSwitcher, switcher_from_env
from app.video_analysis.live import LiveSquatFeed
from app.video_analysis.recognizer import MODEL_FORMAT, ForestRecognizer, load_recognizer, window_features
from tests.synthetic_pose import (arm_curls_standing, jumping_jacks_front, no_pose, pushups_side, squats_side,
                                  standing_still)

FPS = 25.0


class Scripted:
    """Recognizer stand-in: label/confidence as a function of stream time (window end)."""

    def __init__(self, script):
        self.script = script
        self.calls = []

    def predict(self, lm, width, height):
        assert lm.shape == (20, 33, 3)
        t = len(self.calls) * 0.5 + 2.0     # first window ends at 2 s, then one per 0.5 s
        self.calls.append(t)
        return self.script(t, lm)


def run(frames, recognizer, mode="squat", fps=FPS):
    feed = LiveSquatFeed(fps=fps, mode=mode)
    sw = AutoModeSwitcher(recognizer, mode=mode)
    modes, switched_at = [], []
    for i, f in enumerate(frames):
        feed.update(f, 16 / 9)
        new = sw.observe(f, 16 / 9, feed)
        if new:
            switched_at.append((i / fps, new))
        modes.append(feed.mode)
    return feed, sw, modes, switched_at


@pytest.fixture
def preview(monkeypatch):
    def unlock(*modes):
        monkeypatch.setenv("LIFTGUARD_PREVIEW_MODES", ",".join(modes))
    monkeypatch.delenv("LIFTGUARD_PREVIEW_MODES", raising=False)
    return unlock


# --- Switching rules -------------------------------------------------------------------

def test_steady_confident_label_switches_once_after_two_seconds(preview):
    preview("pushup")
    frames = pushups_side(reps=6)
    feed, sw, modes, switched = run(frames, Scripted(lambda t, lm: ("pushups", 0.93)))
    assert len(switched) == 1
    t, mode = switched[0]
    assert mode == "pushup" and feed.mode == "pushup"
    assert 3.8 <= t <= 4.6        # first full 2 s window, then the label held for 2 s
    assert sw.switches == [{"from": "squat", "to": "pushup", "t": pytest.approx(t, abs=0.1)}]
    assert modes[0] == "squat" and modes[-1] == "pushup"


def test_switch_starts_a_fresh_counter_for_the_new_mode(preview):
    preview("pushup")
    frames = pushups_side(reps=8)
    feed, sw, _, switched = run(frames, Scripted(lambda t, lm: ("pushups", 0.95)))
    assert switched
    status = feed.counter.status()
    assert status["movement"] == "pushup" and status["source"] == "calibrated_pushup_counter"
    # Reps come from the push-up landmark rules after the switch, not from the recognizer.
    assert status["rep_count"] >= 1


def test_unvalidated_mode_never_switches_without_preview(preview):
    frames = pushups_side(reps=6)
    feed, sw, modes, switched = run(frames, Scripted(lambda t, lm: ("pushups", 0.99)))
    assert switched == [] and set(modes) == {"squat"}
    assert sw.last["label"] == "pushups" and sw.last["counts"] is False


def test_confidence_below_threshold_changes_nothing(preview):
    preview("pushup", "jumping_jacks")
    _, _, modes, switched = run(pushups_side(reps=6), Scripted(lambda t, lm: ("pushups", 0.79)))
    assert switched == [] and set(modes) == {"squat"}


def test_flickering_labels_never_hold_long_enough(preview):
    preview("pushup", "jumping_jacks")
    flicker = Scripted(lambda t, lm: ("pushups", 0.95) if int(t / 1.5) % 2 == 0 else ("jumping_jacks", 0.95))
    _, _, modes, switched = run(jumping_jacks_front(reps=12), flicker)
    assert switched == [] and set(modes) == {"squat"}


def test_other_labels_and_no_pose_change_nothing(preview):
    preview("pushup", "lunge", "jumping_jacks")
    frames = standing_still(150) + no_pose(100) + arm_curls_standing(reps=4)
    rec = Scripted(lambda t, lm: ("other", 0.0) if np.isnan(lm[..., 0]).all() else ("other", 0.97))
    _, _, modes, switched = run(frames, rec)
    assert switched == [] and set(modes) == {"squat"}


def test_same_mode_label_does_not_restart_the_counter():
    frames = squats_side(reps=4)
    feed, _, modes, switched = run(frames, Scripted(lambda t, lm: ("squats", 0.99)))
    assert switched == [] and set(modes) == {"squat"}
    assert feed.counter.rep_count >= 2       # the squat counter was never reset


def test_never_switches_mid_rep(preview):
    preview("pushup")

    class Feed:
        """Minimal feed whose rep machine is mid-rep until t = 6 s."""
        def __init__(self):
            self.mode, self.fps, self.fixed_fps, self.t = "squat", FPS, FPS, 0.0
            self.counter = SimpleNamespace(machine=SimpleNamespace(state="bottom"))
            self.set_calls = []

        def set_mode(self, mode):
            self.set_calls.append((self.t, mode))
            self.mode = mode
            return True

    feed = Feed()
    sw = AutoModeSwitcher(Scripted(lambda t, lm: ("pushups", 0.95)), mode="squat")
    frame = standing_still(1)[0]
    for i in range(int(10 * FPS)):
        feed.t = i / FPS
        feed.counter.machine.state = "bottom" if feed.t < 6.0 else "standing"
        sw.observe(frame, 16 / 9, feed)
    assert len(feed.set_calls) == 1
    t, mode = feed.set_calls[0]
    assert mode == "pushup" and 6.0 <= t <= 6.6   # held since ~2 s, released at the first window after the rep


def test_samples_at_ten_fps_of_stream_time_whatever_the_feed_rate(preview):
    preview("jumping_jacks")
    for fps in (15.0, 30.0, 60.0):
        rec = Scripted(lambda t, lm: ("jumping_jacks", 0.9))
        frames = jumping_jacks_front(reps=int(fps / 2.5), frames_per_rep=int(fps))  # ~6 s of stream
        _, _, _, switched = run(frames, rec, fps=fps)
        assert len(switched) == 1 and 3.8 <= switched[0][0] <= 4.7, fps


def test_manual_mode_change_resets_the_candidate(preview):
    preview("pushup", "jumping_jacks")
    feed = LiveSquatFeed(fps=FPS)
    sw = AutoModeSwitcher(Scripted(lambda t, lm: ("pushups", 0.95)), mode="squat")
    frames = pushups_side(reps=6)
    for i, f in enumerate(frames):
        if i == int(3.0 * FPS):
            feed.set_mode("jumping_jacks")      # the user picked a mode in settings
        feed.update(f, 16 / 9)
        sw.observe(f, 16 / 9, feed)
        if feed.mode == "pushup":
            break
    # The window and the pushups run restarted at the manual change (3 s): refill 2 s, hold 2 s.
    assert feed.mode == "pushup" and sw.switches[0]["from"] == "jumping_jacks"
    assert 6.5 <= sw.switches[0]["t"] <= 7.5


def test_recognizer_error_turns_auto_detect_off_and_counting_continues():
    def boom(t, lm):
        raise RuntimeError("model broke")
    feed, sw, modes, switched = run(squats_side(reps=4), Scripted(boom))
    assert sw.enabled is False and "model broke" in sw.error
    assert switched == [] and set(modes) == {"squat"} and feed.counter.rep_count >= 2


# --- Model file and turning it on ------------------------------------------------------

def tiny_forest(path, classes=("other_thing", "pushups", "squats")):
    """Two stumps on summary feature 0: <= 0.5 -> class 2 (squats), else class 1 (pushups)."""
    left = np.array([1, -1, -1, 4, -1, -1])
    right = np.array([2, -1, -1, 5, -1, -1])
    feature = np.array([0, -2, -2, 0, -2, -2])
    threshold = np.array([0.5, -2, -2, 0.5, -2, -2], dtype=np.float64)
    value = np.zeros((6, len(classes)), dtype=np.float32)
    value[[1, 4], 2] = 1.0
    value[[2, 5], 1] = 0.9
    value[[2, 5], 0] = 0.1
    np.savez_compressed(path, format=np.array(MODEL_FORMAT), classes=np.array(classes),
                        keep=np.arange(10, dtype=np.int32), roots=np.array([0, 3]), left=left, right=right,
                        feature=feature, threshold=threshold, value=value)
    return path


def test_forest_export_format_predicts_like_the_trees(tmp_path):
    rec = ForestRecognizer(tiny_forest(tmp_path / "m.npz"))
    low = np.zeros(40)
    high = np.zeros(40)
    high[0] = 1.0
    assert rec.predict_proba(low).tolist() == [0.0, 0.0, 1.0]
    assert rec.predict_proba(high) == pytest.approx([0.1, 0.9, 0.0])


def test_window_features_and_no_pose(tmp_path):
    rec = ForestRecognizer(tiny_forest(tmp_path / "m.npz"))
    frames = squats_side(reps=1)[:20]
    lm = np.array([[(p.x, p.y, p.visibility) for p in f] for f in frames], dtype=np.float32)
    assert window_features(lm, 16 / 9, 1.0).shape[0] == 20
    assert window_features(lm[:12], 16 / 9, 1.0).shape[0] == 20      # other lengths are resampled
    assert rec.predict(np.full((20, 33, 3), np.nan), 640, 480) == ("other", 0.0)
    label, conf = rec.predict(lm, 16 / 9, 1.0)
    assert label in {"squats", "pushups", "other"} and 0.0 <= conf <= 1.0


def test_only_the_npz_export_is_loaded(tmp_path):
    bad = tmp_path / "recognizer_rf.joblib"
    bad.write_bytes(b"not loaded")
    with pytest.raises(ValueError, match="npz"):
        load_recognizer(bad)
    wrong = tmp_path / "x.npz"
    np.savez(wrong, a=np.zeros(3))
    with pytest.raises(ValueError, match="not a LiftGuard recognizer"):
        load_recognizer(wrong)


def test_auto_detect_is_off_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("LIFTGUARD_AUTO_DETECT", raising=False)
    monkeypatch.setenv("LIFTGUARD_RECOGNIZER_MODEL", str(tiny_forest(tmp_path / "m.npz")))
    assert switcher_from_env() is None


def test_turned_on_without_a_model_file_stays_off(monkeypatch, tmp_path):
    monkeypatch.setenv("LIFTGUARD_AUTO_DETECT", "1")
    monkeypatch.setenv("LIFTGUARD_RECOGNIZER_MODEL", str(tmp_path / "missing.npz"))
    assert switcher_from_env() is None
    monkeypatch.delenv("LIFTGUARD_RECOGNIZER_MODEL")
    assert switcher_from_env() is None


def test_turned_on_with_a_model_file(monkeypatch, tmp_path):
    monkeypatch.setenv("LIFTGUARD_AUTO_DETECT", "1")
    monkeypatch.setenv("LIFTGUARD_RECOGNIZER_MODEL", str(tiny_forest(tmp_path / "m.npz")))
    sw = switcher_from_env("squat")
    assert isinstance(sw, AutoModeSwitcher) and sw.gate.current == "squat"
    assert sw.status() == {"enabled": True, "last": None, "switches": [], "error": None}


def test_no_model_files_in_the_repo():
    from pathlib import Path
    root = Path(auto_mode.__file__).resolve().parents[3]
    found = [p for ext in ("*.joblib", "*.npz", "*.pkl") for p in root.rglob(ext)
             if "node_modules" not in p.parts and ".venv" not in p.parts]
    assert found == [], f"model files must not be committed: {found}"


# --- Engine frame loop ---------------------------------------------------------------

def test_engine_frame_loop_feeds_the_switcher(preview):
    """The real LiftGuardAI._update_live_squat / configure_live_squat, on a stand-in engine object."""
    engine_mod = pytest.importorskip("app.core.liftguard_engine")   # needs mediapipe; skipped in CI
    preview("pushup")
    Engine = engine_mod.LiftGuardAI
    eng = SimpleNamespace(process_every_n=1, current_exercise_status={}, cached_landmarks_raw=None,
                          auto_detect=AutoModeSwitcher(Scripted(lambda t, lm: ("pushups", 0.95)), mode="squat"))
    Engine.configure_live_squat(eng, source_fps=FPS, mode="squat")
    seen = []
    for f in pushups_side(reps=8):
        eng.cached_landmarks_raw = f
        Engine._update_live_squat(eng, 16 / 9)
        seen.append(eng.current_exercise_status["movement"])
    assert seen[0] == "squat" and seen[-1] == "pushup"
    status = eng.current_exercise_status
    assert status["auto_detect"]["switches"][0]["to"] == "pushup"
    assert status["source"] == "calibrated_pushup_counter" and status["rep_count"] >= 1


def test_engine_without_auto_detect_is_unchanged():
    engine_mod = pytest.importorskip("app.core.liftguard_engine")
    Engine = engine_mod.LiftGuardAI
    eng = SimpleNamespace(process_every_n=1, current_exercise_status={}, cached_landmarks_raw=None, auto_detect=None)
    Engine.configure_live_squat(eng, source_fps=FPS, mode="squat")
    for f in squats_side(reps=3):
        eng.cached_landmarks_raw = f
        Engine._update_live_squat(eng, 16 / 9)
    assert "auto_detect" not in eng.current_exercise_status
    assert eng.current_exercise_status["movement"] == "squat"
