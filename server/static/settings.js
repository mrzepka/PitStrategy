// Field names here must match server/settings_store.py's OverlaySettings
// exactly -- this page just POSTs the whole checkbox state back as one
// object on every change, rather than diffing.
const KEYS = [
  "show_last_lap", "show_max_fuel", "show_avg_fuel", "show_quali_fuel",
  "show_col_laps_left", "show_col_stint", "show_col_finish", "show_col_runout",
  "show_fuel_gauge", "show_fuel_targets", "show_tires", "show_relative", "show_final_window",
  "auto_fuel_enabled",
];
// zoom is a fraction server-side (0.6-2.0, same bounds as overlay.js's
// MIN_SCALE/MAX_SCALE) but shown here as a whole-number percent -- handled
// separately from KEYS since it isn't a boolean checkbox.
const ZOOM_MIN_PCT = 60;
const ZOOM_MAX_PCT = 200;

// auto_fuel_source's selectable options mirror the "Fuel calculations
// (rows)" checkboxes one-to-one -- showKey is which of those must be
// checked on for this source to be pickable here at all.
const AUTO_FUEL_SOURCES = [
  { value: "last_lap", label: "Last lap", showKey: "show_last_lap" },
  { value: "max_fuel", label: "Max fuel", showKey: "show_max_fuel" },
  { value: "avg_fuel", label: "5-lap avg", showKey: "show_avg_fuel" },
  { value: "quali_fuel", label: "Quali fuel", showKey: "show_quali_fuel" },
];

// auto_fuel_buffer_laps bounds mirror settings_store.py's OverlaySettings
// field (ge=-5, le=20) and settings.html's matching min/max attributes.
const BUFFER_LAPS_MIN = -5;
const BUFFER_LAPS_MAX = 20;

const checkboxes = Object.fromEntries(KEYS.map((key) => [key, document.getElementById(key)]));
const zoomInput = document.getElementById("zoom_pct");
const autoFuelSourceSelect = document.getElementById("auto_fuel_source");
const autoFuelBufferLapsInput = document.getElementById("auto_fuel_buffer_laps");
const fuelUnitsSelect = document.getElementById("fuel_units");
const saveStatus = document.getElementById("save-status");

let statusResetTimer = null;

// Rebuilds the dropdown to only the rows currently checked on above. If
// there's nothing checked at all, auto-fuel has no calculation to source
// from, so both the dropdown and "Auto-add on pit entry" are disabled
// outright (and forced off if it was on) rather than left as a
// checked-but-inert box that silently does nothing on pit entry. If the
// current selection isn't one of the available rows (its row just got
// unchecked, or this is a fresh install that's never had one picked), it
// defaults to the first available calculation and persists that -- so
// auto-fuel actually works rather than sitting blank until picked by hand.
function syncAutoFuelSourceOptions(settings) {
  const available = AUTO_FUEL_SOURCES.filter((s) => settings[s.showKey] !== false);
  const currentValue = settings.auto_fuel_source || "";
  const stillValid = available.some((s) => s.value === currentValue);

  autoFuelSourceSelect.innerHTML = "";
  const blankOption = document.createElement("option");
  blankOption.value = "";
  blankOption.textContent = available.length ? "Select a calculation…" : "No rows enabled above";
  autoFuelSourceSelect.appendChild(blankOption);
  for (const source of available) {
    const opt = document.createElement("option");
    opt.value = source.value;
    opt.textContent = source.label;
    autoFuelSourceSelect.appendChild(opt);
  }

  autoFuelSourceSelect.disabled = available.length === 0;
  checkboxes.auto_fuel_enabled.disabled = available.length === 0;

  if (available.length === 0) {
    autoFuelSourceSelect.value = "";
    if (settings.auto_fuel_enabled) saveSetting("auto_fuel_enabled", false);
    return;
  }

  if (stillValid) {
    autoFuelSourceSelect.value = currentValue;
    return;
  }

  autoFuelSourceSelect.value = available[0].value;
  saveSetting("auto_fuel_source", available[0].value);
}

function applySettingsToInputs(settings) {
  for (const key of KEYS) {
    checkboxes[key].checked = settings[key] !== false;
  }
  zoomInput.value = Math.round((typeof settings.zoom === "number" ? settings.zoom : 1) * 100);
  autoFuelBufferLapsInput.value = (typeof settings.auto_fuel_buffer_laps === "number" ? settings.auto_fuel_buffer_laps : 0).toFixed(1);
  fuelUnitsSelect.value = settings.fuel_units === "gallons" ? "gallons" : "liters";
  syncAutoFuelSourceOptions(settings);
}

async function loadSettings() {
  const res = await fetch("/api/settings");
  applySettingsToInputs(await res.json());
}

// Fetches the current server-side settings immediately before saving, and
// merges in only the single field that changed, rather than POSTing this
// whole page's cached state -- zoom can *also* change from the overlay
// side (dragging its corner, see overlay.js's saveZoomSetting()), so if
// this settings page has been open a while, blindly POSTing its
// possibly-stale cached zoom would clobber a fresher drag the moment any
// checkbox here gets toggled. Also refreshes every input from that fresh
// snapshot afterward, so a zoom change made elsewhere shows up here too.
async function saveSetting(key, value) {
  saveStatus.textContent = "Saving…";
  try {
    const freshRes = await fetch("/api/settings");
    const fresh = await freshRes.json();
    const payload = { ...fresh, [key]: value };
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    applySettingsToInputs(payload);
    saveStatus.textContent = "Saved";
  } catch (err) {
    saveStatus.textContent = "Failed to save";
  }
  clearTimeout(statusResetTimer);
  statusResetTimer = setTimeout(() => { saveStatus.textContent = ""; }, 1500);
}

for (const key of KEYS) {
  checkboxes[key].addEventListener("change", () => saveSetting(key, checkboxes[key].checked));
}
zoomInput.addEventListener("change", () => {
  const pct = Math.min(ZOOM_MAX_PCT, Math.max(ZOOM_MIN_PCT, Number(zoomInput.value) || 100));
  zoomInput.value = pct;
  saveSetting("zoom", pct / 100);
});
autoFuelSourceSelect.addEventListener("change", () => {
  saveSetting("auto_fuel_source", autoFuelSourceSelect.value || null);
});
autoFuelBufferLapsInput.addEventListener("change", () => {
  const raw = Math.min(BUFFER_LAPS_MAX, Math.max(BUFFER_LAPS_MIN, Number(autoFuelBufferLapsInput.value) || 0));
  const laps = Math.round(raw * 10) / 10; // snap to the 0.1-lap steps the input offers, in case a typed value landed off-grid
  autoFuelBufferLapsInput.value = laps.toFixed(1);
  saveSetting("auto_fuel_buffer_laps", laps);
});
fuelUnitsSelect.addEventListener("change", () => {
  saveSetting("fuel_units", fuelUnitsSelect.value);
});

loadSettings();
