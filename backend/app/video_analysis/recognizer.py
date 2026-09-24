"""Exercise recognizer: names the movement from a ~2 s window of pose landmarks.

The recognizer only names the movement. Rep counting and every form-risk flag
stay with the mode's own landmark rules (see ``movements.py``), and a label
only changes the mode through ``RecognizerGate`` in ``auto_mode.py``.

The trained model is NOT in this repository and must never be committed or
shipped with the app. It was trained on MM-Fit plus Penn Action; Penn Action
has no licence and is used for non-commercial research with citation:

  Zhang, Zhu, Derpanis, "From Actemes to Action: A Strongly-supervised
  Representation for Detailed Action Understanding", ICCV 2013.

The app reads the model from a local file named by LIFTGUARD_RECOGNIZER_MODEL
(see docs/MOVEMENT_MODES.md). The file is a plain ``.npz`` export of the random
forest (tree arrays only, loaded with ``allow_pickle=False``), made with
``export_recognizer.py``. Loading it needs numpy only: no scikit-learn version
has to match, and no pickled code is ever executed.

Features match the training pipeline (common2d / recognizer.py on the ML
side): 13 joints, 8 joint angles, hip-centred torso-scaled coordinates and
trunk tilt per frame, plus frame-to-frame deltas, summarised by mean, std,
min and max over the window.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

TARGETS = ("squats", "pushups", "lunges", "jumping_jacks")
WINDOW_FRAMES = 20        # 2.0 s at 10 fps; other lengths are resampled
MODEL_FORMAT = "liftguard-recognizer-forest-v1"

ORDER = ["nose", "ls", "rs", "le", "re", "lw", "rw", "lh", "rh", "lk", "rk", "la", "ra"]
MP = dict(nose=0, ls=11, rs=12, le=13, re=14, lw=15, rw=16, lh=23, rh=24, lk=25, rk=26, la=27, ra=28)
ANGLES = [("ls", "le", "lw"), ("rs", "re", "rw"), ("le", "ls", "lh"), ("re", "rs", "rh"),
          ("ls", "lh", "lk"), ("rs", "rh", "rk"), ("lh", "lk", "la"), ("rh", "rk", "ra")]


def pick(xy: np.ndarray, m: dict = MP) -> np.ndarray:
    """(T, 33, 2) -> (T, 13, 2) in ORDER."""
    return np.stack([xy[:, m[k]] for k in ORDER], 1)


def frame_features(P: np.ndarray) -> np.ndarray:
    """P: (T, 13, 2) image coords (any scale, y down). Returns (T, F); NaN rows are kept."""
    i = {k: n for n, k in enumerate(ORDER)}

    def ang(a, b, c):
        v1, v2 = P[:, i[a]] - P[:, i[b]], P[:, i[c]] - P[:, i[b]]
        cos = (v1 * v2).sum(-1) / (np.linalg.norm(v1, axis=-1) * np.linalg.norm(v2, axis=-1) + 1e-8)
        return np.degrees(np.arccos(np.clip(cos, -1, 1))) / 180

    A = np.stack([ang(*t) for t in ANGLES], -1)
    hip = (P[:, i["lh"]] + P[:, i["rh"]]) / 2
    sh = (P[:, i["ls"]] + P[:, i["rs"]]) / 2
    sc = np.linalg.norm(sh - hip, axis=-1, keepdims=True) + 1e-6
    rel = (P - hip[:, None]) / sc[:, None]
    tv = sh - hip
    tilt = (np.arctan2(tv[:, 0], -tv[:, 1]) / math.pi)[:, None]
    return np.concatenate([A, rel.reshape(len(P), -1), np.abs(tilt)], -1).astype(np.float32)


def window_features(lm, width: float, height: float) -> np.ndarray | None:
    """lm: (T, 33, >=2) normalized landmarks, NaN where there is no pose.

    Returns the (WINDOW_FRAMES, 2F) per-frame matrix, or None when fewer than
    80% of the frames have a pose (or the window is too short).
    """
    lm = np.asarray(lm, dtype=np.float32)
    if lm.ndim != 3 or lm.shape[1] != 33 or len(lm) < 5:
        return None
    xy = lm[..., :2].copy()
    xy[..., 0] *= width / height
    F = frame_features(pick(xy))
    ok = ~np.isnan(F).any(-1)
    if ok.mean() < 0.8:
        return None
    idx = np.where(ok, np.arange(len(F)), 0)
    np.maximum.accumulate(idx, out=idx)
    F = F[idx]
    F[:np.argmax(ok)] = F[np.argmax(ok)]
    if len(F) != WINDOW_FRAMES:
        F = F[np.linspace(0, len(F) - 1, WINDOW_FRAMES).round().astype(int)]
    V = np.diff(F, axis=0, prepend=F[:1])
    return np.concatenate([F, V], -1)


def summary_features(X: np.ndarray, keep: np.ndarray) -> np.ndarray:
    X = X[:, keep]
    return np.concatenate([X.mean(0), X.std(0), X.min(0), X.max(0)])


class ForestRecognizer:
    """Random-forest recognizer loaded from the ``.npz`` export (numpy only)."""

    def __init__(self, model_path: str | Path) -> None:
        with np.load(model_path, allow_pickle=False) as z:
            fmt = str(z["format"]) if "format" in z.files else ""
            if fmt != MODEL_FORMAT:
                raise ValueError(f"{model_path}: not a LiftGuard recognizer export (format {fmt!r})")
            self.classes = [str(c) for c in z["classes"]]
            self.keep = z["keep"].astype(np.int64)
            self.left = z["left"].astype(np.int64)
            self.right = z["right"].astype(np.int64)
            self.feature = z["feature"].astype(np.int64)
            self.threshold = z["threshold"].astype(np.float64)
            self.value = z["value"].astype(np.float64)       # per-node class fractions
            self.roots = z["roots"].astype(np.int64)
        if self.value.shape[1] != len(self.classes):
            raise ValueError(f"{model_path}: class count does not match leaf values")

    def predict_proba(self, f: np.ndarray) -> np.ndarray:
        # Trees compare float32 features against float64 thresholds, as scikit-learn does.
        x = np.asarray(f, dtype=np.float32).astype(np.float64)
        node = self.roots.copy()
        while True:
            inner = self.left[node] >= 0
            if not inner.any():
                break
            n = node[inner]
            go_left = x[self.feature[n]] <= self.threshold[n]
            node[inner] = np.where(go_left, self.left[n], self.right[n])
        leaf = self.value[node]
        leaf = leaf / leaf.sum(1, keepdims=True)
        return leaf.mean(0)

    def predict(self, lm, width: float, height: float) -> tuple[str, float]:
        """Returns (label, confidence); label is one of TARGETS or 'other'. No pose -> ('other', 0.0)."""
        X = window_features(lm, width, height)
        if X is None:
            return ("other", 0.0)
        p = self.predict_proba(summary_features(X, self.keep))
        i = int(p.argmax())
        label = self.classes[i]
        return (label if label in TARGETS else "other", float(p[i]))


def load_recognizer(model_path: str | Path) -> ForestRecognizer:
    path = Path(model_path)
    if path.suffix != ".npz":
        raise ValueError(f"{path}: expected the .npz export from export_recognizer.py "
                         "(raw .joblib pickles are not loaded by the app)")
    return ForestRecognizer(path)
