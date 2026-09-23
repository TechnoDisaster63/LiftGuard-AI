#!/usr/bin/env bash
# Build the Hugging Face Space repo from this checkout and push it.
#
#   HF_TOKEN=hf_... HF_SPACE=<user>/liftguard deploy/huggingface/push_space.sh
#
# The token needs write access. The Space must exist (Docker SDK), or pass
# CREATE=1 to create it as a public Docker Space first.
set -euo pipefail
: "${HF_TOKEN:?set HF_TOKEN}" "${HF_SPACE:?set HF_SPACE=<user>/liftguard}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [ "${CREATE:-0}" = 1 ]; then
  curl -fsS -X POST https://huggingface.co/api/repos/create \
    -H "Authorization: Bearer $HF_TOKEN" -H "Content-Type: application/json" \
    -d "{\"type\":\"space\",\"name\":\"${HF_SPACE#*/}\",\"sdk\":\"docker\",\"private\":false}" || true
  echo
fi
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
git -C "$ROOT" archive HEAD backend frontend deploy/huggingface/serve.py | tar -x -C "$WORK"
cp "$ROOT/deploy/huggingface/Dockerfile" "$WORK/Dockerfile"
cp "$ROOT/deploy/huggingface/README_SPACE.md" "$WORK/README.md"
printf '.git\n**/node_modules\n**/.next\nfrontend/out\n**/__pycache__\n' > "$WORK/.dockerignore"
cd "$WORK"
git init -q -b main
git -c user.name="LiftGuard deploy" -c user.email="deploy@liftguard.invalid" add -A
git -c user.name="LiftGuard deploy" -c user.email="deploy@liftguard.invalid" commit -qm "Deploy $(git -C "$ROOT" rev-parse --short HEAD)"
git push -f "https://user:${HF_TOKEN}@huggingface.co/spaces/${HF_SPACE}" main
echo "Pushed. Build log: https://huggingface.co/spaces/${HF_SPACE}?logs=build"
