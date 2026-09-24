# LiftGuard-AI demo video tooling

Scripts that produce the end-to-end demo video from real pipeline runs. Nothing here changes the analyzer.

1. `python demo/slides.py SLIDES_DIR path/to/report.json` renders the title, explainer and terminal cards (1280x720). The numbers on them come from `report.json`.
2. `python demo/record_dashboard.py SQUAT.mp4 NON_SQUAT.mp4 --out demo/recording` starts the Streamlit dashboard, uploads each clip, runs the real analysis and screen-records the walkthrough with Playwright (`pip install playwright && playwright install chromium`).
3. `python demo/build_video.py --slides ... --raw ... --annotated ... --dash-squat ... --dash-refusal ... --out liftguard_demo.mp4` stitches everything into an H.264 + AAC MP4. The analysis wait is sped up 8x and labeled as sped up on screen.

The dashboard itself is `dashboard/app.py`: `streamlit run dashboard/app.py`.
