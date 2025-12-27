document.addEventListener("DOMContentLoaded", () => {

  // =============== THEME TOGGLE ===============
  const themeToggle = document.getElementById('theme-toggle');
  const themeIcon = themeToggle?.querySelector('.icon');
  const themeLabel = themeToggle?.querySelector('.label');
  
  // Load saved theme preference or default to dark mode
  const savedTheme = localStorage.getItem('theme') || 'dark';
  
  function applyTheme(theme) {
    if (theme === 'dark') {
      document.body.classList.add('dark-mode');
      if (themeIcon) themeIcon.textContent = '🌙';
      if (themeLabel) themeLabel.textContent = 'Dark Mode';
    } else {
      document.body.classList.remove('dark-mode');
      if (themeIcon) themeIcon.textContent = '☀️';
      if (themeLabel) themeLabel.textContent = 'Light Mode';
    }
    localStorage.setItem('theme', theme);
  }
  
  // Apply saved theme on page load
  applyTheme(savedTheme);
  
  // Toggle theme on button click
  themeToggle?.addEventListener('click', (e) => {
    e.preventDefault();
    const currentTheme = document.body.classList.contains('dark-mode') ? 'dark' : 'light';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    applyTheme(newTheme);
  });

  // =============== ANIMATED PARTICLES BACKGROUND ===============
  const canvas = document.createElement('canvas');
  canvas.id = 'particles-canvas';
  document.body.prepend(canvas);

  const ctx = canvas.getContext('2d');
  let particles = [];
  let mouseX = 0;
  let mouseY = 0;

  function resizeCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  }

  window.addEventListener('resize', resizeCanvas);
  resizeCanvas();

  document.addEventListener('mousemove', (e) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
  });

  class Particle {
    constructor() {
      this.x = Math.random() * canvas.width;
      this.y = Math.random() * canvas.height;
      this.vx = (Math.random() - 0.5) * 0.5;
      this.vy = (Math.random() - 0.5) * 0.5;
      this.radius = Math.random() * 2 + 1;
    }

    update() {
      this.x += this.vx;
      this.y += this.vy;

      // Mouse interaction
      const dx = mouseX - this.x;
      const dy = mouseY - this.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      
      if (dist < 100) {
        const angle = Math.atan2(dy, dx);
        this.vx -= Math.cos(angle) * 0.05;
        this.vy -= Math.sin(angle) * 0.05;
      }

      // Boundaries
      if (this.x < 0 || this.x > canvas.width) this.vx *= -1;
      if (this.y < 0 || this.y > canvas.height) this.vy *= -1;

      // Damping
      this.vx *= 0.99;
      this.vy *= 0.99;
    }

    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255, 255, 255, 0.3)';
      ctx.fill();
    }
  }

  // Create particles
  for (let i = 0; i < 80; i++) {
    particles.push(new Particle());
  }

  function animateParticles() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    particles.forEach(p => {
      p.update();
      p.draw();
    });

    // Connect nearby particles
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < 120) {
          ctx.beginPath();
          ctx.strokeStyle = `rgba(255, 255, 255, ${0.1 * (1 - dist / 120)})`;
          ctx.lineWidth = 0.5;
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.stroke();
        }
      }
    }

    requestAnimationFrame(animateParticles);
  }

  animateParticles();



