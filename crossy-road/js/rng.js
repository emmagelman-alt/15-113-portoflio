// rng.js — a small seeded random number generator (mulberry32).
//
// The world is generated from a seed rather than Math.random so a run can be
// replayed exactly, which makes odd bugs reproducible.

export class Rng {
  constructor(seed = Date.now()) {
    this.state = seed >>> 0;
  }

  // Returns a float in [0, 1).
  next() {
    this.state = (this.state + 0x6d2b79f5) >>> 0;
    let t = this.state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  range(min, max) {
    return min + this.next() * (max - min);
  }

  int(min, max) {
    return Math.floor(this.range(min, max + 1));
  }

  bool(p = 0.5) {
    return this.next() < p;
  }

  pick(list) {
    return list[Math.floor(this.next() * list.length)];
  }
}

export default Rng;
