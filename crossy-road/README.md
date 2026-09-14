# Crossy Road

An endless road-crossing game that runs in the browser. Hop the chicken forward
through traffic, rivers and railway crossings for as long as you can.

Play it at [`index.html`](index.html), or from the whiteboard on the
[portfolio homepage](../index.html).

## Controls

| Action | Keyboard | Touch |
| --- | --- | --- |
| Hop forward | `↑` / `W` | tap, or swipe up |
| Hop back | `↓` / `S` | swipe down |
| Hop left / right | `←` `→` / `A` `D` | swipe left / right |
| Start or restart | `Space` / `Enter` | tap the button |

On a phone an on-screen d-pad appears as well.

## How it works

There is no build step and no `node_modules`. The page is plain HTML, CSS and ES
modules; Three.js is pulled from a pinned CDN and mapped to the bare name
`three` with an import map, so `import * as THREE from 'three'` works directly in
the browser. Opening `index.html` through any static web server is enough.

The code is split so that the rules of the game never touch the screen:

| File | Responsibility |
| --- | --- |
| `js/config.js` | Every tunable number — speeds, sizes, camera, palette |
| `js/rng.js` | Seeded random number generator, so a run can be replayed |
| `js/world.js` | Lane generation, traffic movement, culling |
| `js/player.js` | The chicken: hop state machine and grid snapping |
| `js/game.js` | Simulation: support, collisions, death, score |
| `js/models.js` | Mesh factories for the blocky look |
| `js/scene.js` | Three.js scene, lights, camera, lane views |
| `js/input.js` | Keyboard, swipe and button input |
| `js/hud.js` | Score, overlays, best score in `localStorage` |
| `js/audio.js` | Synthesised sound effects (no audio files) |
| `js/main.js` | Wires it together and runs the loop |

`game.js` and everything it imports are free of Three.js and the DOM, so the
whole simulation can be stepped headlessly in Node — which is how the collision,
drowning and traffic-spacing behaviour was checked.

### A few design notes

- **Lanes come in runs.** Terrain is picked as "two roads, then a river, then
  grass" rather than one lane at a time, which makes the map read as a place
  instead of noise. A grass lane is forced in if you have gone five lanes
  without one.
- **Traffic never clumps.** Every vehicle in a lane shares one speed and wraps
  around the same belt, so once they are spaced apart they stay that way. Across
  31,000 generated lanes the tightest gap is 0.9 tiles — about 0.34s, comfortably
  longer than the 0.13s hop.
- **The chicken keeps a continuous x but a discrete row.** That is what lets a
  log carry it between tiles while still snapping back to the grid on the next
  hop.
- **Stand still and an eagle takes you**, which stops you waiting out a
  difficult river forever.

Append `?debug` to the URL to expose the running game on `window.crossy`.

## Credits

Crossy Road is by Hipster Whale. This is an original reimplementation written as a
learning exercise for 15-113 — no assets or code from the original were used.
Everything on screen is a scaled cube.
