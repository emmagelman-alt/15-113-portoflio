// models.js — mesh factories for the blocky look.
//
// Two rules keep this cheap: every solid is the SAME unit BoxGeometry scaled to
// size (so geometry is never allocated per entity), and materials are cached by
// colour. Lanes can then be built and thrown away freely without leaking GPU
// memory.

import { BOUND, LANE_WIDTH, PALETTE } from './config.js';

let THREE = null;
let UNIT = null;
const materials = new Map();

export function initModels(three) {
  THREE = three;
  UNIT = new THREE.BoxGeometry(1, 1, 1);
  materials.clear();
}

function material(color, opts = {}) {
  const key = `${color}|${opts.flat ? 1 : 0}|${opts.opacity ?? 1}|${opts.emissive ?? 0}`;
  let mat = materials.get(key);
  if (!mat) {
    mat = new THREE.MeshLambertMaterial({
      color,
      emissive: opts.emissive ?? 0x000000,
      transparent: (opts.opacity ?? 1) < 1,
      opacity: opts.opacity ?? 1,
    });
    materials.set(key, mat);
  }
  return mat;
}

// One scaled unit cube. w/h/d are world units, x/y/z is the centre.
function box(w, h, d, color, x = 0, y = 0, z = 0, opts = {}) {
  const mesh = new THREE.Mesh(UNIT, material(color, opts));
  mesh.scale.set(w, h, d);
  mesh.position.set(x, y, z);
  return mesh;
}

function solid(group, ...args) {
  const mesh = box(...args);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  group.add(mesh);
  return mesh;
}

// --- ground -----------------------------------------------------------------

export function makeGrassTile(shade) {
  const g = new THREE.Group();
  const tile = box(LANE_WIDTH, 0.4, 1, shade ? PALETTE.grassB : PALETTE.grassA, 0, -0.2, 0);
  tile.receiveShadow = true;
  g.add(tile);
  return g;
}

export function makeRoadTile(stripeAhead) {
  const g = new THREE.Group();
  const tile = box(LANE_WIDTH, 0.4, 1, PALETTE.road, 0, -0.2, 0);
  tile.receiveShadow = true;
  g.add(tile);
  // Dashes are painted on the boundary with the next lane, so a block of three
  // roads reads as one three-lane highway instead of three separate strips.
  if (stripeAhead) {
    for (let x = -BOUND - 6; x <= BOUND + 6; x += 2) {
      g.add(box(1.0, 0.02, 0.1, PALETTE.roadStripe, x, 0.005, -0.5));
    }
  }
  return g;
}

export function makeWaterTile() {
  const g = new THREE.Group();
  const tile = box(LANE_WIDTH, 0.4, 1, PALETTE.water, 0, -0.22, 0);
  tile.receiveShadow = true;
  g.add(tile);
  g.add(box(LANE_WIDTH, 0.02, 0.86, PALETTE.waterDeep, 0, -0.03, 0, { opacity: 0.45 }));
  return g;
}

export function makeRailTile() {
  const g = new THREE.Group();
  const tile = box(LANE_WIDTH, 0.4, 1, PALETTE.rail, 0, -0.2, 0);
  tile.receiveShadow = true;
  g.add(tile);
  for (let x = -BOUND - 8; x <= BOUND + 8; x += 0.7) {
    g.add(box(0.28, 0.06, 0.82, PALETTE.sleeper, x, 0.02, 0));
  }
  g.add(box(LANE_WIDTH, 0.09, 0.09, PALETTE.railMetal, 0, 0.06, -0.24));
  g.add(box(LANE_WIDTH, 0.09, 0.09, PALETTE.railMetal, 0, 0.06, 0.24));

  // Signal post on each side; the lamps flash while a train is inbound.
  const lamps = [];
  for (const side of [-1, 1]) {
    const x = side * (BOUND + 1.4);
    solid(g, 0.12, 1.5, 0.12, 0x3a3a40, x, 0.75, 0);
    solid(g, 0.5, 0.3, 0.16, 0x3a3a40, x, 1.55, 0);
    const a = box(0.16, 0.16, 0.06, 0x5a2020, x - 0.12, 1.55, -0.1);
    const b = box(0.16, 0.16, 0.06, 0x5a2020, x + 0.12, 1.55, -0.1);
    g.add(a, b);
    lamps.push(a, b);
  }
  g.userData.lamps = lamps;
  return g;
}

// --- obstacles --------------------------------------------------------------

export function makeTree(height, tint) {
  const g = new THREE.Group();
  solid(g, 0.26, 0.55, 0.26, PALETTE.trunk, 0, 0.27, 0);
  for (let i = 0; i < height; i += 1) {
    const w = 0.82 - i * 0.13;
    solid(g, w, 0.42, w, PALETTE.leaves[tint % PALETTE.leaves.length], 0, 0.62 + i * 0.38, 0);
  }
  return g;
}

