const qualiFuel = document.getElementById("quali-fuel");
const qualiFuelBox = document.getElementById("quali-fuel-box");
const qualiFuelLaps = document.getElementById("quali-fuel-laps");
const qualiFuelStint = document.getElementById("quali-fuel-stint");
const qualiFuelFinish = document.getElementById("quali-fuel-finish");
const qualiFuelRunout = document.getElementById("quali-fuel-runout");
const lastLapBox = document.getElementById("last-lap-box");
const lastLapFuel = document.getElementById("last-lap-fuel");
const lastLapFuelLaps = document.getElementById("last-lap-fuel-laps");
const lastLapFuelStint = document.getElementById("last-lap-fuel-stint");
const lastLapFuelFinish = document.getElementById("last-lap-fuel-finish");
const lastLapFuelRunout = document.getElementById("last-lap-fuel-runout");
const maxFuelBox = document.getElementById("max-fuel-box");
const avgFuelBox = document.getElementById("avg-fuel-box");
const fuelPerLap = document.getElementById("fuel-per-lap");
const fuelPerLapLaps = document.getElementById("fuel-per-lap-laps");
const fuelPerLapStint = document.getElementById("fuel-per-lap-stint");
const fuelPerLapFinish = document.getElementById("fuel-per-lap-finish");
const fuelPerLapRunout = document.getElementById("fuel-per-lap-runout");
const fuelMax = document.getElementById("fuel-max");
const fuelMaxLaps = document.getElementById("fuel-max-laps");
const fuelMaxStint = document.getElementById("fuel-max-stint");
const fuelMaxFinish = document.getElementById("fuel-max-finish");
const fuelMaxRunout = document.getElementById("fuel-max-runout");
const fuelCap = document.getElementById("fuel-cap");
const fuelGaugeCol = document.getElementById("fuel-gauge-col");
const fuelGaugeZones = document.getElementById("fuel-gauge-zones");
const fuelGaugeMask = document.getElementById("fuel-gauge-mask");
const fuelGaugeLabel = document.getElementById("fuel-gauge-label");
const tireStats = document.getElementById("tire-stats");
const tireWorst = document.getElementById("tire-worst");
const tireTemp = document.getElementById("tire-temp");
const lapNum = document.getElementById("lap-num");
const connState = document.getElementById("conn-state");
const relativePanel = document.getElementById("relative-panel");
const fuelTargetRow = document.getElementById("fuel-target-row");
const relativeAhead = document.getElementById("relative-ahead");
const relativeBehind = document.getElementById("relative-behind");
const rateHeader = document.querySelector(".rate-header");
const statRows = document.querySelectorAll(".stat-row");

let lastFittedSize = null; // "widthxheight" of the last resize call, to skip redundant ones

// Shrinks/grows the window to exactly fit the HUD's actual content (the
// pit-window list, relative panel, etc. all change height as data arrives),
// instead of guessing one fixed size up front. Prefers pywebview's own
// resize API (window.pywebview.api.resize(), backed by
// server/webview_launcher.py's _Api.resize() -> Window.resize()) since
// that's the real overlay host now and a page-level window.resizeTo() call
// isn't meaningful for a pywebview window the way it is for a browser tab.
// Falls back to resizeTo() only for the case of opening this page directly
// in a normal browser tab (e.g. while debugging).
function fitWindowToContent() {
  try {
    const contentWidth = document.body.scrollWidth;
    const contentHeight = document.body.scrollHeight;

    if (window.pywebview && window.pywebview.api && window.pywebview.api.resize) {
      const key = `pywebview:${contentWidth}x${contentHeight}`;
      if (key === lastFittedSize) return;
      lastFittedSize = key;
      window.pywebview.api.resize(contentWidth, contentHeight);
      return;
    }

    if (typeof window.resizeTo === "function") {
      const chromeWidth = window.outerWidth - window.innerWidth;
      const chromeHeight = window.outerHeight - window.innerHeight;
      const targetWidth = contentWidth + chromeWidth;
      const targetHeight = contentHeight + chromeHeight;
      const key = `resizeTo:${targetWidth}x${targetHeight}`;
      if (key === lastFittedSize) return;
      lastFittedSize = key;
      window.resizeTo(targetWidth, targetHeight);
    }
  } catch (err) {
    // Best-effort only -- never let a resize failure break rendering.
  }
}

