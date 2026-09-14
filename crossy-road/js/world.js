// world.js — lane generation, traffic movement and culling.
//
// The world is an endless strip of lanes indexed by row number. Lanes are
// created on demand ahead of the player and thrown away once they fall far
// enough behind, so memory stays flat no matter how far you get.
//
// Lane types come in "runs" (two roads in a row, then a river, then grass)
// rather than being picked independently, which is what makes the map read as
// a place instead of noise.

import { Rng } from './rng.js';
import {
  BELT, BELT_SPAN, BOUND, DIFFICULTY_ROWS, ROWS_AHEAD, ROWS_BEHIND, SAFE_ROWS,
  START_ROWS, PALETTE,
} from './config.js';

export const GRASS = 'grass';
export const ROAD = 'road';
export const RIVER = 'river';
export const RAIL = 'rail';

// Rail lanes cycle through these. Trains are telegraphed before they arrive.
const IDLE = 'idle';
const WARN = 'warn';
const PASS = 'pass';

const WARN_TIME = 1.5;
const TRAIN_LEN = 30;
const TRAIN_SPEED = 30;

// Longest run allowed for each terrain, so you never face six rivers back to
// back. Grass runs stay short because a wall of grass is boring.
const RUN_LENGTH = {
  [GRASS]: [1, 2],
  [ROAD]: [1, 3],
  [RIVER]: [1, 3],
  [RAIL]: [1, 2],
};

export function difficultyAt(row) {
  return Math.min(1, Math.max(0, row / DIFFICULTY_ROWS));
}

export class World {
  constructor(seed) {
    this.rng = new Rng(seed);
    this.lanes = new Map();
    this.run = null;        // { type, left }
    this.prevType = null;
    this.sinceGrass = 0;
    this.nextRow = -START_ROWS;
    this.minRow = -START_ROWS;
    this.ensureAhead(0);
  }

  lane(row) {
    return this.lanes.get(row) || null;
  }

  // --- generation ---------------------------------------------------------

  ensureAhead(playerRow) {
    const target = playerRow + ROWS_AHEAD;
    while (this.nextRow <= target) {
      this.lanes.set(this.nextRow, this.buildLane(this.nextRow));
      this.nextRow += 1;
    }
  }

  cullBehind(playerRow) {
    const cutoff = playerRow - ROWS_BEHIND;
    while (this.minRow < cutoff) {
      this.lanes.delete(this.minRow);
      this.minRow += 1;
    }
  }

  chooseType(row) {
    if (row < SAFE_ROWS) return GRASS;

    // A long dangerous stretch with nowhere to breathe is just unfair.
    if (this.sinceGrass >= 5) return GRASS;

    const d = difficultyAt(row);
    const weights = {
      [GRASS]: 20,
      [ROAD]: 34 + 10 * d,
      [RIVER]: 16 + 8 * d,
      [RAIL]: 7 + 7 * d,
    };
    // Never start a new run of the terrain we just finished — that is what the
    // run length is for.
    if (this.prevType) delete weights[this.prevType];

    const total = Object.values(weights).reduce((a, b) => a + b, 0);
    let roll = this.rng.next() * total;
    for (const [type, w] of Object.entries(weights)) {
      roll -= w;
      if (roll <= 0) return type;
    }
    return GRASS;
  }

  buildLane(row) {
    if (!this.run || this.run.left === 0) {
      const type = this.chooseType(row);
      const [lo, hi] = RUN_LENGTH[type];
      this.run = { type, left: this.rng.int(lo, hi), dir: this.rng.bool() ? 1 : -1 };
      this.prevType = type;
    }
    this.run.left -= 1;

    const type = this.run.type;
    this.sinceGrass = type === GRASS ? 0 : this.sinceGrass + 1;

    // Alternate direction between lanes inside a run. Two rivers flowing the
    // same way at the same speed can be impossible; opposing ones never are.
    if (this.run.dir !== undefined && this.rng.bool(0.75)) this.run.dir *= -1;
    const dir = this.run.dir;

    switch (type) {
      case ROAD: return this.buildRoad(row, dir);
      case RIVER: return this.buildRiver(row, dir);
      case RAIL: return this.buildRail(row, dir);
      default: return this.buildGrass(row);
    }
  }

