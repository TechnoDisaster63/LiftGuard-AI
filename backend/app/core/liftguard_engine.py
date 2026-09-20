"""
LiftGuard AI - Main Application V2
====================================
COMPLETE VERSION WITH ALL FEATURES:
- Face Recognition (OpenCV LBPH - No TensorFlow conflicts)
- Temporal Convolutional Network (TCN)
- Monte Carlo Dropout Uncertainty
- Injury Risk Index V2 (Clinical-Grade)
- Acute + Cumulative Risk Separation
- Tri-Modal Corrective Feedback
- Arduino Laser Pointer
- Voice Feedback
- Risk-Color Skeleton Overlay
- Flashing HIGH RISK Border
- Body Part Correction Highlights
- CLEAN PROFESSIONAL UI
 
CONTROLS:
- [Q] Quit
- [V] Toggle Voice
- [A] Toggle Arduino
- [K] Calibrate Laser
- [C] Calibrate Form
- [M] Mirror Mode
- [T] Toggle Temporal Mode
- [U] Uncertainty Summary
- [I] IP Camera
- [0-9] Switch Camera
- [R] Session Report
- [X] Reset Reps
- [S] Save Model
- [E] Export Data
- [L] List Users
- [+/-] Speed/Quality
"""
 
import cv2
import mediapipe as mp
import numpy as np
import threading
import time
from collections import deque
from datetime import datetime
 
 
# ============================================================
# IMPORT CUSTOM MODULES
# ============================================================
 
print("\n" + "=" * 60)
print("   LIFTGUARD AI V2 — LOADING MODULES")
print("=" * 60)
 
# ── Temporal classifier ──────────────────────────────────────
TEMPORAL_CLASSIFIER_AVAILABLE = False
try:
    from ..ml.temporal_risk_classifier_v2 import HybridRiskClassifier
    TEMPORAL_CLASSIFIER_AVAILABLE = True
    print("✅ temporal_risk_classifier_v2.py")
except ImportError:
    print("⚠️  temporal_risk_classifier_v2.py not found")
 
# ── Fallback frame-level classifier ─────────────────────────
RISK_CLASSIFIER_AVAILABLE = False
if not TEMPORAL_CLASSIFIER_AVAILABLE:
    try:
        from ..ml.risk_classifier import LiftRiskClassifier
        RISK_CLASSIFIER_AVAILABLE = True
        print("✅ risk_classifier.py (fallback)")
    except ImportError:
        print("⚠️  risk_classifier.py not found")
 
# ── Uncertainty Manager ──────────────────────────────────────
UNCERTAINTY_MANAGER_AVAILABLE = False
try:
    from ..ml.uncertainty_manager import (
        UncertaintyManager,
        PredictionIntervalVisualizer
    )
    UNCERTAINTY_MANAGER_AVAILABLE = True
    print("✅ uncertainty_manager.py")
except ImportError:
    print("⚠️  uncertainty_manager.py not found")
 
# ── Fatigue Engine ───────────────────────────────────────────
FATIGUE_ENGINE_AVAILABLE = False
try:
    from ..tracking.fatigue_engine import FatigueDetectionEngine
    FATIGUE_ENGINE_AVAILABLE = True
    print("✅ fatigue_engine.py")
except ImportError:
    print("⚠️  fatigue_engine.py not found")
 
# ── Injury Risk Index V2 ─────────────────────────────────────
INJURY_PREDICTOR_AVAILABLE = False
IRI_V2_AVAILABLE            = False
try:
    from ..ml.injury_risk_index_v2 import InjuryRiskIndex
    IRI_V2_AVAILABLE           = True
    INJURY_PREDICTOR_AVAILABLE = True
    print("✅ injury_risk_index_v2.py (IRI V2)")
except ImportError:
    print("⚠️  injury_risk_index_v2.py not found, trying legacy...")
    try:
        from ..ml.injury_predictor import InjuryPredictor
        INJURY_PREDICTOR_AVAILABLE = True
        print("✅ injury_predictor.py (legacy fallback)")
    except ImportError:
        print("⚠️  No injury predictor available")
 
# ── Exercise Tracker ─────────────────────────────────────────
EXERCISE_TRACKER_AVAILABLE = False
try:
    from ..tracking.exercise_tracker import ExerciseTracker
    EXERCISE_TRACKER_AVAILABLE = True
    print("✅ exercise_tracker.py")
except ImportError:
    print("⚠️  exercise_tracker.py not found")
 
# ── Arduino Controller ───────────────────────────────────────
ARDUINO_AVAILABLE = False
try:
    from ..hardware.arduino_controller import ArduinoController
    ARDUINO_AVAILABLE = True
    print("✅ arduino_controller.py")
except ImportError:
    print("⚠️  arduino_controller.py not found")
 
# ── User Manager (Lite first — no TF conflicts) ──────────────
USER_MANAGER_AVAILABLE = False
try:
    from ..identity.user_manager_lite import UserManager, UserProfile
    from ..identity.user_ui import UserUIOverlay
    USER_MANAGER_AVAILABLE = True
    print("✅ user_manager_lite.py (OpenCV LBPH — no TF conflicts)")
except ImportError:
    try:
        from ..identity.user_manager import UserManager, UserProfile  # noqa: F401 -- presence in this import is the availability check
        from ..identity.user_ui import UserUIOverlay
        USER_MANAGER_AVAILABLE = True
        print("✅ user_manager.py")
    except ImportError:
        print("⚠️  No user manager available")
 
# ── Voice ────────────────────────────────────────────────────
VOICE_AVAILABLE = False
try:
    import pyttsx3
    VOICE_AVAILABLE = True
    print("✅ pyttsx3")
except ImportError:
    print("⚠️  pyttsx3 not installed")
 
print("=" * 60)
 
 
# ============================================================
# SIMPLE VOICE SPEAKER
# ============================================================
 
class SimpleSpeaker:
    """Thread-safe voice output with priority-weighted cooldowns."""
 
    def __init__(self, enabled=True):
        self.enabled     = enabled and VOICE_AVAILABLE
        self.is_speaking = False
        self.speech_lock = threading.Lock()
 
        self.cooldowns          = {}
        self.cooldown_durations = {
            1: 5.0,
            2: 7.0,
            3: 12.0,
            4: 20.0
        }
        self.last_speech_time = 0
        self.min_gap          = 2.0
 
        if self.enabled:
            try:
                engine = pyttsx3.init()
                engine.stop()
                print("🔊 Voice initialized")
            except Exception as e:
                print(f"⚠️  Voice failed: {e}")
                self.enabled = False
 
    def can_speak(self, correction_id=None, priority=3):
        if not self.enabled or self.is_speaking:
            return False
        current_time = time.time()
        if current_time - self.last_speech_time < self.min_gap:
            return False
        if correction_id:
            cooldown  = self.cooldown_durations.get(priority, 10.0)
            last_time = self.cooldowns.get(correction_id, 0)
            if current_time - last_time < cooldown:
                return False
        return True
 
    def speak(self, text, correction_id=None, priority=3):
        if not self.can_speak(correction_id, priority):
            return False
        if correction_id:
            self.cooldowns[correction_id] = time.time()
        thread = threading.Thread(
            target=self._speak_thread, args=(text,), daemon=True
        )
        thread.start()
        return True
 
    def speak_now(self, text):
        if not self.enabled or self.is_speaking:
            return False
        thread = threading.Thread(
            target=self._speak_thread, args=(text,), daemon=True
        )
        thread.start()
        return True
 
    def _speak_thread(self, text):
        with self.speech_lock:
            self.is_speaking = True
            try:
                engine = pyttsx3.init()
                engine.setProperty('rate', 175)
                voices = engine.getProperty('voices')
                if len(voices) > 1:
                    engine.setProperty('voice', voices[1].id)
                print(f"🔊 '{text}'")
                engine.say(text)
                engine.runAndWait()
                engine.stop()
            except Exception as e:
                print(f"⚠️  Speech error: {e}")
            finally:
                self.is_speaking      = False
                self.last_speech_time = time.time()
 
 
# ============================================================
# FORM CORRECTOR
# ============================================================
 
