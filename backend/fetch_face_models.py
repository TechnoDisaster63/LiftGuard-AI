"""Download the on-device face ID models (YuNet + SFace from OpenCV Zoo).

  python fetch_face_models.py            # into backend/models/face (gitignored)

Checks each file's sha256. The files are never committed; see docs/FACE_ID.md
for licences and the training-data caveat.
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.identity.face_id import MODEL_SHA256, MODEL_URLS, model_dir  # noqa: E402


def main() -> int:
    d = model_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name, url in MODEL_URLS.items():
        path = d / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256[name]:
            print(f"downloading {name} ...")
            urllib.request.urlretrieve(url, path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != MODEL_SHA256[name]:
            path.unlink()
            print(f"{name}: checksum mismatch ({digest}); deleted", file=sys.stderr)
            return 1
        print(f"{name}: ok")
    print(f"face ID models ready in {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
