/* Task panel: opens when a to-do is clicked. Shows what's behind it (the Slack thread,
   the Notion page, or the conversation with the coworker who sent it) plus any linked
   docs, and lets you act on them without leaving the dashboard. Uses helpers from app.js. */
const panel = { id: null, opener: null };
const URL_RE = /https?:\/\/[^\s<>"'`|]+/g;

function safeUrl(url) {
  return /^(https?:|mailto:)/i.test(url || "") ? url : null;
}

function link(url, text) {
  return el("a", { href: url, target: "_blank", rel: "noopener noreferrer" }, text || url);
}

function linkify(text) {
  const frag = document.createDocumentFragment();
  let last = 0;
  for (const m of (text || "").matchAll(URL_RE)) {
    const url = m[0].replace(/[.,;:!?)\]}]+$/, "");
    frag.append(text.slice(last, m.index), link(url));
    last = m.index + url.length;
  }
  frag.append((text || "").slice(last));
  return frag;
}

function renderSpans(spans) {
  const frag = document.createDocumentFragment();
  for (const s of spans || []) {
    const href = safeUrl(s.href);
    frag.append(href ? link(href, s.text) : linkify(s.text));
  }
  return frag;
}

function when(value) {
  const d = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function section(title, ...children) {
  return el("section", { class: "panel-section" }, el("h3", {}, title), ...children);
}

function labeled(text, control) {
  return el("label", { class: "field" }, el("span", {}, text), control);
}

function message({ author, time, body, classes = "" }) {
  return el("li", { class: `msg ${classes}` },
    el("div", { class: "msg-head" }, el("strong", {}, author), time ? el("time", {}, when(time)) : null),
    el("div", { class: "msg-text" }, body));
}

function fileSize(bytes) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function filesEl(files) {
  if (!files || !files.length) return null;
  return el("div", { class: "files" }, ...files.map((f) => f.is_image
    ? el("a", { class: "file-thumb", href: f.url, target: "_blank", rel: "noopener" }, el("img", { src: f.url, alt: f.name, loading: "lazy" }))
    : el("a", { class: "file-chip", href: f.url, target: "_blank", rel: "noopener" }, `📎 ${f.name}`, f.size ? el("span", { class: "hint" }, ` ${fileSize(f.size)}`) : null)));
}

async function uploadFile(todoId, file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`/api/todos/${todoId}/attachments`, {
    method: "POST", body: form, credentials: "same-origin", headers: { "X-CSRF-Token": state.me.csrf_token },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Upload failed.");
  return data;
}

function composer({ placeholder, button, onSubmit, todoId, maxFiles = 10, note }) {
  const input = el("textarea", { rows: "2", placeholder, "aria-label": placeholder, maxlength: "4000" });
  const err = el("p", { class: "form-error", hidden: "" });
  const submit = el("button", { class: "btn btn-small", type: "submit" }, button);
  const chips = el("div", { class: "pending-files" });
  const picker = el("input", { type: "file", multiple: "", hidden: "" });
  const attached = [];
  let uploading = 0;

  const showError = (message) => { err.textContent = message; err.hidden = !message; };
  const renderChips = () => chips.replaceChildren(...attached.map((f) => el("span", { class: "file-chip" }, `📎 ${f.name}`,
    el("button", { class: "icon-btn", type: "button", "aria-label": `Remove ${f.name}`,
      onclick: () => { attached.splice(attached.indexOf(f), 1); renderChips(); } }, "×"))));

  async function addFiles(list) {
    showError("");
    for (const file of list) {
      if (attached.length + uploading >= maxFiles) { showError(`Attach up to ${maxFiles} files here.`); break; }
      uploading += 1;
      submit.disabled = true;
      try {
        attached.push(await uploadFile(todoId, file));
        renderChips();
      } catch (e) {
        showError(`${file.name}: ${e.message}`);
      } finally {
        uploading -= 1;
        submit.disabled = uploading > 0;
      }
    }
  }

  picker.addEventListener("change", () => { addFiles([...picker.files]); picker.value = ""; });
  input.addEventListener("paste", (e) => {
    const pasted = [...(e.clipboardData ? e.clipboardData.files : [])];
    if (pasted.length) { e.preventDefault(); addFiles(pasted); }
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) form.requestSubmit();
  });

  const form = el("form", {
    class: "composer",
    onsubmit: async (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if ((!text && !attached.length) || uploading) return;
      submit.disabled = true;
      showError("");
      try {
        await onSubmit(text, attached.map((f) => f.id));
      } catch (ex) {
        showError(ex.message);
        submit.disabled = false;
      }
    },
  }, input, chips, el("div", { class: "composer-row" },
    el("div", { class: "composer-tools" },
      el("button", { class: "btn btn-ghost btn-small", type: "button", onclick: () => picker.click() }, "📎 Attach"),
      el("span", { class: "hint" }, note || "⌘↵ to send")),
    submit), picker, err);
  return form;
}

/* ---------- Actions ---------- */

async function panelAction(fn) {
  try {
    await fn();
    await Promise.all([loadPanel(), refresh()]);
  } catch (e) {
    alert(e.message);
    loadPanel();
  }
}

const panelPatch = (changes) => panelAction(() => api(`/api/todos/${panel.id}`, { method: "PATCH", body: JSON.stringify(changes) }));

function notionEdit(changes, control) {
  control.disabled = true;
  return panelAction(() => api(`/api/todos/${panel.id}/notion`, { method: "PATCH", body: JSON.stringify(changes) }));
}

async function panelDismiss() {
  try {
    await api(`/api/todos/${panel.id}`, { method: "DELETE" });
    closePanel();
    await refresh();
  } catch (e) {
    alert(e.message);
  }
}

const post = (path, text, ids) => api(path, { method: "POST", body: JSON.stringify({ text, attachment_ids: ids }) }).then(loadPanel);

/* ---------- Sections ---------- */

function controls(d) {
  const t = d.todo;
  const row = el("div", { class: "panel-controls" });
  const notionStatus = t.source === "notion" && d.notion && (d.notion.status_options || []).length;
  if (t.status === "suggested") {
    row.append(
      el("button", { class: "btn", type: "button", onclick: () => panelPatch({ status: "open" }) }, "Accept"),
      el("button", { class: "btn btn-ghost", type: "button", onclick: panelDismiss }, "Dismiss"));
  } else if (notionStatus) {
    row.append(labeled("Status in Notion", el("select", { onchange: (e) => notionEdit({ status: e.target.value }, e.target) },
      ...d.notion.status_options.map((o) => el("option", { value: o, ...(o === d.notion.status ? { selected: "" } : {}) }, o)))));
  } else {
    const done = t.status === "done";
    row.append(el("button", { class: done ? "btn btn-ghost" : "btn", type: "button",
      onclick: () => panelPatch({ status: done ? "open" : "done" }) }, done ? "Reopen" : "Mark done"));
  }
  const due = el("input", { type: "date", value: t.due_date || "" });
  due.addEventListener("change", (e) => {
    const value = e.target.value || null;
    if (t.source === "notion" && d.notion && !d.notion.error) notionEdit({ due_date: value }, e.target);
    else panelPatch({ due_date: value });
  });
  row.append(labeled(t.source === "notion" ? "Due (updates Notion)" : "Due", due));
  return row;
}

function slackSection(d) {
  const s = d.slack;
  if (s.error) return section("Slack thread", el("p", { class: "muted" }, s.error));
  const list = el("ol", { class: "thread" }, ...s.messages.map((m) => message({
    author: m.author,
    time: Number(m.ts),
    classes: m.highlight ? "highlight" : "",
    body: el("span", {}, linkify(m.text), ...m.files.map((f) => el("span", { class: "msg-file" }, link(f.url, `📎 ${f.name}`)))),
  })));
  const asYou = s.reply_as === "you";
  const reply = s.can_reply
    ? composer({ placeholder: "Reply in the thread…", button: asYou ? "Reply as you" : "Reply", todoId: d.todo.id,
      note: asYou ? "⌘↵ to send" : "Posts as Andean Dashboard, signed with your name",
      onSubmit: (text, ids) => post(`/api/todos/${d.todo.id}/slack-reply`, text, ids) })
    : null;
  return section(s.channel_name ? `Thread in #${s.channel_name}` : "Slack thread", list, reply);
}

function blockEl(b) {
  switch (b.type) {
    case "heading_1": return el("h4", {}, renderSpans(b.spans));
    case "heading_2":
    case "heading_3": return el("h5", {}, renderSpans(b.spans));
    case "to_do": return el("label", { class: "notion-todo" },
      el("input", { type: "checkbox", disabled: "", ...(b.checked ? { checked: "" } : {}) }), el("span", {}, renderSpans(b.spans)));
    case "quote": return el("blockquote", {}, renderSpans(b.spans));
    case "callout": return el("div", { class: "callout" }, renderSpans(b.spans));
    case "code": return el("pre", {}, b.spans.map((s) => s.text).join(""));
    case "divider": return el("hr");
    case "image": return safeUrl(b.url) ? el("img", { src: b.url, alt: b.spans.map((s) => s.text).join("") || "Image from Notion", loading: "lazy" }) : null;
    case "link": return safeUrl(b.url) ? el("p", {}, link(b.url)) : null;
    case "unsupported": return el("p", { class: "muted" }, `(${b.name}: open the page in Notion to see it)`);
    default: return el("p", {}, renderSpans(b.spans));
  }
}

function renderBlocks(blocks, more) {
  const wrap = el("div", { class: "notion-blocks" });
  if (!blocks.length) wrap.append(el("p", { class: "muted" }, "This page has no content yet."));
  let list = null;
  for (const b of blocks) {
    const listTag = { bulleted_list_item: "UL", numbered_list_item: "OL" }[b.type];
    if (listTag) {
      if (!list || list.tagName !== listTag) wrap.append(list = el(listTag.toLowerCase()));
      list.append(el("li", {}, renderSpans(b.spans)));
      continue;
    }
    list = null;
    const node = blockEl(b);
    if (node) wrap.append(node);
  }
  if (more) wrap.append(el("p", { class: "muted" }, "The page continues in Notion."));
  return wrap;
}

function notionSections(d) {
  const n = d.notion;
  if (n.error) return [section("Notion page", el("p", { class: "muted" }, n.error))];
  const comments = n.comments_error
    ? el("p", { class: "hint" }, n.comments_error)
    : el("ol", { class: "thread" }, ...(n.comments.length
      ? n.comments.map((c) => message({ author: c.author, time: c.created_at,
        body: el("span", {}, renderSpans(c.spans), ...(c.files || []).map((f) => el("span", { class: "msg-file" }, link(f.url, `📎 ${f.name}`)))) }))
      : [el("li", { class: "muted" }, "No comments yet.")]));
  return [
    section("Notion page", renderBlocks(n.blocks, n.more_blocks)),
    section("Comments", comments, d.is_owner && !n.comments_error
      ? composer({ placeholder: "Comment on the Notion page…", button: "Comment", todoId: d.todo.id, maxFiles: 3,
        onSubmit: (text, ids) => post(`/api/todos/${d.todo.id}/notion-comments`, text, ids) })
      : null),
  ];
}

function commentsSection(d) {
  const other = d.is_owner ? d.todo.created_by : d.todo.owner;
  const name = other && other.id !== state.me.id ? other.name.split(" ")[0] : null;
  const list = el("ol", { class: "thread" }, ...(d.comments.length
    ? d.comments.map((c) => message({ author: c.is_me ? "You" : c.author, time: c.created_at,
      body: el("span", {}, linkify(c.body), filesEl(c.files)), classes: c.is_me ? "mine" : "" }))
    : [el("li", { class: "muted" }, name ? `Ask ${name} a question, or reply with a link to what you made.` : "Add notes for yourself.")]));
  return section(name ? `Conversation with ${name}` : "Notes", list,
    composer({ placeholder: name ? `Message ${name}…` : "Add a note…", button: "Send", todoId: d.todo.id,
      onSubmit: (text, ids) => post(`/api/todos/${d.todo.id}/comments`, text, ids) }));
}

function previewHead(item, box) {
  return el("div", { class: "preview-head" }, el("strong", {}, item.label),
    el("button", { class: "icon-btn", type: "button", "aria-label": "Close preview", onclick: () => { box.hidden = true; box.replaceChildren(); } }, "×"));
}

async function showPreview(item, box) {
  box.hidden = false;
  if (item.embed) {
    box.replaceChildren(previewHead(item, box),
      el("iframe", { src: item.embed, title: `${item.label} preview`, loading: "lazy", allowfullscreen: "", referrerpolicy: "no-referrer" }));
  } else {
    box.replaceChildren(previewHead(item, box), el("p", { class: "muted" }, "Loading…"));
    try {
      const page = await api(`/api/notion-preview?url=${encodeURIComponent(item.url)}`);
      box.replaceChildren(previewHead(item, box), el("h4", {}, page.title), renderBlocks(page.blocks, page.more_blocks));
    } catch (e) {
      box.replaceChildren(previewHead(item, box), el("p", { class: "muted" }, e.message));
    }
  }
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function linksSection(links) {
  const box = el("div", { class: "preview", hidden: "" });
  return section("Linked docs", el("ul", { class: "links" }, ...links.map((item) => el("li", { class: "link-item" },
    el("span", { class: `badge badge-doc` }, item.label),
    el("span", { class: "link-url" }, link(item.url)),
    item.embed || item.kind === "notion"
      ? el("button", { class: "btn btn-ghost btn-small", type: "button", onclick: () => showPreview(item, box) }, "Preview")
      : null))), box);
}

/* ---------- Open / render / close ---------- */

function renderPanel(d) {
  const t = d.todo;
  const status = { suggested: "Suggested", open: "Open", done: "Done" }[t.status] || t.status;
  $("panel-badges").replaceChildren(
    el("span", { class: `badge badge-${t.source}` }, SOURCE_LABEL[t.source] || t.source),
    el("span", { class: `chip chip-${t.status}` }, status));
  const meta = [];
  if (t.created_by && t.created_by.id !== state.me.id) meta.push(`From ${t.created_by.name}`);
  if (!d.is_owner) meta.push(`Sent to ${t.owner.name}`);
  if (t.notes && t.source !== "internal") meta.push(t.notes);
  const body = [
    el("h2", { id: "panel-title", class: "panel-title" }, t.title),
    meta.length ? el("p", { class: "panel-meta" }, meta.join(" · ")) : null,
    d.is_owner ? controls(d) : null,
    t.notes && t.source === "internal" ? el("p", { class: "panel-notes" }, linkify(t.notes)) : null,
    d.slack ? slackSection(d) : null,
    ...(d.notion ? notionSections(d) : []),
    d.comments ? commentsSection(d) : null,
    d.links.length ? linksSection(d.links) : null,
    t.source_url ? el("p", { class: "panel-footer" }, link(t.source_url, `Open in ${SOURCE_LABEL[t.source]} ↗`)) : null,
  ];
  $("panel-body").replaceChildren(...body.filter(Boolean));
}

async function loadPanel() {
  const id = panel.id;
  if (id === null) return;
  try {
    const data = await api(`/api/todos/${id}/detail`);
    if (panel.id === id) renderPanel(data);
  } catch (e) {
    if (panel.id === id) $("panel-body").replaceChildren(el("p", { class: "form-error" }, e.message));
  }
}

async function openPanel(id) {
  if (panel.id === null) panel.opener = document.activeElement;
  panel.id = id;
  $("panel").hidden = false;
  $("panel-backdrop").hidden = false;
  document.body.classList.add("panel-open");
  history.replaceState(null, "", `#todo-${id}`);
  $("panel-badges").replaceChildren();
  $("panel-body").replaceChildren(el("p", { class: "muted" }, "Loading…"));
  $("panel-close").focus();
  await loadPanel();
}

function closePanel() {
  panel.id = null;
  $("panel").hidden = true;
  $("panel-backdrop").hidden = true;
  document.body.classList.remove("panel-open");
  history.replaceState(null, "", location.pathname);
  if (panel.opener && document.contains(panel.opener)) panel.opener.focus();
}

$("panel-close").addEventListener("click", closePanel);
$("panel-backdrop").addEventListener("click", closePanel);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && panel.id !== null) closePanel();
});
window.addEventListener("hashchange", () => {
  const linked = location.hash.match(/^#todo-(\d+)$/);
  if (linked && Number(linked[1]) !== panel.id) openPanel(Number(linked[1]));
});
