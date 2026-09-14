// player.js — the chicken: hop state machine and grid snapping.
//
// The chicken keeps a continuous x (so a log can carry it between tiles) but a
// discrete row. Every hop re-snaps x to a tile centre, which is what lets you
// step off a drifting log cleanly.

import { BOUND, HOP_HEIGHT, HOP_TIME, QUEUE_MAX } from './config.js';

export const FACING = {
  up: 0,
  left: Math.PI / 2,
  down: Math.PI,
  right: -Math.PI / 2,
};

export class Player {
  constructor() {
    this.reset();
  }

  reset() {
    this.x = 0;
    this.y = 0;
    this.row = 0;
    this.fromRow = 0;
    this.fromX = 0;
    this.toX = 0;
    this.hopping = false;
    this.hopT = 0;
    this.facing = FACING.up;
    this.queue = [];
    this.bumped = false;     // set for one frame when a hop is refused
  }

  // The row used for collision. Halfway through a hop the chicken commits to
  // the lane it is landing in.
  get collisionRow() {
    return this.hopping && this.hopT < 0.5 ? this.fromRow : this.row;
  }

  get col() {
    return Math.round(this.x);
  }

  request(move, world) {
    if (this.hopping) {
      if (this.queue.length < QUEUE_MAX) this.queue.push(move);
      return;
    }
    this.startHop(move, world);
  }

  startHop(move, world) {
    this.facing = FACING[move];

    const dCol = move === 'left' ? -1 : move === 'right' ? 1 : 0;
    const dRow = move === 'up' ? 1 : move === 'down' ? -1 : 0;
    const targetCol = this.col + dCol;
    const targetRow = this.row + dRow;

    // Refuse: off the playfield, past the culled edge, or into a tree.
    if (Math.abs(targetCol) > BOUND) { this.bumped = true; return; }
    if (targetRow < world.minRow) { this.bumped = true; return; }
    const lane = world.lane(targetRow);
    if (lane && lane.blocked && lane.blocked.has(targetCol)) { this.bumped = true; return; }

    this.fromX = this.x;
    this.toX = targetCol;
    this.fromRow = this.row;
    this.row = targetRow;
    this.hopping = true;
    this.hopT = 0;
  }

  update(dt, world) {
    this.bumped = false;
    if (!this.hopping) {
      this.y = 0;
      return;
    }

    this.hopT += dt / HOP_TIME;
    if (this.hopT >= 1) {
      this.x = this.toX;
      this.y = 0;
      this.hopping = false;
      this.hopT = 1;
      const next = this.queue.shift();
      if (next) this.startHop(next, world);
      return;
    }

    this.x = this.fromX + (this.toX - this.fromX) * this.hopT;
    this.y = Math.sin(Math.PI * this.hopT) * HOP_HEIGHT;
  }
}

export default Player;
