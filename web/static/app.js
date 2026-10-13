/* Food Diary dashboard — vanilla JS, no dependencies. */

const $ = (sel) => document.querySelector(sel);

let foods = [];
let sortKey = "name";
let sortDir = 1; // 1 asc, -1 desc
let searchTimer = null;

// ---------- formatting ----------

const fmt = (v) => {
  if (v === null || v === undefined) return "–";
  const n = Number(v);
  if (Number.isInteger(n)) return String(n);
  return n < 10 ? n.toFixed(1) : String(Math.round(n * 10) / 10);
};

const servingLabel = (f) => {
  const s = Number(f.serving_size);
  if (s === 1) return "1 unit";
  if (Number.isInteger(s)) return `${s} g`;
  return `${s} g`;
};

// ---------- data ----------

async function loadStats() {
  try {
    const r = await fetch("/api/stats");
    const s = await r.json();
    $("#stat-foods").textContent = s.foods;
    $("#stat-days").textContent = s.days;
  } catch { /* non-fatal */ }
}

async function loadFoods(q = "") {
  const url = q ? `/api/foods?q=${encodeURIComponent(q)}` : "/api/foods";
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  foods = await r.json();
  render();
}

// ---------- rendering ----------

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

function render() {
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
  $("#result-count").textContent =
    `Showing ${rows.length} of ${foods.length} foods`;

  // sort indicators
  document.querySelectorAll("th.sortable").forEach((th) => {
    th.classList.remove("sorted-asc", "sorted-desc");
    if (th.dataset.key === sortKey) {
      th.classList.add(sortDir === 1 ? "sorted-asc" : "sorted-desc");
    }
  });
}

const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------- search ----------

function onSearchInput() {
  $("#clear-search").hidden = $("#search").value === "";
  render(); // instant client-side pass
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    try {
      await loadFoods($("#search").value.trim());
      render();
    } catch (e) {
      toast(`Search failed: ${e.message}`, true);
    }
  }, 300);
}

// ---------- sorting ----------

function onSortClick(key) {
  if (sortKey === key) sortDir *= -1;
  else { sortKey = key; sortDir = 1; }
  render();
}

// ---------- modal ----------

function openModal() {
  $("#modal-backdrop").hidden = false;
  $("#food-form").reset();
  $("#form-error").hidden = true;
  $("#f-name").focus();
}

function closeModal() {
  $("#modal-backdrop").hidden = true;
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

// ---------- toast ----------

let toastTimer = null;
function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("error", isError);
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3200);
}

// ---------- wiring ----------

document.addEventListener("DOMContentLoaded", () => {
  $("#add-btn").addEventListener("click", openModal);
  $("#modal-close").addEventListener("click", closeModal);
  $("#modal-cancel").addEventListener("click", closeModal);
  $("#modal-backdrop").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });
  $("#food-form").addEventListener("submit", onSubmit);
  $("#search").addEventListener("input", onSearchInput);
  $("#clear-search").addEventListener("click", () => {
    $("#search").value = "";
    onSearchInput();
    $("#search").focus();
  });
  document.querySelectorAll("th.sortable").forEach((th) => {
    th.addEventListener("click", () => onSortClick(th.dataset.key));
  });

  loadStats();
  loadFoods().catch((e) => toast(`Could not load foods: ${e.message}`, true));
});
