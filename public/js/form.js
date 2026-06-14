// Live compatibility checking for the stack picker. CONSTRAINTS / ADDONS_META
// are the same data the server validates against, embedded as JSON so the two
// never drift.
const CONSTRAINTS = JSON.parse(document.getElementById("constraints").textContent);
const ADDONS_META = JSON.parse(document.getElementById("addons-meta").textContent);

const form = document.getElementById("gen-form");
const errorEl = document.getElementById("error");
const submitBtn = document.getElementById("submit");
const schemaField = document.getElementById("schema-input");

function currentSelection() {
  const sel = {};
  form.querySelectorAll("input[type=radio]:checked").forEach((r) => {
    sel[r.name] = r.value;
  });
  return sel;
}

// Returns an error message for an invalid selection, or null if it's fine.
function check(selection) {
  for (const rule of CONSTRAINTS) {
    if (!rule.when.values.includes(selection[rule.when.axis])) continue;
    if (rule.require && !rule.require.values.includes(selection[rule.require.axis])) {
      return rule.message;
    }
    if (rule.forbid && rule.forbid.values.includes(selection[rule.forbid.axis])) {
      return rule.message;
    }
  }
  return null;
}

function hasCustomSchema() {
  const value = (schemaField.value || "").trim();
  return value !== "" && value !== "[]";
}

function refresh() {
  const selection = currentSelection();

  // Disable any radio option that would, on its own, produce an invalid combo.
  form.querySelectorAll("input[type=radio]").forEach((radio) => {
    const trial = { ...selection, [radio.name]: radio.value };
    const invalid = Boolean(check(trial)) && !radio.checked;
    radio.disabled = invalid;
    radio.closest(".option").classList.toggle("disabled", invalid);
  });

  // Gate add-ons that don't fit the chosen stack.
  for (const meta of ADDONS_META) {
    const box = form.querySelector(`input[name=addons][value="${meta.id}"]`);
    if (!box) continue;
    const okBackend =
      !meta.requires_backend.length || meta.requires_backend.includes(selection.backend);
    const okFrontend =
      !meta.requires_frontend.length || meta.requires_frontend.includes(selection.frontend);
    const ok = okBackend && okFrontend;
    box.disabled = !ok;
    if (!ok) box.checked = false;
    box.closest(".option").classList.toggle("disabled", !ok);
  }

  let message = check(selection);
  if (!message && hasCustomSchema() && !["flask", "fastapi"].includes(selection.backend)) {
    message = "Custom data entities need a Python backend (Flask or FastAPI).";
  }
  errorEl.textContent = message || "";
  errorEl.hidden = !message;
  errorEl.classList.remove("info");
  submitBtn.disabled = Boolean(message);
}

form.addEventListener("change", refresh);
form.addEventListener("input", refresh);
refresh();
