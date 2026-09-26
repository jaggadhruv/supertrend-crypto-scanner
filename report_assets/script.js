  (function() {
    var currentFilter = 'all';
    var searchTerm = '';

    function applyFilters() {
      var rows = document.querySelectorAll('#scan-table tbody tr');
      rows.forEach(function(row) {
        var g = function(k) { return row.getAttribute(k); };
        var wSig = g('data-w-signal'), dSig = g('data-d-signal'), hSig = g('data-h-signal');
        var wRec = parseInt(g('data-w-recency') || '9999', 10);
        var dRec = parseInt(g('data-d-recency') || '9999', 10);
        var hRec = parseInt(g('data-h-recency') || '9999', 10);
        var m = true;
        switch (currentFilter) {
          case 'recent7':     m = dRec <= 7 || wRec <= 1 || hRec <= 42; break;  // 7 days on every timeframe
          case 'any-buy':     m = wSig === 'buy' || dSig === 'buy' || hSig === 'buy'; break;
          case 'any-sell':    m = wSig === 'sell' || dSig === 'sell'; break;
          case 'conf-bull':   m = g('data-confluence') === 'bull'; break;
          case 'conf-bear':   m = g('data-confluence') === 'bear'; break;
          case 'weekly-flip': m = g('data-w-flip') === '1'; break;
          case 'daily-flip':  m = g('data-d-flip') === '1'; break;
          case 'h4-flip':     m = g('data-h-flip') === '1'; break;
          case 'held':        m = g('data-held') === '1'; break;
          default:            m = true;
        }
        var matchesSearch = (g('data-ticker') || '').indexOf(searchTerm) !== -1;
        row.classList.toggle('hidden-row', !(m && matchesSearch));
      });
    }

    document.querySelectorAll('.chip-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        document.querySelectorAll('.chip-btn').forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
        currentFilter = btn.getAttribute('data-filter');
        applyFilters();
      });
    });

    var search = document.getElementById('search-box');
    if (search) {
      search.addEventListener('input', function() {
        searchTerm = search.value.trim().toLowerCase();
        applyFilters();
      });
    }

    var sortState = {};
    document.querySelectorAll('#scan-table thead th').forEach(function(th, colIndex) {
      th.addEventListener('click', function() {
        var tbody = document.querySelector('#scan-table tbody');
        var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
        var asc = !(sortState[colIndex] === 'asc');
        sortState = {};
        sortState[colIndex] = asc ? 'asc' : 'desc';
        document.querySelectorAll('#scan-table thead th').forEach(function(h) {
          h.classList.remove('sorted-asc', 'sorted-desc');
        });
        th.classList.add(asc ? 'sorted-asc' : 'sorted-desc');
        rows.sort(function(a, b) {
          var cellA = a.children[colIndex], cellB = b.children[colIndex];
          if (!cellA || !cellB) return 0;
          var va = cellA.getAttribute('data-sort'), vb = cellB.getAttribute('data-sort');
          if (va !== null && vb !== null) {
            va = parseFloat(va); vb = parseFloat(vb);
            return asc ? va - vb : vb - va;
          }
          var ta = cellA.textContent.trim().toLowerCase(), tb = cellB.textContent.trim().toLowerCase();
          if (ta < tb) return asc ? -1 : 1;
          if (ta > tb) return asc ? 1 : -1;
          return 0;
        });
        rows.forEach(function(r) { tbody.appendChild(r); });
      });
    });
  })();
