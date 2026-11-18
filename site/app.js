// Fresher Jobs Radar — loads jobs.json and filters it in the browser. No backend.
"use strict";

const PAGE_SIZE = 40;
const INTERN_RE = /\b(intern|interns|internship|internships|apprentice|apprenticeship)\b/i;
const SOURCE_NAMES = { adzuna: "Adzuna", greenhouse: "company careers page", lever: "company careers page" };

const $ = (id) => document.getElementById(id);
const els = {
  form: $("filters"), q: $("q"), role: $("role"), city: $("city"), intern: $("intern"),
  clear: $("clear"), meta: $("meta"), count: $("count"), list: $("jobs"),
  empty: $("empty"), emptyClear: $("empty-clear"), more: $("more"), tpl: $("job-tpl"),
};

let dropdowns = [];   // custom menus built from the Role / City selects (dropdown.js)
let allJobs = [];
let matches = [];
let shown = 0;

// ---------- helpers ----------

const fmtDate = (iso, opts) => new Date(iso).toLocaleDateString("en-IN", opts);

function relativeDay(iso) {
  if (!iso) return "";
  const days = Math.round((Date.now() - new Date(iso + "T00:00:00").getTime()) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  return fmtDate(iso, { day: "numeric", month: "short", year: "numeric" });
}

function snippet(text, max = 220) {
  if (!text) return "";
  return text.length > max ? text.slice(0, max).replace(/\s+\S*$/, "") + "…" : text;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;   // textContent only — job data is never parsed as HTML
  return node;
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// ---------- filters <-> URL (so a filtered view can be shared) ----------

function readFilters() {
  return {
    q: els.q.value.trim(),
    role: els.role.value,
    city: els.city.value,
    intern: els.intern.checked,
  };
}

function writeUrl(f) {
  const p = new URLSearchParams();
  if (f.q) p.set("q", f.q);
  if (f.role) p.set("role", f.role);
  if (f.city) p.set("city", f.city);
  if (f.intern) p.set("intern", "1");
  const qs = p.toString();
  history.replaceState(null, "", qs ? `?${qs}` : location.pathname);
}

function readUrl() {
  const p = new URLSearchParams(location.search);
  els.q.value = p.get("q") || "";
  els.role.value = p.get("role") || "";
  els.city.value = p.get("city") || "";
  els.intern.checked = p.get("intern") === "1";
}

// ---------- filtering ----------

function matchesFilters(job, f, terms) {
  if (f.role && job.role !== f.role) return false;
  if (f.city && job.city !== f.city) return false;
  if (f.intern && !job._intern) return false;
  return terms.every((t) => job._haystack.includes(t));
}

function apply() {
  const f = readFilters();
  const terms = f.q.toLowerCase().split(/\s+/).filter(Boolean);
  matches = allJobs.filter((j) => matchesFilters(j, f, terms));
  writeUrl(f);
  els.clear.disabled = !(f.q || f.role || f.city || f.intern);
  dropdowns.forEach((d) => d.sync());   // show the current value in the custom menus

  els.list.replaceChildren();
  shown = 0;
  renderMore();

  const n = matches.length;
  els.count.textContent = n === allJobs.length
    ? `Showing all ${n} jobs, newest first`
    : `${n} of ${allJobs.length} jobs match`;
  els.empty.hidden = n !== 0;
}

// ---------- rendering ----------

function card(job) {
  const node = els.tpl.content.firstElementChild.cloneNode(true);

  node.querySelector(".job-title").textContent = job.title;

  const company = node.querySelector(".job-company");
  company.append(el("strong", null, job.company));
  if (job.location_raw) company.append(` · ${job.location_raw}`);

  const chips = node.querySelector(".chips");
  if (job.role && job.role !== "Other") chips.append(el("li", "chip chip-role", job.role));
  if (job.city && job.city !== "Other India") chips.append(el("li", "chip chip-city", job.city));
  if (job._intern) chips.append(el("li", "chip chip-intern", "Internship"));
  if (!chips.children.length) chips.remove();

  const snip = node.querySelector(".job-snippet");
  const text = snippet(job.description);
  if (text) snip.textContent = text; else snip.remove();

  const when = node.querySelector(".job-when");
  const posted = job.posted_at ? `Posted ${relativeDay(job.posted_at)}` : "Date not given";
  when.textContent = `${posted} · via ${SOURCE_NAMES[job.source] || job.source}`;
  if (job.posted_at) when.title = fmtDate(job.posted_at, { day: "numeric", month: "long", year: "numeric" });

  const applyLink = node.querySelector(".apply");
  applyLink.href = job.url;
  applyLink.querySelector(".visually-hidden").textContent =
    ` to ${job.title} at ${job.company} (opens original post in a new tab)`;

  if (job.source === "adzuna" || (job.sources || []).includes("adzuna")) {
    const badge = el("a", "adzuna-badge");
    badge.href = "https://www.adzuna.in";
    badge.target = "_blank";
    badge.rel = "noopener";
    badge.append("Jobs by", el("b", null, "Adzuna"));
    badge.setAttribute("aria-label", "Jobs by Adzuna (opens adzuna.in)");
    node.querySelector(".job-actions").prepend(badge);
  }
  return node;
}

function renderMore() {
  const frag = document.createDocumentFragment();
  matches.slice(shown, shown + PAGE_SIZE).forEach((j) => frag.append(card(j)));
  els.list.append(frag);
  shown = Math.min(shown + PAGE_SIZE, matches.length);
  const left = matches.length - shown;
  els.more.hidden = left <= 0;
  els.more.textContent = `Show ${Math.min(left, PAGE_SIZE)} more (${left} left)`;
}

function fillSelect(select, values, counts) {
  for (const v of values) {
    const n = counts[v] || 0;
    const opt = el("option", null, n ? `${v} (${n})` : v);
    opt.value = v;
    opt.dataset.label = v;       // the custom menu shows the name and count separately
    opt.dataset.count = n;
    select.append(opt);
  }
}

function countBy(jobs, key) {
  const c = {};
  for (const j of jobs) if (j[key]) c[j[key]] = (c[j[key]] || 0) + 1;
  return c;
}

// ---------- start ----------

async function init() {
  let data;
  try {
    const res = await fetch("jobs.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(res.status);
    data = await res.json();
  } catch (err) {
    els.meta.textContent = "Sorry — the job list couldn't be loaded. Please try again later.";
    return;
  }

  allJobs = (data.jobs || []).map((j) => ({
    ...j,
    _intern: INTERN_RE.test(j.title),
    _haystack: `${j.title} ${j.company} ${j.description || ""}`.toLowerCase(),
  }));

  const tax = data.taxonomy || {};
  fillSelect(els.role, tax.roles || Object.keys(countBy(allJobs, "role")).sort(), countBy(allJobs, "role"));
  fillSelect(els.city, tax.cities || Object.keys(countBy(allJobs, "city")).sort(), countBy(allJobs, "city"));

  const updated = data.updated_at ? new Date(data.updated_at).toLocaleString("en-IN", {
    day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit",
    timeZone: "Asia/Kolkata",
  }) : "unknown";
  els.meta.replaceChildren(
    "Last updated: ", el("strong", null, `${updated} IST`),
    " · ", el("strong", null, `${allJobs.length}`), " jobs",
  );

  readUrl();
  if (typeof enhanceSelect === "function") {
    dropdowns = [els.role, els.city].map(enhanceSelect);
  }
  apply();

  els.q.addEventListener("input", debounce(apply, 150));
  els.role.addEventListener("change", apply);
  els.city.addEventListener("change", apply);
  els.intern.addEventListener("change", apply);
  els.form.addEventListener("submit", (e) => { e.preventDefault(); apply(); });
  els.form.addEventListener("reset", () => setTimeout(apply, 0));
  els.emptyClear.addEventListener("click", () => { els.form.reset(); els.q.focus(); });
  els.more.addEventListener("click", renderMore);
}

init();