class FormCorrector:
    """Generates prioritised corrections from biomechanical features."""
 
    def __init__(self):
        self.last_corrections = {}
        self._last_iri        = {}
 
    def get_corrections(self, features, risk_result, fatigue_status):
        if not features:
            return []
 
        stability = features.get('stability_index', 1)
        spine     = features.get('spine_flexion', 0)
        if stability == 0.85 and spine < 2.0:
            return []
 
        corrections = []
 
        spine     = features.get('spine_flexion',      0)
        stability = features.get('stability_index',    1)
        hip       = features.get('hip_hinge_angle',  180)
        knee_asym = features.get('knee_asymmetry',     0)
        lat_tilt  = features.get('spine_lateral_tilt', 0)
        valgus_l  = abs(features.get('knee_valgus_left',  0))
        valgus_r  = abs(features.get('knee_valgus_right', 0))
        load      = features.get('spinal_load_index',  0)
        stance    = features.get('stance_width',     0.2)
 
        # ── Priority 1 — Critical ──────────────────────────────
        if spine > 50:
            corrections.append({
                'id': 'spine_critical', 'priority': 1,
                'command': "STOP! Your back is too bent! Stand up straight!",
                'display': "⚠️ DANGER: Back too bent!",
                'body_part': 'SPINE'
            })
        if stability < 0.4:
            corrections.append({
                'id': 'stability_critical', 'priority': 1,
                'command': "You're unstable! Widen your stance!",
                'display': "⚠️ Unstable! Widen stance!",
                'body_part': 'CENTER'
            })
        if fatigue_status and fatigue_status.get('alert_level') == 'red':
            corrections.append({
                'id': 'fatigue_critical', 'priority': 1,
                'command': "STOP! You're exhausted! Take a break!",
                'display': "⚠️ STOP - Take a break!",
                'body_part': 'HEAD'
            })
        if isinstance(self._last_iri, dict):
            iri_cat = self._last_iri.get('category', 'LOW')
            if iri_cat == 'CRITICAL':
                corrections.append({
                    'id': 'iri_critical', 'priority': 1,
                    'command': "Critical injury risk! Stop and rest immediately!",
                    'display': "🛑 IRI CRITICAL - Rest Now!",
                    'body_part': 'HEAD'
                })
            elif iri_cat == 'HIGH':
                corrections.append({
                    'id': 'iri_high', 'priority': 2,
                    'command': "High injury risk. Consider reducing your load.",
                    'display': "🔶 High IRI - Reduce load",
                    'body_part': 'SPINE'
                })
 
        # ── Priority 2 — Important ─────────────────────────────
        if 40 < spine <= 50:
            corrections.append({
                'id': 'spine_high', 'priority': 2,
                'command': "Straighten your back! You're bending too much!",
                'display': "Straighten your back!",
                'body_part': 'SPINE'
            })
        if hip < 90 and spine > 25:
            corrections.append({
                'id': 'hip_hinge', 'priority': 2,
                'command': "Use your legs more! Push your hips back!",
                'display': "Use legs more!",
                'body_part': 'LEFT_HIP'
            })
        if (valgus_l + valgus_r) / 2 > 15:
            corrections.append({
                'id': 'knee_valgus', 'priority': 2,
                'command': "Push your knees out! They're caving inward!",
                'display': "Push knees outward!",
                'body_part': 'LEFT_KNEE'
            })
        if lat_tilt > 0.3:
            corrections.append({
                'id': 'lateral_lean', 'priority': 2,
                'command': "You're leaning to one side! Center yourself!",
                'display': "Center yourself!",
                'body_part': 'SPINE'
            })
 
        # ── Priority 3 — Moderate ──────────────────────────────
        if fatigue_status and fatigue_status.get('alert_level') == 'orange':
            corrections.append({
                'id': 'fatigue_warning', 'priority': 3,
                'command': "Your form is getting sloppy. Consider a break.",
                'display': "Form degrading - rest soon",
                'body_part': 'HEAD'
            })
        if 30 < spine <= 40:
            corrections.append({
                'id': 'spine_medium', 'priority': 3,
                'command': "Keep your back straighter!",
                'display': "Keep back straighter",
                'body_part': 'SPINE'
            })
        if knee_asym > 20:
            corrections.append({
                'id': 'knee_asymmetry', 'priority': 3,
                'command': "Even out your legs!",
                'display': "Even out your legs!",
                'body_part': 'LEFT_KNEE'
            })
        if load > 0.7:
            corrections.append({
                'id': 'arm_reach', 'priority': 3,
                'command': "Keep the weight closer!",
                'display': "Keep weight closer!",
                'body_part': 'LEFT_SHOULDER'
            })
        if stance < 0.12 and stability < 0.7:
            corrections.append({
                'id': 'stance_width', 'priority': 3,
                'command': "Widen your stance!",
                'display': "Widen your stance!",
                'body_part': 'LEFT_ANKLE'
            })
 
        # ── Priority 4 — Tips ──────────────────────────────────
        if 20 < spine <= 30:
            corrections.append({
                'id': 'spine_low', 'priority': 4,
                'command': "Keep your back a little straighter",
                'display': "Keep back straighter",
                'body_part': 'UPPER_BACK'
            })
        if 90 <= hip < 110 and spine > 20:
            corrections.append({
                'id': 'hip_hinge_mild', 'priority': 4,
                'command': "Bend your knees a bit more",
                'display': "Bend knees more",
                'body_part': 'RIGHT_HIP'
            })
 
        corrections.sort(key=lambda x: x['priority'])
        return corrections
 
    def get_positive(self, risk_result):
        if risk_result and risk_result.get('risk_level') == 0:
            conf = risk_result.get('confidence', 0)
            if conf > 0.95:
                return {'id': 'perfect', 'command': "Perfect form!",
                        'display': "✅ PERFECT!"}
            elif conf > 0.85:
                return {'id': 'great', 'command': "Great form!",
                        'display': "✅ Great!"}
            else:
                return {'id': 'good', 'command': "Good form!",
                        'display': "✅ Good"}
        return None
 
 
# ============================================================
# DUMMY CLASSES
# ============================================================
 
class DummyRiskClassifier:
    def __init__(self):
        self.is_trained = False
 
    def train_on_synthetic_data(self):
        self.is_trained = True
        return self
 
    def train_or_load(self):
        self.is_trained = True
        return self
 
    def extract_biomechanical_features(self, landmarks):
        hip_cx = (landmarks[23][0] + landmarks[24][0]) / 2
        hip_cy = (landmarks[23][1] + landmarks[24][1]) / 2
        sho_cx = (landmarks[11][0] + landmarks[12][0]) / 2
        sho_cy = (landmarks[11][1] + landmarks[12][1]) / 2
        dx     = sho_cx - hip_cx
        dy     = sho_cy - hip_cy
        spine  = np.degrees(np.arctan2(abs(dx), abs(dy)))
        return {
            'spine_flexion':      spine,
            'hip_hinge_angle':    160 - spine,
            'knee_asymmetry':     abs(landmarks[25][1] - landmarks[26][1]) * 10,
            'stability_index':    0.85,
            'spinal_load_index':  spine / 90,
            'spine_lateral_tilt': abs(landmarks[11][1] - landmarks[12][1]) / 100,
            'left_knee_angle':    170,
            'right_knee_angle':   168,
            'knee_valgus_left':   0,
            'knee_valgus_right':  0,
            'stance_width':       abs(landmarks[27][0] - landmarks[28][0]) / 500
        }
 
    def predict_risk(self, features):
        spine = features.get('spine_flexion', 0)
        if   spine < 25: return {'risk_level': 0, 'risk_label': 'SAFE',        'confidence': 0.95}
        elif spine < 35: return {'risk_level': 1, 'risk_label': 'LOW_RISK',    'confidence': 0.80}
        elif spine < 50: return {'risk_level': 2, 'risk_label': 'MEDIUM_RISK', 'confidence': 0.70}
        else:            return {'risk_level': 3, 'risk_label': 'HIGH_RISK',   'confidence': 0.90}
 
    def predict(self, features, use_uncertainty=False):
        result = self.predict_risk(features)
        if use_uncertainty:
            result['uncertainty']           = 0.0
            result['uncertainty_per_class'] = [0.0, 0.0, 0.0, 0.0]
            result['mode']                  = 'frame'
        return result
 
    def calibrate_to_person(self, data):
        pass
 
    def save_model(self, path=None):
        print("💾 Model saved (dummy)")
 
 
class DummyFatigueEngine:
    def __init__(self):
        self.lifts   = 0
        self.fatigue = 100
 
    def update(self, features):
        spine = features.get('spine_flexion', 0)
        if spine > 25:
            self.lifts   += 0.02
            self.fatigue  = max(0, 100 - self.lifts * 2)
        if   self.fatigue > 75: alert = 'green'
        elif self.fatigue > 50: alert = 'yellow'
        elif self.fatigue > 25: alert = 'orange'
        else:                   alert = 'red'
        return {
            'fatigue_score':   self.fatigue,
            'alert_level':     alert,
            'lifts_completed': int(self.lifts)
        }
 
    def get_session_report(self):
        return {'total_lifts': int(self.lifts), 'final_fatigue': self.fatigue}
 
 
class DummyInjuryPredictor:
    def predict_injury_risk(self, **kwargs):
        fatigue = kwargs.get('fatigue_score', 100)
        prob    = max(0, (100 - fatigue) / 2)
        if   prob < 15: cat = 'LOW';      action = '✅ Continue normally'
        elif prob < 35: cat = 'MODERATE'; action = '⚠️ Monitor form'
        elif prob < 60: cat = 'HIGH';     action = '🔶 Reduce load'
        else:           cat = 'CRITICAL'; action = '🛑 STOP - Rest now'
        return {
            'probability': prob, 'category': cat, 'action': action,
            'acute_risk': prob, 'cumulative_risk': prob, 'combined_iri': prob,
            'contributing_factors': ['⚠️ Fallback predictor active'],
            'confidence_interval': {
                'lower': max(0, prob-8), 'upper': min(100, prob+8),
                'text':  f"{prob:.1f}% [{max(0,prob-8):.1f}%–{min(100,prob+8):.1f}%]"
            },
            'disclaimer': 'IRI is not a medical diagnosis'
        }
 
    def get_session_report(self):
        return {
            'total_lifts': 0,
            'iri_stats': {'mean': 0, 'max': 0, 'min': 0, 'final': 0},
            'disclaimer': 'IRI is not a medical diagnosis'
        }
 
    def start_session(self): pass
    def record_lift(self, spine_angle, asymmetry): pass
 
 
class DummyExerciseTracker:
    def __init__(self):
        self.reps           = 0
        self.phase          = 'standing'
        self.exercise       = 'Unknown'
        self.down_threshold = 20
        self.up_threshold   = 12
 
    def update(self, features, risk_result=None, fatigue_status=None):
        spine = features.get('spine_flexion', 0)
        knee  = features.get('left_knee_angle', 180)
        if self.phase == 'standing' and spine > self.down_threshold:
            self.phase = 'down'
        elif self.phase == 'down' and spine < self.up_threshold:
            self.phase = 'standing'
            self.reps += 1
            print(f"   🔢 Rep! Total: {self.reps}")
        if   spine > 30 and knee < 130: self.exercise = 'Squat'
        elif spine > 35 and knee > 140: self.exercise = 'Deadlift'
        elif spine > 20:                self.exercise = 'Hip Hinge'
        return {
            'rep_count':         self.reps,
            'exercise':          self.exercise,
            'phase_display':     '🧍' if self.phase == 'standing' else '⬇️',
            'last_rep_duration': 2.0
        }
 
    def get_session_summary(self):
        return {'total_reps': self.reps, 'exercise': self.exercise}
 
    def export_to_csv(self):       print("📁 CSV exported")
    def export_rep_summary(self):  print("📁 Rep summary exported")
    def reset(self):
        self.reps  = 0
        self.phase = 'standing'
 
 
class DummyArduino:
    def __init__(self):
        self.connected         = False
        self.current_priority  = 0
        self.laser_on          = False
        self.is_calibrated     = False
        self.auto_mode         = False
        self.current_body_part = None
        self.mirror            = False
        self.camera_index      = 0
        self.frame_width       = 1280
        self.frame_height      = 720
 
    def connect(self):             return False
    def disconnect(self):          self.connected = False
    def point_at_body_part(self, part, priority=1): pass
    def set_safe(self):            self.current_priority = 0
    def center(self):              pass
    def laser_on_cmd(self):        self.laser_on = True
    def laser_off(self):           self.laser_on = False
    def beep(self, duration=100):  pass
    def update_frame(self, frame, landmarks=None): pass
    def select_camera(self):       return False
    def calibrate(self):           return False
 
 
