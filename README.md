# PitStrategy

PitStrategy is a free tool for [iRacing](https://www.iracing.com/) that watches
your race live and shows you a small on-screen readout of your fuel and tires,
so you always know how many laps you have left, when you need to pit, and how
much fuel to put in.

It runs as a small floating window on top of iRacing (not inside the game
itself), and works alongside a separate settings window where you can turn
pieces of it on or off.

![Windows only](https://img.shields.io/badge/platform-Windows-blue)

## What it does

- **Fuel readout** — shows how many laps of fuel you have left, calculated a
  few different ways (your last lap, your worst lap, your recent average, and
  your qualifying pace), so you can see which one you trust most.
- **"Will I make it to the end?"** — a green/red indicator on each fuel
  calculation showing whether you'd finish the race without pitting again at
  that pace.
- **Auto-fill fuel** — optionally, the moment you pull into your pit stall it
  automatically dials in exactly enough fuel to finish the race, with an
  adjustable safety cushion, so you don't have to do the math or use the
  in-car menu yourself.
- **Tire wear** — shows which tire is wearing out fastest and by how much.
- **Who's around you** — lap-time comparisons for the cars just ahead of and
  behind you, so you can see if they're gaining or losing time on you.
- **A demo mode** — try the whole thing out with fake race data, without
  needing iRacing open at all.

## Before you start

- **Windows 10 or 11.** This is a Windows-only tool.
- **iRacing** installed (to use it live — you don't need iRacing open just to
  try the demo).
- That's it — you don't need to know how to code. Everything below is just
  downloading a folder and double-clicking a file.

## Getting it

1. Go to the
   [Releases page](https://github.com/mrzepka/PitStrategy/releases/latest)
   and download `PitStrategy-win64.zip`.
2. Right-click the downloaded zip and choose **Extract All...**, then pick a
   folder to put it in (anywhere is fine — your Desktop or Documents both
   work).
3. Open the folder you extracted it to and double-click **`PitStrategy.exe`**.

That's the whole install. There's no installer to run and nothing gets added
to your Start menu — it's just a program folder you can move or delete
whenever you like.

> **Windows might warn you before it opens.** Since this is a small
> independent project, the app isn't digitally signed, so Windows may show a
> blue "Windows protected your PC" screen the first time you run it. Click
> **More info**, then **Run anyway**. This is normal for small open-source
> tools and only happens once.

## Running it

Double-click **`PitStrategy.exe`**. A black console/terminal window will pop
up first — that's expected, leave it open (it's just there to show error
messages if something goes wrong; it doesn't need any input from you). A
couple of seconds later, two more windows will appear:

- The **overlay** — the small live fuel/tire readout meant to sit on top of
  iRacing while you drive.
- The **settings** window — where you turn parts of the overlay on or off.

If iRacing is already running, the overlay connects to it automatically —
there's nothing to configure. If iRacing isn't running yet, the overlay will
just wait, showing dashes until it is.

### Trying it without iRacing (demo mode)

Want to see it in action before you've even got iRacing installed, or just
try it out at your desk? Double-click **`PitStrategy-Demo.exe`** in the same
folder instead of `PitStrategy.exe`.

Everything will behave the same as a real race, just with fake fuel numbers
counting down and fake lap times, so you can click through the settings and
see how it all looks.

## Using it while you race

- **Move it:** click and hold anywhere on the overlay, then drag it wherever
  you want.
- **Resize it:** click and drag the small handle in its bottom-right corner
  to make everything on it bigger or smaller.
- **It doesn't block your clicks to iRacing underneath it** — so put it
  somewhere that isn't covering anything you need to see or click in-game,
  like an empty corner of the screen.
- **Run iRacing in "Borderless Windowed" mode** (in iRacing's video settings)
  rather than full-screen, or put the overlay on a second monitor if you have
  one — this makes sure it actually shows up on top of the game.
- If iRacing or the app restarts mid-session, the overlay reconnects on its
  own — you don't need to relaunch anything.
- **To close everything:** close the overlay window (there's no close button
  on it since it's a bare floating panel — press **Alt+F4** while it's the
  active window, or right-click it in the taskbar and choose Close), then
  close the black console window too.

## Reading the fuel panel

The fuel panel shows up to four rows, each a different way of estimating how
much fuel you're using per lap:

- **Last lap** — based on just your most recent lap.
- **Max fuel** — based on the single thirstiest lap you've driven all
  session. The most cautious/safe number to plan around.
- **5-lap avg** — your average fuel use over the last 5 laps. Smooths out one
  unusually good or bad lap.
- **Quali fuel** — based on your worst lap during qualifying. Only appears
  once qualifying has ended.

Next to each row, several columns tell you what that pace means in practice:

| Column | What it tells you |
|---|---|
| **Laps left** | How many more laps you could drive right now, at this pace, before running dry. Counts down as you drive. |
| **Stint** | How many laps the fuel you *left the pits with* is good for. Unlike "Laps left," this stays fixed for the whole stint — it's a "this pit stop bought me an N-lap stint" reference, not a countdown. |
| **Finish** | A green or red pill showing whether you'd have enough fuel to reach the end of the race without pitting again, at this pace — green means yes (with how much fuel to spare), red means no (with how much you'd be short). |
| **Run out** | The next two lap numbers you'd run out of fuel at this pace, assuming you top up fully each time you'd otherwise run dry. |
| **Final pit** | A dot that turns **green** when pitting right now and filling to a full tank would be enough fuel to finish the race at this pace — in other words, "this could be your last stop." |

## Tires

Shows which tire is wearing out the fastest, how much life it has left, and
its most recent temperature reading, so you know whether tire wear is going
to force a pit stop before fuel does.

## Who's around you

A small panel listing the three cars closest to you in front and the three
closest behind, each with their most recent lap time and how it compares to
yours (green = they're currently slower than you, red = they're currently
faster). Cars that have already made a pit stop this race are marked, so you
can spot who's still on an early strategy.

## Settings window

A separate window lets you customize what shows up on the overlay. Changes
apply instantly — no restart needed.

- **Fuel calculations (rows)** — turn off whichever of the four fuel-rate
  rows (Last lap / Max fuel / 5-lap avg / Quali fuel) you don't want to see.
- **Fuel figures (columns)** — turn off whichever columns (Laps left, Stint,
  Finish, Run out, Final pit) you don't need.
- **Other panels** — show or hide the fuel gauge, the tire panel, and the
  "who's around you" panel.
- **Units** — switch every fuel amount on the overlay between **Liters** and
  **Gallons**.
- **Auto pit fuel** — see below.

Your settings are remembered automatically between races — you only need to
set them up once.

## Auto pit fuel

This feature can automatically dial in the right amount of fuel the instant
you pull into your pit stall, so you don't have to work it out yourself or
use iRacing's in-car pit menu. **It's off by default**, since it's actually
requesting real fuel from the sim, not just showing you a number.

To turn it on, open the **Settings** window and, under **Auto pit fuel**:

1. Check **Auto-add on pit entry**.
2. Use the **Use** dropdown to pick which fuel row (Last lap / Max fuel /
   5-lap avg / Quali fuel) it should base the calculation on. Only rows
   you've left switched on above are selectable.
3. Optionally, set a **Buffer** — extra laps' worth of fuel to add on top of
   the exact amount needed to finish, as a safety cushion in case your actual
   pace ends up a little thirstier than expected. Adjust it up or down in
   tenths of a lap (e.g. `+0.3`, `+1.0`) using the small arrows on the field,
   or type a value directly. A buffer of `0` (the default) adds exactly
   enough to finish and nothing more; a negative buffer intentionally
   requests slightly less than that if you'd rather run lighter.

Once it's on, every time you enter pit road it works out "how much fuel do I
need to finish the race at my chosen pace, plus my buffer, minus what's
already in the tank" and sends that request automatically. You still need to
actually drive into your pit stall for iRacing to apply it — this just
pre-fills the number for you, the same as if you'd dialed it in yourself. A
short status line at the bottom of the overlay confirms what was requested
each time (or tells you if it failed).

## Troubleshooting

**The app won't open at all, or closes immediately.**
Install the [Microsoft Edge WebView2 runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) —
it comes preinstalled on most current Windows 10/11 machines, but a very small
number of systems are missing it. This is what the overlay/settings windows
are built with.

**Windows shows a blue "Windows protected your PC" screen.**
Expected for an unsigned indie tool — click **More info**, then **Run
anyway**. See [Getting it](#getting-it) above.

**The overlay or settings window never shows up.**
Give it a few seconds after double-clicking — they open shortly after the
console window appears, not instantly. If nothing shows up after ~10
seconds, check the console window for red error text.

**Everything shows dashes ("–") instead of numbers.**
This means it isn't connected to a live iRacing session yet — either iRacing
isn't running, or you're still in the main menu rather than actually out on
track. It updates automatically the moment you're in a session.

**The overlay is covering something in iRacing I need to see.**
Click and drag it to a different part of the screen — see
[Using it while you race](#using-it-while-you-race). Switching iRacing to
Borderless Windowed mode (instead of full-screen) also helps, or use a
second monitor.

**I can't find a way to close the overlay window.**
It's a bare panel with no title bar or close button on purpose. Click on it
once to make it the active window, then press **Alt+F4**, or right-click its
icon in the taskbar and choose **Close**.

---

## For developers

The section above is everything most people need. If you'd rather run this
from source (to get unreleased changes, poke at the code, or build it
yourself) instead of the prebuilt download:

**Run it from source** (needs Python 3.11+):

```
pip install -r requirements.txt
python run.py            # connects to a live iRacing session
python run.py --demo     # or, with synthetic practice data instead
```

`run.py` opens the overlay and settings windows for you automatically, same
as the built exe. Both are also reachable directly at
`http://127.0.0.1:8734/overlay` and `http://127.0.0.1:8734/settings` if you
ever need them without the auto-launch (`--no-open-overlay` /
`--no-open-settings`).

**Build the standalone .exe yourself:**

```
pip install -r requirements-build.txt
pyinstaller pitstrategy.spec --noconfirm
```

Produces `dist/PitStrategy/` — the same folder the Releases zip contains,
including both `PitStrategy.exe` and `PitStrategy-Demo.exe` (a tiny separate
launcher that just starts `PitStrategy.exe --demo` — see
`run_demo_launcher.py`).

**Run the tests** (no iRacing connection needed — covers the fuel/tire math
and live pit-window calculations):

```
python -m pytest tests/
```

**Project layout:**

- `core/fuel.py`, `core/tires.py` — rolling-average fuel/tire trackers
- `core/relative.py` — the "who's around you" panel's ranking logic
- `core/session_baseline.py` — detects qualifying ending, feeds the Quali
  fuel row
- `core/leader_pace.py` — tracks the race leader's pace for "laps remaining"
  estimates
- `core/pit_planner.py` — live pit-window calculation
- `core/irsdk_client.py` — live iRacing telemetry + the synthetic demo source
- `server/engine.py` — ties telemetry to the trackers, produces one snapshot
  per tick, and drives auto pit fuel
- `server/settings_store.py` — settings model, persisted to
  `%APPDATA%\PitStrategy\settings.json`
- `server/app.py` — the web server (`/overlay`, `/settings`, live data feed,
  and the settings/fuel-limit API)
- `server/browser.py` / `server/webview_launcher.py` — opens the overlay and
  settings windows
- `server/static/` — the overlay and settings pages themselves
- `run_demo_launcher.py` — the tiny standalone entry point behind
  `PitStrategy-Demo.exe`
- `pitstrategy.spec` — the PyInstaller build spec for both standalone `.exe`s

Releases are cut manually — build from `pitstrategy.spec`, zip
`dist/PitStrategy/`, tag, and publish to GitHub Releases.
