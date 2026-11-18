// Fresher Jobs Radar — loads jobs.json and filters it in the browser. No backend.
// Saved / applied jobs and the last-visit date live only in this browser (localStorage).
"use strict";

const PAGE_SIZE = 60;
const INTERN_RE = /\b(intern|interns|internship|internships|apprentice|apprenticeship)\b/i;
const SOURCE_NAMES = { adzuna: "Adzuna", greenhouse: "the company's careers page (Greenhouse)", lever: "the company's careers page (Lever)" };
const CITY_FALLBACK = "Other India";

// Small line icons (24×24, stroke = currentColor). Static strings only.
const ICONS = {
  pin: '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  cap: '<path d="M22 10 12 5 2 10l10 5 10-5Z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/>',
  tag: '<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8Z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
  external: '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  bookmark: '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>',
  share: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 13.5 6.8 4M15.4 6.5l-6.8 4"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  chevron: '<path d="m6 9 6 6 6-6"/>',
};
const icon = (name, cls = "icon") => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;

const $ = (id) => document.getElementById(id);
const els = {
  form: $("filters"), q: $("q"), intern: $("intern"), meta: $("meta"), count: $("count"),
  jobs: $("jobs"), empty: $("empty"), emptyClear: $("empty-clear"), more: $("more"),
  roleList: $("role-list"), city: $("city"), resultsTitle: $("results-title"),
  facetNote: $("facet-note"), sidebar: $("sidebar"), toggle: $("filters-toggle"),
  filtersCount: $("filters-count"), active: $("active-filters"), savedToggle: $("saved-toggle"),
  savedN: $("saved-n"), heroLede: $("hero-lede"),
  toast: $("toast"),
};

let allJobs = [];
let taxonomy = { roles: [], cities: [] };
let refDay = null;          // the data's "today" (IST), as a day number
let matches = [];
let shown = 0;
let showSaved = false;
const openDetails = new Set();
let cityDropdown = null;    // custom menu built on the City <select> (dropdown.js)

// ---------- this browser's memory (never sent anywhere) ----------

const store = {
  get(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode: just don't remember */ } },
};
const saved = new Set(store.get("fjr.saved", []));
const applied = new Set(store.get("fjr.applied", []));
const persist = () => { store.set("fjr.saved", [...saved]); store.set("fjr.applied", [...applied]); };

let toastTimer;
function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("is-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => els.toast.classList.remove("is-visible"), 2200);
}

// ---------- text helpers ----------

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;   // job data is only ever inserted as text
  return node;
}

// "FIRST NEEDS SALES PVT LTD" -> "First Needs Sales Pvt Ltd"; keeps short acronyms (IT, HR, BDE).
function tidyCase(text) {
  if (!text) return "";
  const letters = text.replace(/[^A-Za-z]/g, "");
  if (letters.length < 5 || letters.replace(/[^A-Z]/g, "").length / letters.length < 0.7) return text;
  return text.toLowerCase().replace(/[a-z][a-z']*/g, (w, i) => {
    const original = text.substr(i, w.length);
    if (w.length <= 3 && /^[A-Z]+$/.test(original) && !["and", "the", "for", "pvt", "ltd"].includes(w)) return original;
    return w[0].toUpperCase() + w.slice(1);
  });
}

// "WE ARE HIRINGBusiness Development" -> "WE ARE HIRING Business Development"
function tidyText(text) {
  if (!text) return "";
  return text.replace(/([A-Z]{2,})([A-Z][a-z])/g, "$1 $2").replace(/([a-z])([A-Z][a-z])/g, "$1 $2");
}

function shortLocation(raw) {
  if (!raw) return "";
  const parts = raw.split(/\s*[,/]\s*/).filter((p) => p && !/^india$/i.test(p));
  return parts.length ? parts[0] : "India";
}

const dayNumber = (iso) => Math.floor(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / 86400000);
const fmtDay = (iso, opts = { day: "numeric", month: "short" }) =>
  new Date(iso + "T00:00:00").toLocaleDateString("en-IN", opts);