class DummyUserManager:
    class _GuestProfile:
        user_id        = -1
        username       = "guest"
        display_name   = "Guest User"
        is_guest       = True
        total_sessions = 0
        last_seen      = None
        baseline       = {}
        settings       = {}
 
    def identify_from_camera(self, cap, **kwargs):
        return self._GuestProfile()
 
    def identify_from_frame(self, frame_rgb):
        return None, [], 1.0
 
    def start_session(self, user_id, exercise="Unknown"):
        return -1
 
    def end_session(self, session_id, summary):       pass
    def record_rep(self, *args, **kwargs):            pass
    def save_baseline(self, user_id, baseline):       pass
    def get_all_users(self):                          return []
    def get_user_by_id(self, uid):                    return None
    def print_all_users(self):
        print("  (user manager not available)")
 
    @property
    def current_session_id(self): return -1
    @property
    def id_candidate(self):       return None
    @property
    def id_frame_count(self):     return 0
 
 
class DummyUserUIOverlay:
    def draw(self, img, user_profile, panel_x, panel_y,
             panel_w=280, id_state="guest"):
        return panel_y
 
    def draw_scanning_overlay(self, img, face_locations,
                              id_count, confirm_needed,
                              candidate_name=None):
        pass
 
 
# ============================================================
# MAIN LIFTGUARD AI CLASS
# ============================================================
 
