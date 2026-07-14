# PitStrategy

A local live fuel/tire monitor for iRacing, shown as a small browser overlay
rather than a native in-game overlay. Focused entirely on reacting to your
current pace lap-to-lap (fuel rates, laps-remaining projections, tire wear).

## TL;DR

**Get it running (no Python needed):**

1. Grab the latest `PitStrategy-win64.zip` from
   [Releases](https://github.com/mrzepka/PitStrategy/releases/latest) and
   extract it anywhere.
2. Open the extracted folder and double-click **`PitStrategy.exe`**. A
   console window opens (deliberate, see
   [Building a standalone executable](#building-a-standalone-executable)),
   then the overlay and settings windows appear a couple seconds later.
3. Needs the WebView2 runtime, which comes preinstalled on most current
   Windows 10/11 systems. If the exe won't launch, that's the first thing
   to check — Microsoft's WebView2 installer is a small, free download.

Prefer to build it yourself from source instead (e.g. to get unreleased
changes, or because you don't want to run a downloaded binary)? Click
**Code → Download ZIP** on the repo page (or `git clone` it), then from a
terminal in that folder:
```
pip install -r requirements.txt -r requirements-build.txt
pyinstaller pitstrategy.spec --noconfirm
```
(Needs Python 3.11+ on `PATH`.) That produces the same `dist\PitStrategy\`
folder the Release zip already contains — `dist/`/`build/` are gitignored
(generated output, not source), which is why a source download alone
doesn't already have a `.exe` in it.

**Use it:**

- It connects to whatever iRacing session is already running — no setup
  needed. (Want to try it without iRacing open first? Run
  `PitStrategy.exe --demo` from a terminal instead of double-clicking.)
- Drag the overlay (click anywhere on it) to a corner that doesn't cover
  iRacing's own HUD — it's frameless and always-on-top. Run iRacing in
  **borderless windowed** mode, or put the overlay on a second monitor,
  since there's no click-through.
- Too big or small? Drag the small corner glyph at the overlay's
  bottom-right to zoom it — see
  [Resizing the overlay](#resizing-the-overlay). Your zoom level is
  remembered next time.
- Use the **Settings** window (opens alongside the overlay) to hide
  whichever rows/columns/panels you don't want cluttering the HUD — see
  [Settings](#settings). Changes apply live, no restart needed.
- To close everything: close the overlay window, then close the console
  window (or Ctrl+C in it). They're independent processes on purpose, so
  closing one doesn't kill the others mid-session — see
  [Using the overlay during a race](#using-the-overlay-during-a-race).

Everything below goes into more depth on all of this.

## Setup

```
pip install -r requirements.txt
```

## Running

Live overlay, connected to a running iRacing session:

```
python run.py
```

Same thing but with synthetic fuel/tire/lap data instead of a real iRacing
connection (useful for trying it out without the sim running):

```
python run.py --demo
```

Fuel drains continuously in `--demo`, not once per simulated lap -- each
lap picks a randomized consumption rate (matching real lap-to-lap variance)
and removes it gradually, tick by tick, proportional to real time elapsed,
the same way iRacing's own `FuelLevel` telemetry behaves. This matters for
anything reading `current_fuel_level` live (the fuel gauge, the "Laps left"
columns on the overlay) -- it used to sit flat for the whole lap and jump
once at the lap boundary, which made those numbers look like they only
updated once per lap even though the underlying pipeline (poll → engine
tick → websocket push) was already fast enough to be smooth. A real
iRacing session never had this problem; it was purely a synthetic-data gap
in `DemoTelemetrySource`.

`run.py` also auto-opens both the overlay and [settings](#settings) windows
for you (see below), so you often don't need to visit these manually, but
they're always available at `http://127.0.0.1:8734/overlay` (live HUD --
fuel, tires, live pit window) and `http://127.0.0.1:8734/settings`.
`--no-open-overlay` skips both; `--no-open-settings` opens just the overlay.

## Building a standalone executable

Prebuilt zips are published on
[GitHub Releases](https://github.com/mrzepka/PitStrategy/releases) -- most
people won't need to build this themselves at all, see
[TL;DR](#tldr) above. Releases are cut manually (no CI/GitHub Actions set
up for this yet -- deliberate for now, since this is a low-frequency solo
project and it's easy to add automation later if that changes) whenever
there's something worth shipping: build fresh from `pitstrategy.spec`, zip
`dist/PitStrategy/`, `git tag vX.Y.Z`,
`gh release create vX.Y.Z PitStrategy-win64.zip`.

For day-to-day development you don't need a terminal at all once built:
`pitstrategy.spec` builds a real Windows `.exe` via
[PyInstaller](https://pyinstaller.org/).

```
pip install -r requirements-build.txt
pyinstaller pitstrategy.spec --noconfirm
```

Produces `dist/PitStrategy/` -- an **onedir** build (a folder containing
`PitStrategy.exe` alongside its dependencies), not a single self-extracting
onefile exe. Onedir starts faster and has been more reliable for
pywebview/pythonnet's WebView2 interop than onefile's self-extract-to-temp
approach; distribute the whole folder (zip it), not just the `.exe`.
Double-clicking `PitStrategy.exe` runs `run.py`'s `main()` with its
defaults -- connects to live iRacing (not `--demo`), opens both the overlay
and settings windows. The same `--demo`/`--host`/`--port`/`--no-open-*`
flags all still work if you run it from a terminal instead of
double-clicking it.

The exe currently keeps a visible console window (`console=True` in the
spec) rather than running fully windowed -- deliberate for now, since this
app is still under active iteration and startup errors (missing WebView2
runtime, pyirsdk failing to attach, etc.) are much easier to diagnose with
visible output than silently failing behind a windowed app. Flip
`console=False` in `pitstrategy.spec` once it's stable enough that this
stops being useful.

One non-obvious wrinkle, documented in `run.py`'s module docstring and
`pitstrategy.spec`'s comments: the overlay and settings windows are opened
by spawning `server/webview_launcher.py` as a *subprocess* (pywebview's
event loop needs to own a process's main thread, and this process's main
thread is already committed to `uvicorn.run()`). When running from source
that's `python -m server.webview_launcher <role> <url>`; a frozen exe has
no `-m` to fall back on since `sys.executable` there is the exe itself, not
a Python interpreter. So `server/browser.py` detects `sys.frozen` and
instead reruns the *same* exe with `--webview-window <role> <url>`, which
`run.py`'s `main()` intercepts before touching any normal server-startup
argument parsing and dispatches straight to
`server.webview_launcher.main()`. This only ever happens in a frozen
build -- running from source always takes the `-m` path.

## Using the overlay during a race

The overlay runs in a **pywebview** window (`server/webview_launcher.py`,
launched as its own subprocess by `server/browser.py`), not a plain browser
tab — this is what makes real transparency and a frameless window possible
at all. Plain Chrome/Edge `--app=` windows (what this used to be) can't do
either: Chrome doesn't expose true per-pixel window transparency to an
ordinary page, and it draws its own minimal window chrome as custom UI that
ignores the OS's title-bar style regardless of what you do to the
underlying window — both were tried and both hit that wall before switching.
pywebview wraps Windows' WebView2 engine and exposes `frameless=True` as a
real window property. `transparent=True` alone turned out *not* to be
enough, though: reading pywebview's own Windows backend
(`webview/platforms/edgechromium.py`) shows it only makes the WebView2
*control* transparent relative to its parent window — the parent window
itself is never made transparent to the desktop, so you'd still see that
plain window's own background color through the "transparent" page instead
of the game. `server/webview_launcher.py` applies real desktop transparency
itself on top of that, via the Win32 layered-window API
(`WS_EX_LAYERED` + `SetLayeredWindowAttributes`) — the same mechanism every
other translucent-overlay tool uses. `WINDOW_ALPHA` in that file (0–255,
currently 235 ≈ 92% opaque) is the one knob that controls how see-through
it is; lower it for more transparency. Because that's applied uniformly to
the whole window, `overlay.css`'s `#hud` background is now fully solid
(`var(--surface-1)`, no CSS alpha) rather than semi-transparent — stacking
a see-through CSS panel on top of an already-transparent window just made
the text harder to read for no benefit, since the desktop-transparency
effect now comes entirely from the window level.

By default, starting the server also opens this overlay window a couple
seconds after startup, so you don't have to launch it yourself each time.
Disable this with `--no-open-overlay` if you'd rather open it manually or
it's already open in a window you want to keep. If you close it mid-session,
`POST /api/open-overlay` relaunches it without restarting the server (same
launch logic run.py uses at startup) — there's currently no page with a
button wired to that endpoint, so hit it directly (e.g. `curl -X POST
http://127.0.0.1:8734/api/open-overlay`) until/unless a settings-style page
exists to host a button for it.

The window is genuinely frameless — there's no title bar, drag strip, or
close button. Move it by clicking and dragging anywhere on the HUD itself
(pywebview's `easy_drag`), and close it with **Alt+F4** or via the taskbar.
It's also always-on-top and starts at 440×420, then **resizes itself to fit
its actual content** (`overlay.js`'s `fitWindowToContent()`, called after
every update) since the HUD's real height varies depending on what's
showing (the relative panel, the Quali fuel row, etc.) — a single fixed
size would always be too big for some states and too small for others. This goes through pywebview's own resize mechanism (a small
`js_api` bridge: the page calls `window.pywebview.api.resize(w, h)`, which
`server/webview_launcher.py`'s `_Api.resize()` forwards to
`Window.resize()`) rather than the page-level `window.resizeTo()` used
before switching to pywebview, since `resizeTo()` isn't meaningful for a
pywebview-hosted window the way it is for a real browser tab. Falls back to
`resizeTo()` only if `window.pywebview` isn't present at all (e.g. opening
`overlay.html` directly in a normal browser tab for debugging). You can
also manually zoom the whole HUD bigger/smaller by dragging its corner --
see [Resizing the overlay](#resizing-the-overlay) below.

If you ever see `[pywebview] Error while processing
window.native.AccessibilityObject...` (or `...DataBindings.Control...`)
spamming the console with a huge dotted chain ending in "maximum recursion
depth exceeded" — that was a real bug here, now fixed, not a pywebview
quirk to just tolerate. pywebview builds the `window.pywebview.api` bridge
by walking every public attribute of the `js_api` object and recursing into
non-callable ones (`webview/util.py`'s `get_functions()`). `_Api` used to
store the real `webview.Window` as a plain `self.window` attribute, so that
walk followed it into `.native` (the raw .NET WinForms object) and from
there into cyclic .NET properties like `SyncRoot`. Pythonnet hands back a
fresh wrapper object on every `.NET` attribute access, so pywebview's
`id()`-based cycle detector never caught the repeat — it recursed until
Python's stack limit before a blanket `except Exception` swallowed it.
Fixed by renaming the attribute to `_window` (leading underscore), which
pywebview's walker skips outright.

pywebview still can't do OS-level *click-through* — clicking where the HUD
is will hit the HUD, not the game underneath, since nothing in this stack
targets that. The practical setup for using it during a race:

1. Run iRacing in **borderless windowed** mode (not exclusive fullscreen),
   or run it on one monitor and the overlay on a second monitor.
2. Drag the window (click anywhere on the HUD) to a corner that doesn't
   cover the in-game HUD. It's already always-on-top, so no extra tooling
   (like PowerToys) is needed for that part anymore.

It reconnects automatically if iRacing (or the server) restarts mid-session.

## Resizing the overlay

Drag the small corner glyph at the bottom-right of the HUD (`#resize-grip`)
to zoom the whole overlay up or down — text, gauges, spacing, all of it,
uniformly. Frameless windows get **no OS-native resize border at all**
(confirmed against pywebview's actual Windows backend: `FormBorderStyle` is
forced to `None` whenever a window is frameless, regardless of the
`resizable` option, which only affects non-frameless windows), so this grip
and its own drag-tracking exist specifically to work around that.

Mechanically: dragging applies a CSS `transform: scale()` to `#hud`
(`overlay.js`'s `applyScale()`), anchored `transform-origin: top left` so
the window's top-left position never moves during a resize -- only the
bottom-right edge does, matching `Window.resize()`'s default resize anchor
(`FixPoint.NORTH | FixPoint.WEST`). The grip's own `mousedown` handler calls
`event.stopPropagation()` so pywebview's `easy_drag` (which treats any
click-drag anywhere on the page as a window *move*) doesn't also fire for
the same click -- without that, grabbing the grip would drag the window
around instead of resizing it.

The zoom factor is clamped to 60%-200% (`MIN_SCALE`/`MAX_SCALE` in
`overlay.js`) and lives only in memory for the current window -- it resets
to 100% on the next launch, it isn't saved to
[Settings](#settings)/`settings.json`. `fitWindowToContent()` (the
existing logic that auto-resizes the window to fit whatever's currently
shown) was made scale-aware so it cooperates with a manual zoom rather than
fighting it: it multiplies `#hud`'s own natural (unscaled) size by the
current zoom before asking pywebview to resize the window, every tick, so
toggling a setting or the HUD's content changing height still resizes the
window correctly *at whatever zoom level you've chosen*, instead of
snapping back to 100%.

One non-obvious pitfall this hit during development, worth flagging in
case it comes up again: `document.body.scrollWidth` (used everywhere else
for measuring "how big does the window need to be") is **not**
scale-invariant -- once a `transform: scale()` is applied anywhere in the
page, `body.scrollWidth` starts reflecting the *visually transformed* size
of its descendants, not their pre-transform layout size (confirmed live
against the real WebView2 engine: at `scale(1.3)` on a 400px-wide HUD,
`body.scrollWidth` read `520`, not `400`). Multiplying that by the current
scale again would silently double-apply it. `#hud.offsetWidth`/`offsetHeight`
(an element's own layout size, which transforms never affect) don't have
this problem, which is why `fitWindowToContent()` and the drag handler both
measure `#hud` directly rather than `document.body`.

## Qualifying baseline (feeds the overlay's Quali fuel row)

The live fuel/lap-time trackers already used by the overlay are watched for
a session change (`core/session_baseline.py`'s `SessionTransitionTracker`,
driven by iRacing's own `SessionNum`), and the moment a qualifying-type
session (`SessionType` containing "Qualify" — covers "Lone Qualify" and
"Open Qualify") ends, its fuel/lap-time data is snapshotted as a baseline.
The fuel side is deliberately the **worst-case (max) single-lap usage**
seen during that session, not a rolling average — a fuel plan built on an
average would come up short on exactly the lap(s) that used more than
that. That baseline is pushed straight into the websocket snapshot as
`qualifying_baseline` and drives the overlay's **Quali fuel** row directly
— no manual step, no separate page. `GET /api/qualifying-baseline` also
exists standalone if something else ever wants to read it.

This is in-memory only for the current server run, not written to disk —
restarting the server between qualifying and the race loses it, same as any
other live tracker state. Any session change (not just qualifying → race)
also resets the live fuel/tire rolling averages, so a practice/qualifying
session's laps never get silently blended into the race's own numbers.

`--demo` exercises this without a real session: the synthetic source starts
in a scripted "Lone Qualify" session for the first 6 (simulated) laps, then
transitions to "Race" with a fresh lap count, full tank, and new tires —
watch the overlay's **Quali fuel** row appear a few seconds after startup.

The overlay's four fuel-rate boxes are **Last lap, Max fuel, 5-lap avg,
Quali fuel** (in that order — Quali sits right beneath 5-lap avg, only
shown once a baseline exists), each with five figures next to it under a
small **Laps left / Stint / Finish / Run out / Final pit** header:

- **Laps left** — `current fuel level ÷ that rate`: how many laps you'd get
  out of what's currently in the tank if you kept running at that pace.
- **Stint** — `stint start fuel level ÷ that rate`: how many laps the fuel
  you actually left the pits with will get you. Unlike Laps left, this
  doesn't shrink as you drive — the fuel amount is captured once, at the
  start of the current stint, and held fixed until your next stop, so it
  reads as a stable "this stint is an N-lap stint" reference rather than a
  countdown. Tracked server-side (`core/fuel.py`'s
  `FuelTracker._stint_start_fuel_level`, sent as
  `fuel.stint_start_fuel_level`), snapshotted the moment a refuel is
  detected — the same fuel-went-up signal already used to reject refuel
  outliers from the rolling average, reused here as "a new stint just
  started."
- **Finish** — `current fuel level − (leader-pace laps remaining × that
  rate)`: the fuel surplus or deficit at the end of the race *if you kept
  running at that specific rate the rest of the way*, shown as a solid
  rounded pill — green (`+4.1`, you'd make it) or red (`−3.2`, you
  wouldn't), black text on the fill so it reads at a glance. Computed
  per-rate, client-side, so all four boxes get their own independent
  answer instead of one box speaking for all of them.
- **Run out** — see [Run-out laps](#run-out-laps) below.
- **Final pit** — see [Final-window indicator](#final-window-indicator) below.

The "laps remaining" behind every Finish figure comes from the **race
leader's** average lap time (`core/leader_pace.py`'s `LeaderPaceTracker`, a
rolling average of whichever car is currently in P1's last-lap-time
readings — it just keeps averaging through a position change at the front
rather than resetting), not the player's own pace or iRacing's
`SessionLapsRemainEx`. That matters specifically for time-certain races:
the checkered flag falls when the *leader* completes the lap during which
the session clock expires, not when you do, so your own pace (especially
mid-pit-stop or stuck in traffic) is a biased proxy for how many laps are
actually left. This is a deliberately separate calculation from the
`laps_remaining_in_race` used elsewhere (the live pit-window color-coding)
— swapping the leader's pace into that shared value would also change
already-verified pit-window behavior, which is a bigger change than this
feature needed; the server just also sends `laps_remaining_leader_pace`
once per tick and the overlay does the per-rate subtraction itself rather
than the server repeating the same math four times over the wire.

The HUD is 400px wide, sized to fit five columns (label, Laps left, Stint,
Finish, Run out) per fuel-rate row without crowding.

## Run-out laps

The 5th column on each fuel-rate row, **Run out**, shows the **next two lap
numbers you'd run dry at that rate**, as a compact `11-24`-style string. The
first number uses whatever's actually in the tank right now (same math as
the "Laps left" column); the second assumes a full refill in between, one
full tank's worth of laps later (same math as "Stint") — so a
higher-consumption rate shows earlier, closer-together numbers than a
lower-consumption one. This is a forward projection from the current lap,
computed client-side in `overlay.js`'s `runoutLapsText()`/`applyRunout()`
from data the websocket already sends every tick.

Originally a separate stacked list next to the pit-window list, and a
3-lap projection; folded into this per-row column (aligned directly with
each rate it belongs to) and trimmed to 2 laps once the pit-window list was
removed.

## Fuel targets

Below the fuel-rate rows/gauge, a row of three cells shows the **inverse**
of the run-out figures above: instead of "at rate X, how many laps," it's
"to hit N laps in this stint, what rate do I need." The leftmost cell is
the whole lap count closest to what your current pace (the 5-lap avg,
same basis the fuel gauge's own number uses) would already get you; the
next two cells are one lap further each, showing the progressively
stricter L/lap you'd need to average from here to stretch the stint that
extra lap or two. All three use `current_fuel_level ÷ target_laps`,
computed client-side in `overlay.js`'s `renderFuelTargets()`, driven
entirely by the live fuel gauge's own numbers.

## Final-window indicator

A 6th column, **Final pit** (rightmost, after Run out), holds a red/green dot
for each fuel-rate row (Last lap, Max fuel, 5-lap avg, Quali fuel). It's
**red** normally and flips to **solid green** when **pitting right now and
filling to a full tank would be enough fuel to finish the race at that
row's rate** — i.e. this could be your last stop. Both colors are
full-opacity and the dot is 11px, specifically so it's unmissable at a
glance -- two earlier versions (fully transparent when "off," then a dim
35%-opacity gray) both turned out too subtle to actually notice while
racing. It also used to be a plain dot with no label at all, appended
directly after the row's name (e.g. "Last lap ●") -- promoted to a proper
labeled column, matching every other per-rate figure on the HUD, once it
became clear a bare unlabeled dot didn't communicate what it meant.
Answers a different question than the Finish column: Finish asks "would my
*current* fuel get me to the end without stopping again," this asks "if I
*do* stop once more, is a full tank enough to make it the final one."

Math (`overlay.js`'s `isFinalWindowOpen()`): `tank_capacity >=
laps_remaining_leader_pace × rate`. Deliberately does **not** factor in
`current_fuel_level` — at a stop you can always fill to `tank_capacity`
regardless of what's currently in the tank, so the ceiling on how much fuel
the car could carry after that stop is `tank_capacity` itself, not
`tank_capacity` plus whatever's left now. `current_fuel_level` would only
matter for computing how much to *add*, which this indicator doesn't show
(it's a yes/no light, not an amount). Both `tank_capacity` and
`current_fuel_level` are the same already-verified fields (`FuelTracker`'s
effective, post-fuel-limit-override capacity and the live `FuelLevel`
reading) every other column on this HUD already uses — no new backend
calculation needed for this feature. `laps_remaining_leader_pace` is the
same leader-pace-based estimate the Finish column uses (see
[Qualifying baseline](#qualifying-baseline-feeds-the-overlays-quali-fuel-row)
above for why leader pace, not your own).

Toggled by the **Final-window indicator** checkbox in
[Settings](#settings) (on by default) — turning it off hides all four dots
at once, it's not per-row.

## Settings

A second window (`http://127.0.0.1:8734/settings`, normal windowed chrome —
not frameless/transparent like the overlay) lets you toggle which pieces of
the overlay are shown, without editing any code:

- **Fuel calculations (rows)** — Last lap, Max fuel, 5-lap avg, Quali fuel.
  Turn off whichever rates you don't look at.
- **Fuel figures (columns)** — Laps left, Stint, Finish, Run out, and Final pit
  (the [final-window indicator](#final-window-indicator) dots). Applies
  across all visible rows at once (e.g. hide "Run out" everywhere but keep
  "Finish").
- **Other panels** — the fuel meter (gauge), target laps (the fuel-targets
  row), tire values, and the ahead/behind relative-deltas panel.
- **Auto pit fuel** — see [Auto pit fuel](#auto-pit-fuel) below.
- **Units** — Liters or Gallons (US), applied to every fuel *volume* figure
  on the overlay (rates, tank size, the Finish column's margin, fuel
  targets). Display-only — everything server-side (`core/fuel.py`'s
  tracking math, the SDK pit-fuel request) always stays in liters
  regardless of this setting; `overlay.js`'s `toDisplayVolume()` converts
  at render time (1 US gal = 3.785411784 L). Laps-based figures (Laps left,
  Stint, Run out, Final pit) never change with this setting — they're
  ratios of volume ÷ rate, and both sides convert the same way, so the lap
  count comes out identical either unit.

Changes save immediately (`POST /api/settings`, persisted to
`%APPDATA%\PitStrategy\settings.json` so they survive restarts) and apply
**live** to any already-open overlay window over the same websocket that
pushes fuel/tire data — no reload, no restart. This works because
`/ws/live` includes the current settings in every pushed frame (not just
once on page load), and `overlay.js`'s `applySettings()` runs at the top of
every `render()` call, hiding/showing elements without touching whether
their values keep getting computed underneath (so flipping something back
on shows current data immediately, not a stale frame).

Hiding a fuel-figures column collapses its grid track to zero width
(`overlay.js`'s `applyColumnVisibility()`) rather than leaving a blank gap
where it used to be — the remaining columns re-flow to fill the space.

Both windows open automatically on startup (see
[Running](#running)/[Building a standalone executable](#building-a-standalone-executable)
above); `POST /api/open-settings` reopens the settings window on demand if
you close it mid-session, the same way `POST /api/open-overlay` already
worked for the overlay.

## Auto pit fuel

Optionally sends iRacing's SDK pit-service fuel request (the same mechanism
the in-car pit menu uses, via `irsdk`'s `pit_command(irsdk.PitCommandMode.fuel, ...)`
— not a chat command) the moment `server/engine.py`'s `StrategyEngine`
detects your car's `CarIdxOnPitRoad` flag go from off to on. **Off by
default** — this actually submits a real request to the sim, not just a
display feature, so it only fires if you turn it on in Settings and pick a
source:

- **Auto-add on pit entry** (checkbox, default off) — turns the feature
  on/off, persisted the same way as every other setting
  (`%APPDATA%\PitStrategy\settings.json`).
- **Use** (dropdown) — which of the four "Fuel calculations (rows)" figures
  (Last lap, Max fuel, 5-lap avg, Quali fuel) to size the request from.
  Options are drawn live from whichever of those rows are currently checked
  on above (`settings.js`'s `syncAutoFuelSourceOptions()`) — unchecking a
  row removes it from the dropdown, and if it was the selected source, the
  selection is cleared (and that clear is saved, not just displayed) so
  auto-fuel never keeps quietly pointing at a hidden calculation.

The amount requested isn't the rate itself — it's *fuel needed to finish
the race at that rate, minus what's already in the tank* (the same math
behind the "Finish" column, solved for "how much more to add" instead of
"what's the margin"), clamped so it never asks for more than the tank can
physically hold. Fires once per pit-road entry (edge-triggered, not held
down), so leaving pit road and coming back around fires it again — freshly
recomputed against however many laps are left at that point. If the
selected source has no rate yet (e.g. "Quali fuel" picked before qualifying
ends) or there's no leader-pace/tank-capacity data yet, it skips and logs
why instead of sending a nonsense amount.

You still need to actually drive into your pit stall for iRacing to apply
the request — this just pre-fills the amount the moment you're on pit road,
the same as if you'd set it on the in-car pit menu yourself. The overlay's
footer shows a brief `Pit fuel: NL (source) sent` (or `FAILED`, if the SDK
call raised) line after each request, driven by `last_fuel_command` in the
websocket payload.

`--demo` mode simulates the player's own car briefly reporting as on pit
road every 12 laps (the same synthetic pit-stop cadence that already resets
demo fuel/tires), so this is exercisable without a real iRacing session —
see `core/irsdk_client.py`'s `DemoTelemetrySource._player_pit_road_until`.

## No more pit-window status bar

The old bottom bar ("Pit window open" / "Too early to pit" / "Pit now —
overdue" / etc., plus the whole-HUD border color it drove) has been
removed entirely — `WINDOW_STATUS_TEXT`, `WINDOW_STATE_TO_HUD_BORDER`,
`renderWindowStatusBar()`, and `setWindowState()` are all gone from
`overlay.js`, along with `#window-status-bar` from `overlay.html` and its
CSS. It had become redundant with the more precise per-rate info already on
the HUD (Laps left/Stint/Finish/Run out/Final pit say more than a single "too early /
open / overdue" label ever could) and the user found its own most
memorable state — "TOO EARLY TO PIT" — actively annoying.
`server/engine.py` still computes the same `strategy` field every tick
(cheap, and something else could use it later), it's just no longer
consumed by the frontend at all.

## What it calculates

- **Fuel**: rolling average liters/lap (last 5 laps, refuels are detected
  and excluded from the average), laps remaining on current fuel.
- **Tires**: which corner/tread (e.g. `RR-L`) is wearing worst, its wear
  remaining, and its last carcass temperature reading — shown instead of a
  "laps remaining on tires" estimate, since that rolling-average number is
  noisy until you've completed at least one real stint (it settles down
  after your first pit stop, once wear has been tracked over consecutive
  green-flag laps without a tire change in the middle). The live pit-window
  calculation still uses the wear-rate estimate internally as one of its
  inputs — only the standalone "laps left on tires" *display* was removed.
- **Live pit window**: whichever of fuel/tires runs out first determines
  "must pit by lap N" (`core/pit_planner.py`'s `compute_live_strategy()`);
  computed every tick but not currently shown on the overlay itself (see
  [No more pit-window status bar](#no-more-pit-window-status-bar) above) —
  the Laps left/Stint/Finish/Run out/Final pit columns are the HUD's actual live
  pit-window signal now.
- **Relative (undercut/overcut panel)**: the 3 cars immediately ahead and
  behind you by race position, each showing their last lap time and the
  delta to *your* last lap (green = they're slower than you, red = they're
  faster), plus a `PIT` tag once a car has made its first stop of the
  session. Deliberately just raw numbers — it doesn't tell you whether to
  undercut, that's still your call. `has_pitted` is sticky (set the first
  time a car is seen on pit road, never cleared), so it only tells you
  *whether* they've stopped at all, not which/how many stops if the race
  needs more than one.

Tank capacity for the live overlay is read automatically from iRacing's
session info (`DriverCarFuelMaxLtr`).

## Known caveats

The relative panel's SDK field names (`CarIdxPosition`, `CarIdxLastLapTime`,
`CarIdxOnPitRoad`, `PlayerCarIdx`) are standard iRacing telemetry channels
used by most third-party overlays, but haven't been checked against a real,
running iRacing session, only against the demo source and unit tests. If the
panel stays empty with a real connection, check those exact var names first.

Same caveat for the tire temp channels (`LFtempCL/CM/CR` etc., "carcass"
temperature) used by the "Tire temp" tile — the channel name pattern is
standard, but neither it nor its unit (presumed °C, matching iRacing's
convention of always reporting raw telemetry in metric regardless of your
in-game display setting) has been confirmed against a live session. The
overlay deliberately shows a bare `°` rather than assuming C or F until
that's checked.

## Tests

```
python -m pytest tests/
```

Covers the fuel/tire rolling-average math and the live pit-window
calculations directly — no iRacing connection needed.

## Project layout

- `core/fuel.py`, `core/tires.py` — rolling-average trackers
- `core/relative.py` — nearest-3-ahead/behind ranking + pit-status tracking for the relative panel
- `core/session_baseline.py` — detects a qualifying-type session ending, feeds the overlay's Quali fuel row
- `core/leader_pace.py` — rolling average of the race leader's lap times, for the leader-pace fuel-to-finish margin
- `core/pit_planner.py` — live pit-window logic (`compute_live_strategy()`)
- `core/irsdk_client.py` — pyirsdk live telemetry source + synthetic demo source
- `server/engine.py` — ties a telemetry source to the trackers, produces one
  JSON snapshot per tick
- `server/settings_store.py` — `OverlaySettings` (pydantic model, doubles as
  the JSON schema persisted to `%APPDATA%\PitStrategy\settings.json`),
  `load_settings()`/`save_settings()`
- `server/app.py` — FastAPI app: `/overlay`, `/settings`, `/ws/live`,
  `/api/fuel-limit`, `/api/qualifying-baseline`, `/api/settings`,
  `/api/open-overlay`, `/api/open-settings`
- `server/browser.py` / `server/webview_launcher.py` — launches the overlay
  (frameless/transparent) and settings (normal windowed) pywebview windows,
  each as its own subprocess
- `server/static/` — overlay and settings HTML/CSS/JS
- `pitstrategy.spec` — PyInstaller build spec for the standalone `.exe` (see
  [Building a standalone executable](#building-a-standalone-executable))