// Column order matches the fixed markup order in every .rate-header/
// .stat-row (label span, then these four) -- index i here is always that
// element's child index minus 1. Widths mirror overlay.css's own
// grid-template-columns so a hidden column collapses to zero width instead
// of leaving a blank gap.
const COLUMN_DEFS = [
  { key: "show_col_laps_left", width: "46px" },
  { key: "show_col_stint", width: "46px" },
  { key: "show_col_finish", width: "52px" },
  { key: "show_col_runout", width: "54px" },
];

function applyColumnVisibility(settings) {
  const widths = ["1fr"];
  COLUMN_DEFS.forEach((col, i) => {
    const visible = settings[col.key] !== false;
    if (visible) widths.push(col.width);
    const headerCell = rateHeader.children[i + 1];
    if (headerCell) headerCell.style.display = visible ? "" : "none";
    statRows.forEach((row) => {
      const cell = row.children[i + 1];
      if (cell) cell.style.display = visible ? "" : "none";
    });
  });
  const template = widths.join(" ");
  rateHeader.style.gridTemplateColumns = template;
  statRows.forEach((row) => { row.style.gridTemplateColumns = template; });
}

// Settings only ever hide/show whole elements -- the values underneath keep
// getting computed and written regardless, so toggling a setting back on
// shows current data immediately instead of a stale/blank frame. Applied
// unconditionally at the top of render() (both connected and disconnected),
// since hidden-by-choice panels should stay hidden either way.
function applySettings(settings) {
  const s = settings || {};
  lastLapBox.style.display = s.show_last_lap === false ? "none" : "";
  maxFuelBox.style.display = s.show_max_fuel === false ? "none" : "";
  avgFuelBox.style.display = s.show_avg_fuel === false ? "none" : "";
  fuelGaugeCol.style.display = s.show_fuel_gauge === false ? "none" : "";
  fuelTargetRow.style.display = s.show_fuel_targets === false ? "none" : "";
  tireStats.style.display = s.show_tires === false ? "none" : "";
  applyColumnVisibility(s);
}

function fmt(value, digits = 1, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  return value.toFixed(digits) + suffix;
}

function fmtLapTime(seconds) {
  if (seconds === null || seconds === undefined) return "–";
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(1).padStart(4, "0");
  return `${m}:${s}`;
}

// "If I kept running at this rate, how many laps could I do on what's in
// the tank right now" -- same math for every fuel-rate stat on the HUD,
// just fed a different rate each time (last lap, max, 5-lap avg, quali).
// Bare number -- the "Now" column header (overlay.html's .rate-header)
// supplies the unit, so it doesn't need to be repeated on every row.
function lapsLeftText(ratePerLap, currentFuelLevel) {
  if (!ratePerLap || ratePerLap <= 0 || currentFuelLevel === null || currentFuelLevel === undefined) return "–";
  return (currentFuelLevel / ratePerLap).toFixed(1);
}

// "If I ran a whole fresh stint at this rate, how many laps would a full
// tank last" -- same idea as lapsLeftText() but against tank capacity
// instead of whatever's currently in the tank, so it doesn't shrink lap to
// lap the way the "Now" column does.
function stintLengthText(ratePerLap, tankCapacity) {
  if (!ratePerLap || ratePerLap <= 0 || !tankCapacity || tankCapacity <= 0) return "–";
  return (tankCapacity / ratePerLap).toFixed(1);
}

