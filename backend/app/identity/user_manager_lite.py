"""
LiftGuard AI - User Manager LITE
==================================
Uses OpenCV only — NO TensorFlow, NO DeepFace, NO dlib.
Face detection via Haar Cascade.
Identity matching via ORB feature descriptors.
Zero dependency conflicts.
"""
 
import cv2
import numpy as np
import sqlite3
import pickle
import json
import time
from datetime import datetime
 
 
# ── OpenCV face detector (always available) ──────────────────
_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
_face_cascade = cv2.CascadeClassifier(_cascade_path)
print("   ✅ OpenCV Lite Face Manager loaded (no TensorFlow needed)")
 
 
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
 
 
class FaceMatcher:
    """
    OpenCV-based face matching using LBP histograms.
    No deep learning — no TensorFlow conflicts.
    """
 
    def __init__(self):
        # LBP face recognizer
        self.recognizer = cv2.face.LBPHFaceRecognizer_create(
            radius=2, neighbors=8, grid_x=8, grid_y=8
        )
        self.is_trained  = False
        self.label_map   = {}   # label_int → user_id
        self.id_map      = {}   # user_id   → label_int
        self.threshold   = 85.0  # Lower = stricter
 
    def detect_faces(self, frame_gray):
        """Returns list of (x,y,w,h) face rectangles."""
        faces = _face_cascade.detectMultiScale(
            frame_gray,
            scaleFactor  = 1.1,
            minNeighbors = 6,
            minSize      = (80, 80),
            flags        = cv2.CASCADE_SCALE_IMAGE
        )
        return faces if len(faces) > 0 else []
 
    def extract_face_region(self, frame_gray, rect, size=(100, 100)):
        """Extract and normalize a face region."""
        x, y, w, h = rect
        # Add margin
        margin = int(min(w, h) * 0.1)
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(frame_gray.shape[1], x + w + margin)
        y2 = min(frame_gray.shape[0], y + h + margin)
 
        face_roi = frame_gray[y1:y2, x1:x2]
        if face_roi.size == 0:
            return None
 
        # Resize to standard size
        face_roi = cv2.resize(face_roi, size)
 
        # Equalize histogram for lighting robustness
        face_roi = cv2.equalizeHist(face_roi)
 
        return face_roi
 
    def train(self, faces_by_user: dict):
        """
        Train recognizer.
        faces_by_user: {user_id: [face_img1, face_img2, ...]}
        """
        if not faces_by_user:
            self.is_trained = False
            return
 
        all_faces  = []
        all_labels = []
        self.label_map = {}
        self.id_map    = {}
 
        for label_int, (user_id, face_list) in enumerate(
            faces_by_user.items()
        ):
            self.label_map[label_int] = user_id
            self.id_map[user_id]      = label_int
            for face in face_list:
                all_faces.append(face)
                all_labels.append(label_int)
 
        if all_faces:
            self.recognizer.train(all_faces, np.array(all_labels))
            self.is_trained = True
            print(f"   🧠 LBPH trained on {len(faces_by_user)} users")
 
    def predict(self, face_img):
        """
        Returns (user_id, confidence) or (None, 999).
        Lower confidence = better match.
        """
        if not self.is_trained:
            return None, 999.0
 
        try:
            label, confidence = self.recognizer.predict(face_img)
            if confidence <= self.threshold:
                user_id = self.label_map.get(label)
                return user_id, confidence
        except Exception:
            pass
 
        return None, 999.0
 
 
