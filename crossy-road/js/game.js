// game.js — the simulation: owns the world and the chicken, resolves support
// and death, and keeps the score. Deliberately free of Three.js and the DOM so
// it can be stepped headlessly in tests.

import { World, RIVER, ROAD, RAIL } from './world.js';
import { Player } from './player.js';
import { BOUND, EAGLE_GRAB, EAGLE_WARN, PLAYER_HALF, ROWS_BEHIND } from './config.js';

export const DEATH = {
  CAR: 'car',
  TRAIN: 'train',
  WATER: 'water',
  EDGE: 'edge',
  EAGLE: 'eagle',
};

export const DEATH_TEXT = {
  [DEATH.CAR]: 'Squashed.',
  [DEATH.TRAIN]: 'Hit by a train.',
  [DEATH.WATER]: 'Chickens cannot swim.',
  [DEATH.EDGE]: 'Carried off the map.',
  [DEATH.EAGLE]: 'An eagle got bored of waiting.',
};

export class Game {
  constructor(seed = Date.now()) {
    this.reset(seed);
  }

  reset(seed = Date.now()) {
    this.world = new World(seed);
    this.player = new Player();
    this.maxRow = 0;
    this.idle = 0;
    this.death = null;
    this.riding = null;      // the log under the chicken, if any
    this.world.ensureAhead(0);
  }

  get score() {
    return this.maxRow;
  }

  get eagleWarning() {
    return !this.death && this.idle > EAGLE_WARN;
  }

  get eagleProgress() {
    return Math.min(1, Math.max(0, (this.idle - EAGLE_WARN) / (EAGLE_GRAB - EAGLE_WARN)));
  }

  move(dir) {
    if (this.death) return;
    this.player.request(dir, this.world);
  }

  // Steps the simulation. Returns a DEATH cause the frame the chicken dies,
  // otherwise null.
  update(dt) {
    // Long frames (tab was backgrounded) would tunnel the chicken through
    // traffic, so clamp rather than simulate a huge step.
    const step = Math.min(dt, 1 / 30);

    // Traffic keeps flowing after death so the world does not freeze mid
    // death animation, but nothing can touch the chicken any more.
    this.world.update(step);
    if (this.death) return null;
    this.player.update(step, this.world);

    const cause = this.resolve(step);
    if (cause) {
      this.death = cause;
      // Drop the log, or a drowning chicken would stay perched on it.
      if (cause !== DEATH.EDGE) this.riding = null;
      return cause;
    }

    if (this.player.row > this.maxRow) {
      this.maxRow = this.player.row;
      this.idle = 0;
    } else {
      this.idle += step;
      if (this.idle >= EAGLE_GRAB) {
        this.death = DEATH.EAGLE;
        return DEATH.EAGLE;
      }
    }

    this.world.ensureAhead(this.player.row);
    this.world.cullBehind(this.maxRow);
    return null;
  }

  // Works out what the chicken is standing on and whether that kills it.
  resolve(dt) {
    const player = this.player;
    const lane = this.world.lane(player.collisionRow);
    this.riding = null;
    if (!lane) return null;

    if (lane.type === ROAD || lane.type === RAIL) {
      for (const item of lane.items) {
        if (Math.abs(player.x - item.x) < item.len / 2 + PLAYER_HALF) {
          return lane.type === RAIL ? DEATH.TRAIN : DEATH.CAR;
        }
      }
      return null;
    }

    if (lane.type === RIVER) {
      // Mid-hop the chicken is in the air, so water only matters on landing.
      if (player.hopping) return null;

      for (const log of lane.items) {
        if (Math.abs(player.x - log.x) <= log.len / 2 + 0.12) {
          this.riding = log;
          player.x += lane.delta;
          if (Math.abs(player.x) > BOUND + 0.65) return DEATH.EDGE;
          return null;
        }
      }
      return DEATH.WATER;
    }

    return null;
  }
}

export default Game;
