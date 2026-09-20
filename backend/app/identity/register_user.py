# save as: register_user.py
# run: python register_user.py
 
"""
Manual user registration for LiftGuard AI.
Run this ONCE to register your face.
Then restart main.py — it will recognise you automatically.
"""
 
import cv2
import time
import sys
 
print("\n" + "=" * 55)
print("  LIFTGUARD AI — USER REGISTRATION")
print("=" * 55)
 
# ── Check face_recognition ────────────────────────────────────
try:
    import face_recognition
    import numpy as np
    print("✅ face_recognition available")
except ImportError:
    print("❌ face_recognition not installed!")
    print("\nInstall with:")
    print("  pip install cmake dlib face-recognition")
    sys.exit(1)
 
# ── Check user_manager ───────────────────────────────────────
try:
    from user_manager import UserManager, UserProfile  # noqa: F401 -- presence in this import is the availability check
    print("✅ user_manager available")
except ImportError:
    print("❌ user_manager.py not found!")
    print("Make sure user_manager.py is in the same folder.")
    sys.exit(1)
 
# ── Get user details ──────────────────────────────────────────
print()
display_name = input("Enter your name (e.g. 'John Smith'): ").strip()
if not display_name:
    display_name = "Athlete"
 
username = (
    display_name.lower()
               .replace(" ", "_")
               .replace("'", "")
)
 
print(f"\nRegistering as: {display_name} (@{username})")
print("\nGet ready — looking at camera in 3 seconds...")
time.sleep(3)
 
# ── Open camera ───────────────────────────────────────────────
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
 
if not cap.isOpened():
    print("❌ Cannot open camera!")
    sys.exit(1)
 
# ── Capture face samples ──────────────────────────────────────
print("\n📷 Capturing face samples...")
print("Look directly at camera and slowly move head left/right")
print("Capturing for 6 seconds...\n")
 
frames_rgb    = []
face_detected = 0
no_face_count = 0
start_time    = time.time()
DURATION      = 6.0
profile_photo = None
 
while time.time() - start_time < DURATION:
    ret, frame = cap.read()
    if not ret:
        continue
 
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    display   = frame.copy()
    h, w      = display.shape[:2]
    elapsed   = time.time() - start_time
 
    # Detect face
    locations = face_recognition.face_locations(frame_rgb, model="hog")
 
    if locations:
        top, right, bottom, left = locations[0]
        face_detected += 1
        frames_rgb.append(frame_rgb.copy())
 
        if profile_photo is None:
            profile_photo = frame.copy()
 
        # Green box
        cv2.rectangle(display, (left, top), (right, bottom), (0, 255, 0), 3)
 
        # Corner accents
        corner = 20
        for (cx, cy), (dx, dy) in [
            ((left, top),     (1, 1)),
            ((right, top),    (-1, 1)),
            ((left, bottom),  (1, -1)),
            ((right, bottom), (-1, -1))
        ]:
            cv2.line(display, (cx, cy), (cx + dx*corner, cy), (0,255,0), 3)
            cv2.line(display, (cx, cy), (cx, cy + dy*corner), (0,255,0), 3)
 
        cv2.putText(display, f"FACE DETECTED #{face_detected}",
                    (left, top - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    else:
        no_face_count += 1
        cv2.putText(display, "No face — look at camera",
                    (w//2 - 180, h//2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
 
    # Progress bar
    progress = elapsed / DURATION
    bar_x    = 50
    bar_y    = h - 60
    bar_w    = w - 100
    cv2.rectangle(display, (bar_x, bar_y), (bar_x+bar_w, bar_y+25),
                  (50, 50, 50), -1)
    cv2.rectangle(display,
                  (bar_x, bar_y),
                  (bar_x + int(bar_w * progress), bar_y + 25),
                  (0, 255, 0) if locations else (100, 100, 100), -1)
 
    cv2.putText(display, f"Registering: {display_name}",
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 220, 0), 2)
    cv2.putText(display,
                f"Samples: {face_detected} | "
                f"Time: {DURATION - elapsed:.1f}s",
                (bar_x, bar_y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
 
    cv2.imshow("LiftGuard AI — Register User", display)
 
    key = cv2.waitKey(1) & 0xFF
    if key in (ord('q'), 27):
        print("\n⚠️  Registration cancelled")
        cap.release()
        cv2.destroyAllWindows()
        sys.exit(0)
 
cap.release()
cv2.destroyAllWindows()
 
# ── Check we got enough samples ───────────────────────────────
print(f"\n📊 Captured {face_detected} face samples")
 
if face_detected < 5:
    print(f"\n❌ Not enough face samples ({face_detected}/5 minimum)")
    print("\nTroubleshooting:")
    print("  • Make sure your face is clearly visible")
    print("  • Improve lighting (face the light source)")
    print("  • Move closer to the camera")
    print("  • Remove sunglasses or hat")
    sys.exit(1)
 
# ── Compute encoding ──────────────────────────────────────────
print("🧠 Computing face encoding...")
 
encodings  = []
step       = max(1, len(frames_rgb) // 15)
 
for i in range(0, len(frames_rgb), step):
    locs = face_recognition.face_locations(frames_rgb[i], model="hog")
    if locs:
        encs = face_recognition.face_encodings(frames_rgb[i], locs)
        if encs:
            encodings.append(encs[0])
    if len(encodings) >= 15:
        break
 
print(f"   Generated {len(encodings)} encodings from samples")
 
if len(encodings) < 3:
    print("❌ Could not generate face encoding!")
    print("   Try again with better lighting.")
    sys.exit(1)
 
mean_encoding = np.mean(encodings, axis=0)
print(f"✅ Mean encoding computed (shape: {mean_encoding.shape})")
 
# ── Save to database ──────────────────────────────────────────
print("\n💾 Saving to database...")
 
try:
    um      = UserManager()
    profile = um.register_user(
        username     = username,
        display_name = display_name,
        face_encoding= mean_encoding,
        profile_photo= profile_photo
    )
 
    print("\n" + "=" * 55)
    print("  ✅ REGISTRATION SUCCESSFUL!")
    print("=" * 55)
    print(f"  Name:     {profile.display_name}")
    print(f"  Username: {profile.username}")
    print(f"  User ID:  #{profile.user_id}")
    print(f"  Samples:  {face_detected} frames")
    print(f"  Encodings:{len(encodings)}")
    print()
    print("  → Now restart main.py")
    print("  → Stand in front of the camera")
    print("  → You will be automatically identified!")
    print("=" * 55)
 
    # Show all registered users
    all_users = um.get_all_users()
    print(f"\n  Total registered users: {len(all_users)}")
    for u in all_users:
        marker = "← YOU" if u.user_id == profile.user_id else ""
        print(f"  [{u.user_id}] {u.display_name} {marker}")
 
except Exception as e:
    print(f"\n❌ Database save failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
