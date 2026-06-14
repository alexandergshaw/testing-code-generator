// Save / share / import the whole configuration. encode/decode mirror
// generator/preset.py (URL-safe base64 of JSON).
const presetForm = document.getElementById("gen-form");
// All seven axes (mirrors registry.AXES) so auth/api/pkg are preserved too.
const AXES = ["backend", "frontend", "database", "styling", "auth", "api", "pkg"];

function buildConfig() {
  const stack = {};
  for (const axis of AXES) {
    const checked = presetForm.querySelector(`input[name=${axis}]:checked`);
    if (checked) stack[axis] = checked.value;
  }
  const addons = [...presetForm.querySelectorAll("input[name=addons]:checked")].map((c) => c.value);
  return {
    version: 1,
    project_name: presetForm.querySelector("input[name=project_name]").value.trim() || "my-app",
    stack,
    addons,
    schema: window.entitiesEditor.getSchema(),
    structure: window.structureEditor.getStructure(),
  };
}

function encodeConfig(config) {
  const b64 = btoa(unescape(encodeURIComponent(JSON.stringify(config))));
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function applyConfig(config) {
  const nameInput = presetForm.querySelector("input[name=project_name]");
  nameInput.value = config.project_name || "";
  for (const axis of AXES) {
    const value = (config.stack || {})[axis];
    const radio = presetForm.querySelector(`input[name=${axis}][value="${value}"]`);
    if (radio) radio.checked = true;
  }
  const addons = new Set(config.addons || []);
  presetForm.querySelectorAll("input[name=addons]").forEach((box) => {
    box.checked = addons.has(box.value);
  });
  window.entitiesEditor.setSchema(config.schema || []);
  window.structureEditor.setStructure(config.structure || {});
  presetForm.dispatchEvent(new Event("change"));
}

// Shared with form.js so the single generation path (POST /api/generate) and the
// save/share features build the exact same config object.
window.buildConfig = buildConfig;
window.applyConfig = applyConfig;

document.getElementById("copy-link").addEventListener("click", async () => {
  const url = `${location.origin}${location.pathname}?c=${encodeConfig(buildConfig())}`;
  try {
    await navigator.clipboard.writeText(url);
    flash("Share link copied to clipboard");
  } catch {
    prompt("Copy this share link:", url);
  }
});

document.getElementById("download-config").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(buildConfig(), null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "stackgen.json";
  a.click();
  URL.revokeObjectURL(a.href);
});

document.getElementById("import-config").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      applyConfig(JSON.parse(reader.result));
    } catch {
      flash("Could not read that config file");
    }
  };
  reader.readAsText(file);
  event.target.value = "";
});

function flash(text) {
  const note = document.getElementById("error");
  note.textContent = text;
  note.hidden = false;
  note.classList.add("info");
  setTimeout(() => {
    note.classList.remove("info");
    if (note.textContent === text) {
      note.hidden = true;
      note.textContent = "";
    }
  }, 2500);
}
