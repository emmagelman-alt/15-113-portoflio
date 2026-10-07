(function () {
  "use strict";

  var SCENE_W = 1600;
  var SCENE_H = 900;
  var FRAME_MS = 250; // time each animation frame is shown (250ms = 4 fps)
  var PING_PONG = false; // true = play forward then backward instead of looping

  var scene = document.getElementById("scene");
  var bubble = document.getElementById("bubble");
  var clockEl = document.getElementById("clock");
  var frames = Array.prototype.slice.call(document.querySelectorAll(".frame"));
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------------------------------------------------------
     Fit the 1600x900 scene inside the window, preserving aspect ratio
  ---------------------------------------------------------------- */
  var scale = 1;
  function fitScene() {
    scale = Math.min(window.innerWidth / SCENE_W, window.innerHeight / SCENE_H);
    scene.style.setProperty("--scale", scale);
  }
  window.addEventListener("resize", fitScene);
  fitScene();

  /* ---------------------------------------------------------------
     Frame-by-frame animation
  ---------------------------------------------------------------- */
  // Order the frames are shown in. Ping-pong: 0 1 2 ... 6 5 4 ... 1, repeat.
  var order = frames.map(function (_, i) { return i; });
  if (PING_PONG && frames.length > 2) {
    order = order.concat(order.slice(1, -1).reverse());
  }

  var step = 0;
  function nextFrame() {
    frames[order[step]].classList.remove("is-active");
    step = (step + 1) % order.length;
    frames[order[step]].classList.add("is-active");
  }
  if (frames.length > 1 && !reduceMotion) {
    setInterval(nextFrame, FRAME_MS);
  }

  // If the frame images aren't there yet, say so instead of showing a blank page.
  var missing = document.getElementById("missingFrames");
  function checkFrame(img) {
    if (img.complete && img.naturalWidth === 0) missing.hidden = false;
  }
  frames.forEach(function (img) {
    img.addEventListener("error", function () { missing.hidden = false; });
    checkFrame(img);
  });

  /* ---------------------------------------------------------------
     Phone screen: map the 100x150 .phone-screen box onto the drawn
     screen's four corners (scene px, clockwise from top-left).
     Nudge these numbers if the overlay drifts off the drawing.
  ---------------------------------------------------------------- */
  var PHONE_SCREEN = [[58, 686], [137, 675], [192, 782], [80, 807]];

  function solve(A, b) {
    // Gaussian elimination with partial pivoting (A is n x n, b is n)
    var n = b.length, i, j, k;
    for (i = 0; i < n; i++) {
      var p = i;
      for (j = i + 1; j < n; j++) if (Math.abs(A[j][i]) > Math.abs(A[p][i])) p = j;
      var t = A[i]; A[i] = A[p]; A[p] = t;
      t = b[i]; b[i] = b[p]; b[p] = t;
      for (j = i + 1; j < n; j++) {
        var f = A[j][i] / A[i][i];
        for (k = i; k < n; k++) A[j][k] -= f * A[i][k];
        b[j] -= f * b[i];
      }
    }
    var x = new Array(n);
    for (i = n - 1; i >= 0; i--) {
      var s = b[i];
      for (j = i + 1; j < n; j++) s -= A[i][j] * x[j];
      x[i] = s / A[i][i];
    }
    return x;
  }

  function perspective(w, h, q) {
    // Homography sending (0,0),(w,0),(w,h),(0,h) to the four points in q
    var src = [[0, 0], [w, 0], [w, h], [0, h]];
    var A = [], b = [];
    for (var i = 0; i < 4; i++) {
      var x = src[i][0], y = src[i][1], X = q[i][0], Y = q[i][1];
      A.push([x, y, 1, 0, 0, 0, -X * x, -X * y]); b.push(X);
      A.push([0, 0, 0, x, y, 1, -Y * x, -Y * y]); b.push(Y);
    }
    var v = solve(A, b); // a b c d e f g h
    return "matrix3d(" + [
      v[0], v[3], 0, v[6],
      v[1], v[4], 0, v[7],
      0, 0, 1, 0,
      v[2], v[5], 0, 1
    ].join(",") + ")";
  }

  var phone = document.querySelector(".phone-screen");
  if (phone) {
    phone.style.transform = perspective(phone.offsetWidth, phone.offsetHeight, PHONE_SCREEN);
  }

  /* ---------------------------------------------------------------
     Live clock (user's local time, 12-hour)
  ---------------------------------------------------------------- */
  function tick() {
    var now = new Date();
    var h = now.getHours() % 12 || 12;
    var m = String(now.getMinutes()).padStart(2, "0");
    clockEl.textContent = h + ":" + m;
  }
  tick();
  setInterval(tick, 1000);

  /* ---------------------------------------------------------------
     "Coming soon" speech bubble
  ---------------------------------------------------------------- */
  var hideTimer = null;

  function showBubble(anchor, text) {
    // Convert the anchor's on-screen position into scene coordinates
    var s = scene.getBoundingClientRect();
    var r = anchor.getBoundingClientRect();
    var x = (r.left + r.width / 2 - s.left) / scale;
    var top = (r.top - s.top) / scale;
    var bottom = (r.bottom - s.top) / scale;

    bubble.textContent = text || "Coming soon!";

    // Point up from below the element if there isn't room above it
    var pointUp = top < 120;
    bubble.classList.toggle("below", pointUp);
    bubble.style.top = (pointUp ? bottom : top) + "px";

    // Restart the pop animation
    bubble.hidden = true;
    void bubble.offsetWidth;
    bubble.hidden = false;

    // Keep the bubble inside the scene, but leave the tail pointing at the anchor
    var margin = 12;
    var half = bubble.offsetWidth / 2;
    var clampedX = Math.min(Math.max(x, half + margin), SCENE_W - half - margin);
    bubble.style.left = clampedX + "px";
    bubble.style.setProperty("--tail-x", (half + (x - clampedX)) + "px");

    clearTimeout(hideTimer);
    hideTimer = setTimeout(hideBubble, 2200);
  }

  function hideBubble() {
    bubble.hidden = true;
  }

  document.querySelectorAll(".squiggle, .app.pending").forEach(function (el) {
    el.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      showBubble(el, "Coming soon!");
    });
  });

  // Clicking anywhere else dismisses the bubble
  document.addEventListener("click", hideBubble);

  /* ---------------------------------------------------------------
     Restaurant rec chat
     Backend: github.com/emmagelman-alt/backend-for-restaurant-bot-
     It only returns places from my Beli list rated 8.0+.
  ---------------------------------------------------------------- */
  var LOCAL = location.hostname === "localhost" || location.hostname === "127.0.0.1";
  var RECS_API = LOCAL ? "http://localhost:8000" : "https://emma-restaurant-recs.onrender.com";
  var COMPACT_SCALE = 0.6; // below this the scene is too small to type on, so the chat goes full-screen

  var recBubble = document.getElementById("recBubble");
  var recChat = document.getElementById("recChat");
  var recClose = document.getElementById("recClose");
  var recLog = document.getElementById("recLog");
  var recForm = document.getElementById("recForm");
  var recInput = document.getElementById("recInput");
  var recSend = recForm.querySelector("button");
  var recSuggestions = document.getElementById("recSuggestions");
  var boardTitle = document.querySelector(".board-title");
  var boardNotes = document.querySelector(".board-notes");
  var BOARD_TITLE = boardTitle.textContent;

  var recHistory = []; // sent back each turn so "what about cafes?" keeps the city
  var backendAwake = false;

  // Render's free tier sleeps when idle; poke it as soon as someone shows
  // interest so it's usually awake by the time they hit Send.
  function wakeBackend() {
    if (backendAwake) return;
    backendAwake = true;
    fetch(RECS_API + "/healthz").catch(function () { backendAwake = false; });
  }

  function placeChat() {
    var compact = scale < COMPACT_SCALE;
    recChat.classList.toggle("is-sheet", compact);
    var home = compact ? document.body : scene;
    if (recChat.parentNode !== home) home.appendChild(recChat);
  }
  window.addEventListener("resize", placeChat);
  placeChat();

  function setChatOpen(open) {
    recChat.hidden = !open;
    boardNotes.hidden = open;
    boardTitle.textContent = open ? "Restaurant recs" : BOARD_TITLE;
    recBubble.setAttribute("aria-expanded", String(open));
    if (open) {
      wakeBackend();
      if (!recLog.children.length) {
        addMessage("emma", "Hi! Tell me a city (or country) and a cuisine or kind of place, " +
                           "and I'll share my favorite spots, all rated 8.0+ on my Beli.");
      }
      recInput.focus();
    } else {
      recBubble.focus();
    }
  }

  function addMessage(who, text, places) {
    var msg = document.createElement("div");
    msg.className = "rec-msg from-" + who;
    msg.textContent = text; // textContent, never innerHTML, for anything from the network

    if (places && places.length) {
      var list = document.createElement("ul");
      list.className = "rec-places";
      places.forEach(function (p) {
        var li = document.createElement("li");
        var score = document.createElement("span");
        score.className = "rec-score";
        score.textContent = p.score.toFixed(1);
        var info = document.createElement("span");
        var name = document.createElement("span");
        name.className = "rec-name";
        name.textContent = p.name;
        var meta = document.createElement("span");
        meta.className = "rec-meta";
        meta.textContent = [p.city, p.cuisines.join(", ") || p.category].join(" · ");
        info.appendChild(name);
        info.appendChild(meta);
        li.appendChild(score);
        li.appendChild(info);
        list.appendChild(li);
      });
      msg.appendChild(list);
    }

    recLog.appendChild(msg);
    recLog.scrollTop = recLog.scrollHeight;
    return msg;
  }

  function ask(message) {
    message = message.trim();
    if (!message || recSend.disabled) return;
    recSuggestions.hidden = true;
    recInput.value = "";
    addMessage("visitor", message);
    var thinking = addMessage("emma", "thinking…");
    thinking.classList.add("is-thinking");
    recSend.disabled = true;

    fetch(RECS_API + "/api/recs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: message, history: recHistory.slice(-12) })
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) throw new Error(data.detail || "Something went wrong. Try again?");
          return data;
        });
      })
      .then(function (data) {
        thinking.remove();
        addMessage("emma", data.reply, data.places);
        recHistory.push({ role: "user", content: message }, { role: "assistant", content: data.reply });
      })
      .catch(function (err) {
        thinking.remove();
        // A network error (not an error reply) almost always means the server is still waking up
        addMessage("emma", err instanceof TypeError
          ? "Sorry, I'm still waking up! Give me a few seconds and send that again."
          : err.message);
        backendAwake = false;
        wakeBackend();
      })
      .then(function () {
        recSend.disabled = false;
        recInput.focus();
      });
  }

  recBubble.addEventListener("pointerenter", wakeBackend);
  recBubble.addEventListener("click", function () { setChatOpen(recChat.hidden); });
  recClose.addEventListener("click", function () { setChatOpen(false); });
  recForm.addEventListener("submit", function (e) {
    e.preventDefault();
    ask(recInput.value);
  });
  recSuggestions.addEventListener("click", function (e) {
    if (e.target.tagName === "BUTTON") ask(e.target.textContent);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !recChat.hidden) setChatOpen(false);
  });
})();
