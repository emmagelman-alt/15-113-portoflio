/* Right-hand column of the dashboard (Figma: "Dashboard" frame, Calendar / Machines /
   sherpa.ai panels). None of these has a data source yet, so they render the design's
   sample content and each panel is labelled "Sample data". Replace SAMPLE with real
   sources (e.g. Outlook calendar via Microsoft Graph) when they exist. Uses helpers from
   app.js and panel.js. */
const SAMPLE = {
  meetings: [
    { time: "10:00 – 10:45", title: "All hands", tag: "All hands", kind: "internal" },
    { time: "11:30 – 12:00", title: "Design team sync", tag: "Team", kind: "notion" },
    { time: "14:00 – 15:00", title: "Brand guidelines review", tag: "Team", kind: "notion" },
    { time: "16:30 – 17:00", title: "Q4 launch check-in", tag: "Team", kind: "notion" },
  ],
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

function renderCalendar() {
  $("calendar-date").textContent = new Date().toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  $("meetings").replaceChildren(...SAMPLE.meetings.map((m) => el("li", { class: "meeting" },
    el("span", { class: "meeting-time" }, m.time),
    el("span", { class: "meeting-title" }, m.title),
    el("span", { class: `badge badge-${m.kind}` }, m.tag))));
}

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

renderCalendar();
renderMachines();
renderSherpa();