export function makeRock() {
  const g = new THREE.Group();
  solid(g, 0.62, 0.4, 0.6, PALETTE.rock, 0, 0.2, 0);
  solid(g, 0.34, 0.22, 0.36, PALETTE.rock, 0.1, 0.48, -0.05);
  g.rotation.y = 0.4;
  return g;
}

// --- traffic ----------------------------------------------------------------

// Vehicles are always modelled pointing +x; the scene flips them for lanes
// that travel the other way.
export function makeCar(len, color) {
  const g = new THREE.Group();
  solid(g, len, 0.34, 0.74, color, 0, 0.29, 0);
  solid(g, len * 0.48, 0.3, 0.64, color, -len * 0.04, 0.6, 0);
  solid(g, len * 0.42, 0.2, 0.66, 0x2b3a4a, -len * 0.04, 0.64, 0);
  for (const sx of [-1, 1]) {
    for (const sz of [-1, 1]) {
      solid(g, 0.26, 0.24, 0.12, 0x22242a, sx * len * 0.3, 0.14, sz * 0.37);
    }
  }
  for (const sz of [-1, 1]) {
    g.add(box(0.06, 0.11, 0.18, 0xfff3b0, len / 2 - 0.01, 0.3, sz * 0.22, { emissive: 0x554a10 }));
  }
  return g;
}

export function makeTruck(len) {
  const g = new THREE.Group();
  solid(g, len * 0.34, 0.66, 0.78, PALETTE.truckCab, len * 0.32, 0.45, 0);
  solid(g, len * 0.3, 0.24, 0.7, 0x2b3a4a, len * 0.33, 0.66, 0);
  solid(g, len * 0.64, 0.78, 0.8, PALETTE.truckBody, -len * 0.17, 0.55, 0);
  for (const sx of [-0.34, -0.02, 0.32]) {
    for (const sz of [-1, 1]) {
      solid(g, 0.28, 0.26, 0.13, 0x22242a, sx * len, 0.15, sz * 0.39);
    }
  }
  return g;
}

export function makeLog(len) {
  const g = new THREE.Group();
  solid(g, len, 0.36, 0.72, PALETTE.log, 0, 0.16, 0);
  solid(g, 0.08, 0.32, 0.64, PALETTE.logEnd, -len / 2, 0.16, 0);
  solid(g, 0.08, 0.32, 0.64, PALETTE.logEnd, len / 2, 0.16, 0);
  return g;
}

export function makeTrain(len) {
  const g = new THREE.Group();
  solid(g, len, 1.15, 0.88, PALETTE.train, 0, 0.62, 0);
  solid(g, len, 0.14, 0.92, 0xd8412f, 0, 0.95, 0);
  solid(g, len * 0.96, 0.3, 0.94, 0x1d1f24, 0, 0.5, 0);
  return g;
}

// --- characters -------------------------------------------------------------

// Modelled facing -z, which is "forward" in world space.
export function makeChicken() {
  const g = new THREE.Group();
  solid(g, 0.58, 0.46, 0.52, PALETTE.chicken, 0, 0.34, 0);
  solid(g, 0.2, 0.28, 0.18, PALETTE.chicken, 0, 0.5, 0.3);
  solid(g, 0.36, 0.32, 0.32, PALETTE.chicken, 0, 0.72, -0.12);
  solid(g, 0.14, 0.1, 0.18, PALETTE.beak, 0, 0.68, -0.34);
  solid(g, 0.09, 0.15, 0.2, PALETTE.comb, 0, 0.92, -0.1);
  solid(g, 0.08, 0.26, 0.36, 0xe8e8e8, -0.32, 0.36, 0.02);
  solid(g, 0.08, 0.26, 0.36, 0xe8e8e8, 0.32, 0.36, 0.02);
  g.add(box(0.07, 0.07, 0.07, 0x2b2b2b, -0.15, 0.76, -0.28));
  g.add(box(0.07, 0.07, 0.07, 0x2b2b2b, 0.15, 0.76, -0.28));
  solid(g, 0.09, 0.16, 0.09, PALETTE.beak, -0.14, 0.08, 0.02);
  solid(g, 0.09, 0.16, 0.09, PALETTE.beak, 0.14, 0.08, 0.02);
  return g;
}

export function makeEagle() {
  const g = new THREE.Group();
  solid(g, 0.5, 0.4, 1.0, 0x4a3728, 0, 0, 0);
  solid(g, 0.34, 0.3, 0.3, 0xd9cfc2, 0, 0.2, -0.5);
  solid(g, 0.16, 0.1, 0.18, PALETTE.beak, 0, 0.16, -0.72);
  const wings = [];
  for (const side of [-1, 1]) {
    const w = box(1.5, 0.1, 0.6, 0x3f2f22, side * 0.95, 0.08, 0.05);
    w.castShadow = true;
    g.add(w);
    wings.push(w);
  }
  g.userData.wings = wings;
  return g;
}

export function makeShadowBlob() {
  const mesh = box(1, 0.02, 1, 0x000000, 0, 0.02, 0, { opacity: 0.28 });
  return mesh;
}