class LiftGuardAI:
    """LiftGuard AI V2 — Complete integrated system."""
 
    # ──────────────────────────────────────────────────────────
    # INIT
    # ──────────────────────────────────────────────────────────
 
    def __init__(
        self,
        voice_enabled    = True,
        arduino_enabled  = True,
        model_complexity = 0,
        process_every_n  = 1,
        use_temporal     = True
    ):
        print("\n" + "=" * 60)
        print("🚀 INITIALIZING LIFTGUARD AI V2")
        print("=" * 60 + "\n")
 
        self.model_complexity = model_complexity
        self.process_every_n  = process_every_n
        self.use_temporal     = use_temporal
        self.ip_camera_url    = "http://10.98.89.217:8080/video"
 
        print(f"⚡ complexity={model_complexity}, skip={process_every_n}")
        print(f"🧠 Temporal: {'ON' if use_temporal else 'OFF'}")
 
        print("\n📦 Loading components...")
        self._init_risk_classifier()
        self._init_fatigue_engine()
        self._init_injury_predictor()
        self._init_exercise_tracker()
        self._init_uncertainty_manager()
        self._init_user_manager()
        self.form_corrector = FormCorrector()
        print("   ✅ Form Corrector")
 
        # Voice
        self.speaker       = SimpleSpeaker(enabled=voice_enabled)
        self.voice_enabled = self.speaker.enabled
        self.last_rep_announced      = 0
        self.last_positive_time      = 0
        self.good_form_start_time    = 0
        self.spoken_corrections      = set()
        self.spoken_corrections_time = 0
 
        # Arduino
        self._init_arduino(arduino_enabled)
 
        # MediaPipe
        self.mp_pose = mp.solutions.pose
        self.pose    = self.mp_pose.Pose(
            static_image_mode        = False,
            model_complexity         = self.model_complexity,
            enable_segmentation      = False,
            min_detection_confidence = 0.5,
            min_tracking_confidence  = 0.5
        )
        self.mp_draw = mp.solutions.drawing_utils
        print(f"\n📷 MediaPipe (complexity={model_complexity})")
 
        self._init_state()
 
        print("\n" + "=" * 60)
        print("✅ LIFTGUARD AI V2 READY")
        print("=" * 60 + "\n")
 
    # ── Component initialisers ─────────────────────────────────
 
    def _init_risk_classifier(self):
        if TEMPORAL_CLASSIFIER_AVAILABLE and self.use_temporal:
            self.risk_classifier = HybridRiskClassifier(
                use_temporal=True, temporal_weight=0.7
            )
            self.risk_classifier.train_or_load()
            self.using_temporal = True
            print("   ✅ Hybrid Risk Classifier (TCN + Frame)")
        elif RISK_CLASSIFIER_AVAILABLE:
            self.risk_classifier = LiftRiskClassifier()
            self.risk_classifier.train_on_synthetic_data()
            self.using_temporal = False
            print("   ✅ Risk Classifier (Frame-Level)")
        else:
            self.risk_classifier = DummyRiskClassifier()
            self.risk_classifier.train_on_synthetic_data()
            self.using_temporal = False
            print("   ⚠️  Dummy Risk Classifier")
 
    def _init_fatigue_engine(self):
        if FATIGUE_ENGINE_AVAILABLE:
            self.fatigue_engine = FatigueDetectionEngine(baseline_lifts=5)
            print("   ✅ Fatigue Engine")
        else:
            self.fatigue_engine = DummyFatigueEngine()
            print("   ⚠️  Dummy Fatigue Engine")
 
    def _init_injury_predictor(self):
        if IRI_V2_AVAILABLE:
            try:
                self.injury_predictor = InjuryRiskIndex()
                self.injury_predictor.start_session()
                self.using_iri_v2 = True
                print("   ✅ Injury Risk Index V2")
            except Exception as e:
                print(f"   ⚠️  IRI V2 failed ({e})")
                self.injury_predictor = DummyInjuryPredictor()
                self.using_iri_v2     = False
        elif INJURY_PREDICTOR_AVAILABLE:
            try:
                self.injury_predictor = InjuryPredictor()
                self.using_iri_v2     = False
                print("   ✅ Injury Predictor (legacy)")
            except Exception as e:
                print(f"   ⚠️  Legacy predictor failed ({e})")
                self.injury_predictor = DummyInjuryPredictor()
                self.using_iri_v2     = False
        else:
            self.injury_predictor = DummyInjuryPredictor()
            self.using_iri_v2     = False
            print("   ⚠️  Dummy Injury Predictor")
 
    def _init_exercise_tracker(self):
        if EXERCISE_TRACKER_AVAILABLE:
            self.exercise_tracker = ExerciseTracker()
            print("   ✅ Exercise Tracker")
        else:
            self.exercise_tracker = DummyExerciseTracker()
            print("   ⚠️  Dummy Exercise Tracker")
 
    def _init_uncertainty_manager(self):
        if UNCERTAINTY_MANAGER_AVAILABLE:
            self.uncertainty_manager = UncertaintyManager(window_size=30)
            self.interval_visualizer = PredictionIntervalVisualizer()
            print("   ✅ Uncertainty Manager")
        else:
            self.uncertainty_manager = None
            self.interval_visualizer = None
            print("   ⚠️  No Uncertainty Manager")
 
    def _init_user_manager(self):
        if USER_MANAGER_AVAILABLE:
            try:
                self.user_manager = UserManager()
                self.user_ui      = UserUIOverlay()
                print("   ✅ User Manager")
            except Exception as e:
                print(f"   ⚠️  User Manager failed ({e})")
                self.user_manager = DummyUserManager()
                self.user_ui      = DummyUserUIOverlay()
        else:
            self.user_manager = DummyUserManager()
            self.user_ui      = DummyUserUIOverlay()
            print("   ⚠️  Dummy User Manager")
 
        self.current_user         = None
        self.id_state             = "not_started"
        self._live_scan_faces     = []
        self._live_scan_count     = 0
        self._live_scan_CONFIRM   = 20
        self._live_scan_enabled   = True
        self._last_frame_rgb      = None
 
    def _init_arduino(self, arduino_enabled):
        self.arduino_enabled   = arduino_enabled
        self.arduino_connected = False
        self.arduino           = DummyArduino()
        self.last_arduino_time = 0
 
        if self.arduino_enabled and ARDUINO_AVAILABLE:
            print("\n🔌 Attempting Arduino connection...")
            try:
                self.arduino = ArduinoController()
                if self.arduino.connect():
                    self.arduino_connected = True
                    print("   ✅ Arduino connected")
                else:
                    self.arduino = DummyArduino()
                    print("   ⚠️  Arduino not found")
            except Exception as e:
                self.arduino = DummyArduino()
                print(f"   ⚠️  Arduino error: {e}")
        else:
            print("\n🔌 Arduino disabled/unavailable")
 
    def _init_state(self):
        self.session_active    = False
        self.calibration_mode  = False
        self.calibration_data  = []
        self.current_camera_id = 0
        self.mirror_mode       = False
 
        self.current_risk_result    = None
        self.current_fatigue_status = {
            'fatigue_score': 100, 'alert_level': 'green',
            'lifts_completed': 0
        }
        self.current_injury_risk = {
            'probability': 0, 'category': 'LOW',
            'acute_risk': 0, 'cumulative_risk': 0, 'combined_iri': 0,
            'contributing_factors': [],
            'confidence_interval': {
                'lower': 0, 'upper': 0, 'text': '0.0% [0.0%–0.0%]'
            },
            'disclaimer': 'IRI is not a medical diagnosis'
        }
        self.current_exercise_status = {
            'rep_count': 0, 'exercise': 'Unknown', 'phase_display': '🧍'
        }
        self.current_features    = None
        self.current_corrections = []
 
        self.cached_results       = None
        self.cached_landmarks     = None
        self.cached_landmarks_raw = None
 
        self.feedback_message = "Stand in front of camera"
        self.feedback_color   = (255, 255, 255)
 
        self.frame_times = deque(maxlen=30)
        self.frame_count = 0
 
        self._session_iri_history   = []
        self._session_spine_history = []
        self._session_peak_risk     = 0
 
    # ──────────────────────────────────────────────────────────
    # CAMERA
    # ──────────────────────────────────────────────────────────
 
    def switch_camera(self, cap, camera_id):
        print(f"\n🔄 Switching to camera {camera_id}...")
        cap.release()
        new_cap = cv2.VideoCapture(camera_id)
        if new_cap.isOpened():
            new_cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
            new_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            new_cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
            self.current_camera_id = camera_id
            print(f"   ✅ Camera {camera_id}")
            if self.voice_enabled:
                label = ("IP camera" if isinstance(camera_id, str)
                         else f"Camera {camera_id}")
                self.speaker.speak_now(f"{label} connected")
            return new_cap
        else:
            print("   ❌ Fallback to camera 0")
            fallback = cv2.VideoCapture(0)
            fallback.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
            fallback.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.current_camera_id = 0
            return fallback
 
    def connect_ip_camera(self, cap):
        return self.switch_camera(cap, self.ip_camera_url)
 
    # ──────────────────────────────────────────────────────────
    # ARDUINO
    # ──────────────────────────────────────────────────────────
 
    def toggle_arduino(self):
        if not ARDUINO_AVAILABLE:
            print("❌ Arduino not available")
            return
        if self.arduino_connected:
            self.arduino.laser_off()
            self.arduino.disconnect()
            self.arduino           = DummyArduino()
            self.arduino_connected = False
            self.arduino_enabled   = False
            print("\n🔌 Arduino disconnected")
            if self.voice_enabled:
                self.speaker.speak_now("Arduino disconnected")
        else:
            try:
                self.arduino = ArduinoController()
                if self.arduino.connect():
                    self.arduino_connected = True
                    self.arduino_enabled   = True
                    print("\n✅ Arduino connected")
                    self.arduino.laser_on_cmd()
                    time.sleep(0.3)
                    self.arduino.laser_off()
                    if self.voice_enabled:
                        self.speaker.speak_now("Arduino connected")
                else:
                    self.arduino = DummyArduino()
                    print("\n❌ Arduino not found")
            except Exception as e:
                self.arduino = DummyArduino()
                print(f"\n❌ Arduino error: {e}")
 
    # ──────────────────────────────────────────────────────────
    # LASER TRANSPORT (USB serial vs WiFi/ESP32, chosen at connect time)
    # ──────────────────────────────────────────────────────────
    # Same hot-swap pattern as switch_camera()/connect_ip_camera() above —
    # tear down whatever's currently connected (USB or WiFi), swap
    # self.arduino for a new controller instance, same public interface
    # either way since WifiArduinoController subclasses ArduinoController.

    def connect_usb_laser(self, port=None):
        self._disconnect_current_laser()
        try:
            self.arduino = ArduinoController()
            if self.arduino.connect(port):
                self.arduino_connected = True
                self.arduino_enabled   = True
                print(f"\n✅ USB laser connected on {self.arduino.port}")
                if self.voice_enabled:
                    self.speaker.speak_now("Laser connected")
            else:
                self.arduino = DummyArduino()
                self.arduino_connected = False
                print("\n❌ USB laser not found")
        except Exception as e:
            self.arduino = DummyArduino()
            self.arduino_connected = False
            print(f"\n❌ USB laser error: {e}")
        return self.arduino_connected

    def connect_wifi_laser(self, host):
        self._disconnect_current_laser()
        try:
            from ..hardware.wifi_arduino_controller import WifiArduinoController
            self.arduino = WifiArduinoController(host)
            if self.arduino.connect():
                self.arduino_connected = True
                self.arduino_enabled   = True
                print(f"\n✅ WiFi laser connected at {host}")
                if self.voice_enabled:
                    self.speaker.speak_now("Laser connected")
            else:
                self.arduino = DummyArduino()
                self.arduino_connected = False
                print(f"\n❌ Could not reach WiFi laser at {host}")
        except Exception as e:
            self.arduino = DummyArduino()
            self.arduino_connected = False
            print(f"\n❌ WiFi laser error: {e}")
        return self.arduino_connected

    def _disconnect_current_laser(self):
        if self.arduino_connected:
            try:
                self.arduino.laser_off()
                self.arduino.disconnect()
            except Exception:
                pass
        self.arduino = DummyArduino()
        self.arduino_connected = False

    def calibrate_laser(self, cap):
        if not self.arduino_connected:
            print("❌ Arduino not connected")
            return cap
        if self.voice_enabled:
            self.speaker.speak_now("Starting laser calibration")
        cap.release()
        cv2.destroyAllWindows()
        self.arduino.camera_index = (
            self.current_camera_id
            if isinstance(self.current_camera_id, int) else 0
        )
        self.arduino.mirror = self.mirror_mode
        if self.arduino.calibrate():
            print("✅ Calibration complete!")
            if self.voice_enabled:
                self.speaker.speak_now("Calibration complete")
        else:
            print("⚠️  Calibration cancelled")
        new_cap = cv2.VideoCapture(self.current_camera_id)
        new_cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
        new_cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        new_cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
        return new_cap
 
    # ──────────────────────────────────────────────────────────
    # FRAME PROCESSING
    # ──────────────────────────────────────────────────────────
 
    def process_frame(self, frame):
        start_time = time.time()
        self.frame_count += 1
        h, w = frame.shape[:2]
        should_process = (self.frame_count % self.process_every_n == 0)
 
        self._last_frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
 
        if should_process:
            results = self.pose.process(self._last_frame_rgb)
 
            if results.pose_landmarks:
                landmarks_raw   = results.pose_landmarks.landmark
                high_conf_count = sum(
                    1 for lm in landmarks_raw if lm.visibility > 0.5
                )
 
                if high_conf_count < 15:
                    self._clear_pose_cache()
                    self.feedback_message = (
                        f"Partial pose ({high_conf_count}/33) "
                        "— step back or improve lighting"
                    )
                    self.feedback_color = (128, 128, 128)
                else:
                    self.cached_results       = results
                    self.cached_landmarks_raw = landmarks_raw
                    self.cached_landmarks     = [
                        (lm.x * w, lm.y * h, lm.z * w)
                        for lm in landmarks_raw
                    ]
 
                    if self.arduino_connected:
                        self.arduino.update_frame(
                            frame, self.cached_landmarks_raw
                        )
                        self.arduino.frame_width  = w
                        self.arduino.frame_height = h
 
                    self.current_features = (
                        self.risk_classifier
                            .extract_biomechanical_features(
                                self.cached_landmarks
                            )
                    )
 
                    if self.calibration_mode:
                        self._collect_calibration()
                    else:
                        self._run_pipeline()
            else:
                self._clear_pose_cache()
                self.feedback_message = "NO POSE — Stand in frame"
                self.feedback_color   = (128, 128, 128)
                if self.arduino_connected:
                    self.arduino.update_frame(frame, None)
 
        if self.frame_count % 10 == 0:
            self._handle_voice()
        if self.frame_count % 5 == 0:
            self._handle_arduino()
 
        # render_mode is unset by default, so this is a no-op for the
        # standalone desktop app — only SessionManager (the web backend)
        # sets engine.render_mode = "web" after construction. Desktop output
        # is byte-for-byte what _draw_full_ui always produced.
        if getattr(self, "render_mode", "desktop") == "web":
            output = self._draw_web_frame(frame)
        else:
            output = self._draw_full_ui(frame)
        self.frame_times.append(time.time() - start_time)
        return output
 
    def _clear_pose_cache(self):
        self.cached_results       = None
        self.cached_landmarks     = None
        self.cached_landmarks_raw = None
        self.current_corrections  = []
 
    def _run_pipeline(self):
        # Risk classification
        if hasattr(self.risk_classifier, 'predict'):
            self.current_risk_result = self.risk_classifier.predict(
                self.current_features, use_uncertainty=True
            )
        else:
            self.current_risk_result = self.risk_classifier.predict_risk(
                self.current_features
            )
 
        # Uncertainty
        if self.uncertainty_manager and self.current_risk_result:
            self.current_risk_result = (
                self.uncertainty_manager
                    .process_prediction(self.current_risk_result)
            )
 
        # Debug high risk
        if self.current_risk_result:
            rl = self.current_risk_result.get('risk_level', 0)
            if rl >= 2:
                spine = self.current_features.get('spine_flexion', 0)
                label = self.current_risk_result.get('risk_label', '?')
                print(f"⚠️  Risk: {label} ({rl}) | Spine: {spine:.1f}°")
 
        # Fatigue
        self.current_fatigue_status = self.fatigue_engine.update(
            self.current_features
        )
 
        # IRI
        self.current_injury_risk = self.injury_predictor.predict_injury_risk(
            cumulative_lifts = self.current_fatigue_status.get('lifts_completed', 0),
            avg_spine_angle  = self.current_features.get('spine_flexion', 0),
            fatigue_score    = self.current_fatigue_status.get('fatigue_score', 100),
            form_variance    = self.current_features.get('knee_asymmetry', 0),
            asymmetry        = abs(
                self.current_features.get('knee_valgus_left',  0) -
                self.current_features.get('knee_valgus_right', 0)
            )
        )
 
        # Exercise tracker
        self.current_exercise_status = self.exercise_tracker.update(
            self.current_features,
            self.current_risk_result,
            self.current_fatigue_status
        )
 
        # Session history
        iri_val = self.current_injury_risk.get(
            'combined_iri', self.current_injury_risk.get('probability', 0)
        )
        self._session_iri_history.append(iri_val)
        self._session_spine_history.append(
            self.current_features.get('spine_flexion', 0)
        )
        risk_lv = (self.current_risk_result.get('risk_level', 0)
                   if self.current_risk_result else 0)
        self._session_peak_risk = max(self._session_peak_risk, risk_lv)
 
        # Corrections
        self.form_corrector._last_iri = self.current_injury_risk
        self.current_corrections = self.form_corrector.get_corrections(
            self.current_features,
            self.current_risk_result,
            self.current_fatigue_status
        )
 
        self._update_feedback()
 
    def _collect_calibration(self):
        if self.current_features:
            self.calibration_data.append([
                self.current_features.get('spine_flexion',    0),
                self.current_features.get('hip_hinge_angle', 90),
                self.current_features.get('knee_asymmetry',   0),
                self.current_features.get('stability_index', 0.5),
                self.current_features.get('spinal_load_index', 0.5)
            ])
        self.feedback_message = f"CALIBRATING... {len(self.calibration_data)}/30"
        self.feedback_color   = (255, 150, 0)
 
    def _update_feedback(self):
        current_time = time.time()
 
        if (self.uncertainty_manager and
                self.current_corrections and
                self.current_risk_result):
            self.current_corrections = [
                c for c in self.current_corrections
                if not self.uncertainty_manager.should_suppress_correction(
                    c, self.current_risk_result
                )
            ]
 
        if self.current_corrections:
            c = self.current_corrections[0]
            self.feedback_message     = c['display']
            colors = {1:(0,0,255), 2:(0,165,255),
                      3:(0,255,255), 4:(0,255,0)}
            self.feedback_color       = colors.get(c['priority'], (255,255,255))
            self.good_form_start_time = 0
 
        elif (self.current_risk_result and
              self.current_risk_result['risk_level'] == 0):
            if self.good_form_start_time == 0:
                self.good_form_start_time = current_time
            positive = self.form_corrector.get_positive(
                self.current_risk_result
            )
            if positive:
                self.feedback_message = positive['display']
                self.feedback_color   = (0, 255, 0)
        else:
            self.feedback_message = "Analyzing..."
            self.feedback_color   = (255, 255, 255)
 
    # ──────────────────────────────────────────────────────────
    # VOICE
    # ──────────────────────────────────────────────────────────
 
    def _handle_voice(self):
        if not self.voice_enabled:
            return
        current_time = time.time()
 
        if current_time - self.spoken_corrections_time > 30:
            self.spoken_corrections.clear()
            self.spoken_corrections_time = current_time
 
        if self.current_corrections:
            for correction in self.current_corrections:
                cid      = correction['id']
                priority = correction['priority']
                if cid in self.spoken_corrections:
                    continue
                if self.speaker.speak(correction['command'], cid, priority):
                    self.spoken_corrections.add(cid)
                    break
 
        if self.current_exercise_status:
            reps = self.current_exercise_status.get('rep_count', 0)
            if reps > 0 and reps % 5 == 0 and reps != self.last_rep_announced:
                if self.speaker.speak(f"{reps} reps!", f'rep_{reps}', 4):
                    self.last_rep_announced = reps
 
        if (not self.current_corrections and
                self.current_risk_result and
                self.current_risk_result.get('risk_level') == 0 and
                current_time - self.last_positive_time > 15):
            if (self.good_form_start_time and
                    current_time - self.good_form_start_time > 3):
                positive = self.form_corrector.get_positive(
                    self.current_risk_result
                )
                if positive:
                    if self.speaker.speak(
                        positive['command'], positive['id'], 4
                    ):
                        self.last_positive_time = current_time
 
    # ──────────────────────────────────────────────────────────
    # ARDUINO
    # ──────────────────────────────────────────────────────────
 
    def _handle_arduino(self):
        if not self.arduino_enabled or not self.arduino_connected:
            return
        current_time = time.time()
        if current_time - self.last_arduino_time < 0.2:
            return
        if self.current_corrections:
            c = self.current_corrections[0]
            self.arduino.point_at_body_part(
                c.get('body_part', 'CENTER'), c['priority']
            )
        elif self.arduino.current_priority != 0:
            self.arduino.set_safe()
        self.last_arduino_time = current_time
 
    # ──────────────────────────────────────────────────────────
    # LIVE FACE SCAN
    # ──────────────────────────────────────────────────────────
 
    def _run_live_face_scan(self, output):
        if self.frame_count % 30 == 0 and self._last_frame_rgb is not None:
            profile, locations, dist = (
                self.user_manager.identify_from_frame(self._last_frame_rgb)
            )
            self._live_scan_faces = locations
            self._live_scan_count = getattr(
                self.user_manager, 'id_frame_count', 0
            )
 
            if profile and not profile.is_guest:
                current_id = (
                    self.current_user.user_id
                    if self.current_user else -1
                )
                if profile.user_id != current_id:
                    print(f"\n👤 User → {profile.display_name}")
                    self.current_user = profile
                    self.id_state     = "identified"
                    self.user_manager.start_session(profile.user_id)
                    if self.voice_enabled:
                        name = profile.display_name.split()[0]
                        self.speaker.speak_now(f"Welcome, {name}!")
 
        if self._live_scan_faces and self.user_ui:
            candidate_name = None
            candidate      = getattr(self.user_manager, 'id_candidate', None)
            if candidate:
                uid = candidate[0] if isinstance(candidate, tuple) else candidate
                p   = self.user_manager.get_user_by_id(uid)
                if p:
                    candidate_name = p.display_name
            self.user_ui.draw_scanning_overlay(
                output, self._live_scan_faces,
                self._live_scan_count,
                self._live_scan_CONFIRM,
                candidate_name
            )
 
    # ──────────────────────────────────────────────────────────
    # WEB UI (clean overlay only — no baked-in text panels)
    # ──────────────────────────────────────────────────────────

    def _draw_web_frame(self, frame):
        """Used instead of _draw_full_ui() when render_mode == 'web'.

        Keeps ONLY the overlays that are genuinely tied to camera pixel
        space — the pose skeleton and the correction highlight circles,
        which have to sit exactly on the tracked joints. Everything else
        _draw_full_ui() drew as OpenCV rectangles/text (user panel, risk
        panel, exercise panel, status badges, fatigue/IRI panel,
        corrections panel, FPS counter, color bar, feedback bar, controls
        hint, flashing high-risk border) is now rendered as HTML/CSS in the
        web dashboard instead, driven by the same underlying data via
        SessionManager._collect_telemetry() — not baked into the pixels.

        _draw_full_ui() itself is untouched; the standalone desktop app
        (run_standalone.py) still gets the exact original OpenCV HUD.
        """
        output = frame.copy()
        if self.cached_results and self.cached_results.pose_landmarks:
            self._draw_skeleton(output, draw_border=False)
        return output

    # ──────────────────────────────────────────────────────────
    # FULL UI
    # ──────────────────────────────────────────────────────────

    def _draw_full_ui(self, frame):
        output = frame.copy()
        h, w   = output.shape[:2]
 
        # Background face scan
        if self._live_scan_enabled:
            self._run_live_face_scan(output)
 
        # Skeleton (risk-colored)
        if self.cached_results and self.cached_results.pose_landmarks:
            self._draw_skeleton(output)
 
        # Layout
        panel_w = 280
        margin  = 15
        v_gap   = 10
        left_x  = margin
        right_x = w - panel_w - margin
 
        # ── LEFT COLUMN ───────────────────────────────────────
        y = margin
        user_bottom = self._draw_user_panel(output, left_x, y, panel_w)
        y = user_bottom + v_gap
        y = self._draw_risk_panel(output, left_x, y, panel_w)
        y += v_gap
        y = self._draw_exercise_panel(output, left_x, y, panel_w)
        y += v_gap
        self._draw_status_badges(output, left_x, y, panel_w)
 
        # ── RIGHT COLUMN ──────────────────────────────────────
        y = margin
        y = self._draw_fatigue_iri_panel(output, right_x, y, panel_w)
        y += v_gap
        self._draw_corrections_panel(output, right_x, y, panel_w)
 
        # ── OVERLAYS ──────────────────────────────────────────
        self._draw_fps_landmarks(output, w)
        self._draw_risk_color_bar(output, w, h)
        self._draw_feedback_bar(output, w, h)
        self._draw_controls_hint(output, w, h)
 
        return output
 
    # ──────────────────────────────────────────────────────────
    # SKELETON (RISK-COLORED WITH HIGHLIGHTS)
    # ──────────────────────────────────────────────────────────
 
    def _draw_skeleton(self, img, draw_border=True):
        """Draw skeleton with risk-based color, thickness, and highlights.

        draw_border defaults to True so every existing caller (desktop
        _draw_full_ui) behaves exactly as before. Web mode passes False —
        the flashing high-risk border becomes a CSS glow on the video
        container in the browser instead of pixels baked into the frame.
        """
        if not self.cached_results or not self.cached_results.pose_landmarks:
            return
 
        risk_level = 0
        if self.current_risk_result:
            risk_level = self.current_risk_result.get('risk_level', 0)
 
        # BGR colors per risk level
        skeleton_colors = {
            0: (0, 255,   0),   # Green  — SAFE
            1: (0, 255, 255),   # Yellow — LOW
            2: (0, 165, 255),   # Orange — MEDIUM
            3: (0,   0, 255),   # Red    — HIGH
        }
        color     = skeleton_colors.get(risk_level, (255, 255, 255))
        thickness = 2 + risk_level           # thicker at higher risk
        radius    = 3 + risk_level           # bigger dots at higher risk
 
        self.mp_draw.draw_landmarks(
            img,
            self.cached_results.pose_landmarks,
            self.mp_pose.POSE_CONNECTIONS,
            self.mp_draw.DrawingSpec(
                color=color, thickness=thickness, circle_radius=radius
            ),
            self.mp_draw.DrawingSpec(
                color=color, thickness=thickness
            )
        )
 
        # Flashing border on HIGH risk
        if draw_border and risk_level == 3:
            self._draw_high_risk_overlay(img)
 
        # Body part highlights for active corrections
        if self.current_corrections and self.cached_landmarks:
            self._draw_correction_highlights(img)
 
    def _draw_high_risk_overlay(self, img):
        """Pulsing red border when risk is HIGH."""
        h, w = img.shape[:2]
        if (self.frame_count // 15) % 2 == 0:
            border = 8
            cv2.rectangle(
                img,
                (border, border),
                (w - border, h - border),
                (0, 0, 255), border
            )
            # "HIGH RISK" text at top center
            text = "! HIGH RISK !"
            (tw, th), _ = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 3
            )
            tx = (w - tw) // 2
            # Background for text
            cv2.rectangle(
                img,
                (tx - 8, 55),
                (tx + tw + 8, 55 + th + 12),
                (0, 0, 0), -1
            )
            cv2.putText(
                img, text, (tx, 55 + th + 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                (0, 0, 255), 3
            )
 
    def _draw_correction_highlights(self, img):
        """Pulsing circles on body parts needing correction."""
        if not self.cached_landmarks or not self.current_corrections:
            return
 
        h, w = img.shape[:2]
 
        body_part_landmarks = {
            'SPINE':          [11, 12, 23, 24],
            'LEFT_KNEE':      [25, 27],
            'RIGHT_KNEE':     [26, 28],
            'LEFT_HIP':       [23, 25],
            'RIGHT_HIP':      [24, 26],
            'LEFT_SHOULDER':  [11, 13],
            'RIGHT_SHOULDER': [12, 14],
            'LEFT_ANKLE':     [27, 29],
            'RIGHT_ANKLE':    [28, 30],
            'HEAD':           [0],
            'CENTER':         [23, 24],
            'UPPER_BACK':     [11, 12],
        }
 
        priority_colors = {
            1: (0,   0, 255),
            2: (0, 165, 255),
            3: (0, 255, 255),
            4: (0, 255,   0),
        }
 
        drawn = set()
        for correction in self.current_corrections[:3]:
            body_part = correction.get('body_part', '')
            priority  = correction.get('priority', 4)
            color     = priority_colors.get(priority, (255, 255, 255))
            indices   = body_part_landmarks.get(body_part, [])
 
            for idx in indices:
                if idx >= len(self.cached_landmarks) or idx in drawn:
                    continue
                lm = self.cached_landmarks[idx]
                px, py = int(lm[0]), int(lm[1])
                if 0 < px < w and 0 < py < h:
                    pulse = int(abs(np.sin(self.frame_count * 0.15)) * 8 + 12)
                    cv2.circle(img, (px, py), pulse, color, 3)
                    cv2.circle(img, (px, py), 5,     color, -1)
                    drawn.add(idx)
 
    # ──────────────────────────────────────────────────────────
    # PANEL: USER
    # ──────────────────────────────────────────────────────────
 
    def _draw_user_panel(self, img, x, y, w):
        h = 110
        cv2.rectangle(img, (x, y), (x+w, y+h), (20, 20, 20), -1)
 
        border_map = {
            "identified":  (0, 255,   0),
            "confirming":  (0, 255, 255),
            "scanning":    (0, 165, 255),
            "guest":       (100, 100, 100),
            "not_started": (80,  80,  80),
        }
        border = border_map.get(self.id_state, (80, 80, 80))
        cv2.rectangle(img, (x, y), (x+w, y+h), border, 2)
 
        # Avatar
        ax, ay = x + 30, y + 42
        cv2.circle(img, (ax, ay), 22, border, -1)
        if self.current_user and not self.current_user.is_guest:
            initials = "".join(
                p[0].upper()
                for p in self.current_user.display_name.split()[:2]
            )
        else:
            initials = "G"
        (tw, th), _ = cv2.getTextSize(
            initials, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2
        )
        cv2.putText(img, initials,
                    (ax - tw//2, ay + th//2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 2)
 
        tx = x + 60
        if self.current_user and not self.current_user.is_guest:
            cv2.putText(img, self.current_user.display_name[:22],
                        (tx, y+22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255,255,255), 1)
            cv2.putText(img, f"ID #{self.current_user.user_id}",
                        (tx, y+40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (160,160,160), 1)
            cv2.putText(img, f"Sessions: {self.current_user.total_sessions}",
                        (tx, y+57),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (140,140,140), 1)
            if self.current_user.last_seen:
                try:
                    dt  = datetime.fromisoformat(self.current_user.last_seen)
                    ago = (datetime.now() - dt).days
                    ls  = f"Last: {ago}d ago" if ago > 0 else "Last: today"
                    cv2.putText(img, ls, (tx, y+73),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                                (120,120,120), 1)
                except Exception:
                    pass
        else:
            cv2.putText(img, "Guest Mode",
                        (tx, y+30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180,180,180), 1)
            cv2.putText(img, "No profile loaded",
                        (tx, y+52),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (120,120,120), 1)
            cv2.putText(img, "Restart to identify",
                        (tx, y+68),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, (100,100,100), 1)
 
        state_labels = {
            "identified":  "✓ IDENTIFIED",
            "confirming":  "CONFIRMING...",
            "scanning":    "SCANNING...",
            "guest":       "GUEST MODE",
            "not_started": "AWAITING ID"
        }
        cv2.putText(img,
                    state_labels.get(self.id_state, self.id_state.upper()),
                    (x+15, y+h-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, border, 1)
        return y + h
 
    # ──────────────────────────────────────────────────────────
    # PANEL: RISK
    # ──────────────────────────────────────────────────────────
 
    def _draw_risk_panel(self, img, x, y, w):
        h = 195
        cv2.rectangle(img, (x, y), (x+w, y+h), (20, 20, 20), -1)
 
        if not self.current_risk_result:
            cv2.rectangle(img, (x, y), (x+w, y+h), (80,80,80), 2)
            cv2.putText(img, "Analyzing pose...",
                        (x+15, y+h//2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (140,140,140), 1)
            return y + h
 
        risk_level  = self.current_risk_result.get('risk_level',  0)
        risk_label  = self.current_risk_result.get('risk_label',  'SAFE')
        confidence  = self.current_risk_result.get('confidence',  0)
        uncertainty = self.current_risk_result.get('uncertainty', 0)
        unc_cat     = self.current_risk_result.get('uncertainty_category', 'LOW')
        mode        = self.current_risk_result.get('mode', 'frame')
 
        risk_colors = {0:(0,255,0), 1:(0,255,255),
                       2:(0,165,255), 3:(0,0,255)}
        risk_color  = risk_colors.get(risk_level, (200,200,200))
 
        cv2.rectangle(img, (x, y), (x+w, y+h), risk_color, 3)
        cv2.putText(img, "RISK LEVEL",
                    (x+15, y+22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (160,160,160), 1)
        cv2.putText(img, risk_label,
                    (x+15, y+55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.95, risk_color, 2)
 
        bar_y  = y + 68
        bar_bw = w - 30
        cv2.rectangle(img, (x+15, bar_y), (x+15+bar_bw, bar_y+18),
                      (50,50,50), -1)
        cv2.rectangle(img, (x+15, bar_y),
                      (x+15+int(bar_bw*confidence), bar_y+18),
                      risk_color, -1)
 
        conf_text = (f"{confidence:.0%} ±{uncertainty:.2f}"
                     if uncertainty > 0 else f"{confidence:.0%}")
        cv2.putText(img, conf_text, (x+15, bar_y+34),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200,200,200), 1)
 
        unc_colors = {'LOW':(0,255,0),'MEDIUM':(0,255,255),
                      'HIGH':(0,165,255),'VERY_HIGH':(0,0,255)}
        cv2.putText(img, f"Cert:{unc_cat}",
                    (x+w-95, bar_y+34),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36,
                    unc_colors.get(unc_cat,(150,150,150)), 1)
 
        mode_colors = {'temporal':(0,255,0),'hybrid':(0,255,255),
                       'frame':(255,180,0),'fallback':(120,120,120)}
        cv2.putText(img, f"Mode:{mode.upper()}",
                    (x+15, bar_y+52),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                    mode_colors.get(mode,(150,150,150)), 1)
 
        if self.current_features:
            feat_y = y + 138
            cv2.line(img, (x+10, feat_y-6), (x+w-10, feat_y-6),
                     (60,60,60), 1)
            spine = self.current_features.get('spine_flexion', 0)
            hip   = self.current_features.get('hip_hinge_angle', 0)
            stab  = self.current_features.get('stability_index', 0)
 
            # Spine color changes with risk
            spine_col = ((0,255,0) if spine < 25 else
                         (0,255,255) if spine < 35 else
                         (0,165,255) if spine < 50 else
                         (0,0,255))
            cv2.putText(img, f"Spine: {spine:.1f}°",
                        (x+15, feat_y+12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, spine_col, 1)
            cv2.putText(img, f"Hip: {hip:.1f}°",
                        (x+15, feat_y+30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180,180,180), 1)
            cv2.putText(img, f"Stability: {stab:.2f}",
                        (x+15, feat_y+48),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180,180,180), 1)
 
        return y + h
 
    # ──────────────────────────────────────────────────────────
    # PANEL: EXERCISE
    # ──────────────────────────────────────────────────────────
 
    def _draw_exercise_panel(self, img, x, y, w):
        h = 90
        cv2.rectangle(img, (x, y), (x+w, y+h), (20,20,20), -1)
        cv2.rectangle(img, (x, y), (x+w, y+h), (220,180,0), 2)
 
        exercise  = self.current_exercise_status.get('exercise',      'Unknown')
        rep_count = self.current_exercise_status.get('rep_count',     0)
        phase     = self.current_exercise_status.get('phase_display', '🧍')
 
        cv2.putText(img, exercise,
                    (x+15, y+22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220,180,0), 1)
        cv2.putText(img, f"REPS: {rep_count}",
                    (x+15, y+62),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0,255,255), 3)
        cv2.putText(img, phase,
                    (x+w-55, y+62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (160,160,160), 2)
        return y + h
 
    # ──────────────────────────────────────────────────────────
    # PANEL: STATUS BADGES
    # ──────────────────────────────────────────────────────────
 
    def _draw_status_badges(self, img, x, y, w):
        badge_h = 26
        badge_w = 58
        gap     = 4
        badges  = []
 
        # Camera
        if isinstance(self.current_camera_id, str):
            badges.append(("IP",   (0,255,255)))
        else:
            badges.append((f"C{self.current_camera_id}", (200,200,200)))
 
        # Voice
        if self.voice_enabled:
            label = "TALK" if self.speaker.is_speaking else "VOX"
            color = (0,255,255) if self.speaker.is_speaking else (0,255,0)
        else:
            label, color = "MUTE", (100,100,100)
        badges.append((label, color))
 
        # Arduino
        if self.arduino_connected:
            label = "AUTO" if self.arduino.is_calibrated else "LSR"
            color = (0,255,0) if self.arduino.is_calibrated else (0,255,255)
        else:
            label, color = "---", (100,100,100)
        badges.append((label, color))
 
        # Mode
        mode = "TCN"
        if self.current_risk_result and 'mode' in self.current_risk_result:
            m = self.current_risk_result['mode']
            if   m == 'hybrid':   mode = "HYB"
            elif m == 'frame':    mode = "FRM"
            elif m == 'fallback': mode = "FB"
        badges.append((mode, (0,255,0)))
 
        # IRI
        badges.append(
            ("IRI2" if self.using_iri_v2 else "IRI",
             (0,255,0) if self.using_iri_v2 else (100,100,100))
        )
 
        # User ID
        if   self.id_state == "identified": badges.append(("ID✓", (0,255,0)))
        elif self.id_state == "guest":      badges.append(("GST", (100,100,100)))
        else:                               badges.append(("ID?", (0,165,255)))
 
        bx = x
        for text, color in badges:
            cv2.rectangle(img, (bx,y), (bx+badge_w, y+badge_h),
                          (30,30,30), -1)
            cv2.rectangle(img, (bx,y), (bx+badge_w, y+badge_h),
                          color, 2)
            (tw, _), _ = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_SIMPLEX, 0.37, 1
            )
            cv2.putText(img, text,
                        (bx + (badge_w-tw)//2, y+17),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.37, color, 1)
            bx += badge_w + gap
 
    # ──────────────────────────────────────────────────────────
    # PANEL: FATIGUE + IRI
    # ──────────────────────────────────────────────────────────
 
    def _draw_fatigue_iri_panel(self, img, x, y, w):
        h = 205
        cv2.rectangle(img, (x, y), (x+w, y+h), (20,20,20), -1)
        cv2.rectangle(img, (x, y), (x+w, y+h), (80,80,80), 2)
 
        # Fatigue
        cv2.putText(img, "FORM HEALTH",
                    (x+15, y+20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (160,160,160), 1)
 
        score = self.current_fatigue_status.get('fatigue_score', 100)
        alert = self.current_fatigue_status.get('alert_level',   'green')
        lifts = self.current_fatigue_status.get('lifts_completed', 0)
 
        alert_colors = {
            'green':(0,255,0),'yellow':(0,255,255),
            'orange':(0,165,255),'red':(0,0,255)
        }
        bar_color = alert_colors.get(alert, (200,200,200))
 
        bar_y  = y + 32
        bar_bw = w - 85
        cv2.rectangle(img, (x+15,bar_y), (x+15+bar_bw, bar_y+20),
                      (50,50,50), -1)
        cv2.rectangle(img, (x+15,bar_y),
                      (x+15+int(bar_bw*score/100), bar_y+20),
                      bar_color, -1)
        cv2.putText(img, f"{score:.0f}%",
                    (x+w-65, bar_y+14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, bar_color, 2)
        cv2.putText(img, f"{alert.upper()}  •  Lifts:{lifts}",
                    (x+15, bar_y+38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180,180,180), 1)
 
        # Divider
        div_y = y + 82
        cv2.line(img, (x+10,div_y), (x+w-10,div_y), (60,60,60), 1)
 
        # IRI
        iri_y = div_y + 16
        cv2.putText(img, "IRI V2" if self.using_iri_v2 else "INJURY RISK",
                    (x+15, iri_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (160,160,160), 1)
 
        prob  = self.current_injury_risk.get(
            'combined_iri', self.current_injury_risk.get('probability', 0)
        )
        acute = self.current_injury_risk.get('acute_risk',      prob)
        cum   = self.current_injury_risk.get('cumulative_risk', prob)
        cat   = self.current_injury_risk.get('category',        'LOW')
 
        cat_colors = {
            'LOW':(0,255,0),'MODERATE':(0,255,255),
            'HIGH':(0,165,255),'CRITICAL':(0,0,255)
        }
        iri_color = cat_colors.get(cat, (180,180,180))
 
        cv2.putText(img, f"{prob:.1f}%",
                    (x+15, iri_y+26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.85, iri_color, 2)
        cv2.putText(img, f"[{cat}]",
                    (x+88, iri_y+26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, iri_color, 1)
 
        iri_bar_y = iri_y + 38
        iri_bar_w = w - 30
        cv2.rectangle(img, (x+15, iri_bar_y),
                      (x+15+iri_bar_w, iri_bar_y+12),
                      (50,50,50), -1)
        cv2.rectangle(img, (x+15, iri_bar_y),
                      (x+15+int(iri_bar_w*min(prob/100,1.0)), iri_bar_y+12),
                      iri_color, -1)
 
        if self.using_iri_v2:
            cv2.putText(img, f"Acute:{acute:.0f}%  Cum:{cum:.0f}%",
                        (x+15, iri_bar_y+28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, (160,160,160), 1)
 
        ci      = self.current_injury_risk.get('confidence_interval', {})
        ci_text = ci.get('text', '')
        if ci_text:
            cv2.putText(img, ci_text,
                        (x+15, iri_bar_y+46),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, (120,120,120), 1)
 
        return y + h
 
    # ──────────────────────────────────────────────────────────
    # PANEL: CORRECTIONS
    # ──────────────────────────────────────────────────────────
 
    def _draw_corrections_panel(self, img, x, y, panel_w):
        h = 180
        cv2.rectangle(img, (x, y), (x+panel_w, y+h), (20,20,20), -1)
 
        border_col = (0,255,0)
        if self.current_corrections:
            p = self.current_corrections[0]['priority']
            if   p == 1: border_col = (0,   0, 255)
            elif p == 2: border_col = (0, 165, 255)
            elif p == 3: border_col = (0, 255, 255)
 
        cv2.rectangle(img, (x, y), (x+panel_w, y+h), border_col, 2)
        cv2.putText(img, f"CORRECTIONS ({len(self.current_corrections)})",
                    (x+15, y+20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (160,160,160), 1)
 
        if (self.current_risk_result and
                'uncertainty_alert' in self.current_risk_result):
            alert = self.current_risk_result['uncertainty_alert']
            if alert['level'] in ['WARNING', 'CRITICAL']:
                cv2.putText(img, "⚠", (x+panel_w-28, y+20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,165,255), 1)
 
        if self.current_corrections:
            for i, c in enumerate(self.current_corrections[:6]):
                cy = y + 42 + i * 22
                if   c['priority'] == 1: ind, col = "!!", (0,   0, 255)
                elif c['priority'] == 2: ind, col = "! ", (0, 165, 255)
                elif c['priority'] == 3: ind, col = "• ", (0, 255, 255)
                else:                    ind, col = "  ", (100, 200, 100)
                spoken  = "♪" if c['id'] in self.spoken_corrections else " "
                display = c['display'][:26]
                cv2.putText(img, f"{ind}{spoken} {display}",
                            (x+10, cy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.36, col, 1)
        else:
            cv2.putText(img, "Form looks good!",
                        (x+15, y+65),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0,255,0), 1)
            action = self.current_injury_risk.get('action', '')
            if action:
                cv2.putText(img, action[:38],
                            (x+15, y+90),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.32, (120,200,120), 1)
 
    # ──────────────────────────────────────────────────────────
    # OVERLAY: RISK COLOR BAR
    # ──────────────────────────────────────────────────────────
 
    def _draw_risk_color_bar(self, img, w, h):
        """Vertical color bar on both edges — instantly shows risk level."""
        risk_level = 0
        if self.current_risk_result:
            risk_level = self.current_risk_result.get('risk_level', 0)
 
        bar_colors = {
            0: (0, 255,   0),
            1: (0, 255, 255),
            2: (0, 165, 255),
            3: (0,   0, 255),
        }
        color = bar_colors.get(risk_level, (128, 128, 128))
        bar_w = 10
 
        cv2.rectangle(img, (0, 0),       (bar_w, h),      color, -1)
        cv2.rectangle(img, (w-bar_w, 0), (w, h),          color, -1)
 
    # ──────────────────────────────────────────────────────────
    # OVERLAY: FPS + LANDMARKS
    # ──────────────────────────────────────────────────────────
 
    def _draw_fps_landmarks(self, img, w):
        if not self.frame_times:
            return
 
        fps = 1.0 / (np.mean(self.frame_times) + 1e-6)
 
        if self.cached_landmarks_raw:
            lm_count = sum(
                1 for lm in self.cached_landmarks_raw if lm.visibility > 0.5
            )
            lm_col  = ((0,255,0) if lm_count >= 25 else
                       (0,255,255) if lm_count >= 15 else (0,0,255))
            lm_text = f"LM:{lm_count}/33"
        else:
            lm_count, lm_col, lm_text = 0, (100,100,100), "LM:0/33"
 
        fps_col = ((0,255,0) if fps >= 25 else
                   (0,255,255) if fps >= 15 else (0,0,255))
 
        box_w = 155
        bx    = w//2 - box_w//2
        cv2.rectangle(img, (bx,8), (bx+box_w,36), (20,20,20), -1)
        cv2.rectangle(img, (bx,8), (bx+box_w,36), (80,80,80), 1)
        cv2.putText(img, f"FPS:{fps:.0f}",
                    (bx+10, 27),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, fps_col, 2)
        cv2.putText(img, lm_text,
                    (bx+75, 27),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, lm_col, 1)
 
    # ──────────────────────────────────────────────────────────
    # OVERLAY: FEEDBACK BAR
    # ──────────────────────────────────────────────────────────
 
    def _draw_feedback_bar(self, img, w, h):
        bar_h = 58
        bar_y = h - bar_h - 30
 
        cv2.rectangle(img, (12, bar_y), (w-12, bar_y+bar_h),
                      (20,20,20), -1)
        cv2.rectangle(img, (12, bar_y), (w-12, bar_y+bar_h),
                      self.feedback_color, 3)
 
        (tw, th), _ = cv2.getTextSize(
            self.feedback_message,
            cv2.FONT_HERSHEY_SIMPLEX, 0.72, 2
        )
        tx = (w - tw) // 2
        ty = bar_y + (bar_h + th) // 2
        cv2.putText(img, self.feedback_message,
                    (tx, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.72,
                    self.feedback_color, 2)
 
    # ──────────────────────────────────────────────────────────
    # OVERLAY: CONTROLS HINT
    # ──────────────────────────────────────────────────────────
 
    def _draw_controls_hint(self, img, w, h):
        hint = ("[Q]uit [V]oice [A]rduino [K]Laser [M]irror "
                "[C]alib [T]emporal [U]ncert [R]eport "
                "[L]ist [E]xport [X]Reset [+/-]Speed")
        cv2.rectangle(img, (10,h-26), (w-10,h-4), (15,15,15), -1)
        cv2.putText(img, hint, (18,h-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, (100,100,100), 1)
 
    # ──────────────────────────────────────────────────────────
    # CONTROLS
    # ──────────────────────────────────────────────────────────
 
    def toggle_voice(self):
        self.voice_enabled   = not self.voice_enabled
        self.speaker.enabled = self.voice_enabled
        print(f"\n🔊 Voice: {'ON' if self.voice_enabled else 'OFF'}")
        if self.voice_enabled:
            self.speaker.speak_now("Voice enabled")
 
    def toggle_temporal(self):
        if not TEMPORAL_CLASSIFIER_AVAILABLE:
            print("\n⚠️  Temporal not available")
            return
        if hasattr(self.risk_classifier, 'use_temporal'):
            self.risk_classifier.use_temporal = (
                not self.risk_classifier.use_temporal
            )
            self.using_temporal = self.risk_classifier.use_temporal
            status = "ON" if self.using_temporal else "OFF"
            print(f"\n🧠 Temporal: {status}")
            if self.voice_enabled:
                self.speaker.speak_now(f"Temporal {status}")
 
    def toggle_mirror(self):
        self.mirror_mode = not self.mirror_mode
        print(f"\n🪞 Mirror: {'ON' if self.mirror_mode else 'OFF'}")
        if self.arduino_connected:
            self.arduino.mirror = self.mirror_mode
 
    def start_calibration(self):
        self.calibration_mode = True
        self.calibration_data = []
        print("\n📐 Calibration started...")
        if self.voice_enabled:
            self.speaker.speak_now("Calibration started. Move naturally.")
 
    def complete_calibration(self):
        if len(self.calibration_data) >= 20:
            self.risk_classifier.calibrate_to_person(self.calibration_data)
            if (self.current_user and
                    not self.current_user.is_guest and
                    USER_MANAGER_AVAILABLE):
                arr = np.array(self.calibration_data)
                baseline = {
                    'spine_mean':     float(np.mean(arr[:, 0])),
                    'spine_std':      float(np.std(arr[:, 0])),
                    'hip_mean':       float(np.mean(arr[:, 1])),
                    'hip_std':        float(np.std(arr[:, 1])),
                    'stability_mean': float(np.mean(arr[:, 3])),
                    'stability_std':  float(np.std(arr[:, 3])),
                }
                self.user_manager.save_baseline(
                    self.current_user.user_id, baseline
                )
                print(f"   💾 Baseline saved for "
                      f"{self.current_user.display_name}")
            print("✅ Calibration complete!")
            if self.voice_enabled:
                self.speaker.speak_now("Calibration complete")
        else:
            print(f"⚠️  Need more data ({len(self.calibration_data)}/20)")
        self.calibration_mode = False
 
    def show_uncertainty_summary(self):
        if self.uncertainty_manager:
            summary = self.uncertainty_manager.get_uncertainty_summary()
            print("\n" + "=" * 50)
            print("📊 UNCERTAINTY SUMMARY")
            print("=" * 50)
            for k, v in summary.items():
                print(f"   {k}: {v:.4f}" if isinstance(v, float)
                      else f"   {k}: {v}")
            print("=" * 50)
        else:
            print("\n⚠️  Uncertainty manager not available")
 
    def list_users(self):
        print("\n" + "=" * 55)
        print("  REGISTERED USERS")
        print("=" * 55)
        if USER_MANAGER_AVAILABLE:
            self.user_manager.print_all_users()
        else:
            print("  (user manager not installed)")
        print("=" * 55)
 
    def _end_session(self):
        if (USER_MANAGER_AVAILABLE and
                self.current_user and
                not self.current_user.is_guest):
            session_id = getattr(
                self.user_manager, 'current_session_id', -1
            )
            if session_id != -1:
                peak_iri = (max(self._session_iri_history)
                            if self._session_iri_history else 0)
                mean_iri = (float(np.mean(self._session_iri_history))
                            if self._session_iri_history else 0)
                mean_sp  = (float(np.mean(self._session_spine_history))
                            if self._session_spine_history else 0)
                self.user_manager.end_session(session_id, {
                    "total_reps": self.current_exercise_status.get('rep_count', 0),
                    "peak_iri":   peak_iri,
                    "mean_iri":   mean_iri,
                    "mean_spine": mean_sp,
                    "peak_risk":  self._session_peak_risk
                })
                print(f"\n✅ Session saved for "
                      f"{self.current_user.display_name}")
 
    def show_session_report(self):
        print("\n" + "=" * 55)
        print("📊 SESSION REPORT")
        print("=" * 55)
 
        if self.current_user:
            print("\n── User ─────────────────────────────────────")
            print(f"   Name:  {self.current_user.display_name}")
            print(f"   ID:    #{self.current_user.user_id}")
            print(f"   Guest: {self.current_user.is_guest}")
 
        fatigue  = self.fatigue_engine.get_session_report()
        exercise = self.exercise_tracker.get_session_summary()
 
        print("\n── Exercise ─────────────────────────────────────")
        for k, v in exercise.items():
            print(f"   {k}: {v:.2f}" if isinstance(v, float)
                  else f"   {k}: {v}")
 
        print("\n── Fatigue ──────────────────────────────────────")
        for k, v in fatigue.items():
            print(f"   {k}: {v:.2f}" if isinstance(v, float)
                  else f"   {k}: {v}")
 
        if hasattr(self.injury_predictor, 'get_session_report'):
            iri_report = self.injury_predictor.get_session_report()
            print("\n── IRI ──────────────────────────────────────")
            iri_stats = iri_report.get('iri_stats', {})
            if iri_stats:
                print(f"   Mean IRI:  {iri_stats.get('mean', 0):.1f}%")
                print(f"   Peak IRI:  {iri_stats.get('max',  0):.1f}%")
                print(f"   Final IRI: {iri_stats.get('final',0):.1f}%")
            print(f"   ⚕️  {iri_report.get('disclaimer','')}")
 
        if self.uncertainty_manager:
            print("\n── Uncertainty ──────────────────────────────")
            summary = self.uncertainty_manager.get_uncertainty_summary()
            for k, v in summary.items():
                print(f"   {k}: {v:.4f}" if isinstance(v, float)
                      else f"   {k}: {v}")
 
        print("\n── System ───────────────────────────────────────")
        print(f"   Temporal: {getattr(self,'using_temporal',False)}")
        print(f"   IRI V2:   {self.using_iri_v2}")
        print(f"   Camera:   {self.current_camera_id}")
        print("=" * 55)
 
    def export_data(self):
        print("\n📁 Exporting...")
        self.exercise_tracker.export_to_csv()
        self.exercise_tracker.export_rep_summary()
        self.risk_classifier.save_model()
        print("✅ Export complete!")
        if self.voice_enabled:
            self.speaker.speak_now("Data exported")
 
    def reset_reps(self):
        self.exercise_tracker.reset()
        print("\n🔄 Reps reset")
        if self.voice_enabled:
            self.speaker.speak_now("Reps reset")
 
    def save_model(self):
        self.risk_classifier.save_model()
        print("\n💾 Model saved")
        if self.voice_enabled:
            self.speaker.speak_now("Model saved")
 
    def adjust_speed(self, faster=True):
        if faster:
            self.process_every_n = max(1, self.process_every_n - 1)
        else:
            self.process_every_n = min(5, self.process_every_n + 1)
        print(f"\n⚡ Every {self.process_every_n} frame(s)")
 
    # ──────────────────────────────────────────────────────────
    # MAIN RUN LOOP
    # ──────────────────────────────────────────────────────────
 
    def run(self, camera_id=0):
        self.current_camera_id = camera_id
 
        print(f"\n📷 Opening camera {camera_id}...")
        cap = cv2.VideoCapture(camera_id)
        if not cap.isOpened():
            print("❌ Cannot open camera!")
            return
 
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
 
        # ── FACE IDENTIFICATION ────────────────────────────────
        print("\n👤 Starting user identification...")
        if USER_MANAGER_AVAILABLE:
            self.current_user = self.user_manager.identify_from_camera(
                cap, timeout=25.0, allow_new_user=True, allow_guest=True
            )
        else:
            self.current_user = DummyUserManager._GuestProfile()
 
        if not self.current_user.is_guest:
            self.id_state = "identified"
            name     = self.current_user.display_name.split()[0]
            sess_num = self.current_user.total_sessions + 1
            greeting = (
                f"Welcome back, {name}! Session {sess_num}!"
                if self.current_user.total_sessions > 0
                else f"Welcome, {name}! Let's start your first session!"
            )
            print(f"\n  👋 {greeting}")
            if self.voice_enabled:
                self.speaker.speak_now(greeting)
 
            if self.current_user.baseline:
                print(f"   📐 Loading baseline for "
                      f"{self.current_user.display_name}")
                self.risk_classifier.calibrate_to_person(
                    self.current_user.baseline
                )
 
            session_id = self.user_manager.start_session(
                self.current_user.user_id
            )
            print(f"   📝 Session #{session_id} started")
        else:
            self.id_state = "guest"
            print("   👤 Running as Guest")
            if self.voice_enabled:
                self.speaker.speak_now("LiftGuard ready!")
 
        # ── STARTUP INFO ───────────────────────────────────────
        print("\n" + "=" * 65)
        print("  🏋️  LIFTGUARD AI V2 — RUNNING")
        print("=" * 65)
        print(f"  User:     {self.current_user.display_name if self.current_user else 'Guest'}")
        print(f"  Voice:    {'ON' if self.voice_enabled else 'OFF'}")
        print(f"  Arduino:  {'CONNECTED' if self.arduino_connected else 'OFF'}")
        print(f"  Temporal: {'ON' if self.using_temporal else 'OFF'}")
        print(f"  IRI V2:   {'ON' if self.using_iri_v2 else 'OFF'}")
        print(f"  Face ID:  {'ON (OpenCV LBPH)' if USER_MANAGER_AVAILABLE else 'OFF'}")
        print("  " + "─" * 61)
        print("  [Q]uit  [V]oice  [A]rduino  [K]Laser  [M]irror")
        print("  [C]alib  [T]emporal  [U]ncert  [L]ist  [R]eport")
        print("  [X]Reset  [E]xport  [S]ave  [I]P  [0-9]Cam  [+/-]")
        print("=" * 65 + "\n")
 
        self.session_active = True
 
        while self.session_active:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue
 
            if self.mirror_mode:
                frame = cv2.flip(frame, 1)
 
            output = self.process_frame(frame)
            cv2.imshow('LiftGuard AI V2', output)
 
            key = cv2.waitKey(1) & 0xFF
 
            if key in (ord('q'), ord('Q')):
                self._end_session()
                self.session_active = False
            elif key in (ord('v'), ord('V')):   self.toggle_voice()
            elif key in (ord('a'), ord('A')):   self.toggle_arduino()
            elif key in (ord('t'), ord('T')):   self.toggle_temporal()
            elif key in (ord('u'), ord('U')):   self.show_uncertainty_summary()
            elif key in (ord('k'), ord('K')):   cap = self.calibrate_laser(cap)
            elif key in (ord('m'), ord('M')):   self.toggle_mirror()
            elif key in (ord('s'), ord('S')):   self.save_model()
            elif key in (ord('r'), ord('R')):   self.show_session_report()
            elif key in (ord('x'), ord('X')):   self.reset_reps()
            elif key in (ord('e'), ord('E')):   self.export_data()
            elif key in (ord('i'), ord('I')):   cap = self.connect_ip_camera(cap)
            elif key in (ord('l'), ord('L')):   self.list_users()
            elif key in (ord('+'), ord('=')):   self.adjust_speed(faster=True)
            elif key in (ord('-'), ord('_')):   self.adjust_speed(faster=False)
            elif key in (ord('c'), ord('C')):
                if self.calibration_mode:
                    self.complete_calibration()
                else:
                    self.start_calibration()
            elif key in [ord(str(i)) for i in range(10)]:
                cap = self.switch_camera(cap, key - ord('0'))
 
        # ── CLEANUP ────────────────────────────────────────────
        cap.release()
        cv2.destroyAllWindows()
 
        if self.arduino_connected:
            self.arduino.laser_off()
            self.arduino.disconnect()
 
        if self.voice_enabled:
            self.speaker.speak_now("Session complete. Great workout!")
            time.sleep(2)
 
        print("\n" + "=" * 55)
        print("  SESSION COMPLETE")
        print("=" * 55)
        self.show_session_report()
        print("\n👋 Thank you for using LiftGuard AI V2!")
 
 
# ============================================================
# ENTRY POINT
# ============================================================
 
# NOTE: the original standalone `python main.py` entry point (cv2.imshow loop,
# keyboard controls) is preserved unchanged in backend/run_standalone.py for
# anyone who wants to run the classic desktop app. The FastAPI path drives
# this same LiftGuardAI class through app/core/session_manager.py instead,
# calling the exact same process_frame()/run()-equivalent methods below.
