"""Convert the ML side's recognizer_rf.joblib into the .npz file the app loads.

Run this where the model was trained (same scikit-learn version, e.g. the
Colab notebook), then copy the .npz to the machine running the backend:

  python export_recognizer.py recognizer_rf.joblib recognizer_rf.npz

The output holds only tree arrays (no pickled code), so the app loads it with
numpy alone. It is still derived from Penn Action training data: keep it out
of git and out of anything you distribute (see docs/MOVEMENT_MODES.md).
The script prints a self-check: exported vs scikit-learn probabilities on
random inputs must agree.
"""
import argparse

import numpy as np


def export(src: str, dst: str) -> None:
    import joblib

    rf, keep = joblib.load(src)
    offsets, parts = [], {k: [] for k in ("left", "right", "feature", "threshold", "value")}
    base = 0
    for est in rf.estimators_:
        t = est.tree_
        offsets.append(base)
        left, right = t.children_left.astype(np.int64), t.children_right.astype(np.int64)
        parts["left"].append(np.where(left >= 0, left + base, -1))
        parts["right"].append(np.where(right >= 0, right + base, -1))
        parts["feature"].append(t.feature.astype(np.int32))
        parts["threshold"].append(t.threshold.astype(np.float64))
        v = t.value[:, 0, :].astype(np.float64)
        parts["value"].append(v / np.maximum(v.sum(1, keepdims=True), 1e-300))
        base += t.node_count
    arrays = {k: np.concatenate(v) for k, v in parts.items()}
    arrays["value"] = arrays["value"].astype(np.float32)
    np.savez_compressed(dst, format=np.array("liftguard-recognizer-forest-v1"),
                        classes=np.array([str(c) for c in rf.classes_]), keep=np.asarray(keep, dtype=np.int32),
                        roots=np.array(offsets, dtype=np.int64), **arrays)

    # Load the app's reader by file path (importing the app package would pull in OpenCV).
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "lg_recognizer", Path(__file__).resolve().parent / "app" / "video_analysis" / "recognizer.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ForestRecognizer = mod.ForestRecognizer

    fr = ForestRecognizer(dst)
    rng = np.random.default_rng(0)
    X = rng.normal(0, 1, (300, rf.n_features_in_)).astype(np.float32)
    ref = rf.predict_proba(X)
    ours = np.stack([fr.predict_proba(x) for x in X])
    same = (ref.argmax(1) == ours.argmax(1)).mean()
    print(f"wrote {dst}: {len(offsets)} trees, {base} nodes; argmax agreement {same:.3f}, "
          f"max |p diff| {np.abs(ref - ours).max():.2e}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src")
    ap.add_argument("dst")
    a = ap.parse_args()
    export(a.src, a.dst)
