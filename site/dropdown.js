// Custom dropdown menu that replaces a native <select>, following the WAI-ARIA
// "select-only combobox" pattern: https://www.w3.org/WAI/ARIA/apg/patterns/combobox/examples/combobox-select-only/
//
// The native <select> stays in the page (hidden) and remains the source of
// truth: picking an option sets select.value and fires a "change" event, so
// the rest of the app keeps working with plain selects.
//
// Keyboard (closed): ↓ ↑ Enter Space open · Home/End open at first/last · typing jumps to a match
// Keyboard (open):   ↓ ↑ move · Home/End · PageUp/PageDown · Enter/Space pick · Esc close · Tab pick + move on
"use strict";

// eslint-disable-next-line no-unused-vars
function enhanceSelect(select) {
  const label = document.querySelector(`label[for="${select.id}"]`);
  const labelId = `${select.id}-label`;
  const listId = `${select.id}-listbox`;
  if (label) {
    label.id = labelId;
    label.removeAttribute("for");
  }

  const wrap = document.createElement("div");
  wrap.className = "dd";

  const combo = document.createElement("div");
  combo.className = "dd-combo";
  combo.tabIndex = 0;
  combo.setAttribute("role", "combobox");
  combo.setAttribute("aria-haspopup", "listbox");
  combo.setAttribute("aria-expanded", "false");
  combo.setAttribute("aria-controls", listId);
  combo.setAttribute("aria-labelledby", labelId);
  const valueEl = document.createElement("span");
  valueEl.className = "dd-value";
  combo.append(valueEl);

  const list = document.createElement("ul");
  list.className = "dd-list";
  list.id = listId;
  list.hidden = true;
  list.tabIndex = -1;
  list.setAttribute("role", "listbox");
  list.setAttribute("aria-labelledby", labelId);

  wrap.append(combo, list);
  select.after(wrap);
  select.hidden = true;
  select.setAttribute("aria-hidden", "true");
  select.tabIndex = -1;

  let items = [];       // [{value, label, count, el}]
  let active = -1;      // highlighted option index while open
  let typed = "";
  let typedTimer;

  // ----- build options from the <select> -----
  function build() {
    list.replaceChildren();
    items = [...select.options].map((opt, i) => {
      const li = document.createElement("li");
      li.id = `${select.id}-opt-${i}`;
      li.className = "dd-option";
      li.setAttribute("role", "option");
      const text = document.createElement("span");
      text.className = "dd-option-label";
      text.textContent = opt.dataset.label || opt.textContent;
      li.append(text);
      const count = Number(opt.dataset.count || 0);
      if (count) {
        const badge = document.createElement("span");
        badge.className = "dd-count";
        badge.textContent = count;
        badge.setAttribute("aria-label", `${count} jobs`);
        li.append(badge);
      }
      if (i === 0) li.classList.add("dd-option-all");
      li.addEventListener("mousedown", (e) => e.preventDefault()); // keep focus on combo
      li.addEventListener("click", () => { pick(i); close(); });
      li.addEventListener("mousemove", () => setActive(i, false));
      list.append(li);
      return { value: opt.value, label: text.textContent, el: li };
    });
    sync();
  }

  // ----- state -----
  const selectedIndex = () => Math.max(0, items.findIndex((it) => it.value === select.value));

  function sync() {
    const idx = selectedIndex();
    items.forEach((it, i) => it.el.setAttribute("aria-selected", String(i === idx)));
    valueEl.textContent = items[idx] ? items[idx].label : "";
    combo.classList.toggle("is-set", Boolean(select.value));
  }

  function setActive(i, scroll = true) {
    if (!items.length) return;
    active = Math.max(0, Math.min(items.length - 1, i));
    items.forEach((it, j) => it.el.classList.toggle("is-active", j === active));
    combo.setAttribute("aria-activedescendant", items[active].el.id);
    if (scroll) items[active].el.scrollIntoView({ block: "nearest" });
  }

  function pick(i) {
    const value = items[i] ? items[i].value : "";
    if (select.value !== value) {
      select.value = value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
    sync();
  }

  function open(startAt) {
    if (!list.hidden) return;
    document.dispatchEvent(new CustomEvent("dd:open", { detail: wrap })); // close other menus
    list.hidden = false;
    combo.setAttribute("aria-expanded", "true");
    wrap.classList.add("is-open");
    setActive(startAt ?? selectedIndex());
  }

  function close() {
    if (list.hidden) return;
    list.hidden = true;
    combo.setAttribute("aria-expanded", "false");
    combo.removeAttribute("aria-activedescendant");
    wrap.classList.remove("is-open");
    active = -1;
  }

  // Type-ahead: jump to the next option starting with the typed letters.
  function typeAhead(ch) {
    clearTimeout(typedTimer);
    typed += ch.toLowerCase();
    typedTimer = setTimeout(() => { typed = ""; }, 600);
    const from = list.hidden ? selectedIndex() : active;
    const order = [...items.keys()].map((k) => (from + 1 + k) % items.length);
    const allSame = [...typed].every((c) => c === typed[0]);
    const find = (s) => order.find((k) => items[k].label.toLowerCase().startsWith(s));
    const hit = find(typed) ?? (allSame ? find(typed[0]) : undefined);
    if (hit !== undefined) { open(hit); setActive(hit); }
  }

  // ----- events -----
  combo.addEventListener("click", () => (list.hidden ? open() : close()));

  combo.addEventListener("keydown", (e) => {
    const isOpen = !list.hidden;
    const k = e.key;
    if (!isOpen) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(k)) { e.preventDefault(); open(); return; }
      if (k === "Home") { e.preventDefault(); open(0); return; }
      if (k === "End") { e.preventDefault(); open(items.length - 1); return; }
    } else {
      switch (k) {
        case "ArrowDown": e.preventDefault(); if (e.altKey) { pick(active); close(); } else setActive(active + 1); return;
        case "ArrowUp":   e.preventDefault(); if (e.altKey) { pick(active); close(); } else setActive(active - 1); return;
        case "Home":      e.preventDefault(); setActive(0); return;
        case "End":       e.preventDefault(); setActive(items.length - 1); return;
        case "PageDown":  e.preventDefault(); setActive(active + 10); return;
        case "PageUp":    e.preventDefault(); setActive(active - 10); return;
        case "Enter": case " ": e.preventDefault(); pick(active); close(); return;
        case "Escape":    e.preventDefault(); close(); return;
        case "Tab":       pick(active); close(); return; // let focus move on
      }
    }
    if (k.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); typeAhead(k); }
  });

  combo.addEventListener("blur", () => close());
  if (label) label.addEventListener("click", () => combo.focus());
  document.addEventListener("pointerdown", (e) => { if (!wrap.contains(e.target)) close(); });
  document.addEventListener("dd:open", (e) => { if (e.detail !== wrap) close(); });

  build();
  return { build, sync, el: combo };
}
