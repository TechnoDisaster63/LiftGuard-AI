# save as: diagnose.py
# run: python diagnose.py
 
print("=" * 55)
print("  LIFTGUARD AI - FACE RECOGNITION DIAGNOSTIC")
print("=" * 55)
 
# ── Test 1: face_recognition ────────────────────────────────
print("\n[1] Testing face_recognition...")
try:
    import face_recognition
    print("    ✅ face_recognition imported OK")
except ImportError as e:
    print(f"    ❌ MISSING: {e}")
    print("    FIX: pip install face-recognition")
 
# ── Test 2: dlib ─────────────────────────────────────────────
print("\n[2] Testing dlib...")
try:
    import dlib
    print(f"    ✅ dlib {dlib.__version__} imported OK")
except ImportError as e:
    print(f"    ❌ MISSING: {e}")
    print("    FIX: pip install dlib")
    print("    OR:  pip install cmake && pip install dlib")
 
# ── Test 3: deepface fallback ────────────────────────────────
print("\n[3] Testing DeepFace (fallback)...")
try:
    from deepface import DeepFace
    print("    ✅ DeepFace imported OK")
except ImportError as e:
    print(f"    ❌ MISSING: {e}")
    print("    FIX: pip install deepface")
 
# ── Test 4: user_manager.py ──────────────────────────────────
print("\n[4] Testing user_manager.py...")
try:
    from user_manager import UserManager, UserProfile
    print("    ✅ user_manager.py found")
    try:
        um = UserManager()
        print(f"    ✅ UserManager() created OK")
        print(f"    ✅ DB path: liftguard_users.db")
        users = um.get_all_users()
        print(f"    ✅ Users in DB: {len(users)}")
        for u in users:
            print(f"       → [{u.user_id}] {u.display_name}")
    except Exception as e:
        print(f"    ❌ UserManager() failed: {e}")
except ImportError as e:
    print(f"    ❌ user_manager.py not found: {e}")
 
# ── Test 5: user_ui.py ───────────────────────────────────────
print("\n[5] Testing user_ui.py...")
try:
    from user_ui import UserUIOverlay
    print("    ✅ user_ui.py found")
except ImportError as e:
    print(f"    ❌ user_ui.py not found: {e}")
 
# ── Test 6: camera ───────────────────────────────────────────
print("\n[6] Testing camera...")
try:
    import cv2
    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret:
            print(f"    ✅ Camera OK — frame shape: {frame.shape}")
        else:
            print("    ❌ Camera opened but no frame")
        cap.release()
    else:
        print("    ❌ Camera 0 not found")
except Exception as e:
    print(f"    ❌ Camera error: {e}")
 
# ── Test 7: Live face detection ──────────────────────────────
print("\n[7] Testing live face detection (3 seconds)...")
try:
    import face_recognition
    import cv2
    import numpy as np
 
    cap  = cv2.VideoCapture(0)
    found = False
    start = __import__('time').time()
 
    while __import__('time').time() - start < 3:
        ret, frame = cap.read()
        if not ret:
            continue
        rgb       = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        locations = face_recognition.face_locations(rgb, model="hog")
        if locations:
            print(f"    ✅ Face detected! Location: {locations[0]}")
            enc = face_recognition.face_encodings(rgb, locations)
            if enc:
                print(f"    ✅ Encoding generated: shape={enc[0].shape}")
            found = True
            break
 
    cap.release()
    if not found:
        print("    ⚠️  No face detected in 3 seconds")
        print("    TIP: Make sure your face is visible to the camera")
        print("    TIP: Improve lighting")
 
except Exception as e:
    print(f"    ❌ Live face test failed: {e}")
 
# ── Summary ──────────────────────────────────────────────────
print("\n" + "=" * 55)
print("  SUMMARY")
print("=" * 55)
 
checks = {
    "face_recognition": False,
    "dlib": False,
    "deepface": False,
    "user_manager": False,
}
 
try:
    import face_recognition
    checks["face_recognition"] = True
except Exception:
    pass
 
try:
    import dlib
    checks["dlib"] = True
except Exception:
    pass
 
try:
    from deepface import DeepFace
    checks["deepface"] = True
except Exception:
    pass
 
try:
    from user_manager import UserManager
    checks["user_manager"] = True
except Exception:
    pass
 
all_ok = checks["face_recognition"] and checks["user_manager"]
 
for k, v in checks.items():
    status = "✅" if v else "❌"
    print(f"  {status} {k}")
 
print()
if all_ok:
    print("  ✅ ALL GOOD — should work. Check lighting/camera angle.")
elif checks["user_manager"] and not checks["face_recognition"]:
    print("  ❌ face_recognition missing — see install guide below")
elif not checks["user_manager"]:
    print("  ❌ user_manager.py missing from project folder")
else:
    print("  ❌ Multiple issues found — follow fixes above")
 
print("=" * 55)