function dayGroup(job) {
  if (!job.posted_at) return { key: "undated", label: "Date not given" };
  const diff = refDay - dayNumber(job.posted_at);
  if (diff <= 0) return { key: "today", label: "Today" };
  if (diff === 1) return { key: "yesterday", label: "Yesterday" };
  if (diff <= 6) return { key: "week", label: "Earlier this week" };
  return { key: "earlier", label: "Earlier" };
}

// ---------- filters ----------

function readFilters() {
  const fd = new FormData(els.form);
  return { q: els.q.value.trim(), role: fd.get("role") || "", city: els.city.value || "", intern: els.intern.checked, saved: showSaved };
}

function setRadio(name, value) {
  const input = els.form.querySelector(`input[name="${name}"][value="${CSS.escape(value)}"]`)
    || els.form.querySelector(`input[name="${name}"][value=""]`);
  if (input) input.checked = true;
}

function setCity(value) {
  els.city.value = value;
  if (cityDropdown) cityDropdown.sync();
}

function writeUrl(f) {
  const p = new URLSearchParams();
  if (f.q) p.set("q", f.q);
  if (f.role) p.set("role", f.role);
  if (f.city) p.set("city", f.city);
  if (f.intern) p.set("intern", "1");
  if (f.saved) p.set("saved", "1");
  const qs = p.toString();
  history.replaceState(null, "", qs ? `?${qs}` : location.pathname);
}

function matchesExcept(job, f, terms, skip) {
  if (f.saved && !saved.has(job.id)) return false;
  if (skip !== "role" && f.role && job.role !== f.role) return false;
  if (skip !== "city" && f.city && job._city !== f.city) return false;
  if (f.intern && !job._intern) return false;
  return terms.every((t) => job._haystack.includes(t));
}

// ---------- category list + city dropdown (both with live counts) ----------

function renderCategories(f, terms) {
  const pool = allJobs.filter((j) => matchesExcept(j, f, terms, "role"));
  const counts = {};
  for (const j of pool) if (j.role) counts[j.role] = (counts[j.role] || 0) + 1;
  const options = [["", "All categories", pool.length], ...taxonomy.roles.map((v) => [v, v, counts[v] || 0])];

  els.roleList.replaceChildren(...options.map(([value, label, n], i) => {
    const li = el("li", value && !n ? "facet-option is-empty" : "facet-option");
    const input = el("input");
    input.type = "radio";
    input.name = "role";
    input.value = value;
    input.id = `role-${i}`;
    input.checked = value === f.role;
    const lab = el("label");
    lab.htmlFor = input.id;
    lab.append(el("span", null, label), el("span", "facet-n", String(n)));
    li.append(input, lab);
    return li;
  }));
}

function cityCounts(f, terms) {
  const pool = allJobs.filter((j) => matchesExcept(j, f, terms, "city"));
  const counts = {};
  for (const j of pool) if (j._city) counts[j._city] = (counts[j._city] || 0) + 1;
  return { pool, counts };
}

function renderCitySelect(f, terms) {
  const { pool, counts } = cityCounts(f, terms);
  const options = [["", "All cities", pool.length], ...taxonomy.cities.map((c) => [c, c, counts[c] || 0])];
  els.city.replaceChildren(...options.map(([value, label, n]) => {
    const opt = el("option", null, n ? `${label} (${n})` : label);
    opt.value = value;
    opt.dataset.label = label;
    opt.dataset.count = n;
    return opt;
  }));
  els.city.value = f.city;
  if (cityDropdown) cityDropdown.build();
}

function renderActiveChips(f) {
  const chips = [];
  const add = (label, clear) => {
    const b = el("button", "chip-remove");
    b.type = "button";
    b.setAttribute("aria-label", `Remove filter: ${label}`);
    b.append(label);
    b.insertAdjacentHTML("beforeend", icon("x"));
    b.addEventListener("click", () => { clear(); apply(); });
    chips.push(b);
  };
  // Only the search term gets a chip: the search box is out of view once you scroll.
  // Category, City and Internships already show their state right above the list.
  if (f.q) add(`“${f.q}”`, () => { els.q.value = ""; });
  els.active.replaceChildren(...chips);
  els.active.hidden = chips.length === 0;
  els.filtersCount.textContent = f.role ? " (1)" : "";
}

