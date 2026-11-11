/* Food Diary dashboard — vanilla JS, no dependencies.
   Three tabs: Catalog (browse/search/add), Day log (view + log a day),
   Trends (daily macro chart, same numbers as trend.py). */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

// ---------- shared helpers ----------

const fmt = (v) => {
  if (v === null || v === undefined) return "–";
  const n = Number(v);
  if (Number.isInteger(n)) return String(n);
  return n < 10 ? n.toFixed(1) : String(Math.round(n * 10) / 10);
};

const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const pad = (n) => String(n).padStart(2, "0");
const todayStamp = () => {
  const d = new Date();
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`;
};
const stampToInput = (s) => `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
const inputToStamp = (v) => v.replace(/-/g, "");
const shiftDate = (s, delta) => {
  const d = new Date(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8));
  d.setDate(d.getDate() + delta);
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`;
};

let toastTimer = null;
function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("error", isError);
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3400);
}

async function loadStats() {
  try {
    const r = await fetch("/api/stats");
    const s = await r.json();
    $("#stat-foods").textContent = s.foods;
    $("#stat-days").textContent = s.days;
  } catch { /* non-fatal */ }
}

// ---------- tabs ----------

let currentTab = null;

function showTab(name, pushHash = true) {
  if (!["catalog", "day", "trends"].includes(name)) name = "catalog";
  currentTab = name;
  $$(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$("#panel-catalog, #panel-day, #panel-trends").forEach((p) => {
    p.hidden = p.id !== `panel-${name}`;
  });
  if (pushHash) history.replaceState(null, "", `#${name}`);
  if (name === "day") loadDay(dayStampCur || todayStamp()).catch(onLoadError);
  if (name === "trends" && !trendsLoaded) loadTrends().catch(onLoadError);
}

const onLoadError = (e) => toast(`Load failed: ${e.message}`, true);

// ---------- catalog ----------

let foods = [];
let sortKey = "name";
let sortDir = 1;
let searchTimer = null;

const servingLabel = (f) => {
  const s = Number(f.serving_size);
  if (s === 1) return "1 unit";
  return `${s} g`;
};

async function loadFoods(q = "") {
  const url = q ? `/api/foods?q=${encodeURIComponent(q)}` : "/api/foods";
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  foods = await r.json();
  renderCatalog();
}

function currentRows() {
  const q = $("#search").value.trim().toLowerCase();
  const filtered = q ? foods.filter((f) => f.name.toLowerCase().includes(q)) : foods;
  return filtered.sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    const cmp = typeof av === "number" && typeof bv === "number"
      ? av - bv
      : String(av).localeCompare(String(bv));
    return cmp * sortDir;
  });
}

