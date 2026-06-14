// Dynamic entity/field editor. Serializes to the hidden #schema-input so the
// form posts a JSON schema; exposes window.entitiesEditor for preset import.
const FIELD_TYPES = JSON.parse(document.getElementById("field-types").textContent);
const INITIAL_SCHEMA = JSON.parse(document.getElementById("initial-schema").textContent);

const editor = document.getElementById("entities-editor");
const schemaInput = document.getElementById("schema-input");
const genForm = document.getElementById("gen-form");

function el(tag, cls) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  return node;
}

function ghostButton(text, onClick) {
  const button = el("button", "ghost small");
  button.type = "button";
  button.textContent = text;
  button.addEventListener("click", onClick);
  return button;
}

function serialize() {
  const entities = [];
  for (const block of editor.querySelectorAll(".entity")) {
    const name = block.querySelector(".entity-name").value.trim();
    const plural = block.querySelector(".entity-plural").value.trim();
    const fields = [];
    for (const row of block.querySelectorAll(".field-row")) {
      const fieldName = row.querySelector(".field-name").value.trim();
      if (!fieldName) continue;
      fields.push({
        name: fieldName,
        type: row.querySelector(".field-type").value,
        required: row.querySelector(".field-required").checked,
      });
    }
    if (name) entities.push(plural ? { name, plural, fields } : { name, fields });
  }
  schemaInput.value = entities.length ? JSON.stringify(entities) : "";
  genForm.dispatchEvent(new Event("change"));
}

function makeField(field) {
  const data = field || { name: "", type: FIELD_TYPES[0], required: false };
  const row = el("div", "field-row");

  const name = el("input", "field-name");
  name.placeholder = "field_name";
  name.value = data.name;

  const type = el("select", "field-type");
  for (const t of FIELD_TYPES) {
    const option = el("option");
    option.value = t;
    option.textContent = t;
    if (t === data.type) option.selected = true;
    type.appendChild(option);
  }

  const reqLabel = el("label", "req");
  const required = el("input", "field-required");
  required.type = "checkbox";
  required.checked = Boolean(data.required);
  reqLabel.append(required, document.createTextNode(" required"));

  const remove = ghostButton("✕", () => {
    row.remove();
    serialize();
  });

  row.append(name, type, reqLabel, remove);
  return row;
}

function makeEntity(entity) {
  const data = entity || { name: "", plural: "", fields: [] };
  const block = el("div", "entity");

  const head = el("div", "entity-head");
  const name = el("input", "entity-name");
  name.placeholder = "EntityName";
  name.value = data.name || "";
  const plural = el("input", "entity-plural");
  plural.placeholder = "plural (optional)";
  plural.value = data.plural || "";
  head.append(name, plural, ghostButton("Remove", () => {
    block.remove();
    serialize();
  }));

  const fields = el("div", "fields");
  const initial = data.fields && data.fields.length
    ? data.fields
    : [{ name: "", type: FIELD_TYPES[0], required: false }];
  for (const field of initial) fields.appendChild(makeField(field));

  block.append(head, fields, ghostButton("+ Add field", () => {
    fields.appendChild(makeField());
    serialize();
  }));
  return block;
}

function setSchema(entities) {
  editor.innerHTML = "";
  for (const entity of entities) editor.appendChild(makeEntity(entity));
  serialize();
}

document.getElementById("add-entity").addEventListener("click", () => {
  editor.appendChild(makeEntity());
  serialize();
});
editor.addEventListener("input", serialize);
editor.addEventListener("change", serialize);

setSchema(INITIAL_SCHEMA);

window.entitiesEditor = {
  setSchema,
  getSchema: () => JSON.parse(schemaInput.value || "[]"),
};
