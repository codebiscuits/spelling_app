(function () {
  'use strict';

  // Sortable tables: click a heading to sort by that column.
  document.querySelectorAll('table.sortable').forEach(function (table) {
    var heads = table.querySelectorAll('thead th');
    heads.forEach(function (th, col) {
      th.style.cursor = 'pointer';
      th.addEventListener('click', function () {
        var tbody = table.tBodies[0];
        var rows = Array.prototype.slice.call(tbody.rows);
        var dir = th.getAttribute('data-dir') === 'asc' ? -1 : 1;
        var numeric = th.getAttribute('data-type') === 'num';
        rows.sort(function (a, b) {
          var x = a.cells[col].textContent.trim();
          var y = b.cells[col].textContent.trim();
          if (numeric) return dir * (parseFloat(x) - parseFloat(y));
          return dir * x.localeCompare(y);
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
        heads.forEach(function (h) { h.removeAttribute('data-dir'); });
        th.setAttribute('data-dir', dir === 1 ? 'asc' : 'desc');
      });
    });
  });

  var dataEl = document.getElementById('chart-data');
  if (!dataEl || typeof Chart === 'undefined') return;
  var d = JSON.parse(dataEl.textContent);

  // Palette colours are set on :root by base.html
  function colour(n, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue('--color-' + n).trim();
    return v || fallback;
  }

  function series(label, data, c) {
    return {
      label: label, data: data, borderColor: c, backgroundColor: c,
      borderWidth: 3, pointRadius: 6, pointHoverRadius: 9,
      tension: 0.2, spanGaps: true
    };
  }

  function open(evt, elements) {
    if (elements.length) window.location.href = d.urls[elements[0].index];
  }

  function make(id, datasets, yTitle, max) {
    var el = document.getElementById(id);
    if (!el) return;
    new Chart(el, {
      type: 'line',
      data: { labels: d.labels, datasets: datasets },
      options: {
        responsive: true,
        onClick: open,
        onHover: function (evt, els) { evt.native.target.style.cursor = els.length ? 'pointer' : 'default'; },
        interaction: { mode: 'nearest', intersect: true },
        scales: {
          y: { beginAtZero: true, max: max, title: { display: true, text: yTitle } }
        }
      }
    });
  }

  make('chart-accuracy', [series('First-try accuracy (%)', d.accuracy, colour(1, '#d63031'))],
       'Percent', 100);
  if (d.subject === 'spelling') {
    make('chart-counts', [
      series('Mastered words', d.secure, colour(3, '#00897b')),
      series('Words needing review', d.review, colour(4, '#1565c0'))
    ], 'Words');
  } else {
    make('chart-counts', [series('Secure directions', d.secure, colour(3, '#00897b'))], 'Directions');
    make('chart-time', [series('Median seconds', d.median_s, colour(4, '#1565c0'))], 'Seconds');
  }
})();
