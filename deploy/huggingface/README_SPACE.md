---
title: LiftGuard
emoji: 🏋️
colorFrom: gray
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
short_description: Real-time movement analysis for injury prevention
---

# LiftGuard

Real-time movement analysis and injury prevention platform. Squat is the first movement mode: it counts reps and flags limited depth, trunk lean and short range of motion. Not a medical diagnosis.

**Try it:** open **Live**, then **Use this device's camera** and allow the camera. Stand side-on, with your whole body in frame, 2-3 m from the camera. Do 3 slow squats so it can learn your depth, and then it starts counting. Spoken cues play on your device.

**Start session** runs the same pipeline on a recorded demo clip, since this server has no camera of its own.

Notes:
- One live session at a time. If someone else is using it, try again in a minute.
- Storage is temporary. Sessions and registered users are wiped when the Space restarts, and anyone visiting this public Space can see them, so don't register real faces here.

Source code: https://github.com/TechnoDisaster63/LiftGuard-AI

Demo clip: "Squat - exercise demonstration video" by FitnessScape, licensed CC BY 3.0 (https://creativecommons.org/licenses/by/3.0/), via Wikimedia Commons: https://commons.wikimedia.org/wiki/File:Squat_-_exercise_demonstration_video.webm
