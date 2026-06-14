// Live compatibility checking for the stack picker.
// CONSTRAINTS is the same data the server validates against (registry.py),
// embedded as JSON so the two never drift.
const CONSTRAINTS = JSON.parse(
  document.getElementById("constraints").textContent,
);

const form = document.getElementById("gen-form");
const errorEl = document.getElementById("error");
const submitBtn = document.getElementById("submit");

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

function refresh() {
  const selection = currentSelection();

  // Disable any option that would, on its own, produce an invalid combo.
  form.querySelectorAll("input[type=radio]").forEach((radio) => {
    const trial = { ...selection, [radio.name]: radio.value };
    const invalid = Boolean(check(trial)) && !radio.checked;
    radio.disabled = invalid;
    radio.closest(".option").classList.toggle("disabled", invalid);
  });

  const message = check(selection);
  errorEl.textContent = message || "";
  errorEl.hidden = !message;
  submitBtn.disabled = Boolean(message);
}

form.addEventListener("change", refresh);
refresh();