function renderCatalog() {
  const rows = currentRows();
  const body = $("#food-body");
  body.innerHTML = "";
  for (const f of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</td>
      <td class="num">${servingLabel(f)}</td>
      <td class="num">${fmt(f.calories)}</td>
      <td class="num">${fmt(f.protein)}</td>
      <td class="num">${fmt(f.fat_total)}</td>
      <td class="num">${fmt(f.carbs_total)}</td>
      <td class="num">${fmt(f.fiber_total)}</td>
      <td class="num">${fmt(f.sugars_total)}</td>
      <td class="num">${fmt(f.sodium)}</td>`;
    body.appendChild(tr);
  }
  $("#empty").hidden = rows.length > 0;
  $("#result-count").textContent = `Showing ${rows.length} of ${foods.length} foods`;

  $$("#food-table th.sortable").forEach((th) => {
    th.classList.remove("sorted-asc", "sorted-desc");
    if (th.dataset.key === sortKey) {
      th.classList.add(sortDir === 1 ? "sorted-asc" : "sorted-desc");
    }
  });
}

function onSearchInput() {
  $("#clear-search").hidden = $("#search").value === "";
  renderCatalog(); // instant client-side pass
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    try {
      await loadFoods($("#search").value.trim());
    } catch (e) {
      toast(`Search failed: ${e.message}`, true);
    }
  }, 300);
}

function onSortClick(key) {
  if (sortKey === key) sortDir *= -1;
  else { sortKey = key; sortDir = 1; }
  renderCatalog();
}

// ---------- add-food modal (catalog) ----------
// The .open class is what shows the backdrop; `hidden` is kept in sync.

function openModal() {
  const b = $("#modal-backdrop");
  b.hidden = false;
  b.classList.add("open");
  $("#food-form").reset();
  $("#form-error").hidden = true;
  $("#f-name").focus();
}

function closeModal() {
  const b = $("#modal-backdrop");
  b.classList.remove("open");
  b.hidden = true;
}

async function onSubmit(ev) {
  ev.preventDefault();
  const form = ev.target;
  const payload = {
    name: form.name.value.trim(),
    serving_size: parseFloat(form.serving_size.value),
    calories: parseFloat(form.calories.value),
    protein: parseFloat(form.protein.value || "0"),
    fat_total: parseFloat(form.fat_total.value || "0"),
    carbs_total: parseFloat(form.carbs_total.value || "0"),
    fiber_total: parseFloat(form.fiber_total.value || "0"),
    sugars_total: parseFloat(form.sugars_total.value || "0"),
    sodium: parseFloat(form.sodium.value || "0"),
  };
  const err = $("#form-error");
  err.hidden = true;
  try {
    const r = await fetch("/api/foods", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      let detail;
      try { detail = (await r.json()).detail; } catch { detail = `HTTP ${r.status}`; }
      if (typeof detail === "object") detail = JSON.stringify(detail);
      err.textContent = detail;
      err.hidden = false;
      return;
    }
    closeModal();
    await loadFoods($("#search").value.trim());
    await loadStats();
    toast(`Added “${payload.name}”`);
  } catch (e) {
    err.textContent = `Request failed: ${e.message}`;
    err.hidden = false;
  }
}

// ---------- day log ----------

let dayStampCur = null; // YYYYMMDD of the day currently shown

function unitFor(serving) {
  return Number(serving) === 1 ? "unit" : "g";
}

async function loadDay(stamp) {
  dayStampCur = stamp;
  $("#day-date").value = stampToInput(stamp);
  const r = await fetch(`/api/days/${stamp}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const day = await r.json();
  renderDay(day);
}

function renderDay(day) {
  dayTotalsCur = day.totals;
  $("#tot-cal").textContent = fmt(day.totals.calories);
  $("#tot-protein").textContent = fmt(day.totals.protein);
  $("#tot-fat").textContent = fmt(day.totals.fat);
  $("#tot-carbs").textContent = fmt(day.totals.carbs);

  // supplementary day totals (collapsed panel; brief peek in the summary)
  const supp = day.supplementary || {};
  const suppSet = (id, key) => { $(id).textContent = fmt(supp[key] ?? 0); };
  suppSet("#tot-fiber", "fiber");
  suppSet("#tot-sodium", "sodium");
  suppSet("#tot-satfat", "saturated_fat");
  suppSet("#tot-chol", "cholesterol");
  suppSet("#tot-sugars", "sugars");
  suppSet("#tot-addsugar", "added_sugars");
  $("#supp-brief").textContent =
    `\u2014 fiber ${fmt(supp.fiber ?? 0)} g \u00b7 sodium ${fmt(supp.sodium ?? 0)} mg`;

  // meal name suggestions for the log form
  const dl = $("#meal-names");
  dl.innerHTML = "";
  for (const m of day.meals) {
    const o = document.createElement("option");
    o.value = m.name;
    dl.appendChild(o);
  }

  const wrap = $("#day-meals");
  wrap.innerHTML = "";
  for (const meal of day.meals) {
    const mt = meal.totals || {
      calories: meal.items.reduce((s, i) => s + (i.macros ? i.macros.calories : 0), 0),
      protein: 0, fat: 0, carbs: 0,
    };
    const card = document.createElement("div");
    card.className = "meal-card";
    let rows = "";
    for (const item of meal.items) {
      const unit = item.serving_size ? unitFor(item.serving_size) : "";
      const servings = item.serving_size && item.weight
        ? item.weight / item.serving_size
        : null;
      const servingsTxt = servings !== null
        ? (servings === 1 ? " · 1 serving" : ` · ${fmt(servings)} servings`)
        : "";
      const cal = item.macros ? `${fmt(item.macros.calories)} cal` : "no data";
      rows += `
        <div class="item-row">
          <span class="item-name" title="${escapeHtml(item.food)}">${escapeHtml(item.food)}</span>
          <span class="item-weight">${fmt(item.weight)} ${unit}${servingsTxt}</span>
          <span class="item-cal">${cal}</span>
          <button class="remove-btn" title="Remove this entry"
                  data-food="${escapeHtml(item.food)}" data-meal="${escapeHtml(meal.name)}"
                  data-weight="${item.weight}">✕</button>
        </div>`;
      if (item.macros) {  // per-item macro contribution line
        const m = item.macros;
        rows += `
        <div class="item-contrib">${fmt(m.protein)}P · ${fmt(m.fat)}F · ${fmt(m.carbs)}C
          · ${fmt(m.fiber)} fiber · ${fmt(m.sodium)} mg Na</div>`;
      }
    }
    card.innerHTML = `
      <div class="meal-head">
        <span>${escapeHtml(meal.name)}</span>
        <span class="meal-cal">${fmt(mt.calories)} cal
          <span class="meal-macros">${fmt(mt.protein)}P · ${fmt(mt.fat)}F · ${fmt(mt.carbs)}C</span></span>
      </div>
      ${rows}`;
    wrap.appendChild(card);
  }
  $("#day-empty").hidden = day.meals.length > 0;
  renderPlan();
}

async function onLogSubmit(ev) {
  ev.preventDefault();
  const food = $("#log-food").value.trim();
  const weight = parseFloat($("#log-weight").value);
  const meal = $("#log-meal").value.trim() || "Miscellaneous";
  const hint = $("#log-hint");
  const err = (msg) => { hint.textContent = msg; hint.classList.add("error"); };
  if (!food) return err("Pick a food from the search list.");
  if (!isFinite(weight) || weight < 0) return err("Enter a weight (one serving is pre-filled).");
  try {
    const r = await fetch(`/api/days/${dayStampCur}/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ food, weight, meal }),
    });
    if (!r.ok) {
      const d = await r.json().catch(() => null);
      return err(d?.detail || `HTTP ${r.status}`);
    }
    hint.textContent = "";
    hint.classList.remove("error");
    const unit = selectedFood ? unitFor(selectedFood.serving) : "";
    toast(`Logged ${fmt(weight)} ${unit} of “${food}” in ${meal}`);
    $("#log-weight").value = selectedFood ? selectedFood.serving : "";
    updateServings();
    await loadDay(dayStampCur);
    await loadStats();
  } catch (e) {
    err(`Request failed: ${e.message}`);
  }
}

async function onRemoveItem(btn) {
  const food = btn.dataset.food;
  const meal = btn.dataset.meal;
  const weight = btn.dataset.weight !== "" ? parseFloat(btn.dataset.weight) : null;
  try {
    const r = await fetch(`/api/days/${dayStampCur}/items`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ food, meal, weight }),
    });
    if (r.status === 409) {
      const d = await r.json().catch(() => null);
      toast(d?.detail || "Multiple entries match — use the CLI: python log.py remove … --weight N", true);
      return;
    }
    if (!r.ok) {
      const d = await r.json().catch(() => null);
      toast(d?.detail || `HTTP ${r.status}`, true);
      return;
    }
    toast(`Removed “${food}” from ${meal}`);
    await loadDay(dayStampCur);
    await loadStats();
  } catch (e) {
    toast(`Remove failed: ${e.message}`, true);
  }
}

// ---------- what-if basket (Day tab) ----------
// A staging area: items live in localStorage (never in the diary DB) and
// the server tallies them via POST /api/what-if. An item enters the real
// diary only when you press Log (normal POST /api/days/{date}/items).

const PLAN_KEY = "food_di..._v1";
let plan = loadPlan();       // [{food, weight}]
let planTally = null;        // last /api/what-if response
let dayTotalsCur = { calories: 0, protein: 0, fat: 0, carbs: 0 };

function loadPlan() {
  try {
    const raw = JSON.parse(localStorage.getItem(PLAN_KEY) || "[]");
    return Array.isArray(raw)
      ? raw.filter((p) => p && typeof p.food === "string" && p.food
          && Number.isFinite(p.weight) && p.weight > 0)
      : [];
  } catch { return []; }
}
const savePlan = () => localStorage.setItem(PLAN_KEY, JSON.stringify(plan));

async function refreshPlanTally() {
  if (!plan.length) { planTally = null; renderPlan(); return; }
  try {
    const r = await fetch("/api/what-if", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: plan }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    planTally = await r.json();
  } catch (e) {
    planTally = null;
    toast(`Basket tally failed: ${e.message}`, true);
  }
  renderPlan();
}

function renderPlan() {
  const rowsEl = $("#plan-rows");
  const foot = $("#plan-foot");
  if (!rowsEl) return;
  rowsEl.innerHTML = "";
  if (!plan.length) { foot.hidden = true; return; }
  foot.hidden = false;
  const tallied = planTally ? planTally.items : [];
  plan.forEach((p, i) => {
    const t = tallied[i];
    let macrosTxt, cal;
    if (!t || t.stub) {
      macrosTxt = t && t.stub ? "not in catalog" : "…";
      cal = "–";
    } else {
      const m = t.macros;
      macrosTxt = `${fmt(m.protein)}P · ${fmt(m.fat)}F · ${fmt(m.carbs)}C` +
        (m.sodium ? ` · ${fmt(m.sodium)}mg Na` : "");
      cal = `${fmt(m.calories)} cal`;
    }
    const tag = p.nutrition
      ? ' <span class="adhoc-tag" title="rough estimate — not in the catalog yet">est.</span>'
      : "";
    const row = document.createElement("div");
    row.className = "item-row plan-item-row";
    row.innerHTML = `
      <span class="item-name" title="${escapeHtml(p.food)}">${escapeHtml(p.food)}${tag}</span>
      <span class="item-weight">${fmt(p.weight)}</span>
      <span class="item-cal">${cal}</span>
      <span class="plan-macros">${macrosTxt}</span>
      <button class="btn small plan-log-btn" data-index="${i}" title="Log this item into the day">Log</button>
      <button class="remove-btn" data-index="${i}" title="Drop from basket">✕</button>`;
    rowsEl.appendChild(row);
  });
  const tot = planTally
    ? planTally.totals
    : { calories: 0, protein: 0, fat: 0, carbs: 0, sodium: 0 };
  $("#plan-cal").textContent = fmt(tot.calories);
  $("#plan-protein").textContent = fmt(tot.protein);
  $("#plan-fat").textContent = fmt(tot.fat);
  $("#plan-carbs").textContent = fmt(tot.carbs);
  $("#plan-sodium").textContent = fmt(tot.sodium);
  $("#plan-vs").textContent = planTally
    ? `This day so far: ${fmt(dayTotalsCur.calories)} cal → ` +
      `${fmt(dayTotalsCur.calories + tot.calories)} cal if the basket is logged.`
    : "";
}

async function onPlanAdd(ev) {
  ev.preventDefault();
  const food = planPicked ? planPicked.name : $("#plan-food").value.trim();
  const weight = parseFloat($("#plan-weight").value);
  const hint = $("#plan-hint");
  const err = (msg) => { hint.textContent = msg; hint.classList.add("error"); };
  if (!food) return err("Pick a food from the search list.");
  if (!isFinite(weight) || weight <= 0) return err("Enter a weight (one serving is pre-filled).");
  hint.textContent = "";
  hint.classList.remove("error");
  plan.push({ food, weight });
  savePlan();
  $("#plan-food").value = "";
  $("#plan-weight").value = "";
  $("#plan-unit").textContent = "";
  planPicked = null;
  await refreshPlanTally();
}

// ad-hoc estimates: rough per-serving macros typed in for a food that is
// NOT yet in the catalog. Tallying stays a pure what-if — the estimate is
// visible first, and nothing is stored until (and unless) it is logged.
function adhocPayload() {
  const num = (id) => {
    const v = parseFloat($(id).value);
    return Number.isFinite(v) && v >= 0 ? v : 0;
  };
  return {
    name: $("#adhoc-name").value.trim(),
    serving_size: parseFloat($("#adhoc-serving").value),
    calories: parseFloat($("#adhoc-cal").value),
    protein: num("#adhoc-protein"),
    fat_total: num("#adhoc-fat"),
    carbs_total: num("#adhoc-carbs"),
    fiber_total: num("#adhoc-fiber"),
    sodium: num("#adhoc-sodium"),
  };
}

async function onAdhocAdd(ev) {
  ev.preventDefault();
  const hint = $("#adhoc-hint");
  const err = (msg) => { hint.textContent = msg; hint.classList.add("error"); };
  const p = adhocPayload();
  const weight = parseFloat($("#adhoc-weight").value);
  if (!p.name) return err("Give the estimate a name.");
  if (!isFinite(p.serving_size) || p.serving_size <= 0) return err("Serving size must be more than 0 g.");
  if (!isFinite(p.calories) || p.calories < 0) return err("Enter calories per serving (0 is allowed).");
  if (!isFinite(weight) || weight <= 0) return err("Enter an amount in grams.");
  try {
    const r = await fetch(`/api/foods?q=${encodeURIComponent(p.name)}&limit=50`);
    if (r.ok) {
      const rows = await r.json();
      if (rows.some((row) => row.name === p.name)) {
        return err(`“${p.name}” is already in the catalog — add it from the catalog search instead.`);
      }
    }
  } catch { /* offline: proceed, the Log step will surface the error */ }
  plan.push({ food: p.name, weight, nutrition: p });
  savePlan();
  hint.textContent = "";
  hint.classList.remove("error");
  for (const id of ["#adhoc-name", "#adhoc-cal", "#adhoc-weight"]) $(id).value = "";
  $("#adhoc-details").open = false;  // collapsed again; basket keeps the estimate
  await refreshPlanTally();
}

// Shared log path: an ad-hoc item first creates its catalog entry (the
// moment rough macros become real data), then logs like any other item.
async function logBasketItem(item) {
  const meal = $("#plan-meal").value.trim() || "Miscellaneous";
  let alreadyInCatalog = false;
  if (item.nutrition) {
    const rF = await fetch("/api/foods", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(item.nutrition),
    });
    if (rF.status === 409) alreadyInCatalog = true;  // catalog copy wins
    else if (!rF.ok) {
      const d = await rF.json().catch(() => null);
      return { ok: false, detail: d?.detail || `HTTP ${rF.status}` };
    }
  }
  const r = await fetch(`/api/days/${dayStampCur}/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ food: item.food, weight: item.weight, meal }),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => null);
    return { ok: false, detail: d?.detail || `HTTP ${r.status}` };
  }
  return { ok: true, meal, alreadyInCatalog };
}

