// input.js — keyboard, swipe and on-screen buttons, all funnelled into one
// callback that takes 'up' | 'down' | 'left' | 'right'.

const KEYS = {
  ArrowUp: 'up', KeyW: 'up',
  ArrowDown: 'down', KeyS: 'down',
  ArrowLeft: 'left', KeyA: 'left',
  ArrowRight: 'right', KeyD: 'right',
};

const SWIPE_MIN = 24;     // px before a drag counts as a swipe
const TAP_MAX = 14;       // px of movement still considered a tap

export class Input {
  constructor(surface, onMove, onConfirm) {
    this.onMove = onMove;
    this.onConfirm = onConfirm;
    this.start = null;

    window.addEventListener('keydown', (e) => {
      if (e.code === 'Space' || e.code === 'Enter') {
        e.preventDefault();
        this.onConfirm();
        return;
      }
      const move = KEYS[e.code];
      if (!move) return;
      e.preventDefault();     // stop arrow keys scrolling the page
      this.onMove(move);
    });

    surface.addEventListener('pointerdown', (e) => {
      this.start = { x: e.clientX, y: e.clientY };
    });

    surface.addEventListener('pointerup', (e) => {
      if (!this.start) return;
      const dx = e.clientX - this.start.x;
      const dy = e.clientY - this.start.y;
      this.start = null;

      // A tap is the mobile shorthand for "hop forward".
      if (Math.abs(dx) < TAP_MAX && Math.abs(dy) < TAP_MAX) {
        this.onMove('up');
        return;
      }
      if (Math.max(Math.abs(dx), Math.abs(dy)) < SWIPE_MIN) return;
      if (Math.abs(dx) > Math.abs(dy)) this.onMove(dx > 0 ? 'right' : 'left');
      else this.onMove(dy > 0 ? 'down' : 'up');
    });

    surface.addEventListener('pointercancel', () => { this.start = null; });

    for (const btn of document.querySelectorAll('[data-move]')) {
      // pointerdown, not click: waiting for click adds a noticeable delay.
      btn.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        this.onMove(btn.dataset.move);
      });
    }
  }
}

export default Input;
