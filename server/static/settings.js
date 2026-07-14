// Field names here must match server/settings_store.py's OverlaySettings
// exactly -- this page just POSTs the whole checkbox state back as one
// object on every change, rather than diffing.
const KEYS = [
  "show_last_lap", "show_max_fuel", "show_avg_fuel", "show_quali_fuel",
  "show_col_laps_left", "show_col_stint", "show_col_finish", "show_col_runout",
  "show_fuel_gauge", "show_fuel_targets", "show_tires", "show_relative",
];

const checkboxes = Object.fromEntries(KEYS.map((key) => [key, document.getElementById(key)]));
const saveStatus = document.getElementById("save-status");

let statusResetTimer = null;

function currentSettings() {
  return Object.fromEntries(KEYS.map((key) => [key, checkboxes[key].checked]));
}

async function loadSettings() {
  const res = await fetch("/api/settings");
  const settings = await res.json();
  for (const key of KEYS) {
    checkboxes[key].checked = settings[key] !== false;
  }
}

async function saveSettings() {
  saveStatus.textContent = "Saving…";
  try {
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentSettings()),
    });
    saveStatus.textContent = "Saved";
  } catch (err) {
    saveStatus.textContent = "Failed to save";
  }
  clearTimeout(statusResetTimer);
  statusResetTimer = setTimeout(() => { saveStatus.textContent = ""; }, 1500);
}

for (const key of KEYS) {
  checkboxes[key].addEventListener("change", saveSettings);
}

loadSettings();
