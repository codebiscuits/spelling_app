(function () {
  'use strict';

  var root = document.getElementById('test-root');
  if (!root) return;

  var attempt     = parseInt(root.dataset.attempt, 10);
  var answerSec   = document.getElementById('answer-section');
  var answerInput = document.getElementById('answer');

  var wellDoneBanner = document.querySelector('.well-done-banner');

  function dismissWellDone() {
    if (wellDoneBanner) wellDoneBanner.style.display = 'none';
  }

  function playAudio(el) {
    var promise = el.play();
    if (promise !== undefined) {
      promise.catch(function (err) {
        console.warn('Audio playback failed:', err);
      });
    }
  }

  // ── Attempt 1: play button reveals input ─────────────────────────────────
  if (attempt === 1) {
    var playBtn = document.getElementById('play-btn');
    var audioEl = document.getElementById('word-audio');

    if (playBtn && audioEl) {
      playBtn.addEventListener('click', function () {
        dismissWellDone();
        playAudio(audioEl);
        answerSec.style.display = '';
        answerInput.focus();
      });
    } else {
      // No audio — reveal input immediately
      answerSec.style.display = '';
      answerInput.focus();
    }
  }

  // ── Attempt 2: auto-play phrase, then "I'm Ready" hides the word ─────────
  if (attempt === 2) {
    var phraseAudio = document.getElementById('phrase-audio');
    var readyBtn    = document.getElementById('ready-btn');
    var wordDisplay = document.getElementById('word-display');

    if (phraseAudio) {
      playAudio(phraseAudio);
    }

    if (readyBtn) {
      readyBtn.addEventListener('click', function () {
        dismissWellDone();
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
