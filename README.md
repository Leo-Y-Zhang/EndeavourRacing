# Endeavour Racing

Combined home for the Endeavour Racing team: the marketing **website**, the **Precision Lap**
setup-and-guess game, and the **Mission Control** dashboard. Imported from three separate
repositories as one squashed commit; the root commit message records why the original histories
are not preserved.

## Sub-projects
- `website/`         - team marketing site (from EndeavourRacingWebsite)
- `precision-lap/`   - lap-time guessing game (from EndeavourPrecisionLap)
- `mission-control/` - project / task / risk / budget dashboard (from EndeavourMissionControl)

## Running any of them

Each app is one self-contained `index.html` with its stylesheet and its whole program inlined.
There is no build step, no package manager and nothing to install, so opening the file is the
entire procedure:

```bash
git clone https://github.com/Leo-Y-Zhang/EndeavourRacing.git
cd EndeavourRacing

open website/index.html        # macOS
xdg-open website/index.html    # Linux
start website/index.html       # Windows, or double-click it, or run website\start.bat
```

The same three commands work for `precision-lap/index.html` and `mission-control/index.html`.
Each page pulls its display typefaces from Google Fonts and falls back to system fonts when that
is blocked or offline; nothing else is fetched, and no page has a backend.

## Checking them

Nothing here is compiled, so a stray brace in an inline script leaves a page that loads, renders
its markup, and does nothing at all. `tools/check_pages.py` is the only thing standing between
that and a commit: it checks tag balance, compiles every inline script the way a browser does
rather than the way `node --check` does, and confirms that in-page anchors and local file
references resolve.

```bash
python tools/check_pages.py
```

Thirteen checks, about a second, and it is the whole test suite. It needs Python 3.9 or newer
(standard library only, no `pip install`) and Node on `PATH` -- Node is what parses the inline
scripts, and the run fails rather than skips when it is missing. CI pins Python 3.13 and Node 22.

Two flags cover what the push gate deliberately leaves out:

```bash
python tools/check_pages.py --strict   # also fail if a page references an external origin
python tools/check_pages.py --links    # also request every outbound URL in the pages
```

`--links` runs weekly on a schedule instead of on push, because somebody else's server being down
is not a defect in this repository.

## Licence

The root `LICENSE` is the complete licence for everything in this repository: source-available,
no reuse rights granted. Read it, run it, check it. The sponsor and partner logos embedded in
`website/index.html` remain the property of their owners and are not covered by it.
