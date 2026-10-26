// Inventory demo: the logic of Warp's Inventory page (code/lib/inventory.ts and the two components in
// code/components/inventory), ported from React and TypeScript to plain JavaScript and run over the
// sample data in data.js. In Warp the parts-to-cut numbers come from the inventory_parts_to_cut()
// database function; partsRows() below does the same sums in the browser.
(function () {
  "use strict";

  const D = window.INVENTORY_DEMO;
  const LOG_KEY = "warp-inventory-demo-log";
  const THEME_KEY = "warp-inventory-demo-theme";
  const ALL = "all";
  const MAX_LOGGED_PARTS = 10000;

  // Short labels for the wheel, where a slice has room for a word or two
  const SHORT_PART_NAMES = {
    MOTHERBOARD: "Motherboard", DAUGHTERBOARD: "Other board", "OPTICAL-DRIVE": "Optical drive", PSU: "Power supply",
    "BATTERY-LI-ION": "Li-ion battery", "BATTERY-OTHER": "Battery", "DISPLAY-PANEL": "Display", "CAMERA-MODULE": "Camera",
    HEATSINK: "Heat sink", CABLE: "Cables", CHASSIS: "Case panels", RAM: "RAM", CPU: "CPU", GPU: "GPU", HDD: "Hard drive", SSD: "SSD",
  };
  const shortPartName = (t) => SHORT_PART_NAMES[t.code] || t.name;

  const typeOrder = new Map(D.componentTypes.map((t, i) => [t.code, i]));
  const typeByCode = new Map(D.componentTypes.map((t) => [t.code, t]));
  const categoryName = new Map(D.categories.map((c) => [c.code, c.name]));
  const modelByCode = new Map(D.models.map((m) => [m.code, m]));

  // Parts the visitor logged, kept in this browser only. Storage can be blocked (private windows),
  // so every read and write is guarded and the page still works without it.
  function loadLog() {
    try {
      const v = JSON.parse(localStorage.getItem(LOG_KEY) || "[]");
      return Array.isArray(v) ? v.filter((m) => m && typeByCode.has(m.type) && Number.isInteger(m.qty)) : [];
    } catch (e) { return []; }
  }
  function saveLog() {
    try { localStorage.setItem(LOG_KEY, JSON.stringify(logged)); } catch (e) { /* kept for this visit only */ }
  }

  let logged = loadLog();
  let selected = ALL;

  /** One row per (category, model, part): expected = processed × parts list, cut = parts logged. */
  function partsRows() {
    const rows = new Map();
    const row = (category, model, type) => {
      const key = [category, model, type].join("|");
      if (!rows.has(key)) rows.set(key, { category, model, type, expected: 0, cut: 0 });
      return rows.get(key);
    };
    for (const s of D.stock) {
      if (!s.processed) continue;
      // A model's own parts list when it has one, else its category's
      const bom = (s.model && D.modelBom[s.model]) || D.categoryBom[s.category] || {};
      for (const [type, qty] of Object.entries(bom)) row(s.category, s.model, type).expected += s.processed * qty;
    }
    for (const m of D.cut.concat(logged)) row(m.category, m.model, m.type).cut += m.qty;
    return [...rows.values()];
  }

  /** Processed devices grouped by product: a model, or a category when the model isn't known. */
  function buildProducts(rows) {
    const out = new Map();
    const add = (category, model, processed) => {
      if (!category) return;
      const key = model || "category:" + category;
      if (out.has(key)) { out.get(key).processed += processed; return; }
      const m = model ? modelByCode.get(model) : null;
      out.set(key, {
        key, category, model, processed,
        name: m ? [m.manufacturer, m.name].filter(Boolean).join(" ") : categoryName.get(category) || "Unknown device",
        detail: m ? categoryName.get(category) || "" : "Model not set",
      });
    };
    for (const s of D.stock) if (s.processed > 0) add(s.category, s.model, s.processed);
    // Parts logged against a kind of device nothing has been processed for yet still get a row
    for (const r of rows) if (r.cut > 0) add(r.category, r.model, 0);
    return [...out.values()].sort((a, b) => b.processed - a.processed || a.name.localeCompare(b.name));
  }

  /** Parts to cut for one product, or for everything (product = null, including parts with no source),
   *  in catalog order so the wheel's slices stay put as counts change. */
  function partTiles(rows, product) {
    const sum = new Map();
    for (const r of rows) {
      if (product && (product.model ? r.model !== product.model : r.model !== null || r.category !== product.category)) continue;
      const s = sum.get(r.type) || { expected: 0, cut: 0 };
      s.expected += r.expected; s.cut += r.cut;
      sum.set(r.type, s);
    }
    return [...sum.entries()].map(([code, s]) => {
      const expected = Math.round(s.expected);
      const left = Math.max(expected - s.cut, 0);
      return { code, name: typeByCode.get(code).name, expected, cut: s.cut, left, done: expected > 0 && left === 0 };
    }).filter((t) => t.expected > 0 || t.cut > 0)
      .sort((a, b) => typeOrder.get(a.code) - typeOrder.get(b.code));
  }

  /** Part picker: top-level types are groups, the types inside them items. */
  function partGroups() {
    const types = D.componentTypes;
    return types.filter((t) => !t.parent).map((g) => ({ label: g.name, items: types.filter((t) => t.parent === g.code) }))
      .filter((g) => g.items.length);
  }

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const plural = (n, word) => n + " " + word + (n === 1 ? "" : "s");

  // ---- Parts wheel (code/components/inventory/parts-wheel.tsx) ----
  // One equal slice per part. The slice is everything expected inside the processed devices; the lit
  // shape grows out from the middle as parts are cut. Hover, focus or tap a slice for its numbers.
  const SIZE = 440, C = SIZE / 2;
  const R_IN = 78, R_OUT = 212;
  const ROUND = 9, GAP = 3, RIM = 7;
  const LABEL_R = R_IN + 0.62 * (R_OUT - R_IN);
  const at = (r, a) => (C + r * Math.cos(a)).toFixed(2) + " " + (C + r * Math.sin(a)).toFixed(2);

  /** Ring sector between radii r0..r1 and angles a0..a1, shrunk by `pad` px on every side. */
  function sector(r0, r1, a0, a1, pad) {
    const ri = r0 + pad, ro = r1 - pad;
    if (ro - ri < 0.5) return null;
    const s0 = a0 + pad / ro, s1 = a1 - pad / ro, t0 = a0 + pad / ri, t1 = a1 - pad / ri;
    const large = s1 - s0 > Math.PI ? 1 : 0;
    return `M${at(ro, s0)} A${ro} ${ro} 0 ${large} 1 ${at(ro, s1)} L${at(ri, t1)} A${ri} ${ri} 0 ${large} 0 ${at(ri, t0)}Z`;
  }

  let wheelId = 0;
  function renderWheel(el, tiles, devices) {
    const uid = "w" + ++wheelId;
    const n = tiles.length, step = (2 * Math.PI) / n;
    const slices = tiles.map((t, i) => {
      const a0 = -Math.PI / 2 + i * step, a1 = a0 + (n === 1 ? 2 * Math.PI - 0.001 : step);
      const half = GAP / 2 + ROUND / 2;
      const outer = sector(R_IN, R_OUT, a0, a1, half);
      const frac = t.expected ? Math.min(t.cut / t.expected, 1) : t.cut > 0 ? 1 : 0;
      const span = R_OUT - R_IN - 2 * RIM;
      // A small share still shows as a nub, so "some cut" never looks like "none cut"
      const litOuter = frac > 0 ? R_IN + RIM + Math.max(frac * span, ROUND + 4) : 0;
      const la0 = a0 + RIM / LABEL_R, la1 = a1 - RIM / LABEL_R;
      const lit = frac > 0 ? sector(R_IN + RIM, litOuter, la0, la1, half) : null;
      // Dark text is clipped to the lit shape, so a label that crosses the lit edge switches colour there
      const litClip = frac > 0 ? sector(R_IN + RIM, litOuter, la0, la1, GAP / 2) : null;
      const mid = (a0 + a1) / 2;
      const lx = (C + LABEL_R * Math.cos(mid)).toFixed(2), ly = C + LABEL_R * Math.sin(mid);
      const text = (dark) =>
        `<text x="${lx}" y="${(ly - 2).toFixed(2)}" text-anchor="middle" class="w-num" fill="rgb(var(${dark ? "--primary-foreground" : "--foreground"}))">${t.expected || t.cut}</text>` +
        `<text x="${lx}" y="${(ly + 15).toFixed(2)}" text-anchor="middle" class="w-label" fill="rgb(var(${dark ? "--primary-foreground" : "--muted-foreground"}))">${esc(shortPartName(t))}</text>`;
      const label = `${t.name}: ${t.cut} of ${t.expected} cut${t.done ? ", done" : `, ${t.left} left`}`;
      return `<g class="slice" data-i="${i}" role="button" tabindex="0" aria-label="${esc(label)}">` +
        (outer ? `<path d="${outer}" fill="rgb(var(--border))" stroke="rgb(var(--border))" stroke-width="${ROUND}" stroke-linejoin="round" />` : "") +
        text(false) +
        (lit ? `<path d="${lit}" fill="rgb(var(--primary))" stroke="rgb(var(--primary))" stroke-width="${ROUND}" stroke-linejoin="round" />` : "") +
        (litClip ? `<clipPath id="${uid}-lit-${i}"><path d="${litClip}" /></clipPath><g clip-path="url(#${uid}-lit-${i})">${text(true)}</g>` : "") +
        `</g>`;
    }).join("");

    el.innerHTML =
      `<svg viewBox="0 0 ${SIZE} ${SIZE}" role="group" aria-label="Parts to cut from ${plural(devices, "processed device")}">` +
      slices + `<g class="center" aria-hidden="true" text-anchor="middle"></g></svg>` +
      `<p class="caption">Each slice is a part. The lit area is how many have been cut.</p>`;

    const center = el.querySelector(".center");
    const groups = [...el.querySelectorAll(".slice")];
    function setActive(i) {
      groups.forEach((g, j) => { g.style.opacity = i === null || i === j ? 1 : 0.45; });
      if (i === null) {
        center.innerHTML =
          `<text x="${C}" y="${C + 4}" class="w-total" fill="rgb(var(--foreground))">${devices}</text>` +
          `<text x="${C}" y="${C + 22}" class="w-label" fill="rgb(var(--muted-foreground))">processed</text>`;
        return;
      }
      const a = tiles[i];
      center.innerHTML =
        `<text x="${C}" y="${C - 12}" class="w-title" fill="rgb(var(--foreground))">${esc(shortPartName(a))}</text>` +
        `<text x="${C}" y="${C + 6}" class="w-sub" fill="rgb(var(--muted-foreground))">${a.cut} of ${a.expected} cut</text>` +
        `<text x="${C}" y="${C + 23}" class="w-sub" font-weight="500" fill="rgb(var(${a.done ? "--success-ink" : "--foreground"}))">${a.done ? "Done" : a.left + " left"}</text>`;
    }
    groups.forEach((g, i) => {
      g.addEventListener("mouseenter", () => setActive(i));
      g.addEventListener("mouseleave", () => setActive(null));
      g.addEventListener("focus", () => setActive(i));
      g.addEventListener("blur", () => setActive(null));
      g.addEventListener("click", () => setActive(i));
    });
    setActive(null);
  }

  // ---- Page ----
  const $ = (id) => document.getElementById(id);
  const form = $("logForm"), partSelect = $("part"), qtyInput = $("qty"), errorEl = $("logError");

  partSelect.insertAdjacentHTML("beforeend", partGroups().map((g) =>
    `<optgroup label="${esc(g.label)}">` + g.items.map((t) => `<option value="${t.code}">${esc(t.name)}</option>`).join("") + `</optgroup>`
  ).join(""));

  function render() {
    const rows = partsRows();
    const products = buildProducts(rows);
    // A product that disappears (nothing left for it) falls back to all products
    const product = products.find((p) => p.key === selected) || null;
    const total = products.reduce((n, p) => n + p.processed, 0);
    const shown = product ? product.processed : total;

    const button = (key, name, detail, count, isSelected) =>
      `<button type="button" class="product" data-key="${esc(key)}" aria-pressed="${isSelected}">` +
      `<span class="product-row"><span><span class="product-name">${esc(name)}</span>` +
      (detail ? `<span class="product-detail">${esc(detail)}</span>` : "") +
      `</span><span class="product-count">${count}</span></span>` +
      `<span class="product-bar" aria-hidden="true"><span style="width:${total ? (count / total) * 100 : 0}%"></span></span></button>`;
    $("productList").innerHTML = button(ALL, "All products", null, total, !product) +
      products.map((p) => button(p.key, p.name, p.detail, p.processed, !!product && product.key === p.key)).join("");

    $("logFrom").textContent = product ? "From " + product.name : "Any device";
    $("partsTitle").textContent = "Parts to cut from " + (product ? product.name : "all products");
    $("partsCount").textContent = plural(shown, "processed device");

    const tiles = partTiles(rows, product);
    if (tiles.length) renderWheel($("wheel"), tiles, shown);
    else $("wheel").innerHTML = `<p class="empty">Nothing to cut yet.</p>`;
    return product;
  }

  $("productList").addEventListener("click", (e) => {
    const b = e.target.closest(".product");
    if (!b) return;
    selected = b.dataset.key;
    render();
  });

  let toastTimer = 0;
  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 2600);
  }

  function showError(msg, field) {
    errorEl.textContent = msg || "";
    errorEl.hidden = !msg;
    partSelect.setAttribute("aria-invalid", String(field === "part"));
    qtyInput.setAttribute("aria-invalid", String(field === "qty"));
  }
  partSelect.addEventListener("change", () => showError(""));
  qtyInput.addEventListener("input", () => showError(""));

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const n = Number(qtyInput.value);
    if (!partSelect.value) { showError("Choose a part", "part"); return; }
    if (!qtyInput.value.trim() || !Number.isInteger(n) || n < 1 || n > MAX_LOGGED_PARTS) {
      showError(`Enter a whole number from 1 to ${MAX_LOGGED_PARTS.toLocaleString("en-US")}`, "qty");
      return;
    }
    const product = buildProducts(partsRows()).find((p) => p.key === selected) || null;
    // Same rule as Warp: a model, else a category, says what the parts came from
    logged.push({ type: partSelect.value, category: product ? product.category : null, model: product ? product.model : null, qty: n });
    saveLog();
    toast(`Added ${n} × ${typeByCode.get(partSelect.value).name}${product ? " from " + product.name : ""}`);
    partSelect.value = "";
    qtyInput.value = "1";
    render();
  });

  $("reset").addEventListener("click", () => {
    logged = [];
    saveLog();
    render();
    toast("Sample data reset");
  });

  // Theme: follows the system until the visitor picks one
  const toggle = $("themeToggle");
  const isDark = () => {
    const t = document.documentElement.dataset.theme;
    return t ? t === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  };
  const labelToggle = () => { toggle.textContent = isDark() ? "Light mode" : "Dark mode"; };
  toggle.addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem(THEME_KEY, next); } catch (e) { /* not remembered */ }
    labelToggle();
  });
  labelToggle();

  render();
})();
