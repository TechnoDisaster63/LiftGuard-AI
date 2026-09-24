# Face ID (on-device)

LiftGuard can recognise who is training when a session starts on the LiftGuard computer's own camera, or on demand with "Identify me" on the Users page. Everything runs on that computer.

## What is stored, and where

- One face signature per enrolled person: 128 numbers (an SFace embedding), the average of the good frames from enrollment. It sits in the local user database (`LIFTGUARD_USER_DB`, table `face_embeddings`).
- No photo, face crop or camera frame is stored. Frames sent for enrollment or identification are decoded in memory, turned into a signature and dropped.
- Upgrading from the older LBPH face ID deletes the face images and profile photos it stored (`purge_stored_face_images`, then `VACUUM` so the bytes are not left in the file). Accounts and session history stay; people re-enroll with "Set up" on the Users page.
- "Delete face" on the Users page removes a person's signature. Their account and history stay.

## What never leaves the computer

- Face signatures and frames are never sent to the contributions store, the Hugging Face dataset, logs, telemetry or the live WebSocket stream. Contributions stay body landmarks only (`tests/test_face_id.py::test_contributions_never_touch_face_data`).
- The face endpoints (`POST /api/users/register`, `POST /api/users/{id}/face`, `POST /api/users/identify`) only accept requests from a browser on the same computer as the backend (`app/identity/locality.py`): loopback peer, no non-local forwarding chain, and a localhost Origin. A phone on the Wi-Fi, a Codespace viewer or a tunnel gets a 403, and the pages say face ID is not available from that device. The "Your face never leaves this device" line is only shown when the backend confirms the browser is local.
- Sessions that use the viewer's browser camera never run face ID (that camera may be on another device), so they start as Guest.

Why the backend and not the browser: the backend already owns the user database, the session-start identification uses the LiftGuard computer's own camera, and keeping one store avoids a second copy in browser storage that would be tied to one browser profile and easy to leave behind.

## Models

Downloaded once, never committed (`backend/models/` is gitignored):

```
cd backend
python fetch_face_models.py
```

| File | What | Licence |
|---|---|---|
| `face_detection_yunet_2023mar.onnx` | YuNet face detector (OpenCV Zoo) | MIT |
| `face_recognition_sface_2021dec.onnx` | SFace face recognizer (OpenCV Zoo) | Apache-2.0 |

Both run through OpenCV's built-in `cv2.FaceDetectorYN` and `cv2.FaceRecognizerSF`; no extra packages. The script checks each file's sha256. Without the files, face ID is off and sessions start as Guest.

Training-data caveat: OpenCV Zoo does not state what the SFace weights were trained on. The SFace paper trained on CASIA-WebFace, VGGFace2 and MS-Celeb-1M, research datasets of public celebrity photos with their own terms. Fine for the free pilot; it needs a second look before any paid or distributed release.

## Matching

- Same person: cosine similarity >= 0.363 (SFace's published threshold) and at least 0.05 above the next enrolled person, so look-alikes are not guessed.
- Enrollment: at least 5 frames with exactly one clear face (>= 60 px), and every pair of frames must match each other.
- Session start: the same person on 3 good frames in a row within 8 s, otherwise Guest. "Identify me": 6 frames, the same person on at least 3 and nobody else on any.

Check on public-domain portraits with the real models (local run): the same person across two different photos scored 0.81 and 0.74; different people scored 0.09 to 0.27.