function clearAll() {
  els.q.value = "";
  els.intern.checked = false;
  showSaved = false;
  setRadio("role", "");
  setCity("");
  apply();
}

function scrollToResults() {
  const top = els.resultsTitle.getBoundingClientRect().top;
  if (top < 0 || top > innerHeight * 0.6) els.resultsTitle.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
}

// ---------- apply + render ----------

function apply() {
  const f = readFilters();
  const terms = f.q.toLowerCase().split(/\s+/).filter(Boolean);
  matches = allJobs.filter((j) => matchesExcept(j, f, terms, null));
  writeUrl(f);

  els.facetNote.hidden = allJobs.some((j) => j.role);
  renderCategories(f, terms);
  renderCitySelect(f, terms);
  renderActiveChips(f);

  els.resultsTitle.textContent = f.saved ? "Saved jobs" : f.role || "All jobs";
  els.savedToggle.setAttribute("aria-pressed", String(f.saved));
  els.savedN.textContent = String(saved.size);
  $("category-reset").hidden = !f.role;

  els.jobs.replaceChildren();
  shown = 0;
  renderMore();

  const n = matches.length;
  els.count.textContent = `${n} ${n === 1 ? "job" : "jobs"}`;
  els.empty.hidden = n !== 0;
  $("empty-title").textContent = f.saved && !saved.size ? "No saved jobs yet" : "No jobs match these filters";
  $("empty-text").textContent = f.saved && !saved.size
    ? "Tap the bookmark on any job to keep it here for later."
    : "Remove a filter or try a shorter search.";
  $("sheet-done").textContent = `Show ${n} jobs`;
}

// Initials for companies without a real logo: "Steigen Elevators" -> "SE", "YourFriendlyhr" -> "YF".
const NAME_NOISE = new Set(["the", "pvt", "private", "ltd", "limited", "inc", "llp", "llc", "co", "corp", "corporation", "&", "and", "of"]);
function initials(company) {
  const words = company.replace(/([a-z])([A-Z])/g, "$1 $2").split(/[\s,.\-_/|()]+/)
    .filter((w) => w && !NAME_NOISE.has(w.toLowerCase()) && /[A-Za-z0-9]/.test(w));
  if (!words.length) return "?";
  const first = (w) => w.match(/[A-Za-z0-9]/)[0].toUpperCase();
  if (words.length > 1) return first(words[0]) + first(words[1]);
  // One word: its first letter — or two characters if it starts with a digit ("2coms" -> "2C").
  const chars = words[0].replace(/[^A-Za-z0-9]/g, "");
  return /^\d/.test(chars) ? chars.slice(0, 2).toUpperCase() : first(words[0]);
}
// The same company always gets the same colour.
function hueFor(text) {
  let h = 0;
  for (const ch of text) h = (h * 31 + ch.codePointAt(0)) % 360;
  return h;
}

function logoBox(job, company) {
  const box = el("span", "job-logo");
  box.setAttribute("aria-hidden", "true");   // the company name is right next to it as text
  const showInitials = () => {
    box.replaceChildren(initials(company));
    box.classList.remove("has-img");
    box.style.setProperty("--h", String(hueFor(company)));
  };
  if (job.logo) {
    const img = el("img");
    img.src = job.logo;
    img.alt = "";
    img.width = 28;
    img.height = 28;
    img.loading = "lazy";
    img.decoding = "async";
    img.addEventListener("error", showInitials);   // missing file -> initials
    box.classList.add("has-img");
    box.append(img);
  } else {
    showInitials();
  }
  return box;
}

