// Field names here must match server/settings_store.py's OverlaySettings
// exactly -- this page just POSTs the whole checkbox state back as one
// object on every change, rather than diffing.
const KEYS = [
  "show_last_lap", "show_max_fuel", "show_avg_fuel", "show_quali_fuel",
  "show_col_laps_left", "show_col_stint", "show_col_finish", "show_col_runout",
  "show_fuel_gauge", "show_fuel_targets", "show_tires", "show_relative", "show_final_window",
];
// zoom is a fraction server-side (0.6-2.0, same bounds as overlay.js's
// MIN_SCALE/MAX_SCALE) but shown here as a whole-number percent -- handled
// separately from KEYS since it isn't a boolean checkbox.
const ZOOM_MIN_PCT = 60;
const ZOOM_MAX_PCT = 200;

const checkboxes = Object.fromEntries(KEYS.map((key) => [key, document.getElementById(key)]));
const zoomInput = document.getElementById("zoom_pct");
const saveStatus = document.getElementById("save-status");

let statusResetTimer = null;

function applySettingsToInputs(settings) {
  for (const key of KEYS) {
    checkboxes[key].checked = settings[key] !== false;
  }
  zoomInput.value = Math.round((typeof settings.zoom === "number" ? settings.zoom : 1) * 100);
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

loadSettings();
