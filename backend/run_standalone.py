"""
LiftGuard AI — Standalone Desktop Runner
=========================================
Preserves the ORIGINAL cv2.imshow / keyboard-driven desktop app exactly as
it behaved before the FastAPI restructure. Run this if you want the classic
single-process experience instead of the web dashboard.

Usage:
    cd backend
    python run_standalone.py
"""

from app.core.liftguard_engine import LiftGuardAI

if __name__ == "__main__":
    print("\n" + "🏋️ " * 22)
    print("\n   LIFTGUARD AI V2")
    print("   OpenCV Face ID + TCN + IRI V2 + Risk Skeleton")
    print("\n" + "🏋️ " * 22 + "\n")

    VOICE_ENABLED    = True
    ARDUINO_ENABLED  = True
    MODEL_COMPLEXITY = 0
    PROCESS_EVERY_N  = 1
    START_CAMERA     = 0
    USE_TEMPORAL     = True

    app = LiftGuardAI(
        voice_enabled    = VOICE_ENABLED,
        arduino_enabled  = ARDUINO_ENABLED,
        model_complexity = MODEL_COMPLEXITY,
        process_every_n  = PROCESS_EVERY_N,
        use_temporal     = USE_TEMPORAL
    )

    app.run(camera_id=START_CAMERA)
