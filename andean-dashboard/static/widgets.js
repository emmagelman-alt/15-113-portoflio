/* Right-hand column of the dashboard (Figma: "Dashboard" frame). Calendar reads the
   employee's Outlook calendar (app/integrations/outlook.py), or a labelled sample calendar
   in the demo and locally until they connect theirs. Machines and sherpa.ai have no data
   source yet, so they render the design's sample content, labelled "Sample data".
   Uses helpers from app.js and panel.js. */
const SAMPLE = {
  machines: [
    { name: "Machine 01", running: true },
    { name: "Machine 02", running: true },
    { name: "Machine 03", running: false },
  ],
  sherpa: [
    { me: true, author: "Emma", time: "Oct 7, 2:02 PM", body: "Pull the latest type rules from the brand-library repo and summarize them." },
    { me: false, author: "sherpa.ai", time: "Oct 7, 2:02 PM",
      body: "Found them on main. Headlines are Paralucent Medium in all caps, body copy is Swiss 721 BT, and Archivo is reserved for large standalone phrases.",
      file: "brand-library/typography/type-rules.md" },
    { me: true, author: "Emma", time: "Oct 7, 2:03 PM", body: "And the supporting palette?" },
    { me: false, author: "sherpa.ai", time: "Oct 7, 2:03 PM", body: "Andean Black, Andean White, Andean Grey, Almond Silk and Soft Blush." },
  ],
};

const TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
const clock = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });

function meetingRow(e) {
  const when = e.all_day ? "All day" : `${clock(e.start)} – ${clock(e.end)}`;
  return el("li", { class: "meeting" },
    el("span", { class: "meeting-time" }, when),
    el("span", { class: "meeting-title" }, e.title),
    e.tag ? el("span", { class: `badge ${/^(all hands|company)$/i.test(e.tag) ? "badge-internal" : "badge-notion"}` }, e.tag) : null);
}

let calendarFormOpen = false;

async function renderCalendar() {
  let data;
  try {
    data = await api(`/api/calendar/today?tz=${encodeURIComponent(TZ)}`);
  } catch (e) {
    $("calendar-note").textContent = e.message;
    $("calendar-note").hidden = false;
    return;
  }
  const [y, m, d] = data.date.split("-").map(Number);
  $("calendar-date").textContent = new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  const sample = !data.connected && !!data.sample;
  $("calendar-connect").hidden = data.connected || (sample && !calendarFormOpen);
  $("calendar-foot").hidden = !data.connected;
  $("calendar-sample-foot").hidden = !sample;
  $("meetings").replaceChildren(...data.events.map(meetingRow));
  const note = data.error || ((data.connected || sample) && !data.events.length ? "No meetings today." : "");
  $("calendar-note").textContent = note;
  $("calendar-note").hidden = !note;
  $("calendar-note").classList.toggle("form-error", !!data.error);
}

$("calendar-connect").addEventListener("submit", async (e) => {
  e.preventDefault();
  const button = e.target.querySelector("button");
  const err = $("calendar-error");
  err.hidden = true;
  button.disabled = true;
  try {
    await api("/api/calendar/link", { method: "PUT", body: JSON.stringify({ url: $("calendar-url").value }) });
    $("calendar-url").value = "";
    await renderCalendar();
  } catch (ex) {
    err.textContent = ex.message;
    err.hidden = false;
  } finally {
    button.disabled = false;
  }
});

$("calendar-connect-own").addEventListener("click", (e) => {
  calendarFormOpen = !calendarFormOpen;
  e.currentTarget.setAttribute("aria-expanded", String(calendarFormOpen));
  $("calendar-connect").hidden = !calendarFormOpen;
  if (calendarFormOpen) $("calendar-url").focus();
});

$("calendar-disconnect").addEventListener("click", async () => {
  if (!confirm("Disconnect your Outlook calendar from the dashboard?")) return;
  await api("/api/calendar/link", { method: "DELETE" }).catch((e) => alert(e.message));
  await renderCalendar();
});

function renderMachines() {
  const running = SAMPLE.machines.filter((m) => m.running).length;
  $("machines-summary").textContent = `${running} running · ${SAMPLE.machines.length - running} idle`;
  $("machine-cards").replaceChildren(...SAMPLE.machines.map((m) => el("div", { class: "machine" },
    el("div", { class: `dashcam${m.running ? "" : " offline"}` }, m.running ? "Dashcam · live" : "Dashcam · offline"),
    el("div", { class: "machine-name" }, el("strong", {}, m.name), el("span", { class: "chip" }, m.running ? "Running" : "Idle")))));
}

// Machines collapses to its header line; the choice is remembered in this browser
const MACHINES_KEY = "andean.machines.collapsed";

function setMachinesCollapsed(collapsed) {
  $("machines").classList.toggle("collapsed", collapsed);
  $("machine-cards").hidden = collapsed;
  const toggle = $("machines-toggle");
  toggle.setAttribute("aria-expanded", String(!collapsed));
  toggle.setAttribute("aria-label", collapsed ? "Expand Machines" : "Collapse Machines");
  try { localStorage.setItem(MACHINES_KEY, collapsed ? "1" : "0"); } catch (e) { /* storage unavailable */ }
}

$("machines-toggle").addEventListener("click", () => setMachinesCollapsed(!$("machines").classList.contains("collapsed")));

function renderSherpa() {
  $("sherpa-thread").replaceChildren(...SAMPLE.sherpa.map((m) => el("li", { class: `sherpa-row${m.me ? " me" : ""}` },
    el("div", { class: `msg${m.me ? " mine" : ""}` },
      el("div", { class: "msg-head" }, el("strong", {}, m.author), el("time", {}, m.time)),
      el("div", { class: "msg-text" }, linkify(m.body))),
    m.file ? el("div", { class: "link-item" },
      el("span", { class: "badge badge-doc" }, "Git file"),
      el("span", { class: "link-url" }, m.file),
      el("button", { class: "btn btn-ghost btn-small", type: "button", disabled: "" }, "Preview")) : null)));
}

renderMachines();
try { setMachinesCollapsed(localStorage.getItem(MACHINES_KEY) === "1"); } catch (e) { setMachinesCollapsed(false); }
renderSherpa();
// Calendar needs the signed-in user (app.js loads it); refresh every 5 minutes
(function waitForMe() {
  if (!state.me) return setTimeout(waitForMe, 100);
  renderCalendar();
  setInterval(() => { if (!document.hidden) renderCalendar(); }, 5 * 60 * 1000);
})();