  buildGrass(row) {
    const lane = { row, type: GRASS, shade: row % 2, obstacles: [], items: [] };
    if (row < SAFE_ROWS) return lane;

    const d = difficultyAt(row);
    const chance = 0.13 + 0.1 * d;
    for (let col = -BOUND; col <= BOUND; col += 1) {
      if (this.rng.next() < chance) {
        lane.obstacles.push({
          col,
          kind: this.rng.bool(0.82) ? 'tree' : 'rock',
          height: this.rng.int(1, 3),
          tint: this.rng.int(0, PALETTE.leaves.length - 1),
        });
      }
    }
    // Leave the row crossable even in the worst roll.
    const maxBlocked = Math.floor((BOUND * 2 + 1) * 0.45);
    while (lane.obstacles.length > maxBlocked) {
      lane.obstacles.splice(this.rng.int(0, lane.obstacles.length - 1), 1);
    }
    lane.blocked = new Set(lane.obstacles.map((o) => o.col));
    return lane;
  }

  buildRoad(row, dir) {
    const d = difficultyAt(row);
    const truck = this.rng.bool(0.26);
    const len = truck ? this.rng.range(2.4, 3.0) : this.rng.range(1.5, 1.8);
    const gap = this.rng.range(5.0 - 2.2 * d, 9.5 - 3.5 * d);
    const speed = this.rng.range(2.6, 3.8) * (1 + 0.62 * d);

    const lane = {
      row, type: ROAD, dir, speed, delta: 0,
      kind: truck ? 'truck' : 'car',
      items: this.spread(len, gap, (i) => ({
        len,
        color: truck ? PALETTE.truckBody : this.rng.pick(PALETTE.cars),
      })),
    };
    return lane;
  }

  buildRiver(row, dir) {
    const d = difficultyAt(row);
    const len = this.rng.range(2.5, 4.5);
    const gap = this.rng.range(2.4, 5.2 + 1.5 * d);
    const speed = this.rng.range(1.5, 2.4) * (1 + 0.5 * d);

    return {
      row, type: RIVER, dir, speed, delta: 0,
      items: this.spread(len, gap, () => ({ len })),
    };
  }

  buildRail(row, dir) {
    return {
      row, type: RAIL, dir, delta: 0,
      phase: IDLE,
      timer: this.rng.range(1.5, 5.0),
      warning: false,
      items: [],
    };
  }

  // Lay entities around the belt in evenly sized slots, jittered inside each
  // slot. Every entity in a lane shares one speed, so once they are spaced they
  // stay spaced forever — no clumping, no overlap.
  spread(len, gap, make) {
    const count = Math.max(2, Math.round(BELT_SPAN / (len + gap)));
    const slot = BELT_SPAN / count;
    const jitter = Math.max(0, (slot - len) * 0.3);
    const items = [];
    for (let i = 0; i < count; i += 1) {
      const center = -BELT + i * slot + slot / 2;
      items.push({
        ...make(i),
        x: center + this.rng.range(-jitter, jitter),
        id: i,
      });
    }
    return items;
  }

  // --- per-frame movement -------------------------------------------------

  update(dt) {
    for (const lane of this.lanes.values()) {
      if (lane.type === ROAD || lane.type === RIVER) {
        const delta = lane.speed * lane.dir * dt;
        lane.delta = delta;
        for (const item of lane.items) {
          item.x += delta;
          if (item.x > BELT) item.x -= BELT_SPAN;
          else if (item.x < -BELT) item.x += BELT_SPAN;
        }
      } else if (lane.type === RAIL) {
        this.updateRail(lane, dt);
      }
    }
  }

  updateRail(lane, dt) {
    lane.timer -= dt;
    if (lane.phase === IDLE) {
      lane.warning = false;
      if (lane.timer <= 0) {
        lane.phase = WARN;
        lane.timer = WARN_TIME;
        lane.warning = true;
      }
    } else if (lane.phase === WARN) {
      lane.warning = true;
      if (lane.timer <= 0) {
        lane.phase = PASS;
        lane.warning = true;
        const start = -lane.dir * (BELT + TRAIN_LEN);
        lane.items = [{ id: 0, x: start, len: TRAIN_LEN }];
        lane.timer = (2 * (BELT + TRAIN_LEN)) / TRAIN_SPEED;
      }
    } else {
      const delta = TRAIN_SPEED * lane.dir * dt;
      lane.delta = delta;
      for (const item of lane.items) item.x += delta;
      if (lane.timer <= 0) {
        lane.phase = IDLE;
        lane.warning = false;
        lane.items = [];
        lane.timer = this.rng.range(2.5, 6.0);
      }
    }
  }

  // Is any rail lane the player can see about to be hit by a train?
  warningNear(row) {
    for (let r = row - 2; r <= row + 6; r += 1) {
      const lane = this.lanes.get(r);
      if (lane && lane.type === RAIL && lane.warning) return true;
    }
    return false;
  }
}

export default World;