// "If I ran the rest of the race at this rate, would what's in the tank be
// enough" -- current fuel minus (leader-pace laps remaining * this rate).
// Positive = surplus (green), negative = shortfall (red). Computed
// per-rate client-side since the server already sends
// laps_remaining_leader_pace once per tick; no reason to have it compute
// the same subtraction four times over the wire.
function applyFinishMargin(el, ratePerLap, currentFuelLevel, lapsRemainingLeaderPace) {
  el.classList.remove("finish-ok", "finish-critical");
  if (!ratePerLap || ratePerLap <= 0 || currentFuelLevel === null || currentFuelLevel === undefined || !lapsRemainingLeaderPace) {
    el.textContent = "–";
    return;
  }
  const margin = currentFuelLevel - lapsRemainingLeaderPace * ratePerLap;
  const sign = margin >= 0 ? "+" : "";
  el.textContent = `${sign}${margin.toFixed(1)}`;
  el.classList.add(margin >= 0 ? "finish-ok" : "finish-critical");
}

function fmtDelta(delta) {
  if (delta === null || delta === undefined) return "–";
  const sign = delta >= 0 ? "+" : "";
  return `${sign}${delta.toFixed(1)}`;
}

function renderRelativeGroup(container, cars) {
  container.innerHTML = "";
  for (const car of cars) {
    const row = document.createElement("div");
    row.className = "relative-row";
    const deltaClass = car.delta_to_my_last_lap === null || car.delta_to_my_last_lap === undefined
      ? ""
      : car.delta_to_my_last_lap > 0 ? "ok" : "bad";
    row.innerHTML = `
      <span class="rel-gap">${car.gap_positions > 0 ? "+" : ""}${car.gap_positions}</span>
      <span class="rel-car">#${car.car_number}</span>
      <span class="rel-laptime">${fmtLapTime(car.last_lap_time)}</span>
      <span class="rel-delta ${deltaClass}">${fmtDelta(car.delta_to_my_last_lap)}</span>
      <span class="rel-pit">${car.has_pitted ? "PIT" : ""}</span>
    `;
    container.appendChild(row);
  }
}

// "If I kept running at this rate, refueling to a full tank each time I hit
// empty, which lap would I be dry on -- two times running." First value
// uses whatever's actually in the tank right now (same math as the "Now"
// column); the second assumes a full refill (same math as "Stint"), just
// projected forward as a consecutive lap number instead of shown as a
// standalone figure. Deliberately a forward projection from the current
// lap -- not counted backward from the total laps remaining -- so it
// directly answers "which lap number do I need to watch for."
function runoutLapsText(ratePerLap, currentLap, currentFuelLevel, tankCapacity) {
  if (
    !ratePerLap || ratePerLap <= 0 ||
    currentLap === null || currentLap === undefined ||
    currentFuelLevel === null || currentFuelLevel === undefined ||
    !tankCapacity || tankCapacity <= 0
  ) {
    return null;
  }
  const stintLaps = Math.floor(tankCapacity / ratePerLap);
  if (stintLaps <= 0) return null;
  const first = currentLap + Math.floor(currentFuelLevel / ratePerLap);
  const second = first + stintLaps;
  return `${first}-${second}`;
}

function applyRunout(el, ratePerLap, currentLap, currentFuelLevel, tankCapacity) {
  el.textContent = runoutLapsText(ratePerLap, currentLap, currentFuelLevel, tankCapacity) ?? "–";
}

// "If I want to stretch this stint to exactly N laps, what fuel/lap do I
// need to hit" -- the inverse of the Laps left/Stint/Finish/Run-out figures
// above, which all go the other way (given a rate, how many laps). Anchors
// on the whole lap count closest to what current pace (the 5-lap avg,
// same basis the fuel gauge's own number uses) would already get you, then
// shows the two next-hardest stretch targets one lap further each.
function renderFuelTargets(fuel) {
  fuelTargetRow.innerHTML = "";
  const currentFuelLevel = fuel.current_fuel_level;
  const lapsAtCurrentPace = fuel.laps_remaining_on_fuel;
  if (
    currentFuelLevel === null || currentFuelLevel === undefined ||
    !lapsAtCurrentPace || lapsAtCurrentPace <= 0
  ) {
    return;
  }

  const nearestLap = Math.max(1, Math.round(lapsAtCurrentPace));
  for (let i = 0; i < 3; i++) {
    const targetLaps = nearestLap + i;
    const targetRate = currentFuelLevel / targetLaps;
    const cell = document.createElement("div");
    cell.className = "fuel-target-cell";
    cell.innerHTML = `
      <div class="fuel-target-lap">${targetLaps} laps</div>
      <div class="fuel-target-rate">${targetRate.toFixed(2)} L/lap</div>
    `;
    fuelTargetRow.appendChild(cell);
  }
}