// =============== MOBILE TOUCH IMPROVEMENTS ===============
  let touchStartY = 0;
  let touchEndY = 0;

  document.addEventListener('touchstart', (e) => {
    touchStartY = e.changedTouches[0].screenY;
  }, { passive: true });

  document.addEventListener('touchend', (e) => {
    touchEndY = e.changedTouches[0].screenY;
  }, { passive: true });

  // Prevent double-tap zoom on buttons
  document.addEventListener('touchend', (e) => {
    if (e.target.matches('button, .action-btn, .nav-btn')) {
      e.preventDefault();
      e.target.click();
    }
  });




  // =============== UTILITIES ===============
  async function postJSON(url, data = {}) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || "Request failed");
    return json;
  }

  const qs = (id) => document.getElementById(id);

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

  // =============== FAVORITES SYSTEM ===============
  let userFavorites = [];

  async function loadFavorites() {
    if (!window.KONVY_LOGGED_IN) return;
    try {
      const res = await postJSON('/api/favorites/list', {});
      userFavorites = res.favorites || [];
    } catch (err) {
      console.error('Failed to load favorites:', err);
    }
  }

  async function toggleFavorite(itemId, btn) {
    if (!window.KONVY_LOGGED_IN) {
      alert('Please login to save favorites');
      return;
    }

    const isFavorite = userFavorites.includes(itemId);
    
    try {
      if (isFavorite) {
        await postJSON('/api/favorites/remove', { item_id: itemId });
        userFavorites = userFavorites.filter(id => id !== itemId);
        btn.classList.remove('active');
        btn.textContent = '♡';
      } else {
        await postJSON('/api/favorites/add', { item_id: itemId });
        userFavorites.push(itemId);
        btn.classList.add('active');
        btn.textContent = '♥';
      }
    } catch (err) {
      alert('Failed to update favorites: ' + err.message);
    }
  }

  // Load favorites on page load
  loadFavorites();

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
      <div class="loading-state">
        <div class="loading-spinner"></div>
        <div class="loading-text">Searching for accounts...</div>
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
          <div class="empty-state">
            <div class="empty-state-icon">😕</div>
            <div class="empty-state-text">No accounts found</div>
            <div class="empty-state-hint">Try different items or adjust your filters</div>
          </div>
        `;
        return;
      }
      
      data.accounts.forEach(acc => {
        const card = document.createElement('div');
        card.className = 'account-card';
        
        const isFavorite = userFavorites.includes(acc.item_id);
        
        card.innerHTML = `
          <!-- Favorite -->
          <button class="favorite-btn ${isFavorite ? "active" : ""}"
                  data-item-id="${acc.item_id}">
            ${isFavorite ? "♥" : "♡"}
          </button>

          <!-- Badge -->
          <div class="full-access-badge">Full Access</div>

          <!-- Header -->
          <div class="account-header">
            <div class="account-price">$${acc.user_price.toFixed(2)}</div>
            <div class="account-id">#${acc.item_id}</div>
          </div>

          <!-- Stats -->
          <div class="account-stats">
            <div class="stat-item">
              <span class="stat-label">🎭 Skins</span>
              <span class="stat-value">${acc.skins || 0}</span>
            </div>

            <div class="stat-item">
              <span class="stat-label">⛏️ Pickaxes</span>
              <span class="stat-value">${acc.pickaxes || 0}</span>
            </div>

            <div class="stat-item">
              <span class="stat-label">💃 Emotes</span>
              <span class="stat-value">${acc.emotes || 0}</span>
            </div>

            <div class="stat-item">
              <span class="stat-label">🪂 Gliders</span>
              <span class="stat-value">${acc.gliders || 0}</span>
            </div>

            <div class="stat-item">
              <span class="stat-label">💰 V-Bucks</span>
              <span class="stat-value">${acc.vbucks || 0}</span>
            </div>

            <div class="stat-item">
              <span class="stat-label">📅 Last Played</span>
              <span class="stat-value">${acc.last_played || "Unknown"}</span>
            </div>
          </div>

          <!-- Actions -->
          <div class="account-actions">
            <button class="action-btn primary buy-btn"
                    data-item-id="${acc.item_id}"
                    data-base-price="${acc.base_price}">
              💳 Buy
            </button>

            <button class="action-btn secondary skins-btn"
                    data-item-id="${acc.item_id}">
              👀 Preview
            </button>
          </div>
        `;

        // Favorite
        const favBtn = card.querySelector(".favorite-btn");
        favBtn.onclick = (e) => {
          e.stopPropagation();
          toggleFavorite(acc.item_id, favBtn);
        };

        // Buy
        const buyBtn = card.querySelector(".buy-btn");
        buyBtn.onclick = async () => {
          if (!window.KONVY_LOGGED_IN) {
            if (confirm("You need to login to purchase accounts. Go to login page?")) {
              window.location.href = "/login";
            }
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
            alert("✅ Purchase successful! Check 'My Accounts' tab.");
            loadMyAccounts();
          } catch (e) {
            hideProcessingOverlay();
            alert("❌ " + e.message);
          }

          buyBtn.disabled = false;
        };

        // Preview
        card.querySelector(".skins-btn").onclick = () => {
          openSkinsModal();
          loadSkinImages(acc.item_id);
        };

        searchResults.appendChild(card);
      });
      
    } catch (err) {
      searchResults.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">❌</div>
          <div class="empty-state-text">Search Error</div>
          <div class="empty-state-hint">${err.message}</div>
        </div>
      `;
    }
  });

  // =============== SECTION NAV ===============
  const navButtons = document.querySelectorAll(".nav-btn");
  const sections = document.querySelectorAll(".section");

  function showSection(name) {
    sections.forEach(sec => sec.style.display = "none");
    navButtons.forEach(btn => btn.classList.remove("active"));

    const target = qs("section-" + name);
    const btn = document.querySelector(`.nav-btn[data-section="${name}"]`);

    if (target) target.style.display = "block";
    if (btn) btn.classList.add("active");
  }

  navButtons.forEach(btn => {
    btn.addEventListener("click", () => showSection(btn.dataset.section));
  });

  showSection("home");

  // =============== SKINS MODAL (OPTIMIZED) ===============
  window.openSkinsModal = () => {
    document.body.style.overflow = "hidden";
    qs("skins-modal").classList.add("open");
  };

  window.closeSkinsModal = () => {
    document.body.style.overflow = "";
    qs("skins-modal").classList.remove("open");
    qs("skins-grid").innerHTML = "";
  };

  window.loadSkinImages = async (itemId) => {
    const grid = qs("skins-grid");
    const loader = qs("skins-loader");
    const loadedEl = qs("skins-loaded");
    const totalEl = qs("skins-total");

    grid.innerHTML = "";
    loader.style.display = "flex";
    loadedEl.textContent = "0";
    totalEl.textContent = "0";

    try {
      const skinsRes = await fetch(`/api/account/${itemId}/skins`);
      const skinsData = await skinsRes.json();
      const names = Array.isArray(skinsData.skins) ? skinsData.skins : [];

      if (!names.length) {
        loader.querySelector(".loader-text").textContent = "No skins available for this account";
        return;
      }

      totalEl.textContent = names.length;

      // OPTIMIZED: Load icons in batches of 10
      const BATCH_SIZE = 10;
      let loaded = 0;
      
      for (let i = 0; i < names.length; i += BATCH_SIZE) {
        const batch = names.slice(i, i + BATCH_SIZE);
        
        const iconsRes = await fetch("/api/skins/icons", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ names: batch }),
        });

        const iconsData = await iconsRes.json();
        const icons = Array.isArray(iconsData.icons) ? iconsData.icons : [];

        // Create images for this batch
        await Promise.all(icons.map(skin => {
          return new Promise((resolve) => {
            const img = new Image();
            img.src = skin.icon || "/static/placeholder.png";
            
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

  // =============== REDEEM ===============
  qs("redeem-btn")?.addEventListener("click", async () => {
    qs("redeem-result").textContent = "Redeeming…";
    try {
      const res = await postJSON("/api/redeem", {
        order_number: Number(qs("redeem-order").value),
      });
      qs("redeem-result").textContent = res.message;
    } catch (e) {
      qs("redeem-result").textContent = e.message;
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

    const emailRaw = item.emailLoginData?.raw || "N/A";
    const epicRaw = item.loginData?.raw || "N/A";

    let emailSite = "Unknown";
    if (emailRaw.includes("@")) {
      emailSite = emailRaw.split(":")[0].split("@")[1] || "Unknown";
    }

    qs("my-accounts-view").innerHTML = `
      <div class="cred-block"><label>Email Login</label><code>${emailRaw}</code></div>
      <div class="cred-block"><label>Email Site</label><code>${emailSite}</code></div>
      <div class="cred-block"><label>Epic Login</label><code>${epicRaw}</code></div>
    `;

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
