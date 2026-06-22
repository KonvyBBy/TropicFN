document.addEventListener("DOMContentLoaded", () => {

  // =============== UTILITIES ===============
  async function postJSON(url, data = {}) {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    let json;
    try { json = await res.json(); } catch(e) { throw new Error(`Server error (${res.status}). Please try again later.`); }
    if (!res.ok) throw new Error(json.message || json.error || "Request failed");
    return json;
  }

  const qs = id => document.getElementById(id);
  const MIN_COSMETIC_SEARCH_LENGTH = 2;
  const MAX_COSMETIC_RESULTS = 10;
  const DEFAULT_COSMETIC_TYPES = ['outfit', 'pickaxe', 'emote', 'glider'];
  const AUTO_SEARCH_DEBOUNCE_MS = 350;
  const TUTORIAL_PROMPT_DELAY_MS = 450;
  const CARDS_PER_PAGE = 12;

  // =============== AUTH ===============
  function openAuthPage(mode) { window.location.href = mode === "register" ? "/register" : "/login"; }
  qs("sign-in-trigger")?.addEventListener("click", () => openAuthPage("login"));

  // =============== PROCESSING OVERLAY ===============
  function showProcessingOverlay() {
    let overlay = qs('processing-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'processing-overlay';
      overlay.className = 'processing-overlay';
      overlay.innerHTML = `<div class="processing-content"><div class="processing-spinner"></div><div class="processing-title">Processing Purchase...</div><div class="processing-message">Please wait while we secure your account.<br>This usually takes 5-15 seconds.</div><div class="processing-warning">⚠️ DO NOT refresh or close this page!<br>Doing so may cause your purchase to fail.</div></div>`;
      document.body.appendChild(overlay);
    }
    overlay.classList.add('active');
  }
  function hideProcessingOverlay() { qs('processing-overlay')?.classList.remove('active'); }

  // =============== NAMING MODAL ===============
  function showNamingModal(purchaseIndex, onDone) {
    const existing = document.getElementById('naming-modal-overlay');
    if (existing) existing.remove();
    const overlay = document.createElement('div');
    overlay.id = 'naming-modal-overlay';
    overlay.className = 'naming-modal-overlay';
    overlay.innerHTML = `<div class="naming-modal"><h3>✅ Purchase Successful!</h3><p>Give this account a name so you can identify it easily.</p><div class="form-group"><label class="form-label">Account Name</label><input id="naming-modal-input" type="text" class="form-input" placeholder="e.g. My Main Account" maxlength="50" /></div><div class="naming-modal-actions"><button id="naming-modal-submit" class="btn-naming-submit">Save Name</button><button id="naming-modal-skip" class="btn-naming-skip">Skip</button></div><div id="naming-modal-error" style="display:none;color:#ff8080;font-size:0.85rem;margin-top:0.5rem;"></div></div>`;
    document.body.appendChild(overlay);
    const input = document.getElementById('naming-modal-input');
    const errEl = document.getElementById('naming-modal-error');
    input.focus();
    async function submitName() {
      const name = input.value.trim();
      if (!name) { errEl.textContent = 'Please enter a name.'; errEl.style.display = 'block'; return; }
      try { await postJSON('/api/fortnite/name-account', { purchase_index: purchaseIndex, name }); overlay.remove(); onDone(); } catch(e) { errEl.textContent = e.message || 'Failed to save name.'; errEl.style.display = 'block'; }
    }
    document.getElementById('naming-modal-submit').onclick = submitName;
    document.getElementById('naming-modal-skip').onclick = () => { overlay.remove(); onDone(); };
    input.addEventListener('keydown', e => { if (e.key === 'Enter') submitName(); });
  }

  // =============== COSMETIC SEARCH ===============
  const cosmeticsCache = new Map();
  const cosmeticsInFlight = new Map();

  async function searchCosmetics(query, allowedTypes) {
    const q = String(query || "").trim().toLowerCase();
    if (q.length < MIN_COSMETIC_SEARCH_LENGTH) return [];
    const types = (allowedTypes || DEFAULT_COSMETIC_TYPES).map(v => String(v).toLowerCase()).sort();
    const key = `${q}::${types.join(',')}`;
    if (cosmeticsCache.has(key)) return cosmeticsCache.get(key);
    if (cosmeticsInFlight.has(key)) return cosmeticsInFlight.get(key);
    const url = `https://fortnite-api.com/v2/cosmetics/br/search/all?name=${encodeURIComponent(q)}&matchMethod=contains&language=en&searchLanguage=en`;
    const req = fetch(url).then(async res => {
      if (!res.ok) throw new Error(`Cosmetic search failed: ${res.status}`);
      const data = await res.json();
      const typeSet = new Set(types);
      const filtered = (Array.isArray(data?.data) ? data.data : []).filter(item => { const t = String(item?.type?.value || '').toLowerCase(); return item.name?.toLowerCase().includes(q) && typeSet.has(t); }).slice(0, MAX_COSMETIC_RESULTS);
      cosmeticsCache.set(key, filtered);
      return filtered;
    }).catch(() => []).finally(() => cosmeticsInFlight.delete(key));
    cosmeticsInFlight.set(key, req);
    return req;
  }

  function updateSelection(items, index) {
    items.forEach((item, idx) => { item.classList.toggle('selected', idx === index); if (idx === index) item.scrollIntoView({ block: 'nearest' }); });
  }

  async function filterCosmetics(query, dropdown, allowedTypes) {
    if (!query || query.length < MIN_COSMETIC_SEARCH_LENGTH) { dropdown.classList.remove('show'); return; }
    const q = query.toLowerCase();
    let filtered = await searchCosmetics(q, allowedTypes);
    const isOutfitSearch = allowedTypes && allowedTypes.some(t => t === 'outfit');
    if (isOutfitSearch) {
      const ogSkins = [
        { id: '030_athena_commando_m_halloween_og', name: 'OG Skull Trooper',     keywords: ['og','skull'] },
        { id: '017_athena_commando_m_og',           name: 'OG Aerial Assault Trooper', keywords: ['og','aerial','assault'] },
        { id: '028_athena_commando_f_og',           name: 'OG Renegade Raider',   keywords: ['og','renegade','raider'] },
        { id: '029_athena_commando_f_halloween_og', name: 'OG Ghoul Trooper',     keywords: ['og','ghoul'] },
      ];
      for (const og of ogSkins) {
        if (og.keywords.some(kw => q.includes(kw)) && !filtered.some(f => f.id === og.id)) {
          filtered.unshift({ id: og.id, name: og.name, type: { value: 'outfit', displayValue: 'Outfit' }, rarity: { displayValue: 'legendary' }, images: { icon: '' } });
        }
      }
    }
    if (filtered.length === 0) { dropdown.innerHTML = '<div class="autocomplete-no-results">No items found</div>'; dropdown.classList.add('show'); return; }
    dropdown.innerHTML = filtered.map((item, idx) => {
      const type = item.type?.displayValue || item.type?.value || 'Item';
      const rarity = item.rarity?.displayValue?.toLowerCase() || 'common';
      const icon = item.images?.icon || item.images?.smallIcon || '';
      return `<div class="autocomplete-item" data-index="${idx}" data-name="${item.name}" data-id="${item.id || ''}">${icon ? `<img src="${icon}" alt="${item.name}" loading="lazy">` : ''}<div class="autocomplete-item-info"><div class="autocomplete-item-name">${item.name}</div><div class="autocomplete-item-type">${type}</div></div><div class="autocomplete-item-rarity rarity-${rarity}">${rarity}</div></div>`;
    }).join('');
    dropdown.classList.add('show');
  }

  function setupAutocomplete(input, dropdown, allowedTypes) {
    let selectedIndex = -1;
    let debounceTimer = null;
    const fieldName = String(input.getAttribute('name') || '');
    const chipsContainer = input.parentElement?.querySelector(`.sel-cos[data-field="${fieldName}"]`);

    function getSelectedIds() { if (!chipsContainer) return []; return Array.from(chipsContainer.querySelectorAll('.sel-cos-chip')).map(chip => String(chip.getAttribute('data-id') || '')).filter(Boolean); }
    function emitChange() { input.dispatchEvent(new Event('change', { bubbles: true })); }

    function addSelected(itemId, itemName) {
      const id = String(itemId || '').trim();
      const name = String(itemName || '').trim();
      if (!chipsContainer || !fieldName || !id || !name) return;
      if (getSelectedIds().includes(id)) { input.value = ''; return; }
      const chip = document.createElement('span');
      chip.className = 'sel-cos-chip';
      chip.setAttribute('data-id', id);
      chip.innerHTML = `<span class="max-w-[8rem] truncate">${name}</span><button type="button" class="rm" aria-label="Remove ${name}">×</button>`;
      const hidden = document.createElement('input');
      hidden.type = 'hidden'; hidden.name = fieldName; hidden.value = id;
      chip.appendChild(hidden);
      chip.querySelector('.rm').addEventListener('click', () => { chip.remove(); emitChange(); });
      chipsContainer.appendChild(chip);
      input.value = '';
      input.removeAttribute('data-cosmetic-id');
      emitChange();
    }

    input.addEventListener('input', e => {
      input.removeAttribute('data-cosmetic-id');
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(async () => { await filterCosmetics(e.target.value, dropdown, allowedTypes); }, 120);
    });
    input.addEventListener('keydown', e => {
      const items = dropdown.querySelectorAll('.autocomplete-item');
      if (e.key === 'ArrowDown') { e.preventDefault(); selectedIndex = Math.min(selectedIndex + 1, items.length - 1); updateSelection(items, selectedIndex); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); selectedIndex = Math.max(selectedIndex - 1, -1); updateSelection(items, selectedIndex); }
      else if (e.key === 'Enter' && selectedIndex >= 0) { e.preventDefault(); items[selectedIndex]?.click(); }
      else if (e.key === 'Escape') { dropdown.classList.remove('show'); }
    });
    dropdown.addEventListener('click', e => {
      const item = e.target.closest('.autocomplete-item');
      if (item) { addSelected(item.dataset.id, item.dataset.name); dropdown.classList.remove('show'); }
    });
  }

  document.querySelectorAll('.cos-search').forEach(input => {
    const dropdown = input.parentElement?.querySelector('.autocomplete-dropdown');
    if (!dropdown) return;
    const type = String(input.dataset.type || '').toLowerCase();
    setupAutocomplete(input, dropdown, type ? [type] : DEFAULT_COSMETIC_TYPES);
  });

  document.addEventListener('click', e => {
    if (!e.target.closest('.autocomplete-wrap')) document.querySelectorAll('.autocomplete-dropdown').forEach(d => d.classList.remove('show'));
  });

  // =============== SEARCH STATE ===============
  const searchForm = document.getElementById('search-form');
  const searchResults = document.getElementById('search-results');
  let currentSort = 'cheap';
  let lastSearchAccounts = [];
  let searchDebounceTimer = null;
  let searchRequestId = 0;
  const initialHtml = searchResults ? searchResults.innerHTML : '';
  const allowedFormKeys = new Set([
    'pmin', 'pmax',
    'skin[]', 'pickaxe[]', 'dance[]', 'glider[]',
    'smin', 'smax', 'pickaxe_min', 'pickaxe_max', 'dmin', 'dmax', 'gmin', 'gmax',
    'vbmin', 'vbmax', 'lmin', 'lmax', 'paid_items_min', 'paid_items_max',
    'refund_credits_min', 'refund_credits_max', 'daybreak', 'daybreak_max',
    'platform'
  ]);
  const ENUM_FILTER_KEYS = new Set(['platform']);

  // Pagination state
  let currentPage = 1;
  let totalPages = 1;

  function normalizeValue(key, value) {
    if (value == null) return undefined;
    const trimmed = String(value).trim();
    if (!trimmed) return undefined;
    if (ENUM_FILTER_KEYS.has(key)) {
      return trimmed.toLowerCase();
    }
    return trimmed;
  }

  function buildPayload(formData, form) {
    const payload = {};
    formData.forEach((value, key) => {
      if (!allowedFormKeys.has(key)) return;
      const norm = normalizeValue(key, value);
      if (norm == null) return;
      if (payload[key] !== undefined) { if (!Array.isArray(payload[key])) payload[key] = [payload[key]]; payload[key].push(norm); }
      else payload[key] = norm;
    });
    // Resolve selected cosmetics
    const prefixes = { 'skin[]': 'cid_', 'dance[]': 'eid_', 'glider[]': 'glider_id_', 'pickaxe[]': '' };
    for (const [field, prefix] of Object.entries(prefixes)) {
      const inputs = form ? Array.from(form.querySelectorAll(`input.selected-cosmetic-value[name="${field}"]`)) : [];
      const ids = inputs.map(h => { const id = (h.value || '').toLowerCase(); return prefix && id.startsWith(prefix) ? id.slice(prefix.length) : id; }).filter(Boolean);
      if (ids.length === 1) payload[field] = ids[0];
      else if (ids.length > 1) payload[field] = ids;
      else delete payload[field];
      // Also check sel-cos-chip hidden inputs
      const chipInputs = form ? Array.from(form.querySelectorAll(`.sel-cos[data-field="${field}"] input[type="hidden"]`)) : [];
      const chipIds = chipInputs.map(h => { const id = (h.value || '').toLowerCase(); return prefix && id.startsWith(prefix) ? id.slice(prefix.length) : id; }).filter(Boolean);
      if (chipIds.length === 1) payload[field] = chipIds[0];
      else if (chipIds.length > 1) payload[field] = chipIds;
    }
    const pmax = Number(payload.pmax || 0);
    if (pmax > 0) payload.budget = pmax;
    return payload;
  }

  function escapeHtml(value) { return String(value ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }

  // =============== SORT ===============
  function getSortedAccounts(accounts) {
    const list = [...accounts];
    list.sort((a, b) => (a.user_price || 0) - (b.user_price || 0));
    return list;
  }



  // =============== RENDER ===============
  function renderInitialState() { if (searchResults) searchResults.innerHTML = initialHtml; }

  function renderEmptyState() {
    searchResults.innerHTML = `
      <div class="mkt-empty">
        <div class="mkt-empty-icon" style="font-size:56px;opacity:0.3;filter:grayscale(0.5);">🔍</div>
        <div style="font-family:'Space Grotesk',sans-serif;font-size:20px;font-weight:700;color:#f1f5f9;margin-bottom:6px;">No accounts match your filters</div>
        <div style="font-size:14px;color:#475569;max-width:320px;margin:0 auto;line-height:1.5;">Try adjusting your filters or search for different cosmetics to find more accounts.</div>
        <button onclick="resetFilters()" style="margin-top:16px;padding:10px 24px;border-radius:12px;background:linear-gradient(135deg,#00E5FF,#7C5CFF);color:#fff;font-weight:700;font-size:13px;border:none;cursor:pointer;">Adjust Filters</button>
      </div>`;
  }

  function updateFilterCount() {
    const form = document.getElementById('search-form');
    if (!form) return;
    const fd = new FormData(form);
    let count = 0;
    for (const [k, v] of fd.entries()) {
      if (v && v.toString().trim()) count++;
    }
    const el = document.getElementById('mobile-filter-count');
    if (el) el.textContent = '(' + count + ')';
  }

  function renderSkeletonCards(count = 3) {
    if (!searchResults) return;
    let html = '';
    for (let i = 0; i < count; i++) {
      html += `
        <div class="mkt-skeleton" style="animation:mktCardIn .5s cubic-bezier(.15,.75,.4,1) forwards;animation-delay:${i * 80}ms;opacity:0;">
          <div class="sk-banner"></div>
          <div class="sk-body">
            <div class="sk-stats">${'<div class="sk-stat"><div class="sk-line w50 h14" style="margin-bottom:4px"></div><div class="sk-line w40 h8"></div></div>'.repeat(6)}</div>
            <div class="sk-bottom">
              <div class="sk-left">
                <div class="sk-badges-row">${'<div class="sk-badge-pill"></div>'.repeat(4)}</div>
                <div class="sk-line w60" style="height:10px"></div>
              </div>
              <div class="sk-cta"></div>
            </div>
          </div>
        </div>`;
    }
    searchResults.innerHTML = html;
  }

  function getActivityClass(daysAgo) {
    if (daysAgo === null || daysAgo === undefined) return 'unknown';
    const d = Number(daysAgo);
    if (!Number.isFinite(d)) return 'unknown';
    if (d >= 21) return 'green';
    if (d >= 4) return 'yellow';
    return 'red';
  }

  function getActivityLabel(daysAgo) {
    if (daysAgo === null || daysAgo === undefined) return 'Unknown';
    const d = Number(daysAgo);
    if (!Number.isFinite(d)) return 'Unknown';
    if (d === 0) return 'Today';
    if (d === 1) return 'Yesterday';
    return `${d}d ago`;
  }
  function getActivityBadgeClass(daysAgo) {
    if (daysAgo === null || daysAgo === undefined) return 'mkt-badge-gray';
    const d = Number(daysAgo);
    if (!Number.isFinite(d)) return 'mkt-badge-gray';
    if (d >= 21) return 'mkt-badge-green';
    if (d >= 4) return 'mkt-badge-orange';
    return 'mkt-badge-red';
  }

  // =============== PAGINATION ===============
  function renderPagination(totalItems) {
    const pag = document.getElementById('mkt-pagination');
    const pageNums = document.getElementById('page-numbers');
    const prev = document.getElementById('page-prev');
    const next = document.getElementById('page-next');
    if (!pag || !pageNums) return;

    totalPages = Math.max(1, Math.ceil(totalItems / CARDS_PER_PAGE));
    if (totalItems <= CARDS_PER_PAGE) { pag.style.display = 'none'; return; }
    pag.style.display = 'flex';

    function goToPage(page) {
      currentPage = Math.max(1, Math.min(page, totalPages));
      updatePaginationUI();
      renderAccounts(getSortedAccounts(lastSearchAccounts));
      searchResults?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function updatePaginationUI() {
      pageNums.innerHTML = '';
      prev.disabled = currentPage <= 1;
      next.disabled = currentPage >= totalPages;

      const range = 2;
      const start = Math.max(1, currentPage - range);
      const end = Math.min(totalPages, currentPage + range);

      if (start > 1) {
        const btn = document.createElement('button');
        btn.className = 'mkt-page-btn'; btn.textContent = '1';
        btn.addEventListener('click', () => goToPage(1));
        pageNums.appendChild(btn);
        if (start > 2) { const dots = document.createElement('span'); dots.className = 'text-zinc-600 text-xs px-1'; dots.textContent = '...'; pageNums.appendChild(dots); }
      }
      for (let i = start; i <= end; i++) {
        const btn = document.createElement('button');
        btn.className = 'mkt-page-btn' + (i === currentPage ? ' active' : '');
        btn.textContent = i;
        btn.addEventListener('click', () => goToPage(i));
        pageNums.appendChild(btn);
      }
      if (end < totalPages) {
        if (end < totalPages - 1) { const dots = document.createElement('span'); dots.className = 'text-zinc-600 text-xs px-1'; dots.textContent = '...'; pageNums.appendChild(dots); }
        const btn = document.createElement('button');
        btn.className = 'mkt-page-btn'; btn.textContent = totalPages;
        btn.addEventListener('click', () => goToPage(totalPages));
        pageNums.appendChild(btn);
      }
    }

    prev.onclick = () => goToPage(currentPage - 1);
    next.onclick = () => goToPage(currentPage + 1);

    updatePaginationUI();
  }

  // =============== RENDER ACCOUNTS (with pagination) ===============
  function renderAccounts(accounts) {
    if (!searchResults) return;
    searchResults.innerHTML = '';

    if (!accounts || accounts.length === 0) {
      renderEmptyState();
      document.getElementById('mkt-pagination').style.display = 'none';
      return;
    }

    // Collect preview cosmetic names for batch icon fetch
    const allNames = [];
    accounts.forEach(acc => {
      (Array.isArray(acc.preview_cosmetics) ? acc.preview_cosmetics.slice(0, 6) : []).forEach(n => { if (!allNames.includes(n)) allNames.push(n); });
    });

    let iconCache = new Map();
    let rarityCache = new Map();
    (async () => {
      if (!allNames.length) return;
      try {
        const res = await fetch("/api/skins/icons", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ names: allNames }) });
        if (res.ok) {
          const data = await res.json();
          (Array.isArray(data.icons) ? data.icons : []).forEach(ic => {
            if (ic.name && ic.icon) iconCache.set(ic.name, ic.icon);
            if (ic.name && ic.rarity) rarityCache.set(ic.name, ic.rarity);
          });
          document.querySelectorAll('.mkt-si-img[data-name]').forEach(img => {
            const url = iconCache.get(img.dataset.name || '');
            if (url) { img.src = url; img.classList.remove('placeholder'); img.parentElement.classList.remove('placeholder'); }
          });
          document.querySelectorAll('.mkt-sc-bg[data-name]').forEach(el => {
            const url = iconCache.get(el.dataset.name || '');
            if (url) { el.style.backgroundImage = `url(${url})`; el.classList.add('loaded'); }
          });
        }
      } catch(_) {}
    })();

    const RARITY_SCORES = { legendary: 7, epic: 6, rare: 5, uncommon: 4, common: 3, marvel: 8, dc: 8, icon: 8, gaming_legends: 7, frozen: 5, lava: 5, slurp: 5, shadow: 6, dark: 6 };
    const RARITY_GRADIENTS = {
      legendary: 'linear-gradient(135deg, rgba(255,175,0,0.15), rgba(200,100,0,0.06))',
      epic: 'linear-gradient(135deg, rgba(124,92,255,0.18), rgba(88,28,200,0.06))',
      dark: 'linear-gradient(135deg, rgba(124,92,255,0.18), rgba(88,28,200,0.06))',
      shadow: 'linear-gradient(135deg, rgba(124,92,255,0.18), rgba(88,28,200,0.06))',
      marvel: 'linear-gradient(135deg, rgba(0,229,255,0.12), rgba(124,92,255,0.1))',
      dc: 'linear-gradient(135deg, rgba(0,229,255,0.12), rgba(124,92,255,0.1))',
      icon: 'linear-gradient(135deg, rgba(255,215,0,0.12), rgba(255,175,0,0.08))',
      rare: 'linear-gradient(135deg, rgba(59,130,246,0.12), rgba(37,99,235,0.06))',
      uncommon: 'linear-gradient(135deg, rgba(34,197,94,0.1), rgba(22,163,74,0.05))',
    };
    const DEFAULT_RARITY_GRADIENT = 'linear-gradient(135deg, rgba(0,229,255,0.08), rgba(124,92,255,0.04))';

    // ── Dynamic Background Colors by Rarity ──
    const BG_GRADIENTS = {
      legendary: { bg: 'linear-gradient(135deg, #1a0f00, #2d1a00)', glow: 'radial-gradient(ellipse at 50% 45%, rgba(255,175,0,0.2), rgba(200,100,0,0.08) 40%, transparent 70%)' },
      epic: { bg: 'linear-gradient(135deg, #0d0a2d, #1a0d40)', glow: 'radial-gradient(ellipse at 50% 45%, rgba(124,92,255,0.2), rgba(88,28,200,0.08) 40%, transparent 70%)' },
      dark: { bg: 'linear-gradient(135deg, #0d0a2d, #1a0d40)', glow: 'radial-gradient(ellipse at 50% 45%, rgba(124,92,255,0.2), rgba(88,28,200,0.08) 40%, transparent 70%)' },
      shadow: { bg: 'linear-gradient(135deg, #100808, #2a0a0a)', glow: 'radial-gradient(ellipse at 50% 45%, rgba(200,50,50,0.18), rgba(100,0,0,0.06) 40%, transparent 70%)' },
      marvel: { bg: 'linear-gradient(135deg, #00101a, #002040)', glow: 'radial-gradient(ellipse at 50% 45%, rgba(0,229,255,0.18), rgba(124,92,255,0.08) 40%, transparent 70%)' },
      dc: { bg: 'linear-gradient(135deg, #00101a, #002040)', glow: 'radial-gradient(ellipse at 50% 45%, rgba(0,229,255,0.18), rgba(124,92,255,0.08) 40%, transparent 70%)' },
      icon: { bg: 'linear-gradient(135deg, #0d0a00, #2d1a00)', glow: 'radial-gradient(ellipse at 50% 45%, rgba(255,215,0,0.2), rgba(200,150,0,0.08) 40%, transparent 70%)' },
      rare: { bg: 'linear-gradient(135deg, #000d1a, #001a3d)', glow: 'radial-gradient(ellipse at 50% 45%, rgba(59,130,246,0.18), rgba(37,99,235,0.06) 40%, transparent 70%)' },
      gaming_legends: { bg: 'linear-gradient(135deg, #0a0d1a, #1a0d30)', glow: 'radial-gradient(ellipse at 50% 45%, rgba(124,92,255,0.18), rgba(88,28,200,0.06) 40%, transparent 70%)' },
    };
    const DEFAULT_BG = { bg: 'linear-gradient(135deg, #050814, #0B1020)', glow: 'radial-gradient(ellipse at 50% 45%, rgba(0,229,255,0.12), rgba(124,92,255,0.07) 40%, transparent 70%)' };

    // ── Generate title from top cosmetics ──
    function generateTitle(scored, acc) {
      if (scored.length === 0) return `Season ${acc.season_num || '?'} Account`;
      const top = scored.slice(0, 3).map(s => s.name).filter(Boolean);
      const skinCount = acc.skins || 0;
      if (top.length === 0) return `${skinCount} Skins Account`;
      const titleStr = top.join(' + ');
      if (titleStr.length > 45) {
        return `${top[0]} + ${skinCount} Skins`;
      }
      return `${titleStr} | ${skinCount} Skins`;
    }

    // ── Compute marketplace header stats ──
    function updateHeaderStats(allAccounts) {
      const elAvg = document.getElementById('hdr-avg-price');
      const elMaxSkins = document.getElementById('hdr-max-skins');
      const elMaxVbucks = document.getElementById('hdr-max-vbucks');
      const hdrStats = document.getElementById('mkt-header-stats');
      if (!elAvg || !allAccounts.length) return;
      if (hdrStats) hdrStats.classList.remove('hidden');
      let totalPrice = 0, maxSkins = 0, maxVbucks = 0, count = 0;
      allAccounts.forEach(a => {
        const p = Number(a.user_price);
        if (Number.isFinite(p)) { totalPrice += p; count++; }
        if ((a.skins || 0) > maxSkins) maxSkins = a.skins;
        if ((a.vbucks || 0) > maxVbucks) maxVbucks = a.vbucks;
      });
      elAvg.textContent = count > 0 ? `$${(totalPrice / count).toFixed(2)}` : '$0.00';
      elMaxSkins.textContent = maxSkins.toLocaleString();
      elMaxVbucks.textContent = Number(maxVbucks).toLocaleString();
    }
    updateHeaderStats(accounts);

    // Apply pagination slice
    const start = (currentPage - 1) * CARDS_PER_PAGE;
    const pageAccounts = accounts.slice(start, start + CARDS_PER_PAGE);

    pageAccounts.forEach((acc, cardIndex) => {
      const card = document.createElement('div');
      card.className = 'mkt-card card-3d reveal';

      const price = Number(acc.user_price);
      const origPrice = acc.original_price ? Number(acc.original_price) : null;
      const hasDiscount = origPrice && origPrice > price;
      const fmtPrice = Number.isFinite(price) ? `$${price.toFixed(2)}` : 'N/A';
      const activityLabel = getActivityLabel(acc.days_ago);
      const fgid = acc.fortnite_item_id || '';

      // Build showcase items from preview_cosmetics (up to 6, with priority by position + rarity)
      const rawNames = Array.isArray(acc.preview_cosmetics) ? acc.preview_cosmetics.slice(0, 6) : [];
      const scored = rawNames.map((name, idx) => {
        const r = (rarityCache.get(name) || '').toLowerCase();
        const rarityScore = RARITY_SCORES[r] || 2;
        return { name, idx, score: (6 - idx) * 2 + rarityScore, rarity: r };
      });
      scored.sort((a, b) => b.score - a.score);

      const highestRarity = scored.length > 0 ? (scored[0].rarity || '') : '';
      const rarityGradient = RARITY_GRADIENTS[highestRarity] || DEFAULT_RARITY_GRADIENT;
      const bgColors = BG_GRADIENTS[highestRarity] || DEFAULT_BG;

      let bannerBgName = '';
      let bannerHtml = '';

      if (scored.length > 0) {
        const mainItem = scored[0];
        bannerBgName = mainItem.name;
        const sideItems = scored.slice(1, 6);

        let itemsHtml = '';
        itemsHtml += `<div class="mkt-si mkt-si-main" data-name="${escapeHtml(mainItem.name)}"><img class="mkt-si-img placeholder" data-name="${escapeHtml(mainItem.name)}" alt="" loading="lazy"></div>`;
        sideItems.forEach((item, si) => {
          const cls = `mkt-si mkt-si-side mkt-si-${si + 1}`;
          itemsHtml += `<div class="${cls}" data-name="${escapeHtml(item.name)}"><img class="mkt-si-img placeholder" data-name="${escapeHtml(item.name)}" alt="" loading="lazy"></div>`;
        });

        bannerHtml = `
          <div class="mkt-sc-bg" data-name="${escapeHtml(mainItem.name)}" style="background:${bgColors.bg}"></div>
          <div class="mkt-sc-rarity" style="${rarityGradient}"></div>
          <div class="mkt-sc-vignette"></div>
          <div class="mkt-sc-glow" style="background:${bgColors.glow}"></div>
          <div class="mkt-sc-streak"></div>
          <div class="mkt-sc-particle"></div>
          <div class="mkt-sc">${itemsHtml}</div>`;
      } else {
        bannerHtml = `
          <div class="mkt-sc-bg" style="background:${DEFAULT_BG.bg}"></div>
          <div class="mkt-sc-rarity" style="${DEFAULT_RARITY_GRADIENT}"></div>
          <div class="mkt-sc-vignette"></div>
          <div class="mkt-sc-glow" style="background:${DEFAULT_BG.glow}"></div>
          <div class="mkt-sc-streak"></div>
          <div class="mkt-sc-particle"></div>
          <div class="mkt-sc">
            <div class="mkt-si mkt-si-main placeholder" style="border-color:rgba(255,255,255,0.04)">
              <div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:38px;color:rgba(255,255,255,0.06);">🎮</div>
            </div>
          </div>`;
      }

      const title = generateTitle(scored, acc);

      card.innerHTML = `
        <div class="mkt-banner">
          ${bannerHtml}
          <div class="mkt-banner-overlay"></div>
          <div class="mkt-banner-top">
            <div class="mkt-banner-platforms">
              <span class="mkt-banner-platform xbox">Xbox</span>
              <span class="mkt-banner-platform psn">PSN</span>
            </div>
            <div class="mkt-banner-actions">
              <button class="mkt-fav" title="Favorite"><i class="ri-heart-line"></i></button>
              <div style="display:flex;flex-direction:column;align-items:flex-end;">
                ${hasDiscount ? `<span style="font-size:10px;color:#f87171;font-weight:700;background:rgba(239,68,68,0.1);padding:1px 7px;border-radius:99px;border:1px solid rgba(239,68,68,0.2);margin-bottom:1px;">-${acc.discount_percent}%</span>` : ''}
                <span class="mkt-price">${fmtPrice}</span>
                ${hasDiscount ? `<span style="font-size:10px;color:#64748b;text-decoration:line-through;">$${origPrice.toFixed(2)}</span>` : ''}
              </div>
            </div>
          </div>
          <div class="mkt-banner-info">
            <div class="mkt-card-title">${title}</div>
            <div class="mkt-card-sub">Full Access · ${acc.skins||0} Skins · #${escapeHtml(String(fgid||acc.item_id))} · <span class="mkt-activity-dot ${getActivityBadgeClass(acc.days_ago)}">${activityLabel}</span></div>
          </div>
        </div>
        <div class="mkt-body">
          <div class="mkt-trust">
            <span class="mkt-trust-item cy"><i class="ri-shield-check-line"></i> Full Access</span>
            <span class="mkt-trust-item gr"><i class="ri-flashlight-line"></i> Instant Delivery</span>
            <span class="mkt-trust-item pu"><i class="ri-verified-badge-line"></i> Warranty</span>
            <span class="mkt-trust-item cy"><i class="ri-lock-line"></i> Safe</span>
          </div>
          <div class="mkt-stats">
            <div class="mkt-stat emphasis"><span class="mkt-stat-icon">🎮</span><span class="mkt-stat-val">${acc.skins||0}</span><span class="mkt-stat-lbl">Skins</span></div>
            <div class="mkt-stat"><span class="mkt-stat-icon">⛏️</span><span class="mkt-stat-val">${acc.pickaxes||0}</span><span class="mkt-stat-lbl">Pickaxes</span></div>
            <div class="mkt-stat"><span class="mkt-stat-icon">💃</span><span class="mkt-stat-val">${acc.emotes||0}</span><span class="mkt-stat-lbl">Emotes</span></div>
            <div class="mkt-stat"><span class="mkt-stat-icon">🪂</span><span class="mkt-stat-val">${acc.gliders||0}</span><span class="mkt-stat-lbl">Gliders</span></div>
            <div class="mkt-stat emphasis"><span class="mkt-stat-icon">💎</span><span class="mkt-stat-val">${Number(acc.vbucks||0).toLocaleString()}</span><span class="mkt-stat-lbl">V-Bucks</span></div>
            <div class="mkt-stat emphasis"><span class="mkt-stat-icon">📊</span><span class="mkt-stat-val">${acc.level||0}</span><span class="mkt-stat-lbl">Level</span></div>
          </div>
          <div class="mkt-bottom">
            <div class="mkt-bottom-left">
              <div class="mkt-meta">
                <span class="mkt-meta-item">🏆 <span class="lbl">${acc.lifetime_wins||0} Wins</span></span>
                <span class="mkt-meta-item">🎟 BP <span class="lbl">${acc.bp_level||0}</span></span>
                <span class="mkt-meta-item">🗓️ S<span class="lbl">${acc.season_num||'?'}</span></span>
                <span class="mkt-meta-item">🛒 <span class="lbl">${acc.shop_skins||0} Shop</span></span>
                <span class="mkt-meta-item">👁️ <span class="lbl">${Number(acc.view_count||0).toLocaleString()}</span></span>
              </div>
            </div>
            <div class="mkt-bottom-right">
              <button class="mkt-cta ripple-btn" type="button"><span>View Account</span> <i class="ri-arrow-right-s-line" style="font-size:18px;line-height:1;"></i></button>
            </div>
          </div>
        </div>
      `;

      const openDetail = () => {
        const id = Number(acc.item_id);
        if (Number.isFinite(id) && id > 0) window.location.href = `/account/${id}`;
      };

      card.querySelector('.mkt-cta')?.addEventListener('click', e => { e.stopPropagation(); openDetail(); });
      card.querySelector('.mkt-fav')?.addEventListener('click', e => { e.stopPropagation(); const icon = e.currentTarget.querySelector('i'); icon.classList.toggle('ri-heart-line'); icon.classList.toggle('ri-heart-fill'); e.currentTarget.style.color = icon.classList.contains('ri-heart-fill') ? '#ec4899' : ''; });
      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");
      card.setAttribute("aria-label", `Open account ${fgid||acc.item_id}`);
      card.addEventListener("click", openDetail);
      card.addEventListener("keydown", event => { if (event.key==="Enter"||event.key===" ") { event.preventDefault(); openDetail(); } });
      card.style.animationDelay = `${cardIndex * 60}ms`;

      searchResults.appendChild(card);
    });

    // Hydrate cached icons (for any images added after initial batch load)
    document.querySelectorAll('.mkt-si-img[data-name]').forEach(img => {
      const url = iconCache.get(img.dataset.name || '');
      if (url) { img.src = url; img.classList.remove('placeholder'); img.parentElement.classList.remove('placeholder'); }
    });
    document.querySelectorAll('.mkt-sc-bg[data-name]:not(.loaded)').forEach(el => {
      const url = iconCache.get(el.dataset.name || '');
      if (url) { el.style.backgroundImage = `url(${url})`; el.classList.add('loaded'); }
    });

    // Render pagination
    renderPagination(accounts.length);
  }

  // =============== EXECUTE SEARCH ===============
  async function executeSearch({ showEmptyAlert = false } = {}) {
    if (!searchForm || !searchResults) return;
    const fd = new FormData(searchForm);
    const payload = buildPayload(fd, searchForm);
    const hasFilters = Object.keys(payload).length > 0;
    if (!hasFilters) { payload['pickaxe[]'] = 'defaultpickaxe'; currentSort = 'cheap'; }

    const requestId = ++searchRequestId;
    currentPage = 1;
    renderSkeletonCards(3);

    try {
      const data = await postJSON('/api/fortnite/search', payload);
      if (requestId !== searchRequestId) return;
      lastSearchAccounts = Array.isArray(data.accounts) ? data.accounts : [];
      renderAccounts(getSortedAccounts(lastSearchAccounts));
      updateFilterCount();
    } catch (err) {
      if (requestId !== searchRequestId) return;
      searchResults.innerHTML = `<div class="text-center py-20"><div class="text-3xl mb-2 opacity-30">❌</div><div class="text-sm font-semibold text-zinc-300">Search Error</div><div class="mt-1 text-xs text-zinc-600">${err.message}</div></div>`;
    }
  }

  function scheduleAutoSearch() {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => executeSearch({ showEmptyAlert: false }), AUTO_SEARCH_DEBOUNCE_MS);
  }

  searchForm?.addEventListener('submit', async e => { e.preventDefault(); executeSearch({ showEmptyAlert: true }); });
  searchForm?.addEventListener('input', e => { if (e.target instanceof HTMLElement && e.target.matches('input, select, textarea')) scheduleAutoSearch(); });
  searchForm?.addEventListener('change', e => { if (e.target instanceof HTMLElement && e.target.matches('input, select, textarea')) scheduleAutoSearch(); });
  searchForm?.addEventListener('reset', () => {
    setTimeout(() => {
      ++searchRequestId; clearTimeout(searchDebounceTimer);
      lastSearchAccounts = [];
      document.querySelectorAll('.autocomplete-dropdown').forEach(d => d.classList.remove('show'));
      document.querySelectorAll('.cos-search').forEach(i => i.removeAttribute('data-cosmetic-id'));
      document.querySelectorAll('.sel-cos-chip').forEach(c => c.remove());
      executeSearch({ showEmptyAlert: false });
    }, 0);
  });

  // =============== TUTORIAL ===============
  function startDashboardTutorial() {
    const isMobile = window.matchMedia('(max-width: 1023px)').matches;
    const steps = isMobile
      ? [{ selector:'#mobile-filter-toggle', title:'Filters', text:'Tap here to open filters and adjust your search.' }, { selector:'#search-results', title:'Results', text:'Accounts will appear here as wide listing cards.' }, { selector:'#result-count', title:'Live Count', text:'This shows how many accounts match right now.' }]
      : [{ selector:'#search-form', title:'Filters Panel', text:'Use this panel to set your account filters.' }, { selector:'#search-results', title:'Results List', text:'Click any account card to open full details.' }, { selector:'#result-count', title:'Result Count', text:'This updates automatically when search results change.' }];
    const validSteps = steps.filter(s => document.querySelector(s.selector));
    if (!validSteps.length) return;
    const old = document.getElementById('dashboard-tutorial-overlay');
    if (old) old.remove();
    if (!document.getElementById('dashboard-tutorial-style')) {
      const style = document.createElement('style');
      style.id = 'dashboard-tutorial-style';
      style.textContent = `.dashboard-tutorial-highlight{position:relative;z-index:1203!important;border-radius:10px;box-shadow:0 0 0 3px rgba(0,200,255,.9),0 0 28px rgba(0,200,255,.45);animation:tutorialPulse 1.2s ease-in-out infinite}@keyframes tutorialPulse{0%,100%{box-shadow:0 0 0 3px rgba(0,200,255,.9),0 0 18px rgba(0,200,255,.35)}50%{box-shadow:0 0 0 5px rgba(0,200,255,1),0 0 32px rgba(0,200,255,.65)}}`;
      document.head.appendChild(style);
    }
    const overlay = document.createElement('div');
    overlay.id = 'dashboard-tutorial-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:1200;background:rgba(2,8,20,.75);';
    const card = document.createElement('div');
    card.style.cssText = 'position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);width:min(92vw,440px);z-index:1204;background:#11131e;border:1px solid rgba(0,200,255,.4);border-radius:14px;padding:14px;color:#e2e8f0;box-shadow:0 20px 45px rgba(0,0,0,.6);';
    const titleEl = document.createElement('div');
    titleEl.style.cssText = 'font-size:13px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#00c8ff;';
    const textEl = document.createElement('p');
    textEl.style.cssText = 'margin:8px 0 0;font-size:13px;line-height:1.45;color:#94a3b8;';
    const controls = document.createElement('div');
    controls.style.cssText = 'margin-top:12px;display:flex;justify-content:flex-end;gap:8px;';
    const skipBtn = document.createElement('button');
    skipBtn.type = 'button'; skipBtn.textContent = 'Skip';
    skipBtn.style.cssText = 'border:1px solid rgba(255,255,255,.15);background:transparent;color:#64748b;border-radius:9px;padding:7px 12px;font-size:12px;font-weight:700;cursor:pointer;';
    const nextBtn = document.createElement('button');
    nextBtn.type = 'button'; nextBtn.textContent = 'Next';
    nextBtn.style.cssText = 'border:none;background:linear-gradient(135deg,#00c8ff,#8b5cf6);color:#fff;border-radius:9px;padding:7px 14px;font-size:12px;font-weight:800;cursor:pointer;';
    controls.appendChild(skipBtn);
    controls.appendChild(nextBtn);
    card.appendChild(titleEl);
    card.appendChild(textEl);
    card.appendChild(controls);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    let currentStep = 0, highlighted = null;
    const clearHighlight = () => { if (highlighted) highlighted.classList.remove('dashboard-tutorial-highlight'); highlighted = null; };
    const closeTutorial = () => { clearHighlight(); overlay.remove(); localStorage.setItem('konvy_tutorial_seen_v1','1'); };
    const renderStep = () => {
      clearHighlight();
      const step = validSteps[currentStep];
      if (!step) return closeTutorial();
      const target = document.querySelector(step.selector);
      if (!target) return closeTutorial();
      highlighted = target;
      highlighted.classList.add('dashboard-tutorial-highlight');
      highlighted.scrollIntoView({ behavior:'smooth', block:'center' });
      titleEl.textContent = `${step.title} (${currentStep+1}/${validSteps.length})`;
      textEl.textContent = step.text;
      nextBtn.textContent = currentStep === validSteps.length - 1 ? 'Finish' : 'Next';
    };
    nextBtn.addEventListener('click', () => { currentStep += 1; if (currentStep >= validSteps.length) { closeTutorial(); return; } renderStep(); });
    skipBtn.addEventListener('click', closeTutorial);
    renderStep();
  }

  function promptDashboardTutorial() {
    if (!searchForm || !searchResults) return;
    if (localStorage.getItem('konvy_tutorial_seen_v1') === '1') return;
    if (document.getElementById('dashboard-tutorial-prompt')) return;
    const prompt = document.createElement('div');
    prompt.id = 'dashboard-tutorial-prompt';
    prompt.style.cssText = 'position:fixed;inset:0;z-index:1190;background:rgba(0,0,0,.7);display:flex;align-items:center;justify-content:center;padding:16px;';
    prompt.innerHTML = `<div style="width:min(94vw,420px);background:#11131e;border:1px solid rgba(0,200,255,.3);border-radius:14px;padding:16px;color:#e2e8f0;"><div style="font-size:14px;font-weight:800;color:#00c8ff;letter-spacing:.08em;text-transform:uppercase;">Need a quick tutorial?</div><p style="margin-top:9px;font-size:13px;line-height:1.45;color:#94a3b8;">We can guide you through filters and results with an animated step-by-step tour.</p><div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px;"><button type="button" data-action="no" style="border:1px solid rgba(255,255,255,.15);background:transparent;color:#64748b;border-radius:9px;padding:7px 12px;font-size:12px;font-weight:700;cursor:pointer;">No thanks</button><button type="button" data-action="yes" style="border:none;background:linear-gradient(135deg,#00c8ff,#8b5cf6);color:#fff;border-radius:9px;padding:7px 12px;font-size:12px;font-weight:800;cursor:pointer;">Start tutorial</button></div></div>`;
    const closePrompt = () => prompt.remove();
    prompt.addEventListener('click', event => { const btn = event.target.closest('button[data-action]'); if (!btn) return; const action = btn.getAttribute('data-action'); closePrompt(); if (action === 'yes') startDashboardTutorial(); else localStorage.setItem('konvy_tutorial_seen_v1','1'); });
    document.body.appendChild(prompt);
  }

  // =============== COSMETIC TYPE DIALOG ===============
  window.showCosmeticTypeDialog = (itemId) => {
    const types = [{ id:'skins', label:'🎭 Skins', emoji:'🎭' }, { id:'pickaxes', label:'⛏️ Pickaxes', emoji:'⛏️' }, { id:'emotes', label:'💃 Emotes', emoji:'💃' }, { id:'gliders', label:'🪂 Gliders', emoji:'🪂' }];
    const html = `<div class="cosmetic-type-dialog" id="cosmetic-type-dialog"><div class="cosmetic-type-content"><h3>Choose what to preview</h3><p>Select the type of cosmetics you want to see</p><div class="cosmetic-type-options">${types.map(t => `<button class="cosmetic-type-btn" data-type="${t.id}" data-item-id="${itemId}"><span class="type-emoji">${t.emoji}</span><span class="type-label">${t.label}</span></button>`).join('')}</div><button class="cosmetic-type-close" onclick="closeCosmeticTypeDialog()">Cancel</button></div></div>`;
    const existing = document.getElementById('cosmetic-type-dialog');
    if (existing) existing.remove();
    document.body.insertAdjacentHTML('beforeend', html);
    document.body.style.overflow = "hidden";
    document.querySelectorAll('.cosmetic-type-btn').forEach(btn => {
      btn.addEventListener('click', () => { const type = btn.dataset.type; const id = btn.dataset.itemId; closeCosmeticTypeDialog(); openSkinsModal(type); loadCosmeticImages(id, type); });
    });
  };
  window.closeCosmeticTypeDialog = () => { const d = document.getElementById('cosmetic-type-dialog'); if (d) { d.remove(); document.body.style.overflow = ""; } };

  // =============== SKINS MODAL ===============
  window.openSkinsModal = (type = 'skins') => {
    document.body.style.overflow = "hidden";
    const modal = qs("skins-modal");
    modal.classList.add("open");
    const titles = { skins:'Account Skins', pickaxes:'Account Pickaxes', emotes:'Account Emotes', gliders:'Account Gliders' };
    const titleEl = modal.querySelector('.skins-modal-header h2');
    if (titleEl) titleEl.textContent = titles[type] || 'Account Cosmetics';
  };
  window.closeSkinsModal = () => { document.body.style.overflow = ""; qs("skins-modal").classList.remove("open"); qs("skins-grid").innerHTML = ""; };

  window.loadCosmeticImages = async (itemId, type = 'skins') => {
    const grid = qs("skins-grid");
    const loader = qs("skins-loader");
    const loadedEl = qs("skins-loaded");
    const totalEl = qs("skins-total");
    grid.innerHTML = "";
    loader.style.display = "flex";
    loadedEl.textContent = "0";
    totalEl.textContent = "0";
    try {
      const res = await fetch(`/api/account/${itemId}/cosmetics/${type}`);
      const data = await res.json();
      const names = Array.isArray(data.cosmetics) ? data.cosmetics : [];
      if (!names.length) { loader.querySelector(".loader-text").textContent = `No ${type} available for this account`; return; }
      totalEl.textContent = names.length;
      const mapping = { skins:'outfit', pickaxes:'pickaxe', emotes:'emote', gliders:'glider' };
      const apiType = mapping[type] || 'outfit';
      const BATCH_SIZE = 10;
      let loaded = 0;
      for (let i = 0; i < names.length; i += BATCH_SIZE) {
        const batch = names.slice(i, i + BATCH_SIZE);
        const iconsRes = await fetch("/api/skins/icons", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ names:batch, type:apiType }) });
        const iconsData = await iconsRes.json();
        const icons = Array.isArray(iconsData.icons) ? iconsData.icons : [];
        await Promise.all(icons.map(cosmetic => new Promise((resolve) => {
          const img = new Image();
          img.src = cosmetic.icon || "/static/placeholder.png";
          const onComplete = () => { loaded++; loadedEl.textContent = loaded; if (loaded === names.length) loader.style.display = "none"; resolve(); };
          img.onload = onComplete;
          img.onerror = onComplete;
          grid.appendChild(img);
        })));
      }
    } catch (err) { loader.querySelector(".loader-text").textContent = "Failed to load preview"; console.error('Preview error:', err); }
  };

  // =============== MY ACCOUNTS ===============
  let myAccounts = [];
  function formatPurchaseDate(ts) { const n = Number(ts||0); if (!Number.isFinite(n)||n<=0) return "Unknown date"; const d = new Date(n*1000); return Number.isNaN(d.getTime()) ? "Unknown date" : d.toLocaleDateString(undefined,{month:"2-digit",day:"2-digit",year:"numeric"}); }
  function formatPrice(raw) { const p = Number(raw); return Number.isFinite(p) ? `€${p.toFixed(2)}` : "N/A"; }
  function splitRaw(raw) { if (!raw) return {login:"",password:""}; const t = String(raw); const i = t.indexOf(":"); return i===-1 ? {login:t,password:""} : {login:t.slice(0,i),password:t.slice(i+1)}; }
  async function copyToClipboard(text) { const v = String(text||""); if (!v||!navigator.clipboard?.writeText) return false; try { await navigator.clipboard.writeText(v); return true; } catch(_) { return false; } }

  function buildCredRow(label, value) {
    const sl = escapeHtml(label);
    const rv = String(value||"N/A");
    const sv = escapeHtml(rv);
    const enc = encodeURIComponent(rv);
    return `<div class="my-account-row"><span class="my-account-row-label">${sl}</span><span class="my-account-row-value">${sv}</span><button type="button" class="my-account-copy-btn" data-copy="${enc}" aria-label="Copy credential value"><i class="ri-file-copy-line"></i></button></div>`;
  }

  function bindMyAccountActions() {
    const root = qs("my-accounts-view");
    if (!root) return;
    root.querySelectorAll(".my-account-copy-btn").forEach(btn => {
      btn.addEventListener("click", async () => { let cv; try { cv = decodeURIComponent(btn.dataset.copy||""); } catch(_) { cv = String(btn.dataset.copy||""); } const copied = await copyToClipboard(cv); if (copied) { btn.classList.add("copied"); setTimeout(() => btn.classList.remove("copied"), 800); } });
    });
    root.querySelectorAll("[data-acc-toggle]").forEach(btn => {
      btn.addEventListener("click", () => { const i = String(btn.dataset.accToggle||""); const c = root.querySelector(`[data-acc-content="${i}"]`); if (!c) return; const o = !c.classList.contains("is-open"); c.classList.toggle("is-open",o); btn.setAttribute("aria-expanded",o?"true":"false"); });
    });
    root.querySelectorAll(".my-account-name-save").forEach(saveBtn => {
      const pi = Number(saveBtn.dataset.purchaseIndex||"-1");
      const input = root.querySelector(`#my-account-name-input-${pi}`);
      const status = root.querySelector(`#my-account-name-status-${pi}`);
      if (!input||!status||!Number.isInteger(pi)||pi<0) return;
      const run = async () => { const n = String(input.value||"").trim(); if (!n) { status.textContent="Enter a name first."; status.classList.add("error"); return; } status.textContent="Saving..."; status.classList.remove("error"); saveBtn.disabled=true; try { await postJSON("/api/fortnite/name-account",{purchase_index:pi,name:n}); if (myAccounts[pi]) myAccounts[pi].name=n; status.textContent="Saved."; status.classList.remove("error"); } catch(e) { status.textContent=e?.message||"Failed to save."; status.classList.add("error"); } finally { saveBtn.disabled=false; } };
      saveBtn.addEventListener("click", run);
      input.addEventListener("keydown", e => { if (e.key==="Enter") { e.preventDefault(); run(); } });
    });
  }

  function buildCredCombo(l, p) { return (!l||!p||l==="N/A"||p==="N/A") ? "N/A" : `${l}:${p}`; }

  async function loadMyAccounts() {
    if (!window.KONVY_LOGGED_IN) return;
    const view = qs("my-accounts-view");
    if (!view) return;
    try { const res = await postJSON("/api/fortnite/my-accounts"); myAccounts = res.accounts||[]; renderAccount(); } catch { view.textContent = "Failed to load accounts."; }
  }

  function getAccountTitle(item, skinsCount, idx) {
    const raw = String(item?.title||item?.title_en||"").trim();
    if (raw) return raw;
    if (Number.isFinite(skinsCount)&&skinsCount>0) return `${skinsCount} Skins`;
    return `Account ${idx+1}`;
  }

  function getPurchaseItemId(acc) {
    const item = acc?.purchase_result?.item||{};
    const raw = item.item_id??item.fortnite_item_id??item.id;
    const p = Number(raw);
    return Number.isInteger(p)&&p>0 ? p : 0;
  }

  function buildAccountCard(acc, idx) {
    const item = acc.purchase_result?.item||{};
    const loginData = item.loginData||{};
    const emailData = item.emailLoginData||{};
    const pf = splitRaw(loginData.raw);
    const pe = splitRaw(emailData.raw);
    const fl = loginData.login||pf.login||"N/A";
    const fp = loginData.password||pf.password||"N/A";
    const fc = buildCredCombo(fl,fp);
    const el = emailData.login||pe.login||"N/A";
    const ep = emailData.password||pe.password||"N/A";
    const eo = emailData.oldPassword||"N/A";
    const esa = emailData.newSecretAnswer||emailData.secretAnswer||"N/A";
    const ec = buildCredCombo(el,ep);
    const sc = Number(item.fortnite_skin_count||item.fortniteSkinCount||(item.fortniteSkins||[]).length||0);
    const ok = String(acc.purchase_result?.status||"").toLowerCase()==="ok";
    const pd = formatPurchaseDate(acc.timestamp);
    const dp = formatPrice(item.priceWithSellerFee??item.price);
    const an = String(acc.name||"").trim()||`Account ${idx+1}`;
    const idInput = `my-account-name-input-${idx}`;
    const idStatus = `my-account-name-status-${idx}`;
    const anum = getPurchaseItemId(acc);
    const at = getAccountTitle(item,sc,idx);
    return `<article class="my-account-panel"><button type="button" class="my-account-summary" data-acc-toggle="${idx}" aria-expanded="false"><div class="my-account-top"><div><div class="my-account-title">${escapeHtml(at)}</div><div class="my-account-date">${escapeHtml(pd)}</div>${anum>0?`<div class="my-account-id-chip">#${escapeHtml(String(anum))}</div>`:""}<div class="my-account-state ${ok?"is-delivered":""}"><i class="${ok?"ri-check-line":"ri-time-line"}"></i><span>${ok?"Delivered":"Pending"}</span></div></div><div class="flex items-center gap-2"><div class="my-account-price">${escapeHtml(dp)}</div><i class="ri-arrow-down-s-line my-account-summary-chevron"></i></div></div></button><div class="my-account-collapse" data-acc-content="${idx}"><div class="my-account-name-wrap"><label class="my-account-name-label" for="${idInput}">Account Name</label><div class="my-account-name-controls"><input id="${idInput}" type="text" class="my-account-name-input" maxlength="50" value="${escapeHtml(an)}" placeholder="Enter account name"><button type="button" class="my-account-name-save" data-purchase-index="${idx}">Save</button></div><div class="my-account-name-status" id="${idStatus}" aria-live="polite"></div></div><section class="my-account-section"><h3>FORTNITE LOGIN</h3>${buildCredRow("Login",fl)}${buildCredRow("Password",fp)}${buildCredRow("Login & Password",fc)}</section><section class="my-account-section"><h3>EMAIL ACCESS</h3>${buildCredRow("Login",el)}${buildCredRow("Password",ep)}${buildCredRow("Old Password",eo)}${buildCredRow("Secret Answer",esa)}${buildCredRow("Login & Password",ec)}</section></div></article>`;
  }

  function renderAccount() {
    const view = qs("my-accounts-view");
    if (!view) return;
    if (!myAccounts.length) { view.textContent = "No purchased accounts."; return; }
    view.innerHTML = myAccounts.map((acc,i) => buildAccountCard(acc,i)).join("");
    bindMyAccountActions();
  }

  if (window.KONVY_LOGGED_IN) loadMyAccounts();

  // =============== INIT ===============
  if (searchForm && searchResults) {
    setTimeout(promptDashboardTutorial, TUTORIAL_PROMPT_DELAY_MS);
  }

  window.resetFilters = function() {
    const form = document.getElementById('search-form');
    if (form) form.dispatchEvent(new Event('reset'));
  };
});
