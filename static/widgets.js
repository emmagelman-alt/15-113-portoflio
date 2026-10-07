/* Right-hand column of the dashboard (Figma: "Dashboard" frame). Calendar reads the
   employee's Outlook calendar (app/integrations/outlook.py). Machines and sherpa.ai have
   no data source yet, so they render the design's sample content, labelled "Sample data".
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
  $("calendar-connect").hidden = data.connected;
  $("calendar-foot").hidden = !data.connected;
  $("meetings").replaceChildren(...data.events.map(meetingRow));
  const note = data.error || (data.connected && !data.events.length ? "No meetings today." : "");
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
renderSherpa();
// Calendar needs the signed-in user (app.js loads it); refresh every 5 minutes
(function waitForMe() {
  if (!state.me) return setTimeout(waitForMe, 100);
  renderCalendar();
  setInterval(() => { if (!document.hidden) renderCalendar(); }, 5 * 60 * 1000);
})();
