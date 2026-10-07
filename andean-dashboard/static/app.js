const state = { me: null, todos: [], sent: [], employees: [], filter: "all" };

const FILTERS = [
  { id: "all", label: "All", test: () => true },
  { id: "coworkers", label: "From coworkers", test: (t) => t.source === "internal" && t.created_by && t.created_by.id !== state.me.id },
  { id: "mine", label: "Added by me", test: (t) => t.source === "internal" && (!t.created_by || t.created_by.id === state.me.id) },
  { id: "slack", label: "Slack", test: (t) => t.source === "slack" },
  { id: "notion", label: "Notion", test: (t) => t.source === "notion" },
];
const SOURCE_LABEL = { internal: "Dashboard", slack: "Slack", notion: "Notion" };

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (options.method && options.method !== "GET") headers["X-CSRF-Token"] = state.me ? state.me.csrf_token : "";
  const res = await fetch(path, { credentials: "same-origin", ...options, headers });
  if (res.status === 401) {
    location.href = "/login";
    throw new Error("signed out");
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const detail = Array.isArray(data.detail) ? data.detail[0].msg : data.detail;
    throw new Error(detail || "Something went wrong.");
  }
  return res.status === 204 ? null : res.json();
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c != null) node.append(c);
  return node;
}

function today() {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function dueLabel(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const due = new Date(y, m - 1, d);
  const days = Math.round((due - today()) / 86400000);
  const text = days === 0 ? "Due today" : days === 1 ? "Due tomorrow" : days < 0 ? `Overdue · ${due.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`
    : `Due ${due.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
  return { text, overdue: days < 0 };
}

function titleButton(t) {
  return el("button", { class: "text todo-title", type: "button", onclick: () => openPanel(t.id) }, t.title);
}

function todoItem(t, { readOnly = false, suggested = false } = {}) {
  const meta = el("div", { class: "meta" }, el("span", { class: `badge badge-${t.source}` }, SOURCE_LABEL[t.source] || t.source));
  if (readOnly) meta.append(el("span", {}, `To ${t.owner.name}`), el("span", {}, t.status === "done" ? "✓ Done" : "Open"));
  else if (t.created_by && t.created_by.id !== state.me.id) meta.append(el("span", {}, `From ${t.created_by.name}`));
  if (t.notes && t.source !== "internal") meta.append(el("span", {}, t.notes));
  if (t.due_date && t.status !== "done") {
    const due = dueLabel(t.due_date);
    meta.append(el("span", { class: due.overdue ? "overdue" : "" }, due.text));
  }
  if (t.source_url) meta.append(el("a", { href: t.source_url, target: "_blank", rel: "noopener noreferrer" }, `Open in ${SOURCE_LABEL[t.source]} ↗`));

  const li = el("li", { class: `todo${t.status === "done" ? " done" : ""}` });
  if (suggested) {
    // Per the Figma "Dashboard" frame: who it's from and the Slack link; Accept/Dismiss live in the task panel
    const author = t.created_by ? t.created_by.name : ((t.notes || "").match(/from (.+)$/i) || [])[1];
    const info = el("div", { class: "meta" }, author ? el("span", {}, `From ${author}`) : t.notes ? el("span", {}, t.notes) : null,
      t.source_url ? el("a", { href: t.source_url, target: "_blank", rel: "noopener noreferrer" }, `Open in ${SOURCE_LABEL[t.source]} ↗`) : null);
    li.className = "todo suggestion";
    li.append(el("div", { class: "body" }, titleButton(t), info));
    return li;
  }
  if (!readOnly) {
    li.append(el("input", {
      type: "checkbox",
      "aria-label": `Mark "${t.title}" ${t.status === "done" ? "not done" : "done"}`,
      ...(t.status === "done" ? { checked: "" } : {}),
      onchange: (e) => setStatus(t, e.target.checked ? "done" : "open"),
    }));
  }
  li.append(el("div", { class: "body" }, titleButton(t), meta));
  if (!readOnly) li.append(el("button", { class: "icon-btn", type: "button", title: "Delete", "aria-label": `Delete "${t.title}"`, onclick: () => remove(t) }, "×"));
  return li;
}

function render() {
  const filter = FILTERS.find((f) => f.id === state.filter);
  const suggested = state.todos.filter((t) => t.status === "suggested");
  const visible = state.todos.filter((t) => t.status !== "suggested" && filter.test(t));
  const open = visible.filter((t) => t.status === "open");
  const done = visible.filter((t) => t.status === "done");

  $("tabs").replaceChildren(...FILTERS.map((f) => {
    const count = state.todos.filter((t) => t.status === "open" && f.test(t)).length;
    return el("button", { class: "tab", type: "button", "aria-pressed": String(f.id === state.filter), onclick: () => { state.filter = f.id; render(); } },
      f.label, el("span", { class: "count" }, String(count)));
  }));

  $("open-list").replaceChildren(...open.map((t) => todoItem(t)));
  $("empty").hidden = open.length > 0;
  $("done-section").hidden = done.length === 0;
  $("done-summary").textContent = `Completed (${done.length})`;
  $("done-list").replaceChildren(...done.map((t) => todoItem(t)));

  $("suggested-section").hidden = suggested.length === 0;
  $("suggested-list").replaceChildren(...suggested.map((t) => todoItem(t, { suggested: true })));

  $("sent-section").hidden = state.sent.length === 0;
  $("sent-list").replaceChildren(...state.sent.map((t) => todoItem(t, { readOnly: true })));

  const openAll = state.todos.filter((t) => t.status === "open");
  const overdue = openAll.filter((t) => t.due_date && dueLabel(t.due_date).overdue).length;
  $("summary").textContent = openAll.length === 0 ? "You're all caught up."
    : `${openAll.length} open to-do${openAll.length === 1 ? "" : "s"}${overdue ? ` · ${overdue} overdue` : ""}`;
  if (suggested.length) $("summary").textContent += ` · ${suggested.length} suggested`;
}

function renderAssignees() {
  $("assignee").replaceChildren(
    el("option", { value: "" }, "Me"),
    ...state.employees.filter((e) => e.id !== state.me.id).map((e) => el("option", { value: String(e.id) }, e.name)),
  );
}

async function refresh() {
  [state.todos, state.sent] = await Promise.all([api("/api/todos"), api("/api/todos/sent")]);
  render();
}

async function setStatus(t, status) {
  try {
    Object.assign(t, await api(`/api/todos/${t.id}`, { method: "PATCH", body: JSON.stringify({ status }) }));
  } catch (e) {
    alert(e.message);
  }
  render();
}

async function remove(t) {
  const verb = t.source === "internal" ? "Delete" : `Remove from your dashboard (it stays in ${SOURCE_LABEL[t.source]})`;
  if (!confirm(`${verb}: "${t.title}"?`)) return;
  try {
    await api(`/api/todos/${t.id}`, { method: "DELETE" });
    state.todos = state.todos.filter((x) => x.id !== t.id);
    render();
  } catch (e) {
    alert(e.message);
  }
}

$("add-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const button = e.submitter || e.target.querySelector("button");
  const err = $("form-error");
  err.hidden = true;
  button.disabled = true;
  try {
    const assignee = $("assignee").value;
    await api("/api/todos", {
      method: "POST",
      body: JSON.stringify({ title: $("title").value, due_date: $("due").value || null, assignee_id: assignee ? Number(assignee) : null }),
    });
    e.target.reset();
    await refresh();
    $("title").focus();
  } catch (ex) {
    err.textContent = ex.message;
    err.hidden = false;
  } finally {
    button.disabled = false;
  }
});

$("sync-notion").addEventListener("click", async (e) => {
  const button = e.currentTarget;
  button.disabled = true;
  button.textContent = "Syncing…";
  try {
    await api("/api/notion/sync", { method: "POST" });
    await refresh();
  } catch (ex) {
    alert(ex.message);
  } finally {
    button.disabled = false;
    button.textContent = "Sync Notion";
  }
});

$("logout").addEventListener("click", async () => {
  await api("/auth/logout", { method: "POST" }).catch(() => {});
  location.href = "/login";
});

(async function init() {
  state.me = await api("/api/me");
  $("who").textContent = state.me.email;
  $("greeting").textContent = `Hi, ${state.me.name.split(" ")[0]}`;
  state.employees = await api("/api/employees");
  fetch("/auth/config").then((r) => r.json()).then((cfg) => { $("sync-notion").hidden = !cfg.notion; }).catch(() => {});
  renderAssignees();
  await refresh();
  setInterval(() => { if (!document.hidden) refresh().catch(() => {}); }, 30000);
  const linked = location.hash.match(/^#todo-(\d+)$/);
  if (linked) openPanel(Number(linked[1]));
})();
