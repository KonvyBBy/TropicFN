document.addEventListener("DOMContentLoaded", () => {

  // =============== UTILITIES ===============
  async function postJSON(url, data = {}) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    let json;
    try {
      json = await res.json();
    } catch (e) {
      console.error("Failed to parse server response as JSON:", e);
      throw new Error(`Server error (${res.status}). Please try again later.`);
    }
    if (!res.ok) throw new Error(json.message || json.error || "Request failed");
    return json;
  }

  const qs = (id) => document.getElementById(id);
  const MIN_COSMETIC_SEARCH_LENGTH = 2;
  const MAX_COSMETIC_RESULTS = 10;
  const DEFAULT_COSMETIC_TYPES = ['outfit', 'pickaxe', 'emote', 'glider'];
  const PREVIEW_TILE_COUNT = 8; // 2 rows × 4 columns in the card image grid
  const AUTO_SEARCH_DEBOUNCE_MS = 350;
  const TUTORIAL_PROMPT_DELAY_MS = 450;

  // =============== AUTH NAVIGATION ===============
  function openAuthPage(mode = "login") {
    window.location.href = mode === "register" ? "/register" : "/login";
  }

  qs("sign-in-trigger")?.addEventListener("click", () => openAuthPage("login"));


  // =============== PROCESSING OVERLAY ===============
  function showProcessingOverlay() {
    let overlay = qs('processing-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'processing-overlay';
      overlay.className = 'processing-overlay';
      overlay.innerHTML = `
        <div class="processing-content">
          <div class="processing-spinner"></div>
          <div class="processing-title">Processing Purchase...</div>
          <div class="processing-message">
            Please wait while we secure your account.<br>
            This usually takes 5-15 seconds.
          </div>
          <div class="processing-warning">
            ⚠️ DO NOT refresh or close this page!<br>
            Doing so may cause your purchase to fail.
          </div>
        </div>
      `;
      document.body.appendChild(overlay);
    }
    overlay.classList.add('active');
  }

  function hideProcessingOverlay() {
    const overlay = qs('processing-overlay');
    if (overlay) overlay.classList.remove('active');
  }

  // =============== NAMING MODAL ===============
  function showNamingModal(purchaseIndex, onDone) {
    const existing = document.getElementById('naming-modal-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'naming-modal-overlay';
    overlay.className = 'naming-modal-overlay';
    overlay.innerHTML = `
      <div class="naming-modal">
        <h3>✅ Purchase Successful!</h3>
        <p>Give this account a name so you can identify it easily.</p>
        <div class="form-group">
          <label class="form-label">Account Name</label>
          <input id="naming-modal-input" type="text" class="form-input" placeholder="e.g. My Main Account" maxlength="50" />
        </div>
        <div class="naming-modal-actions">
          <button id="naming-modal-submit" class="btn-naming-submit">Save Name</button>
          <button id="naming-modal-skip" class="btn-naming-skip">Skip</button>
        </div>
        <div id="naming-modal-error" style="display:none;color:#ff8080;font-size:0.85rem;margin-top:0.5rem;"></div>
      </div>
    `;

    document.body.appendChild(overlay);

    const input = document.getElementById('naming-modal-input');
    const errEl = document.getElementById('naming-modal-error');
    input.focus();

    async function submitName() {
      const name = input.value.trim();
      if (!name) {
        errEl.textContent = 'Please enter a name.';
        errEl.style.display = 'block';
        return;
      }
      try {
        await postJSON('/api/fortnite/name-account', { purchase_index: purchaseIndex, name });
        overlay.remove();
        onDone();
      } catch (e) {
        errEl.textContent = e.message || 'Failed to save name.';
        errEl.style.display = 'block';
      }
    }

    document.getElementById('naming-modal-submit').onclick = submitName;
    document.getElementById('naming-modal-skip').onclick = () => {
      overlay.remove();
      onDone();
    };

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') submitName();
    });
  }


  // =============== LOAD COSMETICS DATA ===============
  const cosmeticsSearchCache = new Map();
  const cosmeticsSearchInFlight = new Map();

  async function searchCosmetics(query, allowedTypes) {
    const q = String(query || "").trim().toLowerCase();
    if (q.length < MIN_COSMETIC_SEARCH_LENGTH) return [];

    const normalizedAllowed = (allowedTypes || DEFAULT_COSMETIC_TYPES)
      .map(v => String(v).toLowerCase())
      .sort();
    const cacheKey = `${q}::${normalizedAllowed.join(',')}`;

    if (cosmeticsSearchCache.has(cacheKey)) {
      return cosmeticsSearchCache.get(cacheKey);
    }
    if (cosmeticsSearchInFlight.has(cacheKey)) {
      return cosmeticsSearchInFlight.get(cacheKey);
    }

    const url = `https://fortnite-api.com/v2/cosmetics/br/search/all?name=${encodeURIComponent(q)}&matchMethod=contains&language=en&searchLanguage=en`;
    const request = fetch(url)
      .then(async (res) => {
        if (!res.ok) throw new Error(`Cosmetic search failed: ${res.status}`);
        const data = await res.json();
        const allowedTypeSet = new Set(normalizedAllowed);
        const filtered = (Array.isArray(data?.data) ? data.data : [])
          .filter(item => {
            const itemType = String(item?.type?.value || '').toLowerCase();
            const name = String(item?.name || '').toLowerCase();
            return name.includes(q) && allowedTypeSet.has(itemType);
          })
          .slice(0, MAX_COSMETIC_RESULTS);
        cosmeticsSearchCache.set(cacheKey, filtered);
        return filtered;
      })
      .catch((err) => {
        console.warn("Cosmetic search failed:", err);
        return [];
      })
      .finally(() => cosmeticsSearchInFlight.delete(cacheKey));

    cosmeticsSearchInFlight.set(cacheKey, request);
    return request;
  }

  // =============== COSMETIC AUTOCOMPLETE LOGIC ===============

  function updateSelection(items, index) {
    items.forEach((item, idx) => {
      item.classList.toggle('selected', idx === index);
      if (idx === index) {
        item.scrollIntoView({ block: 'nearest' });
      }
    });
  }

  async function filterCosmetics(query, dropdown, allowedTypes) {
    if (!query || query.length < MIN_COSMETIC_SEARCH_LENGTH) {
      dropdown.classList.remove('show');
      return;
    }

    const q = query.toLowerCase();
    const filtered = await searchCosmetics(q, allowedTypes);

    if (filtered.length === 0) {
      dropdown.innerHTML = '<div class="autocomplete-no-results">No items found</div>';
      dropdown.classList.add('show');
      return;
    }

    dropdown.innerHTML = filtered.map((item, idx) => {
      const type = item.type?.displayValue || item.type?.value || 'Item';
      const rarity = item.rarity?.displayValue?.toLowerCase() || 'common';
      const icon = item.images?.icon || item.images?.smallIcon || '';
      
      return `
        <div class="autocomplete-item" data-index="${idx}" data-name="${item.name}" data-id="${item.id || ''}">
          ${icon ? `<img src="${icon}" alt="${item.name}" loading="lazy">` : ''}
          <div class="autocomplete-item-info">
            <div class="autocomplete-item-name">${item.name}</div>
            <div class="autocomplete-item-type">${type}</div>
          </div>
          <div class="autocomplete-item-rarity rarity-${rarity}">${rarity}</div>
        </div>
      `;
    }).join('');

    dropdown.classList.add('show');
  }

  function setupAutocomplete(input, dropdown, allowedTypes) {
    let selectedIndex = -1;
    let debounceTimer = null;
    const fieldName = String(input.getAttribute('name') || '');
    const chipsContainer = input.parentElement?.querySelector(`.selected-cosmetics[data-cosmetic-field="${fieldName}"]`);

    function getSelectedIds() {
      if (!chipsContainer) return [];
      return Array.from(chipsContainer.querySelectorAll('.selected-cosmetic-chip'))
        .map((chip) => String(chip.getAttribute('data-cosmetic-id') || ''))
        .filter(Boolean);
    }

    function emitFilterChange() {
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function addSelectedCosmetic(itemId, itemName) {
      const normalizedId = String(itemId || '').trim();
      const normalizedName = String(itemName || '').trim();
      if (!chipsContainer || !fieldName || !normalizedId || !normalizedName) return;
      const existingIds = getSelectedIds();
      if (existingIds.includes(normalizedId)) {
        // Ignore duplicate selections so each cosmetic is only sent once in search payload.
        input.value = '';
        return;
      }

      const chip = document.createElement('span');
      chip.className = 'selected-cosmetic-chip';
      chip.setAttribute('data-cosmetic-id', normalizedId);

      const chipLabel = document.createElement('span');
      chipLabel.className = 'selected-cosmetic-chip-label';
      chipLabel.textContent = normalizedName;

      const removeButton = document.createElement('button');
      removeButton.type = 'button';
      removeButton.className = 'selected-cosmetic-remove';
      removeButton.setAttribute('aria-label', `Remove ${normalizedName}`);
      removeButton.textContent = '×';

      chip.appendChild(chipLabel);
      chip.appendChild(removeButton);

      const hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = fieldName;
      hidden.value = normalizedId;
      hidden.className = 'selected-cosmetic-value';
      hidden.setAttribute('data-cosmetic-id', normalizedId);
      chip.appendChild(hidden);

      removeButton.addEventListener('click', () => {
        chip.remove();
        emitFilterChange();
      });

      chipsContainer.appendChild(chip);
      input.value = '';
      input.removeAttribute('data-cosmetic-id');
      emitFilterChange();
    }
    
    input.addEventListener('input', (e) => {
      input.removeAttribute('data-cosmetic-id');
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(async () => {
        await filterCosmetics(e.target.value, dropdown, allowedTypes);
      }, 200);
    });
    
    input.addEventListener('keydown', (e) => {
      const items = dropdown.querySelectorAll('.autocomplete-item');
      
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
        updateSelection(items, selectedIndex);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        selectedIndex = Math.max(selectedIndex - 1, -1);
        updateSelection(items, selectedIndex);
      } else if (e.key === 'Enter' && selectedIndex >= 0) {
        e.preventDefault();
        items[selectedIndex]?.click();
      } else if (e.key === 'Escape') {
        dropdown.classList.remove('show');
      }
    });
    
    dropdown.addEventListener('click', (e) => {
      const item = e.target.closest('.autocomplete-item');
      if (item) {
        addSelectedCosmetic(item.dataset.id, item.dataset.name);
        dropdown.classList.remove('show');
      }
    });
  }

  document.querySelectorAll('.cosmetic-search-input').forEach((input) => {
    const dropdown = input.parentElement?.querySelector('.autocomplete-dropdown');
    if (!dropdown) return;
    const cosmeticType = String(input.dataset.cosmeticType || '').toLowerCase();
    const allowedTypes = cosmeticType ? [cosmeticType] : DEFAULT_COSMETIC_TYPES;
    setupAutocomplete(input, dropdown, allowedTypes);
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('.autocomplete-wrapper')) {
      document.querySelectorAll('.autocomplete-dropdown').forEach(d => {
        d.classList.remove('show');
      });
    }
  });

  // =============== SEARCH FORM SUBMIT ===============
  const searchForm = document.getElementById('search-form');
  const searchResults = document.getElementById('search-results');
  const sortButtons = Array.from(document.querySelectorAll('.toolbar-tab[data-sort]'));
  const mobileSortSelect = document.getElementById('mobile-sort-select');
  let currentSort = 'cheap';
  let lastSearchAccounts = [];
  let searchDebounceTimer = null;
  let searchRequestId = 0;
  const initialSearchStateHtml = searchResults ? searchResults.innerHTML : '';
  const MAX_PREVIEW_COSMETICS = 8;
  const BOOLEAN_FILTER_KEYS = new Set([]);
  const ENUM_FILTER_KEYS = new Set(['change_email']);
  const allowedFormKeys = new Set([
    'pmin', 'pmax', 'change_email',
    'skin[]', 'pickaxe[]', 'dance[]', 'glider[]',
    'smin', 'smax', 'pickaxe_min', 'pickaxe_max', 'dmin', 'dmax', 'gmin', 'gmax',
    'vbmin', 'vbmax', 'lmin', 'lmax', 'paid_items_min', 'paid_items_max',
    'refund_credits_min', 'refund_credits_max', 'daybreak', 'daybreak_max'
  ]);

  function normalizePayloadValue(key, value) {
    if (value == null) return undefined;
    const trimmed = String(value).trim();
    if (!trimmed) return undefined;

    if (BOOLEAN_FILTER_KEYS.has(key)) {
      if (trimmed === 'yes') return true;
      if (trimmed === 'no') return false;
      if (trimmed === 'true') return true;
      if (trimmed === 'false') return false;
      return undefined;
    }

    if (ENUM_FILTER_KEYS.has(key)) {
      const lowered = trimmed.toLowerCase();
      if (lowered === 'maybe') return 'yes';
      if (lowered === 'yes' || lowered === 'no' || lowered === 'nomatter') return lowered;
      return undefined;
    }

    return trimmed;
  }

  function buildSearchPayload(formData, items, form) {
    const payload = {};
    if (Array.isArray(items) && items.length > 0) {
      payload.item = items.join(', ');
    }

    formData.forEach((value, key) => {
      if (!allowedFormKeys.has(key)) return;
      const normalized = normalizePayloadValue(key, value);
      if (normalized == null) return;

      if (payload[key] !== undefined) {
        if (!Array.isArray(payload[key])) payload[key] = [payload[key]];
        payload[key].push(normalized);
      } else {
        payload[key] = normalized;
      }
    });

    // Resolve cosmetic search inputs: replace text names with marketplace-compatible IDs.
    // The fortnite-api.com IDs (stored in data-cosmetic-id) map to marketplace filter IDs
    // by lowercasing and stripping the known prefix for each cosmetic type.
    const cosmeticFieldPrefixes = {
      'skin[]':    'cid_',
      'dance[]':   'eid_',
      'glider[]':  'glider_id_',
      'pickaxe[]': '',  // keep full lowercase ID
    };
    function toCosmeticMarketId(rawId, prefix) {
      const lowerId = rawId.toLowerCase();
      return prefix && lowerId.startsWith(prefix) ? lowerId.slice(prefix.length) : lowerId;
    }
    for (const [fieldName, prefix] of Object.entries(cosmeticFieldPrefixes)) {
      const selectedInputs = form
        ? Array.from(form.querySelectorAll(`input.selected-cosmetic-value[name="${fieldName}"]`))
        : [];
      const selectedIds = selectedInputs
        .map((hiddenInput) => toCosmeticMarketId(hiddenInput.value || '', prefix))
        .filter(Boolean);
      if (selectedIds.length === 1) payload[fieldName] = selectedIds[0];
      else if (selectedIds.length > 1) payload[fieldName] = selectedIds;
      else delete payload[fieldName];
    }

    const pmax = Number(payload.pmax || 0);
    if (pmax > 0) payload.budget = pmax;

    return payload;
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  const previewIconCache = new Map();

  async function hydratePreviewIcons() {
    const tiles = Array.from(document.querySelectorAll('.market-preview-tile[data-cosmetic-name]'));
    if (!tiles.length) return;

    const names = [...new Set(tiles
      .map(tile => tile.dataset.cosmeticName || '')
      .filter(Boolean))];
    const missing = names.filter(name => !previewIconCache.has(name));

    if (missing.length) {
      try {
        const res = await fetch("/api/skins/icons", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ names: missing }),
        });
        if (!res.ok) throw new Error(`Failed to fetch cosmetic icons: ${res.status}`);
        const data = await res.json();
        const icons = Array.isArray(data.icons) ? data.icons : [];
        const returnedNames = new Set();
        icons.forEach(icon => {
          previewIconCache.set(icon.name, icon.icon || null);
          returnedNames.add(icon.name);
        });
        missing.forEach(name => {
          if (!returnedNames.has(name)) previewIconCache.set(name, null);
        });
      } catch (e) {
        missing.forEach(name => previewIconCache.set(name, null));
      }
    }

    tiles.forEach(tile => {
      if (tile.hasAttribute('data-hydrated')) return;
      const name = tile.dataset.cosmeticName || '';
      const icon = previewIconCache.get(name);
      if (!icon) return;
      tile.innerHTML = `<img src="${escapeHtml(icon)}" alt="${escapeHtml(name)}" loading="lazy">`;
      tile.setAttribute('data-hydrated', '');
      tile.classList.add('has-image');
    });
  }

  function getSortedAccounts(accounts) {
    const list = [...accounts];
    if (currentSort === 'cheap') list.sort((a, b) => (a.user_price || 0) - (b.user_price || 0));
    if (currentSort === 'expensive') list.sort((a, b) => (b.user_price || 0) - (a.user_price || 0));
    if (currentSort === 'newest') list.sort((a, b) => (b.item_id || 0) - (a.item_id || 0));
    if (currentSort === 'oldest') list.sort((a, b) => (a.item_id || 0) - (b.item_id || 0));
    return list;
  }

  function setSort(sort) {
    currentSort = sort;
    sortButtons.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.sort === sort);
    });
    if (mobileSortSelect && mobileSortSelect.value !== sort) {
      mobileSortSelect.value = sort;
    }
    if (lastSearchAccounts.length) renderAccounts(getSortedAccounts(lastSearchAccounts));
  }

  sortButtons.forEach(btn => {
    btn.addEventListener('click', () => setSort(btn.dataset.sort || 'default'));
  });
  mobileSortSelect?.addEventListener('change', () => setSort(mobileSortSelect.value || 'default'));

  function renderInitialState() {
    if (!searchResults) return;
    searchResults.innerHTML = initialSearchStateHtml;
  }

  function renderEmptyState() {
    searchResults.innerHTML = `
      <div style="grid-column:1/-1;text-align:center;padding:48px 24px;">
        <div style="font-size:2.5rem;margin-bottom:12px;opacity:0.5;">😕</div>
        <div style="font-size:0.95rem;font-weight:600;color:#e4e4e7;margin-bottom:6px;">No accounts found</div>
        <div style="font-size:0.82rem;color:#71717a;">Try different items or adjust your filters</div>
      </div>
    `;
  }

  function renderAccounts(accounts) {
    searchResults.innerHTML = '';

    if (!accounts || accounts.length === 0) {
      renderEmptyState();
      return;
    }

    accounts.forEach(acc => {
      const card = document.createElement('div');
      card.className = 'market-account-card';

      const numericPrice = Number(acc.user_price);
      const hasPrice = Number.isFinite(numericPrice);
      const formattedPrice = hasPrice ? numericPrice.toFixed(2) : 'N/A';
      const cardTitle = escapeHtml(acc.title || `${acc.skins || 0} Skins | Fortnite Account`);

      // 8 preview image tiles (2 rows × 4 cols)
      const previews = Array.isArray(acc.preview_cosmetics) ? acc.preview_cosmetics : [];
      const tiles = Array.from({length: PREVIEW_TILE_COUNT}, (_, i) => {
        const name = previews[i] || '';
        return `<div class="market-preview-tile"${name ? ` data-cosmetic-name="${escapeHtml(name)}"` : ''}></div>`;
      }).join('');

      card.innerHTML = `
        <div class="sx-card-imgs">
          <div class="sx-imgs-grid">${tiles}</div>
          <span class="sx-price-badge">$${formattedPrice}</span>
          <div class="sx-img-bar"></div>
        </div>
        <div class="sx-card-body">
          <div class="sx-card-title">${cardTitle}</div>
          <div class="sx-card-meta">
            <span class="sx-meta-item"><i class="ri-t-shirt-2-line"></i> ${acc.skins || 0}</span>
            <span class="sx-meta-item"><i class="ri-copper-diamond-line"></i> ${acc.vbucks || 0}</span>
            <span class="sx-meta-item"><i class="ri-mail-line"></i></span>
          </div>
          <div class="sx-card-platforms">
            <span class="sx-plat sx-plat-xb"><i class="ri-xbox-line"></i> XB</span>
            <span class="sx-plat sx-plat-ps"><i class="ri-playstation-line"></i> PS</span>
          </div>
        </div>
      `;

      const openDetail = () => {
        const itemId = Number(acc.item_id);
        if (!Number.isFinite(itemId) || itemId <= 0) return;
        window.location.href = `/account/${itemId}`;
      };

      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");
      card.setAttribute("aria-label", `Open ${cardTitle}`);
      card.addEventListener("click", openDetail);
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openDetail();
        }
      });

      searchResults.appendChild(card);
    });

    // Lazy-load cosmetic images after all cards are in the DOM
    hydratePreviewIcons();
  }

  async function executeSearch({ showEmptyAlert = false } = {}) {
    if (!searchForm || !searchResults) return;

    const fd = new FormData(searchForm);
    const payload = buildSearchPayload(fd, [], searchForm);
    const hasFilters = Object.keys(payload).length > 0;
    if (!hasFilters) {
      payload['pickaxe[]'] = 'defaultpickaxe';
      currentSort = 'cheap';
    }

    const requestId = ++searchRequestId;
    searchResults.innerHTML = `
      <div style="grid-column:1/-1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:48px 24px;gap:14px;">
        <div style="width:36px;height:36px;border:3px solid rgba(255,255,255,0.08);border-top-color:#0EF475;border-radius:50%;animation:spin 0.8s linear infinite;"></div>
        <div style="font-size:0.9rem;font-weight:500;color:#a1a1aa;">Searching for accounts...</div>
      </div>
    `;

    try {
      const data = await postJSON('/api/fortnite/search', payload);
      if (requestId !== searchRequestId) return;
      lastSearchAccounts = Array.isArray(data.accounts) ? data.accounts : [];
      renderAccounts(getSortedAccounts(lastSearchAccounts));
    } catch (err) {
      if (requestId !== searchRequestId) return;
      searchResults.innerHTML = `
        <div style="grid-column:1/-1;text-align:center;padding:48px 24px;">
          <div style="font-size:2.5rem;margin-bottom:12px;opacity:0.5;">❌</div>
          <div style="font-size:0.95rem;font-weight:600;color:#e4e4e7;margin-bottom:6px;">Search Error</div>
          <div style="font-size:0.82rem;color:#71717a;">${err.message}</div>
        </div>
      `;
    }
  }

  function scheduleAutoSearch() {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
      executeSearch({ showEmptyAlert: false });
    }, AUTO_SEARCH_DEBOUNCE_MS);
  }

  searchForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    executeSearch({ showEmptyAlert: true });
  });

  searchForm?.addEventListener('input', (e) => {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;
    if (!target.matches('input, select, textarea')) return;
    scheduleAutoSearch();
  });

  searchForm?.addEventListener('change', (e) => {
    const target = e.target;
    if (!(target instanceof HTMLElement)) return;
    if (!target.matches('input, select, textarea')) return;
    scheduleAutoSearch();
  });

  searchForm?.addEventListener('reset', () => {
    window.setTimeout(() => {
      ++searchRequestId;
      clearTimeout(searchDebounceTimer);
      lastSearchAccounts = [];
      document.querySelectorAll('.autocomplete-dropdown').forEach(d => d.classList.remove('show'));
      document.querySelectorAll('.cosmetic-search-input').forEach(i => i.removeAttribute('data-cosmetic-id'));
      document.querySelectorAll('.selected-cosmetic-chip').forEach(chip => chip.remove());
      executeSearch({ showEmptyAlert: false });
    }, 0);
  });

  function startDashboardTutorial() {
    const isMobile = window.matchMedia('(max-width: 1023px)').matches;
    const steps = isMobile
      ? [
          { selector: '#mobile-filter-toggle', title: 'Filters', text: 'Tap here to open filters and adjust your search.' },
          { selector: '#search-results', title: 'Results', text: 'Accounts will appear here in a grid.' },
          { selector: '#result-count', title: 'Live Count', text: 'This shows how many accounts match right now.' },
        ]
      : [
          { selector: '#search-form', title: 'Filters Panel', text: 'Use this panel to set your account filters.' },
          { selector: '#search-form button[type="submit"]', title: 'Search', text: 'Press Search Accounts any time to refresh results.' },
          { selector: '#search-results', title: 'Results Grid', text: 'Click any account card to open full account details.' },
          { selector: '#result-count', title: 'Result Count', text: 'This updates automatically when search results change.' },
        ];

    const validSteps = steps.filter(step => document.querySelector(step.selector));
    if (!validSteps.length) return;

    const old = document.getElementById('dashboard-tutorial-overlay');
    if (old) old.remove();

    if (!document.getElementById('dashboard-tutorial-style')) {
      const style = document.createElement('style');
      style.id = 'dashboard-tutorial-style';
      style.textContent = `
        .dashboard-tutorial-highlight { position: relative; z-index: 1203 !important; border-radius: 10px; box-shadow: 0 0 0 3px rgba(14,244,117,.9), 0 0 28px rgba(14,244,117,.45); animation: tutorialPulse 1.2s ease-in-out infinite; }
        @keyframes tutorialPulse { 0%,100% { box-shadow: 0 0 0 3px rgba(14,244,117,.9), 0 0 18px rgba(14,244,117,.35); } 50% { box-shadow: 0 0 0 5px rgba(14,244,117,1), 0 0 32px rgba(14,244,117,.65); } }
      `;
      document.head.appendChild(style);
    }

    const overlay = document.createElement('div');
    overlay.id = 'dashboard-tutorial-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:1200;background:rgba(2,8,20,.75);';

    const card = document.createElement('div');
    card.style.cssText = 'position:fixed;left:50%;bottom:20px;transform:translateX(-50%);width:min(92vw,440px);z-index:1204;background:#0f172a;border:1px solid rgba(14,244,117,.4);border-radius:14px;padding:14px;color:#eafef3;box-shadow:0 20px 45px rgba(0,0,0,.6);';

    const titleEl = document.createElement('div');
    titleEl.style.cssText = 'font-size:13px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#0EF475;';
    const textEl = document.createElement('p');
    textEl.style.cssText = 'margin:8px 0 0;font-size:13px;line-height:1.45;color:#d1fae5;';
    const controls = document.createElement('div');
    controls.style.cssText = 'margin-top:12px;display:flex;justify-content:flex-end;gap:8px;';

    const skipBtn = document.createElement('button');
    skipBtn.type = 'button';
    skipBtn.textContent = 'Skip';
    skipBtn.style.cssText = 'border:1px solid rgba(255,255,255,.25);background:transparent;color:#cbd5e1;border-radius:9px;padding:7px 12px;font-size:12px;font-weight:700;';

    const nextBtn = document.createElement('button');
    nextBtn.type = 'button';
    nextBtn.textContent = 'Next';
    nextBtn.style.cssText = 'border:none;background:#0EF475;color:#03140b;border-radius:9px;padding:7px 14px;font-size:12px;font-weight:800;';

    controls.appendChild(skipBtn);
    controls.appendChild(nextBtn);
    card.appendChild(titleEl);
    card.appendChild(textEl);
    card.appendChild(controls);
    overlay.appendChild(card);
    document.body.appendChild(overlay);

    let currentStep = 0;
    let highlighted = null;

    const clearHighlight = () => {
      if (highlighted) highlighted.classList.remove('dashboard-tutorial-highlight');
      highlighted = null;
    };

    const closeTutorial = () => {
      clearHighlight();
      overlay.remove();
      localStorage.setItem('konvy_tutorial_seen_v1', '1');
    };

    const renderStep = () => {
      clearHighlight();
      const step = validSteps[currentStep];
      if (!step) return closeTutorial();
      const target = document.querySelector(step.selector);
      if (!target) return closeTutorial();

      highlighted = target;
      highlighted.classList.add('dashboard-tutorial-highlight');
      highlighted.scrollIntoView({ behavior: 'smooth', block: 'center' });
      titleEl.textContent = `${step.title} (${currentStep + 1}/${validSteps.length})`;
      textEl.textContent = step.text;
      nextBtn.textContent = currentStep === validSteps.length - 1 ? 'Finish' : 'Next';
    };

    nextBtn.addEventListener('click', () => {
      currentStep += 1;
      if (currentStep >= validSteps.length) {
        closeTutorial();
        return;
      }
      renderStep();
    });
    skipBtn.addEventListener('click', closeTutorial);

    renderStep();
  }

  function promptDashboardTutorial() {
    if (!searchForm || !searchResults) return;
    if (localStorage.getItem('konvy_tutorial_seen_v1') === '1') return;
    const existing = document.getElementById('dashboard-tutorial-prompt');
    if (existing) return;

    const prompt = document.createElement('div');
    prompt.id = 'dashboard-tutorial-prompt';
    prompt.style.cssText = 'position:fixed;inset:0;z-index:1190;background:rgba(0,0,0,.72);display:flex;align-items:center;justify-content:center;padding:16px;';
    prompt.innerHTML = `
      <div style="width:min(94vw,420px);background:#0b1222;border:1px solid rgba(14,244,117,.35);border-radius:14px;padding:16px;color:#e5f8ee;">
        <div style="font-size:14px;font-weight:800;color:#0EF475;letter-spacing:.08em;text-transform:uppercase;">Need a quick tutorial?</div>
        <p style="margin-top:9px;font-size:13px;line-height:1.45;color:#d1fae5;">We can guide you through filters and results with an animated step-by-step tour.</p>
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px;">
          <button type="button" data-action="no" style="border:1px solid rgba(255,255,255,.24);background:transparent;color:#cbd5e1;border-radius:9px;padding:7px 12px;font-size:12px;font-weight:700;">No thanks</button>
          <button type="button" data-action="yes" style="border:none;background:#0EF475;color:#03140b;border-radius:9px;padding:7px 12px;font-size:12px;font-weight:800;">Start tutorial</button>
        </div>
      </div>
    `;

    const closePrompt = () => prompt.remove();
    prompt.addEventListener('click', (event) => {
      const button = event.target.closest('button[data-action]');
      if (!button) return;
      const action = button.getAttribute('data-action');
      closePrompt();
      if (action === 'yes') startDashboardTutorial();
      else localStorage.setItem('konvy_tutorial_seen_v1', '1');
    });
    document.body.appendChild(prompt);
  }

  // =============== COSMETIC TYPE DIALOG ===============
  window.showCosmeticTypeDialog = (itemId) => {
    const types = [
      { id: 'skins', label: '🎭 Skins', emoji: '🎭' },
      { id: 'pickaxes', label: '⛏️ Pickaxes', emoji: '⛏️' },
      { id: 'emotes', label: '💃 Emotes', emoji: '💃' },
      { id: 'gliders', label: '🪂 Gliders', emoji: '🪂' }
    ];

    const dialogHtml = `
      <div class="cosmetic-type-dialog" id="cosmetic-type-dialog">
        <div class="cosmetic-type-content">
          <h3>Choose what to preview</h3>
          <p>Select the type of cosmetics you want to see</p>
          <div class="cosmetic-type-options">
            ${types.map(type => `
              <button class="cosmetic-type-btn" data-type="${type.id}" data-item-id="${itemId}">
                <span class="type-emoji">${type.emoji}</span>
                <span class="type-label">${type.label}</span>
              </button>
            `).join('')}
          </div>
          <button class="cosmetic-type-close" onclick="closeCosmeticTypeDialog()">Cancel</button>
        </div>
      </div>
    `;

    // Remove existing dialog if any
    const existing = document.getElementById('cosmetic-type-dialog');
    if (existing) existing.remove();

    // Add new dialog
    document.body.insertAdjacentHTML('beforeend', dialogHtml);
    document.body.style.overflow = "hidden";

    // Add click handlers
    document.querySelectorAll('.cosmetic-type-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const type = btn.dataset.type;
        const itemId = btn.dataset.itemId;
        closeCosmeticTypeDialog();
        openSkinsModal(type);
        loadCosmeticImages(itemId, type);
      });
    });
  };

  window.closeCosmeticTypeDialog = () => {
    const dialog = document.getElementById('cosmetic-type-dialog');
    if (dialog) {
      dialog.remove();
      document.body.style.overflow = "";
    }
  };

  // =============== SKINS MODAL (OPTIMIZED) ===============
  window.openSkinsModal = (cosmeticType = 'skins') => {
    document.body.style.overflow = "hidden";
    const modal = qs("skins-modal");
    modal.classList.add("open");
    
    // Update modal title based on cosmetic type
    const titles = {
      'skins': 'Account Skins',
      'pickaxes': 'Account Pickaxes',
      'emotes': 'Account Emotes',
      'gliders': 'Account Gliders'
    };
    const titleEl = modal.querySelector('.skins-modal-header h2');
    if (titleEl) {
      titleEl.textContent = titles[cosmeticType] || 'Account Cosmetics';
    }
  };

  window.closeSkinsModal = () => {
    document.body.style.overflow = "";
    qs("skins-modal").classList.remove("open");
    qs("skins-grid").innerHTML = "";
  };

  window.loadCosmeticImages = async (itemId, cosmeticType = 'skins') => {
    const grid = qs("skins-grid");
    const loader = qs("skins-loader");
    const loadedEl = qs("skins-loaded");
    const totalEl = qs("skins-total");

    grid.innerHTML = "";
    loader.style.display = "flex";
    loadedEl.textContent = "0";
    totalEl.textContent = "0";

    try {
      // Use the new cosmetics endpoint
      const cosmeticsRes = await fetch(`/api/account/${itemId}/cosmetics/${cosmeticType}`);
      const cosmeticsData = await cosmeticsRes.json();
      const names = Array.isArray(cosmeticsData.cosmetics) ? cosmeticsData.cosmetics : [];

      if (!names.length) {
        loader.querySelector(".loader-text").textContent = `No ${cosmeticType} available for this account`;
        return;
      }

      totalEl.textContent = names.length;

      // Map cosmetic type to API type
      const typeMapping = {
        'skins': 'outfit',
        'pickaxes': 'pickaxe',
        'emotes': 'emote',
        'gliders': 'glider'
      };
      const apiType = typeMapping[cosmeticType] || 'outfit';

      // OPTIMIZED: Load icons in batches of 10
      const BATCH_SIZE = 10;
      let loaded = 0;
      
      for (let i = 0; i < names.length; i += BATCH_SIZE) {
        const batch = names.slice(i, i + BATCH_SIZE);
        
        const iconsRes = await fetch("/api/skins/icons", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ 
            names: batch,
            type: apiType
          }),
        });

        const iconsData = await iconsRes.json();
        const icons = Array.isArray(iconsData.icons) ? iconsData.icons : [];

        // Create images for this batch
        await Promise.all(icons.map(cosmetic => {
          return new Promise((resolve) => {
            const img = new Image();
            img.src = cosmetic.icon || "/static/placeholder.png";
            
            const onComplete = () => {
              loaded++;
              loadedEl.textContent = loaded;
              if (loaded === names.length) {
                loader.style.display = "none";
              }
              resolve();
            };
            
            img.onload = onComplete;
            img.onerror = onComplete;
            
            grid.appendChild(img);
          });
        }));
      }

    } catch (err) {
      loader.querySelector(".loader-text").textContent = "Failed to load preview";
      console.error('Preview error:', err);
    }
  };

  // =============== BALANCE ===============
  qs("check-balance-btn")?.addEventListener("click", async () => {
    qs("balance-result").textContent = "Loading…";
    try {
      const res = await postJSON("/api/balance");
      qs("balance-result").textContent = `Balance: $${res.balance.toFixed(2)}`;
    } catch (e) {
      qs("balance-result").textContent = e.message;
    }
  });

  // =============== TOP UP ===============
  qs("topup-btn")?.addEventListener("click", async () => {
    qs("topup-result").textContent = "Generating link…";
    try {
      const res = await postJSON("/api/topup", {
        amount: Number(qs("topup-amount").value || 0),
      });
      qs("topup-result").innerHTML =
        `<a href="${res.checkout_url}" target="_blank">Open Checkout</a>`;
    } catch (e) {
      qs("topup-result").textContent = e.message;
    }
  });

  // =============== MY ACCOUNTS ===============
  let myAccounts = [];

  /**
   * Formats a Unix timestamp (seconds) into a short local date string.
   * @param {number|string} timestamp
   * @returns {string}
   */
  function formatPurchaseDate(timestamp) {
    const tsNum = Number(timestamp || 0);
    if (!Number.isFinite(tsNum) || tsNum <= 0) return "Unknown date";
    const date = new Date(tsNum * 1000);
    if (Number.isNaN(date.getTime())) return "Unknown date";
    return date.toLocaleDateString(undefined, { month: "2-digit", day: "2-digit", year: "numeric" });
  }

  function formatPrice(rawPrice) {
    const parsed = Number(rawPrice);
    if (!Number.isFinite(parsed)) return "N/A";
    return `€${parsed.toFixed(2)}`;
  }

  function splitRawCredentials(raw) {
    if (!raw) return { login: "", password: "" };
    const text = String(raw);
    const sepIndex = text.indexOf(":");
    if (sepIndex === -1) return { login: text, password: "" };
    return {
      login: text.slice(0, sepIndex),
      password: text.slice(sepIndex + 1),
    };
  }

  async function copyToClipboard(text) {
    const value = String(text || "");
    if (!value) return false;
    if (!navigator.clipboard || !navigator.clipboard.writeText) return false;
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch (_) {
      return false;
    }
  }

  function buildCredRow(label, value) {
    const safeLabel = escapeHtml(label);
    const rawValue = String(value || "N/A");
    const safeValue = escapeHtml(rawValue);
    // URL-encoding keeps the raw credential intact in a data-* attribute without breaking HTML parsing.
    const encodedCopyValue = encodeURIComponent(rawValue);
    return `
      <div class="my-account-row">
        <span class="my-account-row-label">${safeLabel}</span>
        <span class="my-account-row-value">${safeValue}</span>
        <button type="button" class="my-account-copy-btn" data-copy="${encodedCopyValue}" aria-label="Copy credential value">
          <i class="ri-file-copy-line"></i>
        </button>
      </div>
    `;
  }

  function bindMyAccountActions() {
    const root = qs("my-accounts-view");
    if (!root) return;

    root.querySelectorAll(".my-account-copy-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        let copyValue = "";
        try {
          copyValue = decodeURIComponent(btn.dataset.copy || "");
        } catch (_) {
          copyValue = String(btn.dataset.copy || "");
        }
        const copied = await copyToClipboard(copyValue);
        if (copied) {
          btn.classList.add("copied");
          setTimeout(() => btn.classList.remove("copied"), 800);
        }
      });
    });

    root.querySelectorAll("[data-acc-toggle]").forEach((toggleBtn) => {
      toggleBtn.addEventListener("click", () => {
        const index = String(toggleBtn.dataset.accToggle || "");
        const content = root.querySelector(`[data-acc-content="${index}"]`);
        if (!content) return;
        const willOpen = !content.classList.contains("is-open");
        content.classList.toggle("is-open", willOpen);
        toggleBtn.setAttribute("aria-expanded", willOpen ? "true" : "false");
      });
    });

    root.querySelectorAll(".my-account-name-save").forEach((saveBtn) => {
      const purchaseIndex = Number(saveBtn.dataset.purchaseIndex || "-1");
      const input = root.querySelector(`#my-account-name-input-${purchaseIndex}`);
      const status = root.querySelector(`#my-account-name-status-${purchaseIndex}`);
      if (!input || !status || !Number.isInteger(purchaseIndex) || purchaseIndex < 0) return;

      const runSave = async () => {
        const nextName = String(input.value || "").trim();
        if (!nextName) {
          status.textContent = "Enter a name first.";
          status.classList.add("error");
          return;
        }
        status.textContent = "Saving...";
        status.classList.remove("error");
        saveBtn.disabled = true;
        try {
          await postJSON("/api/fortnite/name-account", { purchase_index: purchaseIndex, name: nextName });
          if (myAccounts[purchaseIndex]) myAccounts[purchaseIndex].name = nextName;
          status.textContent = "Saved.";
          status.classList.remove("error");
        } catch (e) {
          status.textContent = e?.message || "Failed to save.";
          status.classList.add("error");
        } finally {
          saveBtn.disabled = false;
        }
      };

      saveBtn.addEventListener("click", runSave);
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          runSave();
        }
      });
    });
  }

  function buildCredCombo(login, password) {
    if (!login || !password) return "N/A";
    if (login === "N/A" || password === "N/A") return "N/A";
    return `${login}:${password}`;
  }

  async function loadMyAccounts() {
    if (!window.KONVY_LOGGED_IN) return;
    const view = qs("my-accounts-view");
    if (!view) return;
    
    try {
      const res = await postJSON("/api/fortnite/my-accounts");
      myAccounts = res.accounts || [];
      renderAccount();
    } catch {
      view.textContent = "Failed to load accounts.";
    }
  }

  function getAccountTitle(item, skinsCount, fallbackIndex) {
    const rawTitle = String(item?.title || item?.title_en || "").trim();
    if (rawTitle) return rawTitle;
    if (Number.isFinite(skinsCount) && skinsCount > 0) return `${skinsCount} Skins`;
    return `Account ${fallbackIndex + 1}`;
  }

  function getAccountNumber(acc) {
    const item = acc?.purchase_result?.item || {};
    // Canonical marketplace field is item_id; fallbacks keep backward compatibility.
    const rawId = item.item_id ?? item.fortnite_item_id ?? item.id;
    const parsedId = Number(rawId);
    return Number.isInteger(parsedId) && parsedId > 0 ? parsedId : 0;
  }

  function buildAccountCard(acc, cardIndex) {
    const item = acc.purchase_result?.item || {};
    const loginData = item.loginData || {};
    const emailData = item.emailLoginData || {};
    const parsedFortnite = splitRawCredentials(loginData.raw);
    const parsedEmail = splitRawCredentials(emailData.raw);
    const fortniteLogin = loginData.login || parsedFortnite.login || "N/A";
    const fortnitePassword = loginData.password || parsedFortnite.password || "N/A";
    const fortniteCombo = buildCredCombo(fortniteLogin, fortnitePassword);
    const emailLogin = emailData.login || parsedEmail.login || "N/A";
    const emailPassword = emailData.password || parsedEmail.password || "N/A";
    const emailOldPassword = emailData.oldPassword || "N/A";
    const emailSecretAnswer = emailData.newSecretAnswer || emailData.secretAnswer || "N/A";
    const emailCombo = buildCredCombo(emailLogin, emailPassword);
    const skinsCount = Number(item.fortnite_skin_count || item.fortniteSkinCount || (item.fortniteSkins || []).length || 0);
    const delivered = String(acc.purchase_result?.status || "").toLowerCase() === "ok";
    const purchaseDate = formatPurchaseDate(acc.timestamp);
    const displayPrice = formatPrice(item.priceWithSellerFee ?? item.price);
    const accountName = String(acc.name || "").trim() || `Account ${cardIndex + 1}`;
    const accountNameInputId = `my-account-name-input-${cardIndex}`;
    const accountNameStatusId = `my-account-name-status-${cardIndex}`;
    const accountNumber = getAccountNumber(acc);
    const accountTitle = getAccountTitle(item, skinsCount, cardIndex);
    const isOpen = cardIndex === 0;

    return `
      <article class="my-account-panel">
        <button type="button" class="my-account-summary" data-acc-toggle="${cardIndex}" aria-expanded="${isOpen ? "true" : "false"}">
          <div class="my-account-top">
            <div>
              <div class="my-account-title">${escapeHtml(accountTitle)}</div>
              <div class="my-account-date">${escapeHtml(purchaseDate)}</div>
              ${accountNumber > 0 ? `<div class="my-account-id-chip">#${escapeHtml(String(accountNumber))}</div>` : ""}
              <div class="my-account-state ${delivered ? "is-delivered" : ""}">
                <i class="${delivered ? "ri-check-line" : "ri-time-line"}"></i>
                <span>${delivered ? "Delivered" : "Pending"}</span>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <div class="my-account-price">${escapeHtml(displayPrice)}</div>
              <i class="ri-arrow-down-s-line my-account-summary-chevron" aria-hidden="true"></i>
            </div>
          </div>
        </button>

        <div class="my-account-collapse ${isOpen ? "is-open" : ""}" data-acc-content="${cardIndex}">
          <div class="my-account-name-wrap">
            <label class="my-account-name-label" for="${accountNameInputId}">Account Name</label>
            <div class="my-account-name-controls">
              <input id="${accountNameInputId}" type="text" class="my-account-name-input" maxlength="50" value="${escapeHtml(accountName)}" placeholder="Enter account name">
              <button type="button" class="my-account-name-save" data-purchase-index="${cardIndex}">Save</button>
            </div>
            <div class="my-account-name-status" id="${accountNameStatusId}" aria-live="polite"></div>
          </div>

          <section class="my-account-section">
            <h3>FORTNITE LOGIN</h3>
            ${buildCredRow("Login", fortniteLogin)}
            ${buildCredRow("Password", fortnitePassword)}
            ${buildCredRow("Login & Password", fortniteCombo)}
          </section>

          <section class="my-account-section">
            <h3>EMAIL ACCESS</h3>
            ${buildCredRow("Login", emailLogin)}
            ${buildCredRow("Password", emailPassword)}
            ${buildCredRow("Old Password", emailOldPassword)}
            ${buildCredRow("Secret Answer", emailSecretAnswer)}
            ${buildCredRow("Login & Password", emailCombo)}
          </section>
        </div>
      </article>
    `;
  }

  function renderAccount() {
    const view = qs("my-accounts-view");
    if (!view) return;

    if (!myAccounts.length) {
      view.textContent = "No purchased accounts.";
      return;
    }

    view.innerHTML = myAccounts.map((acc, index) => buildAccountCard(acc, index)).join("");
    bindMyAccountActions();
  }

  if (window.KONVY_LOGGED_IN) {
    loadMyAccounts();
  }

  if (searchForm && searchResults) {
    executeSearch({ showEmptyAlert: false });
    window.setTimeout(promptDashboardTutorial, TUTORIAL_PROMPT_DELAY_MS);
  }
});
