"""On-device face ID: face embeddings computed and stored on this machine only.

What is kept: one 128-number embedding per enrolled user (the average of a few
good frames), in the local SQLite user database. No face image, crop or photo
is ever written anywhere. Frames sent for enrollment or identification are
decoded in memory, turned into an embedding and dropped.

What never happens: the embedding is not sent to the contributions store, the
Hugging Face dataset, telemetry, the WebSocket stream or the logs. Contributions
stay body landmarks only.

Models (not in the repo, fetched once with ``fetch_face_models.py``):
- YuNet face detector, MIT licence (OpenCV Zoo).
- SFace face recognizer (MobileFaceNet), Apache-2.0 licence (OpenCV Zoo).
  OpenCV Zoo does not say which dataset these weights were trained on; the
  SFace paper used CASIA-WebFace, VGGFace2 and MS-Celeb-1M, which are research
  datasets of public celebrity photos. Fine for the free pilot; revisit before
  any paid or distributed release. See docs/FACE_ID.md.

Both run through OpenCV's own ``cv2.FaceDetectorYN`` / ``cv2.FaceRecognizerSF``
(already in the pinned opencv-contrib 4.8), so there are no extra packages.
When the model files are missing, face ID is off and sessions start as Guest.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

EMBED_DIM = 128
MODEL_NAME = "sface-2021dec"
DETECTOR_FILE = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_FILE = "face_recognition_sface_2021dec.onnx"
MODEL_SHA256 = {
    DETECTOR_FILE: "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    RECOGNIZER_FILE: "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
}
MODEL_URLS = {
    DETECTOR_FILE: "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/"
                   + DETECTOR_FILE,
    RECOGNIZER_FILE: "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/"
                     + RECOGNIZER_FILE,
}

# SFace's documented cosine threshold for "same person" is 0.363. A match also
# needs a margin over the next enrolled user so two look-alikes are not guessed.
MATCH_THRESHOLD = 0.363
MATCH_MARGIN = 0.05
DETECT_SCORE = 0.9
MIN_FACE_PX = 60           # face box side in pixels; smaller faces embed badly
MIN_ENROLL_SAMPLES = 5
ENROLL_CONSISTENCY = MATCH_THRESHOLD  # every pair of enrollment samples must look like one person
CONFIRM_FRAMES = 3         # identification: same user on 3 good frames in a row


def model_dir() -> Path:
    default = Path(__file__).resolve().parents[2] / "models" / "face"
    return Path(os.environ.get("LIFTGUARD_FACE_MODEL_DIR", "") or default)


def models_present(directory: Path | None = None) -> bool:
    d = directory or model_dir()
    return all((d / f).is_file() for f in (DETECTOR_FILE, RECOGNIZER_FILE))


def normalize(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def cosine(a, b) -> float:
    return float(np.dot(normalize(a), normalize(b)))


@dataclass
class EmbedResult:
    embedding: np.ndarray | None
    reason: str | None          # why there is no embedding: no_face, many_faces, small_face
    box: tuple | None = None    # x, y, w, h of the face (for on-screen guides only)


class SFaceEmbedder:
    """YuNet detection + SFace embedding on one BGR frame. Nothing is stored."""

    def __init__(self, directory: Path | None = None):
        import cv2

        d = directory or model_dir()
        self._cv2 = cv2
        self.detector = cv2.FaceDetectorYN.create(str(d / DETECTOR_FILE), "", (320, 320), DETECT_SCORE, 0.3, 50)
        self.recognizer = cv2.FaceRecognizerSF.create(str(d / RECOGNIZER_FILE), "")

    def embed(self, frame_bgr) -> EmbedResult:
        h, w = frame_bgr.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(frame_bgr)
        if faces is None or len(faces) == 0:
            return EmbedResult(None, "no_face")
        if len(faces) > 1:
            return EmbedResult(None, "many_faces")
        face = faces[0]
        box = tuple(int(round(v)) for v in face[:4])
        if min(box[2], box[3]) < MIN_FACE_PX:
            return EmbedResult(None, "small_face", box)
        aligned = self.recognizer.alignCrop(frame_bgr, face)
        feature = self.recognizer.feature(aligned)
        del aligned                                   # the crop is never kept
        return EmbedResult(normalize(feature), None, box)


def enrollment_embedding(embeddings: list) -> tuple[np.ndarray | None, str | None]:
    """Average of the good samples, or (None, reason)."""
    good = [normalize(e) for e in embeddings if e is not None]
    if len(good) < MIN_ENROLL_SAMPLES:
        return None, f"Found one clear face in only {len(good)} frames (need {MIN_ENROLL_SAMPLES})."
    stack = np.stack(good)
    if float((stack @ stack.T).min()) < ENROLL_CONSISTENCY:
        return None, "The frames don't look like the same face. Keep only yourself in view and try again."
    return normalize(stack.mean(axis=0)), None


def best_match(embedding, gallery: dict[int, np.ndarray]) -> tuple[int | None, float]:
    """(user_id, score) of the enrolled user this face matches, or (None, best score)."""
    if not gallery:
        return None, 0.0
    scores = sorted(((cosine(embedding, g), uid) for uid, g in gallery.items()), reverse=True)
    top, uid = scores[0]
    runner = scores[1][0] if len(scores) > 1 else -1.0
    if top >= MATCH_THRESHOLD and top - runner >= MATCH_MARGIN:
        return uid, top
    return None, top


class FaceGallery:
    """Embeddings in the local user database (table ``face_embeddings``)."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS face_embeddings (
        user_id    INTEGER PRIMARY KEY,
        model      TEXT    NOT NULL,
        dim        INTEGER NOT NULL,
        vector     BLOB    NOT NULL,
        samples    INTEGER NOT NULL,
        created_at TEXT    NOT NULL
    );
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        with self._connect() as conn:
            conn.executescript(self.SCHEMA)

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def save(self, user_id: int, embedding, samples: int) -> None:
        v = normalize(embedding)
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO face_embeddings VALUES (?, ?, ?, ?, ?, ?)",
                         (int(user_id), MODEL_NAME, int(v.size), v.astype(np.float32).tobytes(), int(samples),
                          datetime.now().isoformat(timespec="seconds")))

    def load(self) -> dict[int, np.ndarray]:
        with self._connect() as conn:
            rows = conn.execute("SELECT user_id, dim, vector FROM face_embeddings WHERE model = ?",
                                (MODEL_NAME,)).fetchall()
        return {uid: np.frombuffer(blob, dtype=np.float32, count=dim).copy() for uid, dim, blob in rows}

    def forget(self, user_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM face_embeddings WHERE user_id = ?", (int(user_id),))
            return cur.rowcount > 0

    def enrolled_ids(self) -> set[int]:
        return set(self.load())


def purge_stored_face_images(db_path: str | Path) -> int:
    """Delete face images and photos older versions stored (LBPH samples, profile JPEG).

    Returns how many users had image data removed. Their accounts and history
    stay; they re-enroll to get a face embedding.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
        wanted = [c for c in ("face_features", "profile_photo", "face_histogram") if c in cols]
        if not wanted:
            return 0
        where = " OR ".join(f"{c} IS NOT NULL" for c in wanted)
        n = conn.execute(f"SELECT COUNT(*) FROM users WHERE {where}").fetchone()[0]
        if n:
            conn.execute(f"UPDATE users SET {', '.join(f'{c} = NULL' for c in wanted)}")
            conn.commit()
            conn.execute("VACUUM")     # so the deleted image bytes are not left in the file
        return int(n)
    finally:
        conn.close()


class Identifier:
    """Streaming identification: the same user on CONFIRM_FRAMES good frames in a row."""

    def __init__(self, gallery: dict[int, np.ndarray], confirm_frames: int = CONFIRM_FRAMES):
        self.gallery = gallery
        self.confirm_frames = confirm_frames
        self.candidate: int | None = None
        self.count = 0
        self.last_score = 0.0

    def observe(self, embedding) -> int | None:
        if embedding is None:
            self.candidate, self.count = None, 0
            return None
        uid, self.last_score = best_match(embedding, self.gallery)
        if uid is None or uid != self.candidate:
            self.candidate, self.count = uid, (1 if uid is not None else 0)
        else:
            self.count += 1
        if uid is not None and self.count >= self.confirm_frames:
            return uid
        return None