async function planLogItem(index) {
  const item = plan[index];
  if (!item) return;
  try {
    const res = await logBasketItem(item);
    if (!res.ok) return toast(res.detail || "Log failed", true);
    plan.splice(index, 1);
    savePlan();
    let note = "";
    if (item.nutrition) {
      note = res.alreadyInCatalog
        ? " (already in catalog — day shows its values, not your estimate)"
        : " (estimate saved to catalog)";
    }
    toast(`Logged ${fmt(item.weight)} of “${item.food}” in ${res.meal}${note}`);
    await refreshPlanTally();
    await loadDay(dayStampCur);
    await loadStats();
  } catch (e) {
    toast(`Log failed: ${e.message}`, true);
  }
}

async function planLogAll() {
  let ok = 0;
  const failed = [];
  for (const item of [...plan]) {
    let res;
    try { res = await logBasketItem(item); } catch (e) { res = { ok: false, detail: e.message }; }
    if (res.ok) {
      const i = plan.indexOf(item);
      if (i >= 0) plan.splice(i, 1);
      ok++;
    } else {
      failed.push(`${item.food} (${res.detail})`);
    }
  }
  savePlan();
  if (ok) toast(`Logged ${ok} basket item(s) into ${$("#plan-meal").value.trim() || "Miscellaneous"}`);
  if (failed.length) toast(`Not logged: ${failed.join(", ")}`, true);
  await refreshPlanTally();
  if (ok) {
    await loadDay(dayStampCur);
    await loadStats();
  }
}

