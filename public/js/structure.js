// Project structure editor: layout/root controls + a files/folders list. Exposes
// window.structureEditor.{getStructure,setStructure}; the result is sent under
// `structure` in the /api/generate request and round-tripped by preset.js.
const INITIAL_STRUCTURE = JSON.parse(document.getElementById("initial-structure").textContent);

const filesEditor = document.getElementById("files-editor");
const customDirs = document.getElementById("custom-dirs");
const backendDirInput = document.getElementById("dir-backend");
const frontendDirInput = document.getElementById("dir-frontend");
const rootInput = document.getElementById("root-dir");
const noWrapper = document.getElementById("no-wrapper");
const structForm = document.getElementById("gen-form");

function layoutValue() {
  const checked = structForm.querySelector("input[name=layout]:checked");
  return checked ? checked.value : "nested";
}

function updateVisibility() {
  customDirs.hidden = layoutValue() !== "custom";
  rootInput.disabled = noWrapper.checked;
}

function makeFileRow(file) {
  const data = file || { path: "", content: "" };
  const row = document.createElement("div");
  row.className = "file-row";

  const path = document.createElement("input");
  path.className = "file-path";
  path.placeholder = "assignments/hw1/README.md  (or  assignments/hw1/  for a folder)";
  path.value = data.path || "";

  const content = document.createElement("textarea");
  content.className = "file-content";
  content.rows = 2;
  content.placeholder = "file contents (leave empty for an empty file)";
  content.value = data.content || "";

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "ghost small";
  remove.textContent = "✕";
  remove.addEventListener("click", () => row.remove());

  const head = document.createElement("div");
  head.className = "file-head";
  head.append(path, remove);
  row.append(head, content);
  return row;
}

function getStructure() {
  const layout = layoutValue();
  const struct = {};

  if (layout === "monorepo") {
    struct.layout = "monorepo";
  } else if (layout === "custom") {
    struct.layout = "nested";
    const dirs = {};
    const b = backendDirInput.value.trim();
    const f = frontendDirInput.value.trim();
    if (b) dirs.backend = b;
    if (f) dirs.frontend = f;
    if (Object.keys(dirs).length) struct.dirs = dirs;
  } else {
    struct.layout = "nested";
  }

  if (noWrapper.checked) {
    struct.root = "";
  } else {
    const r = rootInput.value.trim();
    if (r) struct.root = r;
  }

  const files = [];
  for (const row of filesEditor.querySelectorAll(".file-row")) {
    const path = row.querySelector(".file-path").value.trim();
    if (!path) continue;
    files.push({ path, content: row.querySelector(".file-content").value });
  }
  if (files.length) struct.files = files;

  return struct;
}

function setStructure(struct) {
  struct = struct || {};
  const dirs = struct.dirs || {};
  const radioValue =
    struct.layout === "monorepo"
      ? "monorepo"
      : dirs.backend || dirs.frontend
      ? "custom"
      : "nested";
  const radio = structForm.querySelector(`input[name=layout][value="${radioValue}"]`);
  if (radio) radio.checked = true;
  backendDirInput.value = dirs.backend || "";
  frontendDirInput.value = dirs.frontend || "";

  if (struct.root === "") {
    noWrapper.checked = true;
    rootInput.value = "";
  } else {
    noWrapper.checked = false;
    rootInput.value = struct.root || "";
  }

  filesEditor.innerHTML = "";
  for (const file of struct.files || []) filesEditor.appendChild(makeFileRow(file));
  updateVisibility();
}

document.getElementById("add-file").addEventListener("click", () => {
  filesEditor.appendChild(makeFileRow());
});
structForm.addEventListener("change", updateVisibility);

setStructure(INITIAL_STRUCTURE);

window.structureEditor = { getStructure, setStructure };
