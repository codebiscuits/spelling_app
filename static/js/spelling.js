(function () {
  'use strict';

  var root = document.getElementById('test-root');
  if (!root) return;

  var mode        = root.dataset.mode;
  var attempt     = parseInt(root.dataset.attempt, 10);
  var audioUrl    = root.dataset.audioUrl;

  var playBtn     = document.getElementById('play-btn');
  var audioEl     = document.getElementById('word-audio');
  var answerSec   = document.getElementById('answer-section');
  var answerInput = document.getElementById('answer');
  var readyBtn    = document.getElementById('ready-btn');
  var wordDisplay = document.getElementById('word-display');

  // ── Attempt 2: "I'm Ready" flow ──────────────────────────────────────────
  if (attempt === 2 && readyBtn) {
    readyBtn.addEventListener('click', function () {
      if (wordDisplay) wordDisplay.style.display = 'none';
      readyBtn.style.display = 'none';
      var audioSec = document.getElementById('audio-section');
      if (audioSec) audioSec.style.display = '';
      answerSec.style.display = '';
      answerInput.focus();
    });
    return; // don't also run audio/visual logic
  }

  // ── Audio mode, attempt 1 ─────────────────────────────────────────────────
  if (mode === 'audio' && attempt === 1) {
    if (playBtn && audioEl) {
      playBtn.addEventListener('click', function () {
        audioEl.play();
        answerSec.style.display = '';
        answerInput.focus();
      });
    } else {
      // No audio available — show answer box immediately
      answerSec.style.display = '';
      answerInput.focus();
    }
    return;
  }

  // ── Visual mode, attempt 1 ────────────────────────────────────────────────
  if (mode === 'visual' && attempt === 1) {
    var visualWord  = document.getElementById('visual-word');
    var hideWordBtn = document.getElementById('hide-word-btn');

    if (!visualWord) return;

    var word = root.dataset.word || '';
    if (!word) {
      answerSec.style.display = '';
      answerInput.focus();
      return;
    }

    visualWord.textContent = word;
    hideWordBtn.style.display = '';

    hideWordBtn.addEventListener('click', function () {
      visualWord.textContent = '';
      hideWordBtn.style.display = 'none';
      answerSec.style.display = '';
      answerInput.focus();
    });
  }

  // ── Submit guard: prevent empty submission ────────────────────────────────
  var form = document.getElementById('spell-form');
  if (form) {
    form.addEventListener('submit', function (e) {
      var val = answerInput ? answerInput.value.trim() : '';
      if (!val) {
        e.preventDefault();
        answerInput && answerInput.focus();
      }
    });
  }
})();
