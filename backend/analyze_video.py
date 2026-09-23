"""CLI: python analyze_video.py INPUT.mp4 --output outputs/run-name"""
import argparse
import json
from app.video_analysis import analyze_video

parser = argparse.ArgumentParser(description="Analyze one recorded side-view squat video offline")
parser.add_argument("input")
parser.add_argument("--output", default="outputs/latest")
args = parser.parse_args()
print(json.dumps(analyze_video(args.input, args.output)["summary"], indent=2))