// basket autocomplete — same catalog search as the log form
let planACTimer = null;
let planPicked = null;

function hidePlanAC() { $("#plan-ac-list").hidden = true; }

function onPlanFoodInput() {
  planPicked = null;
  hidePlanAC();
  $("#plan-unit").textContent = "";
  const q = $("#plan-food").value.trim();
  if (!q) return;
  clearTimeout(planACTimer);
  planACTimer = setTimeout(async () => {
    try {
      const r = await fetch(`/api/foods?q=${encodeURIComponent(q)}&limit=12`);
      if (!r.ok) return;
      renderPlanAC(await r.json());
    } catch { /* ignore */ }
  }, 200);
}

function renderPlanAC(rows) {
  const list = $("#plan-ac-list");
  if (!rows.length) { hidePlanAC(); return; }
  list.innerHTML = "";
  for (const row of rows) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "ac-item";
    b.innerHTML = `${escapeHtml(row.name)}<span class="ac-cal">${fmt(row.calories)} cal / ${servingLabel(row)}</span>`;
    b.addEventListener("click", () => pickPlanFood(row.name, Number(row.serving_size)));
    list.appendChild(b);
  }
  list.hidden = false;
}

function pickPlanFood(name, serving) {
  planPicked = { name, serving };
  $("#plan-food").value = name;
  hidePlanAC();
  $("#plan-weight").value = serving; // default: one serving, like log.py
  $("#plan-unit").textContent = unitFor(serving);
  $("#plan-weight").focus();
}

