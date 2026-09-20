# LiftGuard AI — Frontend

Next.js 14 (App Router) + Tailwind dashboard for the FastAPI backend in `../backend/`.

## Design direction

Dark, clinical-instrument aesthetic — closer to a lab dial than a fitness app,
since the product is a clinical-grade injury risk index, not a rep counter.

- **Palette**: near-black graphite (`#0A0E13`) base, glass panels at low
  opacity, a clinical teal (`#4FD1C5`) for the calm/low-risk state, amber →
  red → crimson escalation for risk levels (this maps directly to
  `risk_level` from the engine, it's functional, not decorative), and a
  violet (`#8B7FD1`) reserved for the MC-Dropout uncertainty band.
- **Type**: Space Grotesk for display/headings, Inter for UI text,
  JetBrains Mono for anything that's actually a live number — telemetry,
  frame counts, gauge readouts. The mono readouts are the one deliberate
  "instrument" signature carried through every page.
- **Signature element**: the radial risk gauge on the Live Analysis page —
  a 270° instrument-dial arc with tick marks, where the shaded band isn't
  decoration, it's the model's actual MC-Dropout uncertainty interval
  rendered as an arc segment.

## Register page: fixed a real camera bug

The camera preview never showed up, even though the permission prompt appeared (camera
light turns on). Root cause: `videoRef.current.srcObject` was being set *before*
`setStep("preview")` ran — but the `<video>` element only mounts once `step` becomes
`"preview"`, so `videoRef.current` was still `null` at that point and the assignment
silently did nothing. Fixed with a `useEffect` that attaches the stream after the element
actually exists in the DOM, watching `step`. Also switched the camera constraints from bare
numbers to `{ ideal: 640 }` and added `autoPlay` as a second safety net, plus specific error
messages for permission-denied / no-camera / camera-in-use / insecure-context instead of one
generic message.

## Grid layout, redesigned to balance left/right

`MagicBento`'s desktop layout used to give one card a 2x2 span and another an L-shaped
block — asymmetric, tuned only for exactly 6 cards. Replaced with `grid-auto-flow: column`
on a clean 2-column grid: cards 1-3 fill straight down the left column, cards 4-6 fill
straight down the right — an even, deliberate half-and-half split, uniform card sizes, and
it now scales to any card count (the `compact` variant's 4-card set on Users just gets 2
rows instead of 3, no per-card overrides needed anymore).

## Folder: real drawer motion

The papers used to scatter outward with wide rotation on open — redesigned to read as a
drawer being pulled toward you: papers slide straight up into a tight offset stack with only
a couple degrees of rotation each, staggered so they pull out one after another rather than
all at once. Opening uses a spring/overshoot easing (`cubic-bezier(0.34, 1.56, 0.64, 1)`) for
that "pulled out and settled" feel; closing uses a quick, snappy ease-in with no stagger —
intentionally asymmetric timing, since pulling something out and pushing it back in aren't
the same motion physically. The folder itself now lifts and gains a drop shadow on open
instead of just a flat translateY.

## Deeper black + sparkles

Base background darkened from `#08090D` to `#050608` — a truer black, more contrast for the
particle/glow effects to read against. `SparklesCore` now appears in three places instead of
just the Dashboard hero: the Register page's success screen (a small celebratory burst
behind the checkmark), and the Live page's idle state (before a session starts — reads as
"instrument warming up," specifically not shown during the connecting/error states so it
never implies things are fine when they aren't).

## React Bits components — now used across the whole app, not just Dashboard

- **MagicBento** — Dashboard's hero "Explore" grid (6 cards), plus a `compact` variant now
  used for a 4-card "Quick Actions" grid on the Users page. `cardData` was hardcoded inside
  the original component; it's now a `cards` prop (`DEFAULT_BENTO_CARDS` export as the
  fallback) so any page can pass its own set without duplicating the component.
- **Folder** — Dashboard's "Recent Session Reports" is reused as-is on the Sessions page
  (quick access above the full history list). A second, purpose-built instance —
  `components/reports/RelatedSessionsFolder.tsx` — appears on the Reports page, showing up
  to 3 *other* sessions from the same user (filtered by `user_id`, excluding the one you're
  currently viewing) so you can jump between a person's sessions without going back to
  Sessions first.
- **OptionWheel** — was only Settings' Pose Model Complexity picker; now also Process Every N
  Frames and Default Camera on the same page (both were plain number inputs), and the Live
  page's Control Deck camera picker (was a plain button list, now a proper wheel + a
  separate IP Camera action below it).

## Design system, systematized (now app-wide)

`components/ui/` holds the app's real primitives (shadcn convention — `cn()` in
`lib/utils.ts`, `Button`, `Card`/`CardHeader`/`CardTitle`/`CardEyebrow`/`CardContent`,
`Badge` + `riskToneFromLevel`, `EmptyState`). Every page — Dashboard, Live, Analytics,
Reports, Sessions, Users, Register, Hardware, Settings — now uses these instead of hand-typed
className strings, plus `framer-motion` entrance/list animations throughout. The Sidebar's
active nav indicator uses a `layoutId` spring transition; `TopNav`'s Settings icon actually
navigates now (it was a dead button before). `/register` was missing from the Sidebar's own
nav list — added.