function renderFuelGauge(fuel) {
  const cap = fuel.tank_capacity;
  const level = fuel.current_fuel_level;

  if (!cap || cap <= 0 || level === null || level === undefined) {
    fuelGaugeZones.style.background = "var(--muted)";
    fuelGaugeMask.style.height = "100%";
    fuelGaugeLabel.textContent = "";
    return;
  }

  const usedPct = Math.max(0, Math.min(100, (1 - level / cap) * 100));
  fuelGaugeMask.style.height = `${usedPct}%`;

  const avg = fuel.avg_fuel_per_lap;
  if (avg && avg > 0) {
    const redPct = Math.min(100, ((1 * avg) / cap) * 100);
    const yellowPct = Math.min(100, ((3 * avg) / cap) * 100);
    fuelGaugeZones.style.background = `linear-gradient(to top,
      var(--critical) 0%, var(--critical) ${redPct}%,
      var(--warning) ${redPct}%, var(--warning) ${yellowPct}%,
      var(--safe-fuel) ${yellowPct}%, var(--safe-fuel) 100%)`;

    const lapsLeft = fuel.laps_remaining_on_fuel;
    fuelGaugeLabel.textContent = lapsLeft !== null && lapsLeft !== undefined ? Math.floor(lapsLeft) : "";
    fuelGaugeLabel.style.top = `${usedPct}%`;
  } else {
    fuelGaugeZones.style.background = "var(--safe-fuel)";
    fuelGaugeLabel.textContent = "";
  }
}