// food autocomplete in the log form (searches the catalog DB)
let acTimer = null;
let selectedFood = null; // {name, serving}

function hideAC() { $("#ac-list").hidden = true; }

function onLogFoodInput() {
  selectedFood = null;
  hideAC();
  $("#log-unit").textContent = "";
  updateServings();
  const q = $("#log-food").value.trim();
  if (!q) return;
  clearTimeout(acTimer);
  acTimer = setTimeout(async () => {
    try {
      const r = await fetch(`/api/foods?q=${encodeURIComponent(q)}&limit=12`);
      if (!r.ok) return;
      renderAC(await r.json());
    } catch { /* ignore */ }
  }, 200);
}

function renderAC(rows) {
  const list = $("#ac-list");
  if (!rows.length) { hideAC(); return; }
  list.innerHTML = "";
  for (const row of rows) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "ac-item";
    b.innerHTML = `${escapeHtml(row.name)}<span class="ac-cal">${fmt(row.calories)} cal / ${servingLabel(row)}</span>`;
    b.addEventListener("click", () => pickFood(row.name, Number(row.serving_size)));
    list.appendChild(b);
  }
  list.hidden = false;
}

function pickFood(name, serving) {
  selectedFood = { name, serving };
  $("#log-food").value = name;
  hideAC();
  $("#log-weight").value = serving; // default: one serving, like log.py
  $("#log-unit").textContent = unitFor(serving);
  updateServings();
  $("#log-weight").focus();
}