class UserManager:
    """
    OpenCV-only user manager.
    Works without TensorFlow, DeepFace, or dlib.
    """
 
    def __init__(self, db_path="liftguard_users.db"):
        self.db_path  = db_path
        self.matcher  = FaceMatcher()
 
        self._current_session_id = -1
        self.current_user        = UserProfile.guest()
 
        # ID state machine
        self.id_candidate   = None
        self.id_frame_count = 0
        self.CONFIRM_FRAMES = 20
 
        self._init_db()
        self._load_and_train()
 
        n = len(self._get_user_count())
        print(f"   📁 DB: {db_path} ({n} users)")
 
    @property
    def current_session_id(self):
        return self._current_session_id
 
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
        """Load face data from DB and train LBPH recognizer."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_id, face_features FROM users "
                "WHERE face_features IS NOT NULL"
            ).fetchall()
 
        faces_by_user = {}
        for row in rows:
            try:
                face_list = pickle.loads(row["face_features"])
                faces_by_user[row["user_id"]] = face_list
            except Exception:
                pass
 
        if not faces_by_user:
            print("   ℹ️  No face data in DB yet")
            return
 
        # Train LBPH
        all_faces  = []
        all_labels = []
        self.matcher.label_map = {}
        self.matcher.id_map    = {}
 
        for label_int, (user_id, face_list) in enumerate(
            faces_by_user.items()
        ):
            self.matcher.label_map[label_int] = user_id
            self.matcher.id_map[user_id]      = label_int
            for face in face_list:
                all_faces.append(face)
                all_labels.append(label_int)
 
        if all_faces:
            self.matcher.recognizer.train(
                all_faces, np.array(all_labels)
            )
            self.matcher.is_trained = True
            print(f"   🧠 LBPH trained: {len(faces_by_user)} users, "
                  f"{len(all_faces)} face samples")
 
    def register_user(self, username, display_name,
                     face_images=None, profile_photo=None):
        """Register user with list of face images (numpy arrays)."""
        features_blob = None
        if face_images:
            features_blob = pickle.dumps(face_images)
 
        photo_blob = None
        if profile_photo is not None:
            _, buf = cv2.imencode(
                '.jpg', profile_photo,
                [cv2.IMWRITE_JPEG_QUALITY, 85]
            )
            photo_blob = buf.tobytes()
 
        now = datetime.now().isoformat()
 
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """INSERT INTO users
                       (username, display_name, created_at,
                        last_seen, face_features, profile_photo)
                       VALUES (?,?,?,?,?,?)""",
                    (username, display_name, now, now,
                     features_blob, photo_blob)
                )
                user_id = cur.lastrowid
                conn.commit()
 
            print(f"   ✅ Registered: {display_name} (ID={user_id})")
 
            # Retrain recognizer with new user
            self._load_and_train()
 
            return UserProfile(
                user_id=user_id,
                username=username,
                display_name=display_name
            )
 
        except sqlite3.IntegrityError:
            print("   ⚠️  Username exists")
            return self.get_user_by_username(username)
 
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
        """Single-frame identification."""
        frame_gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)
        faces = self.matcher.detect_faces(frame_gray)
 
        if len(faces) == 0:
            self.id_frame_count = 0
            self.id_candidate   = None
            return None, [], 1.0
 
        # Use largest face
        largest = max(faces, key=lambda f: f[2] * f[3])
        x, y, w, h = largest
 
        # Convert to (top, right, bottom, left) for UI
        locations = [(y, x+w, y+h, x)]
 
        if not self.matcher.is_trained:
            return None, locations, 1.0
 
        face_img = self.matcher.extract_face_region(frame_gray, largest)
        if face_img is None:
            return None, locations, 1.0
 
        user_id, confidence = self.matcher.predict(face_img)
 
        if user_id is None:
            self.id_frame_count = 0
            self.id_candidate   = None
            return None, locations, 1.0
 
        # Normalize confidence to 0-1 distance
        distance = confidence / 100.0
 
        # State machine
        if self.id_candidate and self.id_candidate[0] == user_id:
            self.id_frame_count += 1
        else:
            self.id_candidate   = (user_id, confidence)
            self.id_frame_count = 1
 
        if self.id_frame_count >= self.CONFIRM_FRAMES:
            profile = self.get_user_by_id(user_id)
            if profile:
                self.id_frame_count = 0
                self.id_candidate   = None
                return profile, locations, distance
 
        return None, locations, distance
 
    def identify_from_camera(self, cap, timeout=20.0,
                            allow_new_user=True, allow_guest=True):
        """Full identification UI flow."""
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
        CONFIRM      = 20
 
        while True:
            ret, frame = cap.read()
            if not ret:
                continue
 
            elapsed    = time.time() - start_time
            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            display    = frame.copy()
            h, w       = display.shape[:2]
 
            faces = self.matcher.detect_faces(frame_gray)
            matched_uid  = None
            confidence_v = 999.0
 
            if len(faces) > 0:
                largest = max(faces, key=lambda f: f[2]*f[3])
                x, y, fw, fh = largest
 
                if self.matcher.is_trained:
                    face_img = self.matcher.extract_face_region(
                        frame_gray, largest
                    )
                    if face_img is not None:
                        matched_uid, confidence_v = self.matcher.predict(
                            face_img
                        )
 
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
                    label = f"Match: {nm} ({confidence_v:.0f})"
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
 
    def _enroll_new_user(self, cap, existing_frames=None):
        """Enroll new user with LBPH face recognition."""
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
 
        face_images   = []
        profile_photo = None
        start_time    = time.time()
        DURATION      = 6.0
        MIN_FACES     = 30   # minimum samples needed
 
        while time.time() - start_time < DURATION or \
              len(face_images) < MIN_FACES:
 
            # Hard timeout
            if time.time() - start_time > DURATION + 3:
                break
 
            ret, frame = cap.read()
            if not ret:
                continue
 
            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            display    = frame.copy()
            h, w       = display.shape[:2]
            elapsed    = time.time() - start_time
 
            faces = self.matcher.detect_faces(frame_gray)
 
            if len(faces) > 0:
                largest = max(faces, key=lambda f: f[2]*f[3])
                x, y, fw, fh = largest
 
                face_img = self.matcher.extract_face_region(
                    frame_gray, largest
                )
                if face_img is not None:
                    face_images.append(face_img)
                    if profile_photo is None:
                        profile_photo = frame.copy()
 
                cv2.rectangle(display,(x,y),(x+fw,y+fh),(0,255,0),3)
                cv2.putText(display,
                           f"CAPTURED #{len(face_images)}",
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
                       f"{len(face_images)} samples — "
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
 
        print(f"\n  📊 Captured {len(face_images)} face samples")
 
        if len(face_images) < 10:
            print("  ❌ Not enough samples — try better lighting")
            return UserProfile.guest()
 
        # Save and train
        profile = self.register_user(
            username      = username,
            display_name  = display_name,
            face_images   = face_images,
            profile_photo = profile_photo
        )
 
        print(f"\n  ✅ REGISTERED: {display_name} (ID #{profile.user_id})")
        print(f"  Samples: {len(face_images)}")
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
