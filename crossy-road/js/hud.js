// hud.js — all DOM updates in one place, so nothing else has to touch the page.

import { DEATH_TEXT } from './game.js';

const BEST_KEY = 'crossy-best';

const $ = (id) => document.getElementById(id);

export class Hud {
  constructor() {
    this.el = {
      start: $('start'),
      over: $('over'),
      score: $('score'),
      best: $('best'),
      finalScore: $('final-score'),
      finalBest: $('final-best'),
      newBest: $('new-best'),
      cause: $('cause'),
      warnTrain: $('warn-train'),
      warnEagle: $('warn-eagle'),
      mute: $('mute'),
      pads: $('pads'),
    };
    this.best = Number(localStorage.getItem(BEST_KEY) || 0);
    // The best to beat for the current run, captured at the start so the
    // "new best" ribbon can tell a record from merely matching one.
    this.runStartBest = this.best;
    this.shownScore = -1;
    this.el.best.textContent = this.best;

    // Touch devices get the d-pad; a mouse user has the keyboard.
    if (matchMedia('(hover: none)').matches) this.el.pads.hidden = false;
  }

  setScreen(name) {
    this.el.start.hidden = name !== 'start';
    this.el.over.hidden = name !== 'over';
    document.body.dataset.screen = name;
  }

  setScore(score) {
    if (score === this.shownScore) return;
    this.shownScore = score;
    this.el.score.textContent = score;
    if (score > this.best) {
      this.best = score;
      this.el.best.textContent = score;
      // Persist as it climbs, so a refresh mid-run does not lose the record.
      localStorage.setItem(BEST_KEY, String(score));
    }
    this.el.score.classList.remove('pop');
    void this.el.score.offsetWidth;    // restart the CSS animation
    this.el.score.classList.add('pop');
  }

  setWarnings(train, eagle) {
    this.el.warnTrain.hidden = !train;
    this.el.warnEagle.hidden = !eagle;
  }

  showGameOver(score, cause) {
    const isBest = score > 0 && score > this.runStartBest;
    if (score > this.best) {
      this.best = score;
      localStorage.setItem(BEST_KEY, String(score));
    }
    this.el.finalScore.textContent = score;
    this.el.finalBest.textContent = this.best;
    this.el.newBest.hidden = !isBest;
    this.el.cause.textContent = DEATH_TEXT[cause] || '';
    this.setScreen('over');
  }

  setMuted(muted) {
    this.el.mute.textContent = muted ? 'Sound off' : 'Sound on';
    this.el.mute.setAttribute('aria-pressed', String(muted));
  }

  reset() {
    this.runStartBest = this.best;
    this.shownScore = -1;
    this.setScore(0);
    this.setWarnings(false, false);
  }
}

export default Hud;