function updateServings() {
  if (!selectedFood) return;
  const w = parseFloat($("#log-weight").value);
  if (!isFinite(w) || w < 0) return;
  const n = w / selectedFood.serving;
  $("#log-unit").textContent = unitFor(selectedFood.serving);
  const el = $("#log-hint");
  el.classList.remove("error");
  el.textContent = n === 1 ? "One serving." : `≈ ${n < 10 ? n.toFixed(1) : Math.round(n)} serving(s) of ${selectedFood.name}.`;
}

// ---------- trends ----------

let trendsLoaded = false;
let trendDays = [];
let trendTargets = [1800, 2000];
let proteinTarget = 100;

const SERIES = {
  cal: [{ key: "calories", label: "Calories", color: "#2f9e55" }],
  macro: [
    { key: "protein", label: "Protein (g)", color: "#3b82c4" },
    { key: "fat", label: "Fat (g)", color: "#e0a13c" },
    { key: "carbs", label: "Carbs (g)", color: "#c9564f" },
  ],
};

function setTrendRange(days, markPreset) {
  const d = new Date();
  if (days === "all") {
    $("#trend-from").value = "2020-01-01";
  } else {
    d.setDate(d.getDate() - Number(days));
    $("#trend-from").value = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }
  const t = new Date();
  $("#trend-to").value = `${t.getFullYear()}-${pad(t.getMonth() + 1)}-${pad(t.getDate())}`;
  $$(".presets .btn").forEach((b) =>
    b.classList.toggle("active", markPreset && b.dataset.days === String(days)));
}

async function loadTrends() {
  trendsLoaded = true;
  const from = inputToStamp($("#trend-from").value);
  const to = inputToStamp($("#trend-to").value);
  if (!/^\d{8}$/.test(from) || !/^\d{8}$/.test(to)) {
    $("#chart-note").textContent = "Pick both dates first.";
    $("#chart-cal").innerHTML = "";
    $("#chart-macro").innerHTML = "";
    return;
  }
  const [r, s] = await Promise.all([
    fetch(`/api/trends?from=${from}&to=${to}`),
    fetch("/api/settings").catch(() => null),
  ]);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  if (s && s.ok) {
    const saved = await s.json();
    const t = Array.isArray(saved.trend_targets) ? saved.trend_targets.map(Number) : null;
    trendTargets = t && t.length ? t : [1800, 2000];
    syncTargetInputs();
    proteinTarget = typeof saved.protein_target === "number" ? saved.protein_target : 100;
    $("#trend-protein-target").value = proteinTarget;
  }
  const data = await r.json();
  trendDays = data.days;
  drawTrends(trendDays);
}

function syncTargetInputs() {
  $("#trend-target-1").value = trendTargets[0] ?? "";
  $("#trend-target-2").value = trendTargets[1] ?? "";
}

async function saveTrendTargets() {
  const vals = [$("#trend-target-1").value, $("#trend-target-2").value]
    .map((v) => parseFloat(v))
    .filter((v) => Number.isFinite(v) && v >= 0);
  const pt = parseFloat($("#trend-protein-target").value);
  const protein = Number.isFinite(pt) && pt >= 0 ? pt : null;
  trendTargets = vals;
  proteinTarget = protein ?? 0;
  drawTrends(trendDays);
  try {
    const r = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trend_targets: vals, protein_target: protein }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
  } catch (e) {
    toast(`Saving targets failed: ${e.message}`, true);
  }
}

