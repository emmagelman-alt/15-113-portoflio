// main.js — bootstrap: builds the game, the scene and the input, then runs the
// fixed-order loop (simulate, then draw).

import { Game } from './game.js';
import { SceneView } from './scene.js';
import { Input } from './input.js';
import { Hud } from './hud.js';
import { Sfx } from './audio.js';

const canvas = document.getElementById('canvas');
const hud = new Hud();
const sfx = new Sfx();

let scene;
try {
  scene = new SceneView(canvas);
} catch (err) {
  document.getElementById('fatal').hidden = false;
  document.getElementById('fatal-detail').textContent = err.message;
  throw err;
}

const game = new Game();
let screen = 'start';
let last = performance.now();
let milestone = 0;

function begin() {
  game.reset();
  scene.clear();
  scene.snap(game);
  hud.reset();
  hud.setScreen('play');
  milestone = 0;
  screen = 'play';
}

function confirm() {
  // Deliberately not during 'dying': a key pressed as you die would otherwise
  // restart the run before the game-over screen was ever seen.
  if (screen === 'start' || screen === 'over') begin();
}

function move(dir) {
  if (screen !== 'play') { confirm(); return; }
  const wasHopping = game.player.hopping;
  game.move(dir);
  // A move while already mid-hop is queued silently; only real hops click.
  if (game.player.bumped) sfx.bump();
  else if (!wasHopping) sfx.hop();
}

new Input(canvas, move, confirm);

document.getElementById('play').addEventListener('click', begin);
document.getElementById('again').addEventListener('click', begin);
document.getElementById('mute').addEventListener('click', () => hud.setMuted(sfx.toggleMute()));
hud.setMuted(sfx.muted);

// Append ?debug to the URL to poke at the running game from the console.
if (location.search.includes('debug')) window.crossy = { game, scene, hud, sfx };

window.addEventListener('resize', () => scene.resize());
hud.setScreen('start');

function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min((now - last) / 1000, 0.1);
  last = now;

  if (screen === 'dying') {
    // Death is latched; this only keeps the traffic moving behind the animation.
    game.update(dt);
  }

  if (screen === 'play') {
    const death = game.update(dt);
    hud.setScore(game.score);
    hud.setWarnings(game.world.warningNear(game.player.row), game.eagleWarning);

    if (game.score >= milestone + 10) {
      milestone = Math.floor(game.score / 10) * 10;
      sfx.milestone();
    }

    if (death) {
      if (death === 'water') sfx.splash();
      else if (death === 'eagle') sfx.screech();
      else sfx.crash();
      screen = 'dying';
      // Let the death animation play before the panel covers the scene.
      setTimeout(() => {
        hud.showGameOver(game.score, death);
        screen = 'over';
      }, 850);
    }
  }

  scene.sync(game, dt);
  scene.render();
}

requestAnimationFrame(frame);
