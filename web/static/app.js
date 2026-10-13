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
  $("#tot-cal").textContent = fmt(day.totals.calories);
  $("#tot-protein").textContent = fmt(day.totals.protein);
  $("#tot-fat").textContent = fmt(day.totals.fat);
  $("#tot-carbs").textContent = fmt(day.totals.carbs);

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
    const mealCal = meal.items
      .reduce((s, i) => s + (i.macros ? i.macros.calories : 0), 0);
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
    }
    card.innerHTML = `
      <div class="meal-head">
        <span>${escapeHtml(meal.name)}</span>
        <span class="meal-cal">${fmt(mealCal)} cal</span>
      </div>
      ${rows}`;
    wrap.appendChild(card);
  }
  $("#day-empty").hidden = day.meals.length > 0;
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
  const r = await fetch(`/api/trends?from=${from}&to=${to}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const data = await r.json();
  drawTrends(data.days);
}

function drawLineChart(days, seriesList, minSpan = 1) {
  const W = 940, H = 300;
  const padL = 52, padR = 18, padT = 14, padB = 38;
  const iw = W - padL - padR, ih = H - padT - padB;
  const maxV = Math.max(...days.map((d) =>
    Math.max(...seriesList.map((s) => d[s.key]))), minSpan) * 1.1;
  const x = (i) => padL + (days.length === 1 ? iw / 2 : (i * iw) / (days.length - 1));
  const y = (v) => padT + ih * (1 - v / maxV);

  let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Line chart">`;
  for (let g = 0; g <= 4; g++) {
    const v = (maxV / 4) * g, yy = y(v);
    svg += `<line x1="${padL}" y1="${yy.toFixed(1)}" x2="${W - padR}" y2="${yy.toFixed(1)}" class="grid"/>`;
    svg += `<text x="${padL - 8}" y="${(yy + 4).toFixed(1)}" text-anchor="end" class="tick">${Math.round(v)}</text>`;
  }
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
        `<circle cx="${x(i).toFixed(1)}" cy="${y(d[s.key]).toFixed(1)}" r="2.5" fill="${s.color}"/>`).join("");
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
  $("#chart-cal").innerHTML = drawLineChart(days, SERIES.cal);
  $("#chart-macro").innerHTML = drawLineChart(days, SERIES.macro, 50);
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

  // trends
  setTrendRange(30, true);
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
});