function jobRow(job, groupKey) {
  const li = el("li", "job");
  const detailsId = `d-${job.id.replace(/[^a-zA-Z0-9_-]/g, "_")}`;
  const title = tidyCase(job.title);
  const company = tidyCase(job.company);

  // Title: opens the description in place. Chevron glued to the last word.
  const h = el("h3", "job-title");
  const toggle = el("button", "job-toggle");
  toggle.type = "button";
  toggle.setAttribute("aria-expanded", String(openDetails.has(job.id)));
  toggle.setAttribute("aria-controls", detailsId);
  const cut = title.lastIndexOf(" ");
  const tail = el("span", "nowrap", cut === -1 ? title : title.slice(cut + 1));
  tail.insertAdjacentHTML("beforeend", icon("chevron", "job-chevron"));
  toggle.append(cut === -1 ? "" : title.slice(0, cut + 1), tail);
  h.append(toggle);

  // Meta line with icons.
  const meta = el("p", "job-meta");
  const metaItem = (iconName, text, cls = "") => {
    const s = el("span", `meta ${cls}`.trim());
    s.insertAdjacentHTML("afterbegin", icon(iconName));
    s.append(text);
    return s;
  };
  meta.append(el("span", "meta job-company", company));   // no icon: the logo/initials badge already marks the company
  const place = job._city && job._city !== CITY_FALLBACK ? job._city : shortLocation(job.location_raw);
  meta.append(place && place !== "India"
    ? metaItem("pin", place, "job-place")
    : metaItem("pin", "City not listed", "job-place job-place-unknown"));
  if (job.role && job.role !== "Other" && !readFilters().role) meta.append(metaItem("tag", job.role, "job-tag"));
  if (job._intern) meta.append(metaItem("cap", "Internship", "job-tag job-tag-intern"));
  if ((groupKey === "earlier" || groupKey === "week") && job.posted_at) meta.append(metaItem("calendar", fmtDay(job.posted_at), "job-date"));

  // Actions: save, (Adzuna badge), apply.
  const side = el("div", "job-side");
  const saveBtn = el("button", "icon-btn save-btn");
  saveBtn.type = "button";
  const paintSave = () => {
    const on = saved.has(job.id);
    saveBtn.setAttribute("aria-pressed", String(on));
    saveBtn.setAttribute("aria-label", `${on ? "Remove from saved" : "Save"}: ${title} at ${company}`);
    saveBtn.title = on ? "Saved" : "Save for later";
  };
  saveBtn.insertAdjacentHTML("afterbegin", icon("bookmark"));
  paintSave();
  saveBtn.addEventListener("click", () => {
    if (saved.has(job.id)) { saved.delete(job.id); toast("Removed from saved jobs"); }
    else { saved.add(job.id); toast("Saved. Find it under Saved."); }
    persist();
    paintSave();
    els.savedN.textContent = String(saved.size);
    saveBtn.classList.remove("pop"); void saveBtn.offsetWidth; saveBtn.classList.add("pop");
  });

  const applyLink = el("a", "apply");
  applyLink.href = job.url;
  applyLink.target = "_blank";
  applyLink.rel = "noopener";
  const paintApply = () => {
    const done = applied.has(job.id);
    applyLink.classList.toggle("is-applied", done);
    applyLink.replaceChildren(done ? "Applied" : "Apply");
    applyLink.insertAdjacentHTML("beforeend", icon(done ? "check" : "external"));
    applyLink.setAttribute("aria-label", `${done ? "Applied — open again" : "Apply"}: ${title} at ${company} (opens the original post in a new tab)`);
  };
  paintApply();
  applyLink.addEventListener("click", () => {
    if (!applied.has(job.id)) { applied.add(job.id); persist(); setTimeout(paintApply, 300); }
  });

  side.append(applyLink);
  if (job.source === "adzuna" || (job.sources || []).includes("adzuna")) {
    const badge = el("a", "adzuna-badge");
    badge.href = "https://www.adzuna.in";
    badge.target = "_blank";
    badge.rel = "noopener";
    badge.append("Jobs by", el("b", null, "Adzuna"));
    side.append(badge);
  }
  side.append(saveBtn);

  // Details (opened from the title).
  const details = el("div", "job-details");
  details.id = detailsId;
  details.hidden = !openDetails.has(job.id);
  const desc = tidyText(job.description || "");
  details.append(el("p", null, desc ? (desc.length > 600 ? desc.slice(0, 600).replace(/\s+\S*$/, "") + "…" : desc) : "No description was given. Open the original post for details."));
  const posted = job.posted_at ? `Posted ${fmtDay(job.posted_at, { day: "numeric", month: "long", year: "numeric" })}` : "Posting date not given";
  const facts = el("p", "job-source", `${posted} on ${SOURCE_NAMES[job.source] || job.source}.`);
  if (job.location_raw && !/^india$/i.test(job.location_raw.trim())) facts.append(` Location: ${job.location_raw}.`);
  const actions = el("div", "details-actions");
  const share = el("button", "details-share", "Share");
  share.type = "button";
  share.insertAdjacentHTML("afterbegin", icon("share"));
  share.addEventListener("click", async () => {
    const text = `${title} at ${company}`;
    try {
      if (navigator.share) { await navigator.share({ title: text, text, url: job.url }); return; }
      await navigator.clipboard.writeText(`${text}: ${job.url}`);
      toast("Link copied");
    } catch { /* share sheet closed */ }
  });
  actions.append(share);
  details.append(facts, actions);

  toggle.addEventListener("click", () => {
    const open = details.hidden;
    details.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    if (open) openDetails.add(job.id); else openDetails.delete(job.id);
  });

  li.append(logoBox(job, company), h, side, meta, details);
  return li;
}

