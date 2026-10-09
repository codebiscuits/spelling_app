(function () {
  'use strict';

  var form = document.getElementById('arith-form');
  if (!form) return;

  var input = document.getElementById('answer');
  var timeField = document.getElementById('response-ms');
  // Time from the question appearing to the answer being sent. The server
  // checks and limits this value, and uses its own clock if it is missing.
  var shownAt = (window.performance && performance.now) ? performance.now() : null;

  if (input) input.focus();

  form.addEventListener('submit', function (e) {
    if (!input || !/^\s*\d+\s*$/.test(input.value)) {
      e.preventDefault();
      if (input) input.focus();
      return;
    }
    if (timeField && shownAt !== null) {
      timeField.value = String(Math.max(0, Math.round(performance.now() - shownAt)));
    }
  });
})();
