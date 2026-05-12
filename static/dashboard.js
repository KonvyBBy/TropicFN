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
    } catch {
      throw new Error(`Server error (${res.status}). Please try again later.`);
    }
    if (!res.ok) throw new Error(json.error || "Request failed");
    return json;
  }

  const qs = (id) => document.getElementById(id);

  // =============== AUTH REDIRECT ===============
  function openAuthModal(mode = "login") {
    window.location.href = mode === "register" ? "/register" : "/login";
  }


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

  // =============== MULTI-ITEM SEARCH LOGIC ===============
  let itemInputCount = 1;

  function updateRemoveButtons() {
    const rows = document.querySelectorAll('.item-input-row');
    rows.forEach((row, idx) => {
      const btn = row.querySelector('.remove-item-btn');
      if (btn) btn.style.display = rows.length > 1 ? 'block' : 'none';
    });
  }

  function updateSelection(items, index) {
    items.forEach((item, idx) => {
      item.classList.toggle('selected', idx === index);
      if (idx === index) {
        item.scrollIntoView({ block: 'nearest' });
      }
    });
  }

  function filterCosmetics(query, dropdown) {
    if (!query || query.length < 2) {
      dropdown.classList.remove('show');
      return;
    }

    const q = query.toLowerCase();
    const allowedTypes = ['outfit', 'pickaxe', 'emote', 'glider'];
    
    const filtered = window.allCosmetics
      .filter(item => {
        const itemType = (item.type?.value || '').toLowerCase();
        const nameMatch = item.name.toLowerCase().includes(q);
        return nameMatch && allowedTypes.includes(itemType);
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
        <div class="autocomplete-item" data-index="${idx}" data-name="${item.name}">
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

  function setupAutocomplete(input, dropdown) {
    let selectedIndex = -1;
    let debounceTimer = null;
    
    input.addEventListener('input', (e) => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        filterCosmetics(e.target.value, dropdown);
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
        dropdown.classList.remove('show');
      }
    });
  }

  const firstInput = document.querySelector('.item-search-input');
  const firstDropdown = document.querySelector('.autocomplete-dropdown');
  if (firstInput && firstDropdown) {
    setupAutocomplete(firstInput, firstDropdown);
  }

  document.getElementById('add-item-btn')?.addEventListener('click', () => {
    if (itemInputCount >= 5) {
      alert('Maximum 5 items allowed');
      return;
    }
    
    itemInputCount++;
    const container = document.getElementById('items-container');
    
    const row = document.createElement('div');
    row.className = 'item-input-row';
    row.innerHTML = `
      <div class="autocomplete-wrapper">
        <input 
          type="text" 
          class="item-search-input" 
          placeholder="Type item name..." 
          autocomplete="off">
        <div class="autocomplete-dropdown"></div>
      </div>
      <button type="button" class="remove-item-btn">✕</button>
    `;
    
    container.appendChild(row);
    
    const input = row.querySelector('.item-search-input');
    const dropdown = row.querySelector('.autocomplete-dropdown');
    setupAutocomplete(input, dropdown);
    
    row.querySelector('.remove-item-btn').addEventListener('click', () => {
      row.remove();
      itemInputCount--;
      updateRemoveButtons();
    });
    
    updateRemoveButtons();
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

  searchForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const inputs = document.querySelectorAll('.item-search-input');
    const items = Array.from(inputs)
      .map(input => input.value.trim())
      .filter(val => val.length > 0);
    
    if (items.length === 0) {
      alert('Please enter at least one item to search');
      return;
    }
    
    searchResults.innerHTML = `
      <div style="grid-column:1/-1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:48px 24px;gap:14px;">
        <div style="width:36px;height:36px;border:3px solid rgba(255,255,255,0.08);border-top-color:#10b981;border-radius:50%;animation:spin 0.8s linear infinite;"></div>
        <div style="font-size:0.9rem;font-weight:500;color:#a1a1aa;">Searching for accounts...</div>
      </div>
    `;
    
    const fd = new FormData(searchForm);
    const budgetInput = document.getElementById('budget-input');
    const budget = budgetInput.value ? parseFloat(budgetInput.value) : 999999;
    
    try {
      const data = await postJSON('/api/fortnite/search', {
        item: items.join(', '),
        days: Number(fd.get('days') || 0),
        skins: Number(fd.get('skins') || 0),
        budget: budget,
      });
      
      searchResults.innerHTML = '';
      
      if (!data.accounts || data.accounts.length === 0) {
        searchResults.innerHTML = `
          <div style="grid-column:1/-1;text-align:center;padding:48px 24px;">
            <div style="font-size:2.5rem;margin-bottom:12px;opacity:0.5;">😕</div>
            <div style="font-size:0.95rem;font-weight:600;color:#e4e4e7;margin-bottom:6px;">No accounts found</div>
            <div style="font-size:0.82rem;color:#71717a;">Try different items or adjust your filters</div>
          </div>
        `;
        return;
      }
      
      data.accounts.forEach(acc => {
        const card = document.createElement('div');
        card.className = 'glass-panel group relative overflow-hidden rounded-2xl transition hover:border-white/20';
        card.style.display = 'flex';
        card.style.flexDirection = 'column';

        const warrantyTag = acc.last_played_days != null && acc.last_played_days >= 11
          ? `<span style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.3);color:#34d399;padding:2px 8px;border-radius:99px;font-size:0.65rem;font-weight:700;">✓ Warranty</span>`
          : '';

        card.innerHTML = `
          <div style="padding:16px 18px 0;display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;">
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
              <span style="background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);color:#e4e4e7;padding:3px 8px;border-radius:99px;font-size:0.65rem;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;">Full Access</span>
              ${warrantyTag}
            </div>
            <div style="font-family:'Space Grotesk',sans-serif;font-size:1.25rem;font-weight:700;color:#fff;">$${acc.user_price.toFixed(2)}</div>
          </div>

          <div style="padding:14px 18px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;flex:1;">
            <div style="text-align:center;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:10px 6px;">
              <div style="font-size:0.7rem;color:#71717a;margin-bottom:3px;">🎭 Skins</div>
              <div style="font-weight:700;color:#fff;font-size:0.95rem;">${acc.skins || 0}</div>
            </div>
            <div style="text-align:center;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:10px 6px;">
              <div style="font-size:0.7rem;color:#71717a;margin-bottom:3px;">💃 Emotes</div>
              <div style="font-weight:700;color:#fff;font-size:0.95rem;">${acc.emotes || 0}</div>
            </div>
            <div style="text-align:center;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:10px 6px;">
              <div style="font-size:0.7rem;color:#71717a;margin-bottom:3px;">⛏️ Picks</div>
              <div style="font-weight:700;color:#fff;font-size:0.95rem;">${acc.pickaxes || 0}</div>
            </div>
            <div style="text-align:center;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:10px 6px;">
              <div style="font-size:0.7rem;color:#71717a;margin-bottom:3px;">🪂 Gliders</div>
              <div style="font-weight:700;color:#fff;font-size:0.95rem;">${acc.gliders || 0}</div>
            </div>
            <div style="text-align:center;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:10px 6px;">
              <div style="font-size:0.7rem;color:#71717a;margin-bottom:3px;">💰 V-Bucks</div>
              <div style="font-weight:700;color:#fff;font-size:0.95rem;">${acc.vbucks || 0}</div>
            </div>
            <div style="text-align:center;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:12px;padding:10px 6px;">
              <div style="font-size:0.7rem;color:#71717a;margin-bottom:3px;">📅 Offline</div>
              <div style="font-weight:700;color:#fff;font-size:0.85rem;">${acc.last_played || "?"}</div>
            </div>
          </div>

          <div style="padding:0 18px 16px;display:flex;gap:8px;">
            <button class="buy-btn" data-item-id="${acc.item_id}" data-base-price="${acc.base_price}"
              style="flex:1;background:#10b981;color:#000;border:none;border-radius:12px;padding:10px;font-size:0.82rem;font-weight:700;cursor:pointer;transition:background 0.15s;">
              💳 Buy Now
            </button>
            <button class="skins-btn" data-item-id="${acc.item_id}"
              style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:#a1a1aa;border-radius:12px;padding:10px 14px;font-size:0.82rem;font-weight:600;cursor:pointer;transition:all 0.15s;white-space:nowrap;">
              👀 Preview
            </button>
          </div>
        `;

        // Buy
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

            // Load accounts to get current count for index
            let currentAccounts = [];
            try {
              const accsRes = await postJSON("/api/fortnite/my-accounts");
              currentAccounts = accsRes.accounts || [];
            } catch {}
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

        // Preview
        card.querySelector(".skins-btn").onclick = () => {
          showCosmeticTypeDialog(acc.item_id);
        };

        searchResults.appendChild(card);
      });
      
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
