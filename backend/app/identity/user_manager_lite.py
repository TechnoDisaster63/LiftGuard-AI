"""
LiftGuard AI - User Manager LITE
==================================
Users, baselines and sessions in a local SQLite file, plus on-device face ID
(see face_id.py): one face embedding per enrolled user, computed and stored on
this machine only. No face images or photos are stored.
"""

import cv2
import sqlite3
import json
import time
from datetime import datetime

from . import face_id


DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT    UNIQUE NOT NULL,
    display_name   TEXT    NOT NULL,
    created_at     TEXT    NOT NULL,
    last_seen      TEXT,
    total_sessions INTEGER DEFAULT 0,
    face_histogram BLOB,
    face_features  BLOB,
    profile_photo  BLOB,
    settings       TEXT DEFAULT '{}'
);
 
CREATE TABLE IF NOT EXISTS user_baselines (
    baseline_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    created_at     TEXT    NOT NULL,
    spine_mean     REAL DEFAULT 0,
    spine_std      REAL DEFAULT 5,
    hip_mean       REAL DEFAULT 160,
    hip_std        REAL DEFAULT 10,
    stability_mean REAL DEFAULT 0.85,
    stability_std  REAL DEFAULT 0.05,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
 
CREATE TABLE IF NOT EXISTS sessions (
    session_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    started_at    TEXT    NOT NULL,
    ended_at      TEXT,
    total_reps    INTEGER DEFAULT 0,
    peak_iri      REAL    DEFAULT 0,
    mean_iri      REAL    DEFAULT 0,
    mean_spine    REAL    DEFAULT 0,
    peak_risk     INTEGER DEFAULT 0,
    exercise_type TEXT    DEFAULT 'Unknown',
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
"""
 
 
class UserProfile:
    def __init__(self, user_id, username, display_name,
                 face_encoding=None, baseline=None,
                 settings=None, total_sessions=0, last_seen=None):
        self.user_id        = user_id
        self.username       = username
        self.display_name   = display_name
        self.face_encoding  = face_encoding
        self.baseline       = baseline  or {}
        self.settings       = settings  or {}
        self.total_sessions = total_sessions
        self.last_seen      = last_seen
        self.is_guest       = (user_id == -1)
 
    @classmethod
    def guest(cls):
        return cls(-1, "guest", "Guest User")
 
 
class UserManager:
    """
    OpenCV-only user manager.
    Works without TensorFlow, DeepFace, or dlib.
    """
 
    def __init__(self, db_path="liftguard_users.db"):
        self.db_path  = db_path

        self._current_session_id = -1
        self.current_user        = UserProfile.guest()

        # ID state machine (identify_from_frame)
        self.CONFIRM_FRAMES = face_id.CONFIRM_FRAMES
        self.id_candidate   = None
        self.id_frame_count = 0

        self._init_db()
        # Older versions stored face images (LBPH samples) and a profile JPEG
        # per user. Delete them: only embeddings are kept now.
        purged = face_id.purge_stored_face_images(db_path)
        if purged:
            print(f"   🧹 Deleted stored face images for {purged} user(s); they re-enroll for face ID")
        self.gallery   = face_id.FaceGallery(db_path)
        self._embedder = None
        self._embedder_error = None
        self._load_and_train()
        self._identifier = face_id.Identifier(self._embeddings)

        n = len(self._get_user_count())
        print(f"   📁 DB: {db_path} ({n} users)")

    @property
    def current_session_id(self):
        return self._current_session_id

    # ── face ID ───────────────────────────────────────────────
    @property
    def embedder(self):
        """The YuNet+SFace embedder, or None when the model files are missing."""
        if self._embedder is None and self._embedder_error is None:
            if not face_id.models_present():
                self._embedder_error = "models_missing"
            else:
                try:
                    self._embedder = face_id.SFaceEmbedder()
                except Exception as exc:  # corrupt file, OpenCV without FaceRecognizerSF
                    self._embedder_error = f"{type(exc).__name__}"
        return self._embedder

    def face_id_status(self):
        available = self.embedder is not None
        return {
            "available": available,
            "reason": None if available else self._embedder_error,
            "model": face_id.MODEL_NAME if available else None,
            "enrolled_user_ids": sorted(self._embeddings),
        }

    def embed_bgr(self, frame_bgr):
        emb = self.embedder
        if emb is None:
            return face_id.EmbedResult(None, "unavailable")
        return emb.embed(frame_bgr)

    def enroll_face(self, user_id, embeddings):
        """Save the average embedding for user_id. Returns (ok, message)."""
        mean, err = face_id.enrollment_embedding(embeddings)
        if mean is None:
            return False, err
        self.gallery.save(user_id, mean, samples=sum(e is not None for e in embeddings))
        self._load_and_train()
        return True, None

    def forget_face(self, user_id):
        removed = self.gallery.forget(user_id)
        self._load_and_train()
        return removed

    def is_enrolled(self, user_id):
        return user_id in self._embeddings

    def match_embedding(self, embedding):
        return face_id.best_match(embedding, self._embeddings)

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(DB_SCHEMA)
            conn.commit()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_user_count(self):
        with self._connect() as conn:
            rows = conn.execute("SELECT user_id FROM users").fetchall()
        return rows

    def _load_and_train(self):
        """Load enrolled face embeddings from the local database."""
        self._embeddings = self.gallery.load()
        if getattr(self, "_identifier", None) is not None:
            self._identifier.gallery = self._embeddings

    def register_user(self, username, display_name, embeddings=None):
        """Create a user; with ``embeddings`` (from embed_bgr) also enroll their face.

        No images are stored. Returns the profile, or None if the face
        samples were rejected (then no user is created).
        """
        if embeddings is not None:
            mean, err = face_id.enrollment_embedding(embeddings)
            if mean is None:
                raise ValueError(err)
        now = datetime.now().isoformat()
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO users (username, display_name, created_at, last_seen)
                       VALUES (?,?,?,?)""",
                    (username, display_name, now, now),
                )
                user_id = cur.lastrowid
                conn.commit()
        except sqlite3.IntegrityError:
            print("   ⚠️  Username exists")
            return self.get_user_by_username(username)
        if embeddings is not None:
            self.gallery.save(user_id, mean, samples=sum(e is not None for e in embeddings))
            self._load_and_train()
        print(f"   ✅ Registered user ID={user_id}")
        return UserProfile(user_id=user_id, username=username, display_name=display_name)

    def get_user_by_id(self, user_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id=?", (user_id,)
            ).fetchone()
        return self._row_to_profile(row) if row else None
 
    def get_user_by_username(self, username):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username=?", (username,)
            ).fetchone()
        return self._row_to_profile(row) if row else None
 
    def get_all_users(self):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY last_seen DESC"
            ).fetchall()
        return [self._row_to_profile(r) for r in rows]
 
    def _row_to_profile(self, row):
        if not row:
            return None
        settings = {}
        if row["settings"]:
            try:
                settings = json.loads(row["settings"])
            except Exception:
                pass
        baseline = self._load_baseline(row["user_id"])
        return UserProfile(
            user_id       = row["user_id"],
            username      = row["username"],
            display_name  = row["display_name"],
            baseline      = baseline,
            settings      = settings,
            total_sessions= row["total_sessions"],
            last_seen     = row["last_seen"]
        )
 
    def _load_baseline(self, user_id):
        with self._connect() as conn:
            row = conn.execute(
                """SELECT * FROM user_baselines
                   WHERE user_id=?
                   ORDER BY created_at DESC LIMIT 1""",
                (user_id,)
            ).fetchone()
        return dict(row) if row else {}
 
    def save_baseline(self, user_id, baseline_data):
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO user_baselines
                   (user_id, created_at,
                    spine_mean, spine_std,
                    hip_mean, hip_std,
                    stability_mean, stability_std)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    user_id, now,
                    baseline_data.get("spine_mean",       0),
                    baseline_data.get("spine_std",        5),
                    baseline_data.get("hip_mean",       160),
                    baseline_data.get("hip_std",         10),
                    baseline_data.get("stability_mean", 0.85),
                    baseline_data.get("stability_std",  0.05),
                )
            )
            conn.commit()
 
    def start_session(self, user_id, exercise="Unknown"):
        if user_id == -1:
            return -1
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO sessions
                   (user_id, started_at, exercise_type)
                   VALUES (?,?,?)""",
                (user_id, now, exercise)
            )
            sid = cur.lastrowid
            conn.commit()
        self._current_session_id = sid
        return sid
 
    def end_session(self, session_id, summary):
        if session_id == -1:
            return
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """UPDATE sessions
                   SET ended_at=?, total_reps=?,
                       peak_iri=?, mean_iri=?,
                       mean_spine=?, peak_risk=?
                   WHERE session_id=?""",
                (
                    now,
                    summary.get("total_reps", 0),
                    summary.get("peak_iri",   0),
                    summary.get("mean_iri",   0),
                    summary.get("mean_spine", 0),
                    summary.get("peak_risk",  0),
                    session_id
                )
            )
            row = conn.execute(
                "SELECT user_id FROM sessions WHERE session_id=?",
                (session_id,)
            ).fetchone()
            if row:
                conn.execute(
                    """UPDATE users
                       SET total_sessions = total_sessions + 1,
                           last_seen = ?
                       WHERE user_id = ?""",
                    (now, row["user_id"])
                )
            conn.commit()
 
    def record_rep(self, session_id, user_id, rep_number,
                   spine_angle, risk_level, iri_score):
        pass  # Simplified for lite version
 
    def identify_from_frame(self, frame_rgb):
        """One frame of streaming identification.

        Returns (profile or None, face locations as (top, right, bottom, left),
        distance 0..2 where lower is closer). A profile is returned only after
        the same enrolled user matched on CONFIRM_FRAMES good frames in a row.
        """
        if self.embedder is None or not self._embeddings:
            self.id_candidate, self.id_frame_count = None, 0
            return None, [], 1.0
        result = self.embed_bgr(cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR))
        locations = []
        if result.box is not None:
            x, y, w, h = result.box
            locations = [(y, x + w, y + h, x)]
        uid = self._identifier.observe(result.embedding)
        cand = self._identifier.candidate
        self.id_candidate   = (cand, self._identifier.last_score) if cand is not None else None
        self.id_frame_count = self._identifier.count
        distance = 1.0 - self._identifier.last_score
        if uid is not None:
            profile = self.get_user_by_id(uid)
            self._identifier.candidate, self._identifier.count = None, 0
            self.id_candidate, self.id_frame_count = None, 0
            return profile, locations, distance
        return None, locations, distance

    def identify_from_camera(self, cap, timeout=20.0,
                            allow_new_user=True, allow_guest=True,
                            interactive=True):
        """Full identification UI flow.

        ``interactive=False`` is for the web backend: no OpenCV windows, no
        console input, no enrollment (it needs a typed name). It matches an
        already-enrolled face if one is seen within ``timeout`` and otherwise
        returns the Guest profile.
        """
        if not interactive:
            return self._identify_headless(cap, timeout)
        print("\n" + "=" * 55)
        print("  👤 USER IDENTIFICATION (OpenCV Lite)")
        print(f"  Users: {len(self._get_user_count())}")
        print("  [N] New   [G] Guest   [Q] Quit")
        print("=" * 55)
 
        users = self.get_all_users()
        if not users and allow_new_user:
            print("  No users yet — enrolling first user...")
            return self._enroll_new_user(cap)
 
        start_time   = time.time()
        id_candidate = None
        id_count     = 0
        CONFIRM      = 5   # interactive: 5 good frames in a row
 
        while True:
            ret, frame = cap.read()
            if not ret:
                continue
 
            elapsed    = time.time() - start_time
            display    = frame.copy()
            h, w       = display.shape[:2]

            res = self.embed_bgr(frame)
            faces = [res.box] if res.box is not None else []
            matched_uid  = None
            confidence_v = 0.0

            if faces:
                x, y, fw, fh = res.box
                if res.embedding is not None:
                    matched_uid, confidence_v = self.match_embedding(res.embedding)
                    if matched_uid:
                        if id_candidate == matched_uid:
                            id_count += 1
                        else:
                            id_candidate = matched_uid
                            id_count     = 1
                    else:
                        id_candidate = None
                        id_count     = 0

                # Draw face box
                box_col = (
                    (0, 255,   0) if matched_uid else
                    (0, 255, 255) if id_count > 5  else
                    (0, 165, 255)
                )
                cv2.rectangle(display, (x,y), (x+fw,y+fh), box_col, 3)
 
                # Corner accents
                corner = 18
                for (cx,cy),(dx,dy) in [
                    ((x,y),(1,1)), ((x+fw,y),(-1,1)),
                    ((x,y+fh),(1,-1)), ((x+fw,y+fh),(-1,-1))
                ]:
                    cv2.line(display,(cx,cy),(cx+dx*corner,cy),box_col,3)
                    cv2.line(display,(cx,cy),(cx,cy+dy*corner),box_col,3)
 
                if matched_uid:
                    p = self.get_user_by_id(matched_uid)
                    nm = p.display_name if p else "?"
                    label = f"Match: {nm} ({confidence_v:.2f})"
                    cv2.putText(display, label,
                               (x, y-12),
                               cv2.FONT_HERSHEY_SIMPLEX,
                               0.65, box_col, 2)
                else:
                    cv2.putText(display, "Unknown",
                               (x, y-12),
                               cv2.FONT_HERSHEY_SIMPLEX,
                               0.65, box_col, 2)
 
            # Progress bar
            if id_count > 0:
                bar_w = 320
                bar_x = (w - bar_w) // 2
                bar_y = h - 90
                filled = int(bar_w * id_count / CONFIRM)
                cv2.rectangle(display,(bar_x,bar_y),
                             (bar_x+bar_w,bar_y+20),(50,50,50),-1)
                cv2.rectangle(display,(bar_x,bar_y),
                             (bar_x+filled,bar_y+20),(0,255,0),-1)
                cv2.putText(display,
                           f"Confirming... {id_count}/{CONFIRM}",
                           (bar_x, bar_y-8),
                           cv2.FONT_HERSHEY_SIMPLEX,
                           0.52, (200,200,200), 1)
 
            # Header
            cv2.rectangle(display,(0,0),(w,52),(20,20,20),-1)
            cv2.putText(display,"LIFTGUARD AI — USER ID (OpenCV)",
                       (18,34),cv2.FONT_HERSHEY_SIMPLEX,
                       0.7,(255,220,0),2)
 
            # Status
            remaining = max(0, timeout - elapsed)
            if len(faces) == 0:
                status = f"No face detected [{remaining:.0f}s]"
                col    = (100, 100, 255)
            elif not matched_uid:
                status = f"Not recognised  [N]ew [{remaining:.0f}s]"
                col    = (0, 165, 255)
            else:
                p = self.get_user_by_id(matched_uid)
                status = f"Recognising: {p.display_name if p else '?'}"
                col    = (0, 255, 0)
 
            cv2.putText(display, status, (18, h-115),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)
 
            # Footer
            cv2.rectangle(display,(0,h-42),(w,h),(20,20,20),-1)
            cv2.putText(display,
                       "[N] New User    [G] Guest    [Q] Quit",
                       (18, h-14),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                       (140,140,140), 1)
 
            cv2.imshow("LiftGuard AI — Identify", display)
            key = cv2.waitKey(1) & 0xFF
 
            # Confirmed
            if id_count >= CONFIRM and id_candidate:
                profile = self.get_user_by_id(id_candidate)
                if profile:
                    cv2.destroyWindow("LiftGuard AI — Identify")
                    self.current_user = profile
                    print(f"\n  ✅ Identified: {profile.display_name}")
                    return profile
 
            if key in (ord('n'), ord('N')) and allow_new_user:
                cv2.destroyWindow("LiftGuard AI — Identify")
                return self._enroll_new_user(cap)
            elif key in (ord('g'), ord('G')) and allow_guest:
                cv2.destroyWindow("LiftGuard AI — Identify")
                print("\n  👤 Guest")
                return UserProfile.guest()
            elif key in (ord('q'), ord('Q'), 27):
                cv2.destroyWindow("LiftGuard AI — Identify")
                return UserProfile.guest()
 
            if elapsed >= timeout:
                cv2.destroyWindow("LiftGuard AI — Identify")
                if allow_new_user and len(faces) > 0:
                    return self._enroll_new_user(cap)
                return UserProfile.guest()
 
        cv2.destroyWindow("LiftGuard AI — Identify")
        return UserProfile.guest()
 
    def _identify_headless(self, cap, timeout):
        """Recognize an enrolled user without any UI; Guest on no match."""
        if not self._embeddings or self.embedder is None:
            print("  👤 Guest (no enrolled users or face ID unavailable)")
            return UserProfile.guest()
        self.id_candidate, self.id_frame_count = None, 0
        self._identifier.candidate, self._identifier.count = None, 0
        deadline = time.time() + timeout
        while time.time() < deadline:
            ret, frame = cap.read()
            if not ret:
                break
            # identify_from_frame returns a profile only after CONFIRM_FRAMES
            # consecutive matches of the same user.
            profile, _, _ = self.identify_from_frame(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if profile is not None:
                self.current_user = profile
                print(f"  ✅ Identified: {profile.display_name}")
                return profile
        print("  👤 Guest (no enrolled face recognized)")
        return UserProfile.guest()

    def _enroll_new_user(self, cap, existing_frames=None):
        """Desktop enrollment: a few seconds of frames -> one averaged face embedding."""
        print("\n" + "=" * 55)
        print("  🆕 NEW USER ENROLLMENT")
        print("=" * 55)
 
        cv2.destroyAllWindows()
        display_name = input("  Your name: ").strip() or "Athlete"
        username = display_name.lower().replace(" ","_").replace("'","")
 
        base, count = username, 1
        while self.get_user_by_username(username):
            username = f"{base}_{count}"
            count   += 1
 
        print(f"\n  Name: {display_name}")
        print("  📷 Capturing face (6 seconds)...")
        print("  Look at camera, slowly move head left & right\n")
 
        embeddings    = []
        start_time    = time.time()
        DURATION      = 6.0
        MIN_FACES     = 15   # good frames wanted
 
        while time.time() - start_time < DURATION or \
              len(embeddings) < MIN_FACES:
 
            # Hard timeout
            if time.time() - start_time > DURATION + 3:
                break
 
            ret, frame = cap.read()
            if not ret:
                continue
 
            display    = frame.copy()
            h, w       = display.shape[:2]
            elapsed    = time.time() - start_time

            res = self.embed_bgr(frame)
            faces = [res.box] if res.box is not None else []

            if faces:
                x, y, fw, fh = res.box
                if res.embedding is not None:
                    embeddings.append(res.embedding)

                cv2.rectangle(display,(x,y),(x+fw,y+fh),(0,255,0),3)
                cv2.putText(display,
                           f"CAPTURED #{len(embeddings)}",
                           (x, y-12),
                           cv2.FONT_HERSHEY_SIMPLEX,
                           0.7, (0,255,0), 2)
 
            # Progress bar
            progress = min(elapsed / DURATION, 1.0)
            bar_x, bar_y, bar_bw = 50, h-65, w-100
            cv2.rectangle(display,(bar_x,bar_y),
                         (bar_x+bar_bw,bar_y+22),(50,50,50),-1)
            cv2.rectangle(display,(bar_x,bar_y),
                         (bar_x+int(bar_bw*progress),bar_y+22),
                         (0,255,0) if len(faces)>0 else (80,80,80),-1)
            cv2.putText(display,
                       f"Enrolling {display_name} — "
                       f"{len(embeddings)} samples — "
                       f"{max(0,DURATION-elapsed):.1f}s",
                       (bar_x, bar_y-10),
                       cv2.FONT_HERSHEY_SIMPLEX,0.5,(200,200,200),1)
            cv2.putText(display, f"Enrolling: {display_name}",
                       (18,34),cv2.FONT_HERSHEY_SIMPLEX,
                       0.85,(255,220,0),2)
 
            cv2.imshow("LiftGuard AI — Enrollment", display)
            if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
                break
 
        cv2.destroyWindow("LiftGuard AI — Enrollment")
 
        print(f"\n  📊 Captured {len(embeddings)} face samples")
 
        try:
            profile = self.register_user(username=username, display_name=display_name,
                                         embeddings=embeddings)
        except ValueError as exc:
            print(f"  ❌ {exc}")
            return UserProfile.guest()

        print(f"\n  ✅ REGISTERED: {display_name} (ID #{profile.user_id})")
        print(f"  Samples: {len(embeddings)}")
        self.current_user = profile
        return profile
 
    def print_all_users(self):
        users = self.get_all_users()
        print("\n" + "=" * 55)
        print("  REGISTERED USERS")
        print("=" * 55)
        if not users:
            print("  (none)")
        for u in users:
            print(f"  [{u.user_id}] {u.display_name}"
                  f" — {u.total_sessions} sessions"
                  f" — last: {u.last_seen}")
        print("=" * 55)
 
    def update_last_seen(self, user_id):
        if user_id == -1:
            return
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET last_seen=? WHERE user_id=?",
                (now, user_id)
            )
            conn.commit()
