// config.js — every tunable number in the game lives here.
//
// The world is a grid of "lanes" (rows) that runs forward forever. One tile is
// one world unit, so a column index doubles as an x coordinate.

export const TILE = 1;

// Playable columns run from -BOUND to +BOUND. Hops past this are refused.
export const BOUND = 9;

// Cars, trucks and logs ride a conveyor belt that is much wider than the
// screen and wraps around at +/-BELT, so traffic never pops into view.
export const BELT = 24;
export const BELT_SPAN = BELT * 2;

// Lane tiles are drawn wider still, so the ground has no visible edge.
export const LANE_WIDTH = BELT * 2 + 16;

// How much world is kept alive around the player.
export const ROWS_AHEAD = 26;
export const ROWS_BEHIND = 10;

// The first few rows are always empty grass so you never die on frame one,
// plus an apron behind the start line so row 0 is not the edge of the world.
export const SAFE_ROWS = 4;
export const START_ROWS = 8;

// A hop is deliberately snappy — Crossy Road lives or dies on this number.
export const HOP_TIME = 0.13;
export const HOP_HEIGHT = 0.55;
export const QUEUE_MAX = 1;          // moves buffered while mid-hop

// The chicken's footprint, used for every collision test.
export const PLAYER_HALF = 0.32;

// Stall for too long and an eagle carries you off.
export const EAGLE_WARN = 9;
export const EAGLE_GRAB = 13;

// Difficulty ramps from 0 to 1 over this many rows, then stays pinned.
export const DIFFICULTY_ROWS = 160;

// Camera: orthographic, fixed isometric angle, damped follow.
export const CAMERA_VIEW = 12.5;     // world units of vertical view
// No sideways yaw: lanes then run straight across the screen and you see the
// long side of every car, which is the look the real game uses.
export const CAMERA_DIR = [0, 7.6, 6.4];
// Never show much more than the playfield, however wide the window is.
export const CAMERA_MAX_WIDTH = 21;
// The camera is orthographic, so this distance only sets where the scene sits
// in depth. Fog is placed relative to it rather than in absolute units.
export const CAMERA_DIST = 60;
export const CAMERA_LAG = 6.5;
export const CAMERA_X_CLAMP = 3.2;   // how far sideways the camera drifts
// Aim ahead of the chicken so it sits low on screen and you can read the road.
export const CAMERA_AHEAD = 3.4;

export const PALETTE = {
  grassA: 0x7cc242,
  grassB: 0x74b83c,
  road: 0x4a4a52,
  roadStripe: 0xe8e4d8,
  water: 0x3d94d6,
  waterDeep: 0x2f79b4,
  rail: 0x5a5a62,
  sleeper: 0x6b5138,
  railMetal: 0xb8bcc4,
  log: 0x8a5a32,
  logEnd: 0x74492a,
  trunk: 0x7a5230,
  leaves: [0x3f8f3a, 0x479c40, 0x357f31],
  rock: 0x9aa0a6,
  train: 0x2f3138,
  chicken: 0xfdfdfd,
  beak: 0xf5a623,
  comb: 0xe04545,
  cars: [0xe23b3b, 0x3b7de2, 0xf2c53d, 0x8e4fd0, 0xff8c42, 0x2fb47c, 0xe7e7e7],
  truckCab: 0x3a4a5e,
  truckBody: 0xf0f0f0,
};