function render(data) {
  applySettings(data.settings);

  if (!data.connected) {
    qualiFuel.textContent = "–";
    qualiFuelLaps.textContent = "–";
    qualiFuelStint.textContent = "–";
    qualiFuelFinish.textContent = "–";
    qualiFuelFinish.classList.remove("finish-ok", "finish-critical");
    qualiFuelRunout.textContent = "–";
    qualiFuelBox.style.display = "none";
    lastLapFuel.textContent = "–";
    lastLapFuelLaps.textContent = "–";
    lastLapFuelStint.textContent = "–";
    lastLapFuelFinish.textContent = "–";
    lastLapFuelFinish.classList.remove("finish-ok", "finish-critical");
    lastLapFuelRunout.textContent = "–";
    fuelPerLap.textContent = "–";
    fuelPerLapLaps.textContent = "–";
    fuelPerLapStint.textContent = "–";
    fuelPerLapFinish.textContent = "–";
    fuelPerLapFinish.classList.remove("finish-ok", "finish-critical");
    fuelPerLapRunout.textContent = "–";
    fuelMax.textContent = "–";
    fuelMaxLaps.textContent = "–";
    fuelMaxStint.textContent = "–";
    fuelMaxFinish.textContent = "–";
    fuelMaxFinish.classList.remove("finish-ok", "finish-critical");
    fuelMaxRunout.textContent = "–";
    fuelCap.textContent = "–";
    fuelTargetRow.innerHTML = "";
    renderFuelGauge({});
    tireWorst.textContent = "–";
    tireTemp.textContent = "–";
    lapNum.textContent = "Lap –";
    connState.textContent = "disconnected";
    relativePanel.style.display = "none";
    fitWindowToContent();
    return;
  }

  connState.textContent = "connected";
  lapNum.textContent = `Lap ${data.lap ?? "–"}`;

  const fuel = data.fuel || {};
  const currentFuelLevel = fuel.current_fuel_level;
  const tankCapacity = fuel.tank_capacity;
  const currentLap = data.lap;
  const lapsRemainingLeaderPace = data.laps_remaining_leader_pace;
  fuelPerLap.textContent = fmt(fuel.avg_fuel_per_lap, 2, " L/lap");
  fuelPerLapLaps.textContent = lapsLeftText(fuel.avg_fuel_per_lap, currentFuelLevel);
  fuelPerLapStint.textContent = stintLengthText(fuel.avg_fuel_per_lap, tankCapacity);
  applyFinishMargin(fuelPerLapFinish, fuel.avg_fuel_per_lap, currentFuelLevel, lapsRemainingLeaderPace);
  applyRunout(fuelPerLapRunout, fuel.avg_fuel_per_lap, currentLap, currentFuelLevel, tankCapacity);
  fuelMax.textContent = fmt(fuel.max_fuel_per_lap, 2, " L/lap");
  fuelMaxLaps.textContent = lapsLeftText(fuel.max_fuel_per_lap, currentFuelLevel);
  fuelMaxStint.textContent = stintLengthText(fuel.max_fuel_per_lap, tankCapacity);
  applyFinishMargin(fuelMaxFinish, fuel.max_fuel_per_lap, currentFuelLevel, lapsRemainingLeaderPace);
  applyRunout(fuelMaxRunout, fuel.max_fuel_per_lap, currentLap, currentFuelLevel, tankCapacity);
  fuelCap.textContent = fuel.tank_capacity !== null && fuel.tank_capacity !== undefined
    ? fmt(fuel.tank_capacity, 1, " L") + (fuel.fuel_pct_available && fuel.fuel_pct_available !== 100 ? ` (×${fuel.fuel_pct_available}%)` : "")
    : "–";
  renderFuelGauge(fuel);
  renderFuelTargets(fuel);

  const qualiBaseline = data.qualifying_baseline;
  const showQuali = qualiBaseline && (data.settings || {}).show_quali_fuel !== false;
  qualiFuelBox.style.display = showQuali ? "" : "none";
  if (qualiBaseline) {
    qualiFuel.textContent = fmt(qualiBaseline.fuel_per_lap, 2, " L/lap");
    qualiFuelLaps.textContent = lapsLeftText(qualiBaseline.fuel_per_lap, currentFuelLevel);
    qualiFuelStint.textContent = stintLengthText(qualiBaseline.fuel_per_lap, tankCapacity);
    applyFinishMargin(qualiFuelFinish, qualiBaseline.fuel_per_lap, currentFuelLevel, lapsRemainingLeaderPace);
    applyRunout(qualiFuelRunout, qualiBaseline.fuel_per_lap, currentLap, currentFuelLevel, tankCapacity);
  }

  lastLapFuel.textContent = fmt(fuel.last_lap_fuel_per_lap, 2, " L/lap");
  lastLapFuelLaps.textContent = lapsLeftText(fuel.last_lap_fuel_per_lap, currentFuelLevel);
  lastLapFuelStint.textContent = stintLengthText(fuel.last_lap_fuel_per_lap, tankCapacity);
  applyFinishMargin(lastLapFuelFinish, fuel.last_lap_fuel_per_lap, currentFuelLevel, lapsRemainingLeaderPace);
  applyRunout(lastLapFuelRunout, fuel.last_lap_fuel_per_lap, currentLap, currentFuelLevel, tankCapacity);

  const tires = data.tires || {};
  tireWorst.textContent = tires.worst_wear_remaining !== null && tires.worst_wear_remaining !== undefined
    ? `${tires.worst_tire_position ?? "?"} ${fmt(tires.worst_wear_remaining * 100, 0, "%")}`
    : "–";
  tireTemp.textContent = fmt(tires.worst_tire_temp, 0, "°");

  const relative = data.relative || { ahead: [], behind: [] };
  renderRelativeGroup(relativeAhead, relative.ahead);
  renderRelativeGroup(relativeBehind, relative.behind);
  const showRelative = (relative.ahead.length || relative.behind.length) && (data.settings || {}).show_relative !== false;
  relativePanel.style.display = showRelative ? "" : "none";

  fitWindowToContent();
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/live`);

  ws.onmessage = (event) => {
    try {
      render(JSON.parse(event.data));
    } catch (err) {
      // ignore malformed frame, next tick will correct it
    }
  };

  ws.onclose = () => {
    connState.textContent = "reconnecting…";
    setTimeout(connect, 1500);
  };

  ws.onerror = () => ws.close();
}

connect();