function drawLineChart(days, seriesList, minSpan = 1, targets = [], unit = "") {
  const W = 940, H = 300;
  const padL = 52, padR = 18, padT = 14, padB = 38;
  const iw = W - padL - padR, ih = H - padT - padB;
  const maxV = Math.max(
    ...days.map((d) => Math.max(...seriesList.map((s) => d[s.key]))),
    ...targets,
    minSpan,
  ) * 1.1;
  const x = (i) => padL + (days.length === 1 ? iw / 2 : (i * iw) / (days.length - 1));
  const y = (v) => padT + ih * (1 - v / maxV);

  let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Line chart">`;
  for (let g = 0; g <= 4; g++) {
    const v = (maxV / 4) * g, yy = y(v);
    svg += `<line x1="${padL}" y1="${yy.toFixed(1)}" x2="${W - padR}" y2="${yy.toFixed(1)}" class="grid"/>`;
    svg += `<text x="${padL - 8}" y="${(yy + 4).toFixed(1)}" text-anchor="end" class="tick">${Math.round(v)}</text>`;
  }
  // x/y axis lines
  svg += `<line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + ih}" class="axis"/>`;
  svg += `<line x1="${padL}" y1="${padT + ih}" x2="${W - padR}" y2="${padT + ih}" class="axis"/>`;
  // dotted horizontal target lines (lower target gets a calmer color)
  const shown = targets.filter((t) => t > 0).sort((a, b) => a - b);
  shown.forEach((t, idx) => {
    const yy = y(t);
    const cls = idx === 0 ? "target low" : "target";
    svg += `<line x1="${padL}" y1="${yy.toFixed(1)}" x2="${W - padR}" y2="${yy.toFixed(1)}" class="${cls}" stroke-dasharray="7 5"/>`;
    svg += `<text x="${W - padR - 6}" y="${(yy - 5).toFixed(1)}" text-anchor="end" class="${idx === 0 ? "target-label low" : "target-label"}">${t}</text>`;
  });
  const step = Math.max(1, Math.ceil(days.length / 7));
  for (let i = 0; i < days.length; i += step) {
    const d = days[i].date;
    svg += `<text x="${x(i).toFixed(1)}" y="${H - padB + 18}" text-anchor="middle" class="tick">${d.slice(4, 6)}-${d.slice(6, 8)}</text>`;
  }
  for (const s of seriesList) {
    const pts = days.map((d, i) => `${x(i).toFixed(1)},${y(d[s.key]).toFixed(1)}`).join(" ");
    svg += `<polyline points="${pts}" fill="none" stroke="${s.color}" stroke-width="2"/>`;
    if (days.length <= 120) {
      svg += days.map((d, i) =>
        `<circle cx="${x(i).toFixed(1)}" cy="${y(d[s.key]).toFixed(1)}" r="2.5" fill="${s.color}" ` +
        `data-date="${d.date}" data-label="${s.label}" data-value="${d[s.key]} ${unit}"/>`).join("");
    }
  }
  svg += "</svg>";
  return svg;
}

function drawTrends(days) {
  const legendFor = (el, seriesList) => {
    el.innerHTML = seriesList
      .map((s) => `<span><i style="background:${s.color}"></i>${s.label}</span>`).join("");
  };
  legendFor($("#chart-legend-cal"), SERIES.cal);
  legendFor($("#chart-legend-macro"), SERIES.macro);

  if (!days.length) {
    $("#chart-cal").innerHTML = "";
    $("#chart-macro").innerHTML = "";
    $("#chart-note").textContent = "No logged days in this range.";
    return;
  }
  $("#chart-cal").innerHTML = drawLineChart(days, SERIES.cal, 1, trendTargets, "cal");
  $("#chart-macro").innerHTML = drawLineChart(days, SERIES.macro, 50, proteinTarget > 0 ? [proteinTarget] : [], "g");
  $("#chart-note").textContent =
    `${days.length} logged day(s). Days with no meals are omitted.`;
}

// ---------- wiring ----------

