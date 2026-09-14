// scene.js — everything Three.js. Turns the simulation's numbers into meshes.
//
// Lane views are created when a lane first comes into range and disposed when
// the simulation culls the lane, so the scene graph stays roughly constant in
// size however far you run.

import * as THREE from 'three';
import {
  BOUND, CAMERA_AHEAD, CAMERA_DIR, CAMERA_DIST, CAMERA_LAG, CAMERA_MAX_WIDTH,
  CAMERA_VIEW, CAMERA_X_CLAMP, ROWS_AHEAD,
} from './config.js';
import { GRASS, RAIL, RIVER, ROAD } from './world.js';
import {
  initModels, makeCar, makeChicken, makeEagle, makeGrassTile, makeLog,
  makeRailTile, makeRoadTile, makeRock, makeShadowBlob, makeTrain, makeTree,
  makeTruck, makeWaterTile,
} from './models.js';

const SKY = 0xbfe4f7;

export class SceneView {
  constructor(canvas) {
    this.canvas = canvas;
    initModels(THREE);

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(SKY);
    // Only the far edge of the world fades out; the play area stays crisp.
    this.scene.fog = new THREE.Fog(SKY, CAMERA_DIST + 8, CAMERA_DIST + 26);

    this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, CAMERA_DIST * 3);
    this.camDir = new THREE.Vector3(...CAMERA_DIR).normalize();
    this.camX = 0;
    this.camZ = 0;

    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x86b96f, 0.75));
    const sun = new THREE.DirectionalLight(0xffffff, 0.85);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    const s = sun.shadow.camera;
    s.left = -16; s.right = 16; s.top = 16; s.bottom = -16; s.near = 1; s.far = 80;
    this.sun = sun;
    this.scene.add(sun);
    this.scene.add(sun.target);

    this.chicken = makeChicken();
    this.scene.add(this.chicken);

    this.eagle = makeEagle();
    this.eagle.visible = false;
    this.scene.add(this.eagle);

    this.blob = makeShadowBlob();
    this.blob.visible = false;
    this.scene.add(this.blob);

    this.laneViews = new Map();
    this.clock = 0;
    this.sink = 0;
    this.resize();
  }

  resize() {
    const w = this.canvas.clientWidth || window.innerWidth;
    const h = this.canvas.clientHeight || window.innerHeight;
    this.renderer.setSize(w, h, false);
    const aspect = w / h;
    // On tall phone screens pull back a little so the road still reads.
    let vh = CAMERA_VIEW * (aspect < 0.8 ? 1.3 : 1);
    let vw = vh * aspect;
    // On wide monitors, trade height for width rather than letting the view
    // spill past the playfield edges. The frustum must keep the canvas aspect
    // or the whole scene stretches, so height has to give.
    if (vw > CAMERA_MAX_WIDTH) {
      vw = CAMERA_MAX_WIDTH;
      vh = vw / aspect;
    }
    this.camera.left = -vw / 2;
    this.camera.right = vw / 2;
    this.camera.top = vh / 2;
    this.camera.bottom = -vh / 2;
    this.camera.updateProjectionMatrix();
  }

  // --- lane views ---------------------------------------------------------

  buildLaneView(lane, world) {
    let group;
    if (lane.type === ROAD) {
      const ahead = world.lane(lane.row + 1);
      group = makeRoadTile(!!ahead && ahead.type === ROAD);
    } else if (lane.type === RIVER) {
      group = makeWaterTile();
    } else if (lane.type === RAIL) {
      group = makeRailTile();
    } else {
      group = makeGrassTile(lane.shade);
    }
    group.position.z = -lane.row;

    for (const o of lane.obstacles || []) {
      const mesh = o.kind === 'tree' ? makeTree(o.height, o.tint) : makeRock();
      mesh.position.x = o.col;
      group.add(mesh);
    }

    const view = { group, meshes: new Map(), lane };
    this.scene.add(group);
    this.syncItems(view, lane);
    return view;
  }

  // Rail lanes gain and lose a train, so item meshes are reconciled by id
  // rather than built once.
  syncItems(view, lane) {
    const live = new Set();
    for (const item of lane.items) {
      live.add(item.id);
      let mesh = view.meshes.get(item.id);
      if (!mesh) {
        if (lane.type === RIVER) mesh = makeLog(item.len);
        else if (lane.type === RAIL) mesh = makeTrain(item.len);
        else if (lane.kind === 'truck') mesh = makeTruck(item.len);
        else mesh = makeCar(item.len, item.color);
        mesh.rotation.y = lane.dir > 0 ? 0 : Math.PI;
        view.group.add(mesh);
        view.meshes.set(item.id, mesh);
      }
      mesh.position.x = item.x;
    }
    for (const [id, mesh] of view.meshes) {
      if (!live.has(id)) {
        view.group.remove(mesh);
        view.meshes.delete(id);
      }
    }
  }

  dropLaneView(row) {
    const view = this.laneViews.get(row);
    if (!view) return;
    this.scene.remove(view.group);
    this.laneViews.delete(row);
  }

  // --- per frame ----------------------------------------------------------

  sync(game, dt) {
    this.clock += dt;
    const { world, player } = game;

    for (const [row, lane] of world.lanes) {
      if (row > player.row + ROWS_AHEAD) continue;
      // The frontier lane has no neighbour yet, and stripes are decided
      // once at build time. It is far off camera, so just wait a frame.
      if (row >= world.nextRow - 1) continue;
      let view = this.laneViews.get(row);
      if (!view) {
        view = this.buildLaneView(lane, world);
        this.laneViews.set(row, view);
      }
      this.syncItems(view, lane);
      if (lane.type === RAIL) {
        const on = lane.warning && Math.sin(this.clock * 12) > 0;
        for (let i = 0; i < view.group.userData.lamps.length; i += 1) {
          const lamp = view.group.userData.lamps[i];
          // The two lamps on a post alternate, like a real level crossing.
          const lit = lane.warning && (i % 2 === 0 ? on : !on);
          lamp.material = lit ? this.lampOn() : this.lampOff();
        }
      }
    }

    for (const row of [...this.laneViews.keys()]) {
      if (!world.lanes.has(row)) this.dropLaneView(row);
    }

    this.syncChicken(game, dt);
    this.syncEagle(game, dt);
    this.syncCamera(game, dt);
  }

  lampOn() {
    if (!this._lampOn) {
      this._lampOn = new THREE.MeshLambertMaterial({ color: 0xff4b3a, emissive: 0xcc2010 });
    }
    return this._lampOn;
  }

  lampOff() {
    if (!this._lampOff) this._lampOff = new THREE.MeshLambertMaterial({ color: 0x5a2020 });
    return this._lampOff;
  }

  syncChicken(game, dt) {
    const p = game.player;
    const lift = game.riding ? 0.34 : 0;
    // Interpolate z across the hop: -fromRow at t=0, -row at t=1.
    const z = -p.row + (p.hopping ? (1 - p.hopT) * (p.row - p.fromRow) : 0);
    this.chicken.position.set(p.x, p.y + lift - this.sink, z);

    // Lean into the hop and squash on landing — cheap, but it sells the weight.
    const t = p.hopping ? p.hopT : 1;
    const squash = p.hopping ? 1 + 0.18 * Math.sin(Math.PI * t) : 1;
    this.chicken.scale.set(1 / Math.sqrt(squash), squash, 1 / Math.sqrt(squash));
    this.chicken.rotation.y = p.facing;

    if (game.death === 'car' || game.death === 'train') {
      this.chicken.scale.set(1.3, 0.1, 1.3);
      this.chicken.position.y = 0.02;
    } else if (game.death === 'water' && this.sink < 0.9) {
      this.sink += dt * 1.6;
    }

    this.blob.visible = game.death !== 'water' && game.death !== 'eagle';
    this.blob.position.set(this.chicken.position.x, 0.03, z);
    const spread = 1 - Math.min(0.45, p.y * 0.5);
    this.blob.scale.set(0.7 * spread, 0.02, 0.7 * spread);
  }

  syncEagle(game, dt) {
    const showing = game.eagleWarning || game.death === 'eagle';
    this.eagle.visible = showing;
    if (!showing) return;

    const p = this.chicken.position;
    const dive = game.death === 'eagle' ? 1 : game.eagleProgress;
    const height = 7 - dive * 5.4;
    const orbit = this.clock * 2.2;
    const radius = 2.6 * (1 - dive * 0.85);

    this.eagle.position.set(
      p.x + Math.cos(orbit) * radius,
      height + (game.death === 'eagle' ? -1.2 : 0),
      p.z + Math.sin(orbit) * radius,
    );
    this.eagle.rotation.y = -orbit + Math.PI / 2;
    const flap = Math.sin(this.clock * 9) * 0.5;
    for (let i = 0; i < this.eagle.userData.wings.length; i += 1) {
      this.eagle.userData.wings[i].rotation.z = i === 0 ? flap : -flap;
    }
    if (game.death === 'eagle') this.chicken.position.copy(this.eagle.position);
  }

  syncCamera(game, dt) {
    const p = game.player;
    const targetX = Math.max(-CAMERA_X_CLAMP, Math.min(CAMERA_X_CLAMP, p.x * 0.55));
    const targetZ = -p.row;
    const k = 1 - Math.exp(-CAMERA_LAG * dt);
    this.camX += (targetX - this.camX) * k;
    this.camZ += (targetZ - this.camZ) * k;

    const focus = new THREE.Vector3(this.camX, 0, this.camZ - CAMERA_AHEAD);
    this.camera.position.copy(focus).addScaledVector(this.camDir, CAMERA_DIST);
    this.camera.lookAt(focus);

    this.sun.position.copy(focus).add(new THREE.Vector3(9, 18, 6));
    this.sun.target.position.copy(focus);
    this.sun.target.updateMatrixWorld();
  }

  snap(game) {
    this.sink = 0;
    this.camX = 0;
    this.camZ = -game.player.row;
  }

  clear() {
    for (const row of [...this.laneViews.keys()]) this.dropLaneView(row);
  }

  render() {
    this.renderer.render(this.scene, this.camera);
  }
}

export default SceneView;