`components/ui/sparkles.tsx` — `SparklesCore`, a `@tsparticles`-based particle field, ported
with LiftGuard's brand violet as the default color and density brought down from the
original 1200 to 60 (this is a clinical dashboard, not a marketing landing page — it needed
to read as "subtle instrument shimmer" behind the Dashboard hero heading, not a confetti
burst). New dependencies: `@tsparticles/react`, `@tsparticles/engine`, `@tsparticles/slim`,
`tailwind-merge`.

## React Bits components (customized, not demo drop-ins)

Three components ported from React Bits to TypeScript, in `components/reactbits/`, each
wired to a real feature rather than left as generic demo content:

- **MagicBento** (`gsap`-driven spotlight/particle/glow bento grid) — the Dashboard's
  "Explore" section. `cardData` was replaced with LiftGuard's actual 6 destinations (Live
  Analysis, Injury Risk Index, Analytics, Hardware, Register User, Reports), each card a
  real `next/link`, not just a ripple effect. `glowColor` uses the app's brand violet
  (`124, 92, 255`) instead of the original purple default.
- **Folder** — `components/dashboard/RecentReportsFolder.tsx` wraps it with real data: the 3
  most recent completed sessions from `/api/sessions/history`, rendered as clickable papers
  (avatar initials colored by that session's peak risk, name, date) that navigate to
  `/reports?history={id}`.
- **OptionWheel** — replaces the plain `<select>` for Pose Model Complexity on the Settings
  page. Scroll/drag/arrow-key selection, wired to the same `PATCH /api/settings` call the
  select used.

## Signature element (updated)

The Live Analysis video feed now carries its own HUD — identity chip, status badges,
biomechanics readout, rep counter — rendered as solid, sharp-edged HTML/CSS overlays
(`components/live/VideoHUD.tsx`) instead of baked into the video pixels by OpenCV. The
video itself only carries the pose skeleton (genuinely pixel-tied). High risk state is a
CSS glow on the video container, not a flashing border drawn into the frame.

## Theme (redesigned)

No more glassmorphism — panels are solid fill (`#10131A`/`#151922`) with crisp 1px borders
and a real shadow for depth, not blur. Sharper corners throughout (6px panels, 4px controls,
down from 16px/10px). Brand color is now a deliberate violet (`#7C5CFF`), decoupled from
risk semantics — it used to share the exact same hex as "low risk," which quietly implied
"the button is safe" every time it was really just "this is the active brand color." Risk
colors are now their own independent scale (green/amber/red/crimson) that only ever means
risk. `framer-motion` drives entrance animations, staggered card reveals, button press
feedback, and the toast/modal transitions.

## Every keyboard shortcut is now a button

The original desktop app had 13 keyboard shortcuts (voice, laser, mirror, temporal model,
calibration, reset, export, save model, speed up/down, camera switch, IP camera). Only 6
were exposed as web buttons before this pass — the rest existed on the backend
(`session_manager.handle_control`) but had no UI. `components/live/ControlBar.tsx` is now a
full "Control Deck" exposing all of them, plus a camera-source picker. Button presses also
get real feedback now — `control_ack` messages over the WebSocket surface as toasts
(`components/live/ToastStack.tsx`), replacing what used to be `print()` statements only
visible in a terminal the web user never sees. The uncertainty summary (`[U]` in the
original) got the same treatment: a proper panel (`UncertaintyPanel.tsx`) instead of a
console dump.

## Setup

```bash
cd frontend
npm install
cp .env.local.example .env.local   # point at your backend
npm run dev
```

Requires the backend running (`cd ../backend && uvicorn app.main:app --reload`)
for any page beyond static layout to show real data.

## Pages

| Route | Status |
|---|---|
| `/dashboard` | Built — active session count, registered users, quick-start |
| `/live` | Built — the core screen: video stream, risk gauge, corrections, controls |
| `/analytics` | Built — per-session IRI/spine timelines for the currently selected active session |
| `/reports` | Built — session report detail; works for both live (`?session=`) and completed (`?history=`) sessions |
| `/sessions` | Built — active sessions + persisted "Past Sessions" list, stop/view-report |
| `/register` | Built — browser-webcam face enrollment: name → live preview → 3-2-1 countdown → 6s auto-capture with a radial progress ring → submit → success/retry |
| `/users` | Built — registered users table + Register User CTA |
| `/hardware` | Built — laser connect with a USB/WiFi transport picker (WiFi needs an ESP32 running the firmware in `../firmware/`), status, calibrate |
| `/settings` | Built — editable session defaults (camera, voice, Arduino, model complexity, TCN), persisted server-side and applied to the next session you start |

## Status

Functionally complete across backend + frontend: live streaming, session persistence,
editable settings. Two things this sandbox genuinely can't finish because they need real
hardware: a live-camera/Arduino UX pass, and validating `npm install`/`pip install` actually
resolve cleanly on your machine (network was disabled here — see backend README for the
dependency notes to sanity-check first).
