// Live compatibility checking for the stack picker. MODULE_TAGS / ADDONS_META
// are the same data the server validates against, embedded as JSON so the two
// never drift. Compatibility is decided by capability tags: a selection is valid
// when every option's `requires` tags are provided by the rest of the selection.
const MODULE_TAGS = JSON.parse(document.getElementById("module-tags").textContent);
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

function providedTags(selection) {
  const set = new Set();
  for (const axis in selection) {
    const meta = MODULE_TAGS[axis] && MODULE_TAGS[axis][selection[axis]];
    if (meta) for (const tag of meta.provides) set.add(tag);
  }
  return set;
}

// Returns an error message for an invalid selection, or null if it's fine.
function check(selection) {
  const provided = providedTags(selection);
  for (const axis in selection) {
    const meta = MODULE_TAGS[axis] && MODULE_TAGS[axis][selection[axis]];
    if (!meta) continue;
    for (const tag of meta.requires) {
      if (!provided.has(tag)) {
        return meta.msg || "That option isn't compatible with the rest of the stack.";
      }
    }
  }
  if (!provided.has("backend") && !provided.has("frontend")) {
    return "Pick at least a backend or a frontend — not neither.";
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
  if (!message && hasCustomSchema() && selection.backend === "none") {
    message = "Custom data entities need a backend.";
  }
  errorEl.textContent = message || "";
  errorEl.hidden = !message;
  errorEl.classList.remove("info");
  submitBtn.disabled = Boolean(message);
}

form.addEventListener("change", refresh);
form.addEventListener("input", refresh);
refresh();