function renderMore() {
  const slice = matches.slice(shown, shown + PAGE_SIZE);
  let section = els.jobs.lastElementChild;
  let list = section ? section.querySelector(".jobs") : null;
  let currentKey = section ? section.dataset.key : null;

  for (const job of slice) {
    const g = dayGroup(job);
    if (g.key !== currentKey) {
      section = el("section", `day day-${g.key}`);
      section.dataset.key = g.key;
      const total = matches.filter((j) => dayGroup(j).key === g.key).length;
      const head = el("h2", "day-head");
      head.append(el("span", null, g.label), el("span", "day-n", `${total} ${total === 1 ? "job" : "jobs"}`));
      list = el("ul", "jobs");
      section.append(head, list);
      els.jobs.append(section);
      currentKey = g.key;
    }
    list.append(jobRow(job, g.key));
  }
  shown += slice.length;
  const left = matches.length - shown;
  els.more.hidden = left <= 0;
  els.more.textContent = `Show ${Math.min(left, PAGE_SIZE)} more jobs`;
}

// ---------- greeting (follows India time, whatever the visitor's own time zone) ----------
function greetingForIST(date = new Date()) {
  const hour = Number(new Intl.DateTimeFormat("en-GB", { hour: "numeric", hourCycle: "h23", timeZone: "Asia/Kolkata" }).format(date));
  if (hour >= 5 && hour < 12) return "Good morning";
  if (hour >= 12 && hour < 17) return "Good afternoon";
  return "Good evening";   // 5 pm – 5 am ("Good night" is a goodbye, not a greeting)
}

function setupGreeting() {
  const title = $("hero-title");
  if (!title) return;
  const update = () => { const g = greetingForIST(); if (title.textContent !== g) title.textContent = g; };
  update();
  setInterval(update, 60 * 1000);   // switches over by itself if the page stays open
}

// ---------- hero background video ----------
// Plays (muted, looping) unless the visitor prefers reduced motion or has data saver on —
// then the still poster frame is shown. The pause button lets anyone stop it.
function setupHeroVideo() {
  const video = $("hero-video");
  const btn = $("hero-pause");
  if (!video || !btn) return;
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const saveData = navigator.connection && navigator.connection.saveData;

  const paint = () => {
    const paused = video.paused;
    btn.setAttribute("aria-pressed", String(paused));
    btn.setAttribute("aria-label", paused ? "Play background animation" : "Pause background animation");
  };
  const play = () => { video.preload = "auto"; return video.play().catch(() => {}).finally(paint); };

  btn.hidden = false;
  btn.addEventListener("click", () => {
    if (video.paused) { play(); store.set("fjr.heroPaused", false); }
    else { video.pause(); store.set("fjr.heroPaused", true); }
  });
  video.addEventListener("play", paint);
  video.addEventListener("pause", paint);

  if (!reduceMotion && !saveData && !store.get("fjr.heroPaused", false)) play();
  else paint();
}

