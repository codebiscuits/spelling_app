(function () {
  'use strict';

  var root = document.getElementById('test-root');
  if (!root) return;

  var attempt     = parseInt(root.dataset.attempt, 10);
  var answerSec   = document.getElementById('answer-section');
  var answerInput = document.getElementById('answer');

  // ── Attempt 1: play button reveals input ─────────────────────────────────
  if (attempt === 1) {
    var playBtn = document.getElementById('play-btn');
    var audioEl = document.getElementById('word-audio');

    if (playBtn && audioEl) {
      playBtn.addEventListener('click', function () {
        audioEl.play();
        answerSec.style.display = '';
        answerInput.focus();
      });
    } else {
      // No audio — reveal input immediately
      answerSec.style.display = '';
      answerInput.focus();
    }
  }

  // ── Attempt 2: "I'm Ready" hides the word and reveals input ──────────────
  if (attempt === 2) {
    var readyBtn    = document.getElementById('ready-btn');
    var wordDisplay = document.getElementById('word-display');

    if (readyBtn) {
      readyBtn.addEventListener('click', function () {
        if (wordDisplay) wordDisplay.style.display = 'none';
        readyBtn.style.display = 'none';
        answerSec.style.display = '';
        answerInput.focus();
      });
    }
  }

  // ── Submit guard: prevent empty submission ────────────────────────────────
  var form = document.getElementById('spell-form');
  if (form) {
    form.addEventListener('submit', function (e) {
      if (!answerInput || !answerInput.value.trim()) {
        e.preventDefault();
        if (answerInput) answerInput.focus();
      }
    });
  }
})();
