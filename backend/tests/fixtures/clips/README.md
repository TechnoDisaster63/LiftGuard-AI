Recorded-clip fixtures for the movement-mode release gate. Landmarks only, no video pixels.

Add one with `python clip_check.py extract ...`, check it with `python clip_check.py check ... --save-expected`,
and commit the `.json.gz`. `tests/test_clip_check.py` re-checks every fixture here on each pull request.
Public-facing clips must be Techno's own recordings; trainer or third-party footage stays internal.
