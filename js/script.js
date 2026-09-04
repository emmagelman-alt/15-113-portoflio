(function () {
  "use strict";

  var SCENE_W = 1600;
  var SCENE_H = 900;
  var FRAME_MS = 320; // time each animation frame is shown
  var PING_PONG = true; // play forward then backward so the loop never snaps

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
})();
