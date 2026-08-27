# Precision Lap — Endeavour Racing

A lap-time prediction game for Endeavour Racing. A track and a weather scenario are drawn at random, you choose tyre compound, fuel load, ERS and DRS, and then enter the lap time you think that setup will produce. The app simulates the lap and scores how close you were.

## Features

- **Setup Configuration** — Choose tyre compound, fuel level, ERS mode, and DRS
- **Scored Guess** — Enter an expected lap time, then see the simulated lap, the delta, the race event that hit it and the points it was worth
- **Grade Bands** — Eight bands from PERFECT PREDICTION (within 0.4s, 1000 points) down to DNF, with a medal and a comment for each
- **Session Leaderboard** — Top ten runs, kept in the browser's own local storage; nothing is uploaded and no server is involved
- **Animated UI** — Rain particle effects, scanline overlay, F1-style dark theme

## What the simulation is, and is not

It is a game, not a model of a car. The simulated lap starts from the track's ideal time plus a weather offset plus a random ±2s drawn before you touch a single control, so the exact answer is deliberately not derivable from the setup. Your choices then move it by hand-picked constants — soft tyres −0.6s, hard +1.4s, low fuel −0.5s, ERS −0.9s, DRS scaled by the track's DRS rating — and a further roll can drop a virtual safety car, a yellow flag or a tailwind onto the lap. Those constants were chosen so the trade-offs feel right, not fitted to telemetry, and nothing here is calibrated against real lap data.

## Running

No build step. Single self-contained HTML file. The only external reference is one optional Google Fonts CDN link for the display typefaces; if it is blocked or offline, the app still works and falls back to system fonts.

```bash
# macOS: open in the default browser
open index.html
```

```bat
:: Windows: double-click index.html, or run the launcher
start.bat
```

Or double-click `index.html` in File Explorer.