document.addEventListener("DOMContentLoaded", () => {
  // tabs
  $$(".tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  window.addEventListener("hashchange", () => {
    const h = location.hash.slice(1);
    if (["catalog", "day", "trends"].includes(h) && h !== currentTab) showTab(h, false);
  });

  // catalog
  $("#add-btn").addEventListener("click", openModal);
  $("#modal-close").addEventListener("click", closeModal);
  $("#modal-cancel").addEventListener("click", closeModal);
  $("#modal-backdrop").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("#modal-backdrop").hidden) closeModal();
  });
  $("#food-form").addEventListener("submit", onSubmit);
  $("#search").addEventListener("input", onSearchInput);
  $("#clear-search").addEventListener("click", () => {
    $("#search").value = "";
    onSearchInput();
    $("#search").focus();
  });
  $$("#food-table th.sortable").forEach((th) => {
    th.addEventListener("click", () => onSortClick(th.dataset.key));
  });

  // day log
  const bumpDay = (delta) => {
    const v = inputToStamp($("#day-date").value);
    if (/^\d{8}$/.test(v)) loadDay(shiftDate(v, delta)).catch(onLoadError);
  };
  $("#day-prev").addEventListener("click", () => bumpDay(-1));
  $("#day-next").addEventListener("click", () => bumpDay(1));
  $("#day-date").addEventListener("change", () => {
    const v = inputToStamp($("#day-date").value);
    if (/^\d{8}$/.test(v)) loadDay(v).catch(onLoadError);
    else toast("Pick a valid date (YYYY-MM-DD).", true);
  });
  $("#day-today").addEventListener("click", () => loadDay(todayStamp()).catch(onLoadError));
  $("#log-form").addEventListener("submit", onLogSubmit);
  $("#log-food").addEventListener("input", onLogFoodInput);
  $("#log-food").addEventListener("blur", () => setTimeout(hideAC, 150));
  $("#log-weight").addEventListener("input", updateServings);
  $("#day-meals").addEventListener("click", (e) => {
    const b = e.target.closest(".remove-btn");
    if (b) onRemoveItem(b);
  });

  // what-if basket
  $("#plan-form").addEventListener("submit", onPlanAdd);
  $("#plan-food").addEventListener("input", onPlanFoodInput);
  $("#plan-food").addEventListener("blur", () => setTimeout(hidePlanAC, 150));
  $("#adhoc-details").addEventListener("toggle", () => {
    if ($("#adhoc-details").open) $("#adhoc-name").focus();
  });
  $("#adhoc-form").addEventListener("submit", onAdhocAdd);
  $("#plan-log-all").addEventListener("click", planLogAll);
  $("#plan-clear").addEventListener("click", async () => {
    plan = [];
    savePlan();
    await refreshPlanTally();
  });
  $("#plan-rows").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-index]");
    if (!b) return;
    const i = Number(b.dataset.index);
    if (b.classList.contains("plan-log-btn")) planLogItem(i);
    else { plan.splice(i, 1); savePlan(); refreshPlanTally(); }
  });

  // trends
  setTrendRange(7, true);

  // chart hover tooltips (delegated — survives chart redraws)
  const tip = document.createElement("div");
  tip.className = "chart-tip";
  tip.hidden = true;
  document.body.appendChild(tip);
  const moveTip = (e) => {
    tip.hidden = false;
    tip.style.left = `${e.clientX + 14}px`;
    tip.style.top = `${e.clientY + 14}px`;
  };
  document.addEventListener("mouseover", (e) => {
    const c = e.target.closest && e.target.closest("circle[data-value]");
    if (c) {
      const d = c.dataset.date;
      tip.textContent = `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)} · ${c.dataset.label}: ${c.dataset.value}`;
      moveTip(e);
    } else if (!tip.hidden) {
      tip.hidden = true;
    }
  });
  document.addEventListener("mousemove", (e) => {
    if (!tip.hidden) moveTip(e);
  });
  window.addEventListener("scroll", () => { tip.hidden = true; });

  for (const id of ["#trend-target-1", "#trend-target-2", "#trend-protein-target"]) {
    $(id).addEventListener("change", saveTrendTargets);
  }
  $("#trend-apply").addEventListener("click", () => {
    $$(".presets .btn").forEach((b) => b.classList.remove("active"));
    loadTrends().catch(onLoadError);
  });
  $$(".presets .btn").forEach((b) =>
    b.addEventListener("click", () => { setTrendRange(b.dataset.days, true); loadTrends().catch(onLoadError); }));

  loadStats();
  const h = location.hash.slice(1);
  showTab(["day", "trends"].includes(h) ? h : "catalog", false);
  loadFoods().catch(onLoadError);
  refreshPlanTally();  // rehydrate the saved basket (no-op when empty)
});
