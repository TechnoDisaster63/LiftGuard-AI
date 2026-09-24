"""Full 33-point MediaPipe-style skeletons built from geometry, for recognizer wiring tests.

Each generator returns a list of frames; a frame is a list of 33 objects with
``x``, ``y`` (normalized to the frame, y down) and ``visibility``, like
``results.pose_landmarks.landmark``. Coordinates are built in frame-height
units and x is divided by the aspect ratio. These are cartoons of each
movement, not recordings: they prove the plumbing, not recognition accuracy.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np

ASPECT = 16 / 9
TORSO, THIGH, SHIN, UPPER, FORE = 0.28, 0.22, 0.22, 0.15, 0.14


def _vec(angle_deg, length):
    """Unit direction measured from straight down, positive = towards +x."""
    a = math.radians(angle_deg)
    return np.array([math.sin(a), math.cos(a)]) * length


def _frame(j: dict, rng, noise=0.003, vis=0.95, hidden_side=None):
    nose = j["nose"]
    pts = [None] * 33
    pts[0] = nose
    for k, dx in zip(range(1, 11), (-.01, -.015, -.02, .01, .015, .02, -.03, .03, -.01, .01)):
        pts[k] = nose + np.array([dx, -0.01 if k < 7 else (0.0 if k < 9 else 0.02)])
    names = {11: "ls", 12: "rs", 13: "le", 14: "re", 15: "lw", 16: "rw", 23: "lh", 24: "rh",
             25: "lk", 26: "rk", 27: "la", 28: "ra"}
    for k, n in names.items():
        pts[k] = j[n]
    for k, w in zip(range(17, 23), (15, 16, 15, 16, 15, 16)):
        pts[k] = j["lw" if w == 15 else "rw"] + np.array([0.01 * (k % 3), 0.02])
    pts[29], pts[30] = j["la"] + np.array([-0.02, 0.01]), j["ra"] + np.array([-0.02, 0.01])
    pts[31], pts[32] = j["la"] + np.array([0.05, 0.02]), j["ra"] + np.array([0.05, 0.02])
    out = []
    for k, p in enumerate(pts):
        p = p + rng.normal(0, noise, 2)
        v = vis
        if hidden_side and k in {"left": (11, 13, 15, 23, 25, 27), "right": (12, 14, 16, 24, 26, 28)}[hidden_side]:
            v = 0.3
        out.append(SimpleNamespace(x=float(p[0] / ASPECT), y=float(p[1]), visibility=v))
    return out


def _cycle(frames_per_rep, reps, rest=0):
    """0 -> 1 -> 0 depth trace per rep (cosine), with optional rest frames between reps."""
    t = np.linspace(0, 2 * math.pi, frames_per_rep, endpoint=False)
    one = list((1 - np.cos(t)) / 2) + [0.0] * rest
    return one * reps


def _side_body(ankle, shin_deg, thigh_deg, torso_deg, arm_deg, elbow_bend=10.0, facing=1):
    f = facing
    knee = ankle - _vec(-f * shin_deg, SHIN) * np.array([1, 1])
    knee = np.array([ankle[0] + f * math.sin(math.radians(shin_deg)) * SHIN,
                     ankle[1] - math.cos(math.radians(shin_deg)) * SHIN])
    hip = np.array([knee[0] - f * math.sin(math.radians(thigh_deg)) * THIGH,
                    knee[1] - math.cos(math.radians(thigh_deg)) * THIGH])
    sh = np.array([hip[0] + f * math.sin(math.radians(torso_deg)) * TORSO,
                   hip[1] - math.cos(math.radians(torso_deg)) * TORSO])
    el = sh + np.array([f * math.sin(math.radians(arm_deg)) * UPPER, math.cos(math.radians(arm_deg)) * UPPER])
    wr = el + np.array([f * math.sin(math.radians(arm_deg + elbow_bend)) * FORE,
                        math.cos(math.radians(arm_deg + elbow_bend)) * FORE])
    nose = sh + np.array([f * 0.05, -0.09])
    return knee, hip, sh, el, wr, nose


def squats_side(reps=6, frames_per_rep=60, fps_noise=0.003, seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    for d in _cycle(frames_per_rep, reps, rest=5):
        ankle = np.array([0.9, 0.9])
        knee, hip, sh, el, wr, nose = _side_body(ankle, 35 * d, 95 * d, 40 * d, 80 * d)
        off = np.array([0.012, 0.0])
        j = dict(nose=nose, ls=sh + off, rs=sh, le=el + off, re=el, lw=wr + off, rw=wr, lh=hip + off, rh=hip,
                 lk=knee + off, rk=knee, la=ankle + off, ra=ankle)
        frames.append(_frame(j, rng, fps_noise))
    return frames


def squats_front(reps=6, frames_per_rep=60, seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    for d in _cycle(frames_per_rep, reps, rest=5):
        cx, floor = 0.9, 0.9
        drop = (THIGH + SHIN) * (1 - math.cos(math.radians(55 * d)))
        hip_y = floor - THIGH - SHIN + drop
        knee_spread = 0.09 + 0.04 * d
        sh_y = hip_y - TORSO * math.cos(math.radians(35 * d))
        j = dict(nose=np.array([cx, sh_y - 0.1]),
                 ls=np.array([cx + 0.09, sh_y]), rs=np.array([cx - 0.09, sh_y]),
                 le=np.array([cx + 0.1, sh_y + 0.02 + 0.1 * (1 - d)]), re=np.array([cx - 0.1, sh_y + 0.02 + 0.1 * (1 - d)]),
                 lw=np.array([cx + 0.06, sh_y + 0.05 + 0.2 * (1 - d)]), rw=np.array([cx - 0.06, sh_y + 0.05 + 0.2 * (1 - d)]),
                 lh=np.array([cx + 0.065, hip_y]), rh=np.array([cx - 0.065, hip_y]),
                 lk=np.array([cx + knee_spread, (hip_y + floor) / 2 + 0.02 * d]),
                 rk=np.array([cx - knee_spread, (hip_y + floor) / 2 + 0.02 * d]),
                 la=np.array([cx + 0.09, floor]), ra=np.array([cx - 0.09, floor]))
        frames.append(_frame(j, rng))
    return frames


def pushups_side(reps=6, frames_per_rep=50, seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    wrist, ankle = np.array([1.25, 0.86]), np.array([0.35, 0.84])
    for d in _cycle(frames_per_rep, reps, rest=5):
        elbow = 170 - 90 * d
        dist = math.sqrt(UPPER**2 + FORE**2 - 2 * UPPER * FORE * math.cos(math.radians(elbow)))
        sh = np.array([wrist[0], wrist[1] - dist])
        mx, my = (sh + wrist) / 2
        h = math.sqrt(max(UPPER**2 - (dist / 2) ** 2, 0))
        el = np.array([mx - h, my])
        hip = (sh + ankle) / 2
        knee = (hip + ankle) / 2
        nose = sh + np.array([0.08, 0.0])
        off = np.array([0.0, -0.01])
        j = dict(nose=nose, ls=sh + off, rs=sh, le=el + off, re=el, lw=wrist + off, rw=wrist, lh=hip + off, rh=hip,
                 lk=knee + off, rk=knee, la=ankle + off, ra=ankle)
        frames.append(_frame(j, rng))
    return frames


def jumping_jacks_front(reps=8, frames_per_rep=25, seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    for d in _cycle(frames_per_rep, reps):
        cx, floor = 0.9, 0.9 - 0.03 * math.sin(math.pi * d)
        hip_y = floor - THIGH - SHIN
        sh_y = hip_y - TORSO
        arm = 15 + 155 * d                      # abduction from the body
        feet = 0.08 + 0.14 * d
        def arm_pts(s):
            sh = np.array([cx + s * 0.09, sh_y])
            el = sh + np.array([s * math.sin(math.radians(arm)) * UPPER, math.cos(math.radians(arm)) * UPPER])
            wr = el + np.array([s * math.sin(math.radians(arm)) * FORE, math.cos(math.radians(arm)) * FORE])
            return sh, el, wr
        ls, le, lw = arm_pts(1)
        rs, re, rw = arm_pts(-1)
        j = dict(nose=np.array([cx, sh_y - 0.1]), ls=ls, rs=rs, le=le, re=re, lw=lw, rw=rw,
                 lh=np.array([cx + 0.065, hip_y]), rh=np.array([cx - 0.065, hip_y]),
                 lk=np.array([cx + (0.065 + feet) / 2, hip_y + THIGH]), rk=np.array([cx - (0.065 + feet) / 2, hip_y + THIGH]),
                 la=np.array([cx + feet, floor]), ra=np.array([cx - feet, floor]))
        frames.append(_frame(j, rng))
    return frames


def lunges_side(reps=6, frames_per_rep=60, seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    front_ankle, back_ankle = np.array([1.05, 0.9]), np.array([0.7, 0.9])
    for d in _cycle(frames_per_rep, reps, rest=5):
        drop = 0.16 * d
        hip = np.array([0.87, 0.9 - 0.4 + drop])
        def knee_between(ankle, forward):
            mid = (hip + ankle) / 2
            v = ankle - hip
            L = np.linalg.norm(v)
            h = math.sqrt(max(THIGH**2 - (L / 2) ** 2, 0))
            n = np.array([-v[1], v[0]]) / L
            return mid + (n if forward else -n) * h * (1 if forward else 1)
        fk = knee_between(front_ankle, False)
        bk = knee_between(back_ankle, True)
        sh = hip + np.array([0.02, -TORSO])
        el, wr = sh + np.array([0, UPPER]), sh + np.array([0.01, UPPER + FORE])
        j = dict(nose=sh + np.array([0.05, -0.09]), ls=sh, rs=sh + np.array([0.01, 0]), le=el, re=el, lw=wr, rw=wr,
                 lh=hip, rh=hip + np.array([0.01, 0]), lk=fk, rk=bk, la=front_ankle, ra=back_ankle)
        frames.append(_frame(j, rng))
    return frames


def standing_still(n=300, seed=0):
    rng = np.random.default_rng(seed)
    ankle = np.array([0.9, 0.9])
    knee, hip, sh, el, wr, nose = _side_body(ankle, 0, 0, 0, 0)
    off = np.array([0.012, 0.0])
    j = dict(nose=nose, ls=sh + off, rs=sh, le=el + off, re=el, lw=wr + off, rw=wr, lh=hip + off, rh=hip,
             lk=knee + off, rk=knee, la=ankle + off, ra=ankle)
    return [_frame(j, rng) for _ in range(n)]


def arm_curls_standing(reps=8, frames_per_rep=40, seed=0):
    """Standing bicep curls: an 'other' movement for LiftGuard (no mode)."""
    rng = np.random.default_rng(seed)
    frames = []
    ankle = np.array([0.9, 0.9])
    for d in _cycle(frames_per_rep, reps):
        knee, hip, sh, el, wr, nose = _side_body(ankle, 0, 0, 0, 5, elbow_bend=10 + 130 * d)
        off = np.array([0.012, 0.0])
        j = dict(nose=nose, ls=sh + off, rs=sh, le=el + off, re=el, lw=wr + off, rw=wr, lh=hip + off, rh=hip,
                 lk=knee + off, rk=knee, la=ankle + off, ra=ankle)
        frames.append(_frame(j, rng))
    return frames


def no_pose(n=100):
    return [None] * n


STREAMS = {
    "squats_side": squats_side, "squats_front": squats_front, "pushups_side": pushups_side,
    "jumping_jacks_front": jumping_jacks_front, "lunges_side": lunges_side,
    "standing_still": standing_still, "arm_curls_standing": arm_curls_standing,
}