// ---------- start ----------

async function init() {
  setupGreeting();
  setupHeroVideo();
  let data;
  try {
    const res = await fetch("jobs.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(res.status);
    data = await res.json();
  } catch (err) {
    els.meta.textContent = "The job list couldn't be loaded. Refresh the page to try again.";
    els.heroLede.textContent = "The job list couldn't be loaded. Refresh the page to try again.";
    return;
  }

  taxonomy = data.taxonomy || taxonomy;
  const updatedIST = data.updated_at
    ? new Date(data.updated_at).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" })   // YYYY-MM-DD
    : new Date().toISOString().slice(0, 10);
  refDay = dayNumber(updatedIST);

  allJobs = (data.jobs || []).map((j) => ({
    ...j,
    _city: j.city || j.city_from_location || null,      // LLM city, else read from the location text
    _intern: INTERN_RE.test(j.title),
    _haystack: `${j.title} ${j.company} ${j.description || ""}`.toLowerCase(),
  }));

  // Top bar: freshness.
  const when = data.updated_at ? new Date(data.updated_at).toLocaleString("en-IN", {
    day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata",
  }) : "unknown";
  els.meta.textContent = `Updated ${when} IST`;

  // Hero: today's numbers + "since your last visit".
  const newToday = allJobs.filter((j) => j.posted_at && dayNumber(j.posted_at) >= refDay).length;
  const lastVisit = store.get("fjr.lastVisitDay", null);
  const sinceLast = lastVisit != null && lastVisit < refDay
    ? allJobs.filter((j) => j.posted_at && dayNumber(j.posted_at) > lastVisit).length : 0;
  store.set("fjr.lastVisitDay", refDay);
  const lede = [];
  lede.push(newToday
    ? `${newToday} new fresher jobs and internships landed today, out of ${allJobs.length} open across India.`
    : `${allJobs.length} fresher jobs and internships open across India.`);
  if (sinceLast) lede.push(`${sinceLast} are new since your last visit.`);
  els.heroLede.textContent = lede.join(" ");

  const p = new URLSearchParams(location.search);
  els.q.value = p.get("q") || "";
  els.intern.checked = p.get("intern") === "1";
  showSaved = p.get("saved") === "1";
  apply();                          // builds the category list and city options
  if (typeof enhanceSelect === "function") cityDropdown = enhanceSelect(els.city);
  setRadio("role", p.get("role") || "");
  setCity(p.get("city") || "");
  apply();

  els.q.addEventListener("input", debounce(apply, 150));
  els.intern.addEventListener("change", apply);
  els.form.addEventListener("change", (e) => {
    if (e.target.type !== "radio" && e.target !== els.city) return;
    apply();
    if (e.target.name === "role") scrollToResults();
  });
  els.form.addEventListener("submit", (e) => { e.preventDefault(); apply(); scrollToResults(); });
  els.emptyClear.addEventListener("click", () => { clearAll(); els.q.focus(); });
  els.more.addEventListener("click", renderMore);
  $("category-reset").addEventListener("click", () => { setRadio("role", ""); apply(); els.resultsTitle.focus(); });
  els.savedToggle.addEventListener("click", () => { showSaved = !showSaved; apply(); });

  // Phones: categories open as a bottom sheet.
  const setSheet = (open) => {
    els.sidebar.classList.toggle("is-open", open);
    els.toggle.setAttribute("aria-expanded", String(open));
    document.body.style.overflow = open ? "hidden" : "";
    if (open) (els.sidebar.querySelector("input:checked") || els.sidebar).focus();
    else els.toggle.focus();
  };
  els.toggle.addEventListener("click", () => setSheet(!els.sidebar.classList.contains("is-open")));
  $("sheet-done").addEventListener("click", () => { setSheet(false); scrollToResults(); });
  $("sheet-backdrop").addEventListener("click", () => setSheet(false));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && els.sidebar.classList.contains("is-open")) setSheet(false);
    if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) {
      e.preventDefault();
      els.q.focus();
    }
  });
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

init();
