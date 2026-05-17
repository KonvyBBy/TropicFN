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
    if (!res.ok) throw new Error(json.error || "Request failed");
    return json;
  }

  const qs = (id) => document.getElementById(id);

  // =============== AUTH MODAL ===============
  function openAuthModal(mode = "login") {
    const overlay = qs("auth-modal-overlay");
    const frame = qs("auth-modal-frame");
    if (!overlay || !frame) {
      window.location.href = mode === "register" ? "/register" : "/login";
      return;
    }
    frame.src = mode === "register" ? "/register" : "/login";
    overlay.classList.add("open");
    overlay.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function closeAuthModal() {
    const overlay = qs("auth-modal-overlay");
    if (!overlay) return;
    overlay.classList.remove("open");
    overlay.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  qs("sign-in-trigger")?.addEventListener("click", () => openAuthModal("login"));
  qs("auth-modal-close")?.addEventListener("click", closeAuthModal);
  qs("auth-modal-overlay")?.addEventListener("click", (e) => {
    if (e.target.id === "auth-modal-overlay") closeAuthModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAuthModal();
  });
  qs("auth-modal-frame")?.addEventListener("load", () => {
    const frame = qs("auth-modal-frame");
    if (!frame) return;
    try {
      const path = frame.contentWindow?.location?.pathname || "";
      if (path && path !== "/login" && path !== "/register") {
        window.location.reload();
      }
    } catch (e) {
      console.debug("Ignored modal iframe access error", e);
    }
  });


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
  window.allCosmetics = [];
  
  async function loadCosmetics() {
    try {
      const res = await fetch("https://fortnite-api.com/v2/cosmetics/br");
      const data = await res.json();
      if (data.status === 200 && data.data) {
        window.allCosmetics = data.data;
        console.log(`Loaded ${window.allCosmetics.length} Fortnite cosmetics`);
      }
    } catch (err) {
      console.error("Failed to load cosmetics:", err);
    }
  }
  
  loadCosmetics();

  // =============== COSMETIC AUTOCOMPLETE LOGIC ===============

  function updateSelection(items, index) {
    items.forEach((item, idx) => {
      item.classList.toggle('selected', idx === index);
      if (idx === index) {
        item.scrollIntoView({ block: 'nearest' });
      }
    });
  }

  function filterCosmetics(query, dropdown, allowedTypes) {
    if (!query || query.length < 2) {
      dropdown.classList.remove('show');
      return;
    }

    const q = query.toLowerCase();
    const allowedTypeSet = new Set((allowedTypes || ['outfit', 'pickaxe', 'emote', 'glider']).map(v => String(v).toLowerCase()));
    
    const filtered = window.allCosmetics
      .filter(item => {
        const itemType = (item.type?.value || '').toLowerCase();
        const nameMatch = item.name.toLowerCase().includes(q);
        return nameMatch && allowedTypeSet.has(itemType);
      })
      .slice(0, 10);

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
    
    input.addEventListener('input', (e) => {
      input.removeAttribute('data-cosmetic-id');
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        filterCosmetics(e.target.value, dropdown, allowedTypes);
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
        input.value = item.dataset.name;
        input.setAttribute('data-cosmetic-id', item.dataset.id || '');
        dropdown.classList.remove('show');
      }
    });
  }

  document.querySelectorAll('.cosmetic-search-input').forEach((input) => {
    const dropdown = input.parentElement?.querySelector('.autocomplete-dropdown');
    if (!dropdown) return;
    const cosmeticType = String(input.dataset.cosmeticType || '').toLowerCase();
    const allowedTypes = cosmeticType ? [cosmeticType] : ['outfit', 'pickaxe', 'emote', 'glider'];
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
  let currentSort = 'default';
  let lastSearchAccounts = [];
  const MAX_PREVIEW_COSMETICS = 8;
  const BOOLEAN_FILTER_KEYS = new Set(['email_login_data']);
  const ENUM_FILTER_KEYS = new Set(['change_email', 'bp']);
  const allowedFormKeys = new Set([
    'pmin', 'pmax', 'email_login_data', 'change_email',
    'skin[]', 'pickaxe[]', 'dance[]', 'glider[]',
    'smin', 'smax', 'pickaxe_min', 'pickaxe_max', 'dmin', 'dmax', 'gmin', 'gmax',
    'vbmin', 'vbmax', 'lmin', 'lmax', 'paid_items_min', 'paid_items_max',
    'refund_credits_min', 'refund_credits_max', 'daybreak', 'daybreak_max',
    'bp', 'bp_lmin', 'bp_lmax', 'country[]',
    'stw_mode'
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
      if (key === 'stw_mode') return;
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
      const inputEl = form ? form.querySelector(`input[name="${fieldName}"]`) : null;
      const storedId = inputEl ? inputEl.getAttribute('data-cosmetic-id') : null;
      if (storedId) {
        payload[fieldName] = toCosmeticMarketId(storedId, prefix);
      } else {
        // No confirmed selection — remove the raw text name so it doesn't confuse the API.
        delete payload[fieldName];
      }
    }

    const stwMode = String(formData.get('stw_mode') || '').trim();
    if (stwMode === 'include') payload['stw[]'] = [1];
    if (stwMode === 'exclude') payload['not_stw[]'] = [1];

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
      const name = tile.dataset.cosmeticName || '';
      const icon = previewIconCache.get(name);
      if (!icon) return;
      if (tile.hasAttribute('data-hydrated')) return;
      tile.setAttribute('data-hydrated', '');
      tile.innerHTML = `<img src="${escapeHtml(icon)}" alt="${escapeHtml(name)}" loading="lazy">`;
      tile.classList.add('has-image');
    });
  }

  function getSortedAccounts(accounts) {
    const list = [...accounts];
    if (currentSort === 'cheap') list.sort((a, b) => (a.user_price || 0) - (b.user_price || 0));
    if (currentSort === 'expensive') list.sort((a, b) => (b.user_price || 0) - (a.user_price || 0));
    if (currentSort === 'newest') list.sort((a, b) => (b.item_id || 0) - (a.item_id || 0));
    return list;
  }

  function setSort(sort) {
    currentSort = sort;
    sortButtons.forEach(btn => {
      const active = btn.dataset.sort === sort;
      btn.classList.toggle('active', active);
      btn.classList.toggle('project-muted', !active);
    });
    if (lastSearchAccounts.length) renderAccounts(getSortedAccounts(lastSearchAccounts));
  }

  sortButtons.forEach(btn => {
    btn.addEventListener('click', () => setSort(btn.dataset.sort || 'default'));
  });

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
      card.className = 'glass-panel market-account-card group';

      const warrantyTag = acc.last_played_days != null && acc.last_played_days >= 11
        ? `<span class="market-chip market-chip--warranty">✓ Warranty</span>`
        : '';

      const numericPrice = Number(acc.user_price);
      const hasPrice = Number.isFinite(numericPrice);
      const formattedPrice = hasPrice ? numericPrice.toFixed(2) : 'N/A';

      const previewNames = Array.isArray(acc.preview_cosmetics) ? acc.preview_cosmetics.slice(0, MAX_PREVIEW_COSMETICS) : [];
      const previewTiles = previewNames.map((name) => {
        const safe = String(name || '').trim();
        const initials = safe ? safe.split(/\s+/).slice(0, 2).map(p => p[0]).join('').toUpperCase() : '?';
        return `
          <div class="market-preview-tile" title="${escapeHtml(safe)}" data-cosmetic-name="${escapeHtml(safe)}">
            <span class="market-preview-fallback">${escapeHtml(initials)}</span>
          </div>
        `;
      }).join('');
      const cardTitle = escapeHtml(acc.title || `${acc.skins || 0} Skins | Fortnite Account`);

      card.innerHTML = `
        <div class="market-card-head">
          <div class="market-chip-row">
            ${warrantyTag}
          </div>
          <div class="market-price-badge">${formattedPrice} €</div>
        </div>

        <div class="market-preview-grid">
          ${previewNames.length > 0 ? previewTiles : '<div class="market-preview-empty">No preview cosmetics</div>'}
        </div>

        <div class="market-card-main">
          <div class="market-card-title">${cardTitle}</div>

          <div class="market-stat-line">
            <span class="market-stat-main">${acc.skins || 0} Skins</span>
          </div>

          <div class="market-icon-row">
            <span class="market-icon-item"><i class="ri-t-shirt-2-line"></i> ${acc.skins || 0}</span>
            <span class="market-icon-item"><i class="ri-coin-line"></i> ${acc.vbucks || 0}</span>
            <span class="market-icon-item"><i class="ri-calendar-event-line"></i> ${escapeHtml(acc.last_played || "N/A")}</span>
          </div>
        </div>

        <div class="market-card-actions">
          <button type="button" class="preview-btn market-preview-btn" data-item-id="${acc.item_id}">
            Preview Cosmetics
          </button>
          <button class="buy-btn market-buy-btn" data-item-id="${acc.item_id}" data-base-price="${acc.base_price}">
            Buy Account
          </button>
        </div>
      `;

      const openPreview = () => {
        showCosmeticTypeDialog(acc.item_id);
      };
      const previewBtn = card.querySelector(".preview-btn");
      const previewGrid = card.querySelector(".market-preview-grid");
      previewBtn.onclick = openPreview;
      previewGrid?.addEventListener("click", openPreview);

      const buyBtn = card.querySelector(".buy-btn");
      buyBtn.onclick = async () => {
        if (!window.KONVY_LOGGED_IN) {
          openAuthModal("login");
          return;
        }

        buyBtn.disabled = true;
        showProcessingOverlay();

        try {
          await postJSON("/api/fortnite/buy", {
            item_id: acc.item_id,
            base_price: acc.base_price
          });

          hideProcessingOverlay();

          let currentAccounts = [];
          try {
            const accsRes = await postJSON("/api/fortnite/my-accounts");
            currentAccounts = accsRes.accounts || [];
          } catch (e) {
            console.error("Failed to refresh purchased accounts after purchase", e);
          }
          const newIndex = currentAccounts.length - 1;

          showNamingModal(newIndex, () => {
            loadMyAccounts();
          });
        } catch (e) {
          hideProcessingOverlay();
          alert("❌ " + e.message);
        }

        buyBtn.disabled = false;
      };

      searchResults.appendChild(card);
    });

    hydratePreviewIcons();
  }

  searchForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const fd = new FormData(searchForm);
    const payload = buildSearchPayload(fd, [], searchForm);
    const hasFilters = Object.keys(payload).length > 0;

    if (!hasFilters) {
      alert('Please set at least one filter to search');
      return;
    }

    searchResults.innerHTML = `
      <div style="grid-column:1/-1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:48px 24px;gap:14px;">
        <div style="width:36px;height:36px;border:3px solid rgba(255,255,255,0.08);border-top-color:#10b981;border-radius:50%;animation:spin 0.8s linear infinite;"></div>
        <div style="font-size:0.9rem;font-weight:500;color:#a1a1aa;">Searching for accounts...</div>
      </div>
    `;
    
    try {
      const data = await postJSON('/api/fortnite/search', payload);
      lastSearchAccounts = Array.isArray(data.accounts) ? data.accounts : [];
      renderAccounts(getSortedAccounts(lastSearchAccounts));
      
    } catch (err) {
      searchResults.innerHTML = `
        <div style="grid-column:1/-1;text-align:center;padding:48px 24px;">
          <div style="font-size:2.5rem;margin-bottom:12px;opacity:0.5;">❌</div>
          <div style="font-size:0.95rem;font-weight:600;color:#e4e4e7;margin-bottom:6px;">Search Error</div>
          <div style="font-size:0.82rem;color:#71717a;">${err.message}</div>
        </div>
      `;
    }
  });

  searchForm?.addEventListener('reset', () => {
    window.setTimeout(() => {
      document.querySelectorAll('.autocomplete-dropdown').forEach(d => d.classList.remove('show'));
      document.querySelectorAll('.cosmetic-search-input').forEach(i => i.removeAttribute('data-cosmetic-id'));
    }, 0);
  });

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
  let accIndex = 0;

  async function loadMyAccounts() {
    if (!window.KONVY_LOGGED_IN) return;
    
    try {
      const res = await postJSON("/api/fortnite/my-accounts");
      myAccounts = res.accounts || [];
      accIndex = 0;
      renderAccount();
    } catch {
      qs("my-accounts-view").textContent = "Failed to load accounts.";
    }
  }

  function renderAccount() {
    if (!myAccounts.length) {
      qs("my-accounts-view").textContent = "No purchased accounts.";
      return;
    }

    const acc = myAccounts[accIndex];
    const item = acc.purchase_result?.item || {};
    const accountName = acc.name || "Unnamed Account";

    const emailRaw = item.emailLoginData?.raw || "N/A";
    const epicRaw = item.loginData?.raw || "N/A";

    let emailSite = "Unknown";
    if (emailRaw.includes("@")) {
      emailSite = emailRaw.split(":")[0].split("@")[1] || "Unknown";
    }

    qs("my-accounts-view").innerHTML = `
      <div class="account-name-header"></div>
      <div class="cred-block"><label>Email Login</label><code>${emailRaw}</code></div>
      <div class="cred-block"><label>Email Site</label><code>${emailSite}</code></div>
      <div class="cred-block"><label>Epic Login</label><code>${epicRaw}</code></div>
    `;
    qs("my-accounts-view").querySelector(".account-name-header").textContent = accountName;

    qs("account-indicator").textContent =
      `Account ${accIndex + 1} / ${myAccounts.length}`;
  }

  qs("prev-account")?.addEventListener("click", () => {
    accIndex = Math.max(0, accIndex - 1);
    renderAccount();
  });

  qs("next-account")?.addEventListener("click", () => {
    accIndex = Math.min(myAccounts.length - 1, accIndex + 1);
    renderAccount();
  });

  if (window.KONVY_LOGGED_IN) {
    loadMyAccounts();
  }
});
