/**
 * Cloud Deals — Telegram Mini App (TMA) Client Application
 * Handles authentication, catalog browsing, cart operations,
 * crypto/balance checkout, live payment polling, and credentials vault.
 */

(function () {
  'use strict';

  // --- Telegram WebApp SDK Initialization ---
  const tg = window.Telegram?.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
    if (tg.enableClosingConfirmation) {
      tg.enableClosingConfirmation();
    }
  }

  // --- Haptic Feedback Helper ---
  function haptic(type) {
    if (!tg?.HapticFeedback) return;
    try {
      if (type === 'light' || type === 'medium' || type === 'heavy') {
        tg.HapticFeedback.impactOccurred(type);
      } else if (type === 'success' || type === 'error' || type === 'warning') {
        tg.HapticFeedback.notificationOccurred(type);
      } else if (type === 'selection') {
        tg.HapticFeedback.selectionChanged();
      }
    } catch (e) {
      // Ignored if haptics unavailable
    }
  }

  // --- Application State ---
  const state = {
    initData: tg?.initData || '',
    token: (function () {
      try {
        return sessionStorage.getItem('cloud_deals_jwt') || null;
      } catch (e) {
        return null;
      }
    })(),
    telegramId: null,
    user: null,
    store: null,
    categories: [],
    products: [],
    activeCategory: 'all',
    searchQuery: '',
    cart: {
      items: [],
      total_items: 0,
      subtotal: '0.00',
      final_amount: '0.00',
      discount_eligible: false,
      discount_amount: '0.00',
      currency: 'USD',
    },
    selectedProduct: null,
    modalQuantity: 1,
    activeModal: null,
    currentPaymentOrder: null,
    pollTimer: null,
    appliedCoupon: null,
  };

  // --- DOM Elements Cache ---
  const el = {
    userChipBtn: document.getElementById('userChipBtn'),
    userAvatar: document.getElementById('userAvatar'),
    userName: document.getElementById('userName'),
    userBalance: document.getElementById('userBalance'),
    promoBanner: document.getElementById('promoBanner'),
    claimDiscountBtn: document.getElementById('claimDiscountBtn'),
    discountActiveCard: document.getElementById('discountActiveCard'),
    searchInput: document.getElementById('searchInput'),
    clearSearchBtn: document.getElementById('clearSearchBtn'),
    categoriesBar: document.getElementById('categoriesBar'),
    catalogTitle: document.getElementById('catalogTitle'),
    productCountBadge: document.getElementById('productCountBadge'),
    productsGrid: document.getElementById('productsGrid'),
    emptyCatalog: document.getElementById('emptyCatalog'),
    resetFiltersBtn: document.getElementById('resetFiltersBtn'),
    cartBadge: document.getElementById('cartBadge'),
    stickyCheckoutBar: document.getElementById('stickyCheckoutBar'),
    stickyTotalAmount: document.getElementById('stickyTotalAmount'),
    stickyCheckoutBtn: document.getElementById('stickyCheckoutBtn'),
    modalOverlay: document.getElementById('modalOverlay'),

    // Modals
    productModal: document.getElementById('productModal'),
    modalCategory: document.getElementById('modalCategory'),
    modalStockBadge: document.getElementById('modalStockBadge'),
    modalRatingBadge: document.getElementById('modalRatingBadge'),
    modalTitle: document.getElementById('modalTitle'),
    modalPrice: document.getElementById('modalPrice'),
    modalDescription: document.getElementById('modalDescription'),
    modalQtyRow: document.getElementById('modalQtyRow'),
    modalQtyMinus: document.getElementById('modalQtyMinus'),
    modalQtyPlus: document.getElementById('modalQtyPlus'),
    modalQtyValue: document.getElementById('modalQtyValue'),
    modalQtySubtotal: document.getElementById('modalQtySubtotal'),
    modalOutOfStockBox: document.getElementById('modalOutOfStockBox'),
    modalStockAlertBtn: document.getElementById('modalStockAlertBtn'),
    modalLogoPreview: document.getElementById('modalLogoPreview'),
    modalLogoImg: document.getElementById('modalLogoImg'),
    modalActionFooter: document.getElementById('modalActionFooter'),
    modalAddToCartBtn: document.getElementById('modalAddToCartBtn'),
    modalBuyNowBtn: document.getElementById('modalBuyNowBtn'),
    closeProductModal: document.getElementById('closeProductModal'),

    cartModal: document.getElementById('cartModal'),
    cartModalItemCount: document.getElementById('cartModalItemCount'),
    cartItemsList: document.getElementById('cartItemsList'),
    emptyCartView: document.getElementById('emptyCartView'),
    cartSummaryCard: document.getElementById('cartSummaryCard'),
    couponInput: document.getElementById('couponInput'),
    applyCouponBtn: document.getElementById('applyCouponBtn'),
    couponStatusMsg: document.getElementById('couponStatusMsg'),
    cartSubtotalAmount: document.getElementById('cartSubtotalAmount'),
    cartDiscountRow: document.getElementById('cartDiscountRow'),
    cartDiscountLabel: document.getElementById('cartDiscountLabel'),
    cartDiscountAmount: document.getElementById('cartDiscountAmount'),
    cartFinalAmount: document.getElementById('cartFinalAmount'),
    btnCheckoutTotal: document.getElementById('btnCheckoutTotal'),
    clearCartBtn: document.getElementById('clearCartBtn'),
    continueShoppingBtn: document.getElementById('continueShoppingBtn'),
    closeCartModal: document.getElementById('closeCartModal'),
    executeCheckoutBtn: document.getElementById('executeCheckoutBtn'),
    cryptoMethodOption: document.getElementById('cryptoMethodOption'),
    balanceMethodOption: document.getElementById('balanceMethodOption'),
    methodBalanceSub: document.getElementById('methodBalanceSub'),

    paymentModal: document.getElementById('paymentModal'),
    payModalOrderId: document.getElementById('payModalOrderId'),
    payModalAmount: document.getElementById('payModalAmount'),
    payInvoiceLink: document.getElementById('payInvoiceLink'),
    trackerStatusTitle: document.getElementById('trackerStatusTitle'),
    trackerStatusSubtitle: document.getElementById('trackerStatusSubtitle'),
    checkPaymentStatusBtn: document.getElementById('checkPaymentStatusBtn'),
    cancelOrderBtn: document.getElementById('cancelOrderBtn'),
    closePaymentModal: document.getElementById('closePaymentModal'),

    vaultModal: document.getElementById('vaultModal'),
    vaultCredentialsContent: document.getElementById('vaultCredentialsContent'),
    copyAllCredentialsBtn: document.getElementById('copyAllCredentialsBtn'),
    vaultDoneBtn: document.getElementById('vaultDoneBtn'),
    closeVaultModal: document.getElementById('closeVaultModal'),

    ordersModal: document.getElementById('ordersModal'),
    ordersList: document.getElementById('ordersList'),
    emptyOrdersView: document.getElementById('emptyOrdersView'),
    closeOrdersModal: document.getElementById('closeOrdersModal'),

    profileModal: document.getElementById('profileModal'),
    profAvatar: document.getElementById('profAvatar'),
    profName: document.getElementById('profName'),
    profUsername: document.getElementById('profUsername'),
    profId: document.getElementById('profId'),
    profBalance: document.getElementById('profBalance'),
    topupActionCard: document.getElementById('topupActionCard'),
    referralActionCard: document.getElementById('referralActionCard'),
    referralSubText: document.getElementById('referralSubText'),
    copyRefLinkBtn: document.getElementById('copyRefLinkBtn'),
    supportActionCard: document.getElementById('supportActionCard'),
    closeProfileModal: document.getElementById('closeProfileModal'),

    // Navigation Dock & Search
    dockCatalogBtn: document.getElementById('dockCatalogBtn'),
    dockProductsBtn: document.getElementById('dockProductsBtn'),
    dockOrdersBtn: document.getElementById('dockOrdersBtn'),
    dockCartBtn: document.getElementById('dockCartBtn'),
    dockProfileBtn: document.getElementById('dockProfileBtn'),
    dockSearchBtn: document.getElementById('dockSearchBtn'),
    searchSection: document.getElementById('searchSection'),

    // Dev preview
    devPreviewBar: document.getElementById('devPreviewBar'),
    devUserIdInput: document.getElementById('devUserIdInput'),
    devSwitchUserBtn: document.getElementById('devSwitchUserBtn'),
    toastContainer: document.getElementById('toastContainer'),
  };

  // --- API Request Wrapper ---
  async function api(endpoint, options = {}) {
    const url = `/api/webapp${endpoint}`;
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (state.token) {
      headers['Authorization'] = `Bearer ${state.token}`;
    }
    if (state.initData) {
      headers['X-Telegram-Init-Data'] = state.initData;
    }
    if (state.telegramId) {
      headers['X-Dev-Telegram-Id'] = String(state.telegramId);
    }

    try {
      const response = await fetch(url, { ...options, headers });
      const data = await response.json();
      if (!response.ok) {
        if (response.status === 401 && state.token) {
          // Token expired or invalid, clear cached token
          state.token = null;
          try {
            sessionStorage.removeItem('cloud_deals_jwt');
          } catch (e) {}
        }
        throw new Error(data.detail || data.message || 'Request failed');
      }
      return data;
    } catch (err) {
      console.error(`API [${endpoint}] Error:`, err);
      throw err;
    }
  }

  // --- Toast Notification ---
  function showToast(message, type = 'normal') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${message}</span>`;
    el.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(-10px)';
      toast.style.transition = 'all 0.25s ease';
      setTimeout(() => toast.remove(), 260);
    }, 2800);
  }

  // --- Modal & Drawer Management ---
  function openModal(modalEl) {
    if (state.activeModal) {
      state.activeModal.classList.add('hidden');
    }
    modalEl.classList.remove('hidden');
    el.modalOverlay.classList.remove('hidden');
    state.activeModal = modalEl;
    document.body.style.overflow = 'hidden';

    // Telegram Back Button Hook
    if (tg?.BackButton) {
      tg.BackButton.show();
      tg.BackButton.onClick(handleTgBackClick);
    }
    haptic('medium');
  }

  function closeModal() {
    if (state.activeModal) {
      state.activeModal.classList.add('hidden');
      state.activeModal = null;
    }
    el.modalOverlay.classList.add('hidden');
    document.body.style.overflow = '';

    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }

    if (tg?.BackButton) {
      tg.BackButton.hide();
      tg.BackButton.offClick(handleTgBackClick);
    }
    haptic('light');
  }

  function handleTgBackClick() {
    closeModal();
  }

  // Overlay click closes current open modal
  el.modalOverlay.addEventListener('click', closeModal);
  el.closeProductModal.addEventListener('click', closeModal);
  el.closeCartModal.addEventListener('click', closeModal);
  el.closePaymentModal.addEventListener('click', closeModal);
  el.closeVaultModal.addEventListener('click', closeModal);
  el.closeOrdersModal.addEventListener('click', closeModal);
  el.closeProfileModal.addEventListener('click', closeModal);

  // --- Bootstrap & Authentication ---
  async function initAuth() {
    try {
      const authData = await api('/auth', {
        method: 'POST',
        body: JSON.stringify({
          init_data: state.initData || undefined,
          dev_telegram_id: state.telegramId || undefined,
          token: state.token || undefined,
        }),
      });

      if (authData.token) {
        state.token = authData.token;
        try {
          sessionStorage.setItem('cloud_deals_jwt', authData.token);
        } catch (e) {}
      }

      state.user = authData.user;
      state.store = authData.store;
      state.telegramId = authData.user.telegram_id;

      renderUserProfile();
      renderPromotions();
      await fetchCatalog();
      await fetchCart();

      // Show dev preview bar if not running inside Telegram WebApp
      if (!state.initData && el.devPreviewBar) {
        el.devPreviewBar.classList.remove('hidden');
        el.devUserIdInput.value = state.telegramId;
      }
    } catch (err) {
      showToast('Connection error: ' + err.message, 'error');
    }
  }

  // --- User Profile Rendering ---
  function renderUserProfile() {
    if (!state.user) return;
    const u = state.user;
    const displayName = u.first_name || u.username || 'Customer';
    const initials = (u.first_name?.[0] || u.username?.[0] || 'C').toUpperCase();

    el.userName.textContent = displayName;
    el.userAvatar.textContent = initials;
    el.userBalance.textContent = `$${parseFloat(u.balance || 0).toFixed(2)}`;

    // Profile drawer
    el.profAvatar.textContent = initials;
    el.profName.textContent = displayName;
    el.profUsername.textContent = u.username ? `@${u.username}` : 'No username';
    el.profId.textContent = `Telegram ID: ${u.telegram_id}`;
    el.profBalance.textContent = `$${parseFloat(u.balance || 0).toFixed(2)}`;
    el.methodBalanceSub.textContent = `Available: $${parseFloat(u.balance || 0).toFixed(2)}`;

    // Referral stats in profile
    if (el.referralSubText) {
      const count = u.referral_count || 0;
      const earned = parseFloat(u.referral_earnings || 0).toFixed(2);
      const rate = u.referral_commission_percent ? `${u.referral_commission_percent}%` : '5%';
      el.referralSubText.textContent = `${count} invited • $${earned} earned (${rate} per order)`;
    }
  }

  // --- Promo Banner Rendering ---
  function renderPromotions() {
    if (!state.user) return;
    const u = state.user;

    if (!u.channel_discount_claimed && !u.channel_discount_used) {
      el.promoBanner.classList.remove('hidden');
      el.discountActiveCard.classList.add('hidden');
    } else if (u.channel_discount_claimed && !u.channel_discount_used) {
      el.promoBanner.classList.add('hidden');
      el.discountActiveCard.classList.remove('hidden');
    } else {
      el.promoBanner.classList.add('hidden');
      el.discountActiveCard.classList.add('hidden');
    }
  }

  // Claim discount button
  el.claimDiscountBtn.addEventListener('click', async () => {
    haptic('medium');
    try {
      const res = await api('/discount/claim', {
        method: 'POST',
        body: JSON.stringify({
          init_data: state.initData || undefined,
          telegram_id: state.telegramId || undefined,
        }),
      });

      if (res.claimed) {
        state.user.channel_discount_claimed = true;
        renderPromotions();
        await fetchCart();
        showToast('🎉 10% First-Order Discount activated!', 'success');
        haptic('success');
      } else {
        showToast(res.message, 'normal');
      }
    } catch (err) {
      showToast(err.message, 'error');
      haptic('error');
    }
  });

  // --- Catalog & Products Rendering ---
  async function fetchCatalog() {
    try {
      const data = await api('/catalog');
      state.categories = data.categories || [];
      state.products = data.products || [];
      renderCategories();
      renderProducts();
    } catch (err) {
      showToast('Failed to load products: ' + err.message, 'error');
    }
  }

  function renderCategories() {
    // Keep "All Products" and append categories
    el.categoriesBar.innerHTML = `
      <button class="cat-pill ${state.activeCategory === 'all' ? 'active' : ''}" data-category-id="all">
        <span class="cat-icon">⚡</span>
        <span class="cat-label">All</span>
      </button>
    `;

    state.categories.forEach((cat) => {
      const pill = document.createElement('button');
      pill.className = `cat-pill ${state.activeCategory === String(cat.id) ? 'active' : ''}`;
      pill.dataset.categoryId = String(cat.id);
      pill.innerHTML = `
        <span class="cat-icon">${cat.icon || '📦'}</span>
        <span class="cat-label">${cat.name}</span>
      `;
      el.categoriesBar.appendChild(pill);
    });

    // Category click handler
    el.categoriesBar.querySelectorAll('.cat-pill').forEach((btn) => {
      btn.addEventListener('click', () => {
        haptic('light');
        el.categoriesBar.querySelectorAll('.cat-pill').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        state.activeCategory = btn.dataset.categoryId;
        renderProducts();
      });
    });
  }

  // --- Cloud Provider Logo Resolver ---
  function resolveCloudLogo(prod) {
    if (!prod) return '/webapp/logos/vps.svg';

    // 1. Explicit image_url
    if (prod.image_url && typeof prod.image_url === 'string') {
      const url = prod.image_url.trim();
      if (url.startsWith('/') || url.startsWith('http://') || url.startsWith('https://')) {
        return url;
      }
    }

    // 2. Keyword fallback matching
    const name = (prod.name || '').toLowerCase();
    const cat = (prod.category_name || '').toLowerCase();
    const haystack = `${name} ${cat}`;

    if (haystack.includes('oracle') || haystack.includes('oci')) {
      return '/webapp/logos/oracle.png';
    }
    if (haystack.includes('aws') || haystack.includes('amazon')) {
      return '/webapp/logos/aws.png';
    }
    if (haystack.includes('digitalocean') || haystack.includes('digital ocean') || haystack.includes('do ')) {
      return '/webapp/logos/digitalocean.png';
    }
    if (haystack.includes('google') || haystack.includes('gcp')) {
      return '/webapp/logos/gcp.png';
    }
    if (haystack.includes('upcloud')) {
      return '/webapp/logos/upcloud.png';
    }
    if (haystack.includes('azure') || haystack.includes('microsoft')) {
      return '/webapp/logos/azure.svg';
    }

    return '/webapp/logos/vps.svg';
  }

  // --- Smart Search Matcher (Alias & Fuzzy Aware) ---
  function matchesSearch(product, rawQuery) {
    if (!rawQuery) return true;
    const q = rawQuery.trim().toLowerCase();
    if (!q) return true;

    const name = (product.name || '').toLowerCase();
    const desc = (product.description || '').toLowerCase();
    const cat = (product.category_name || '').toLowerCase();
    const combined = `${name} ${desc} ${cat}`;

    // 1. Direct substring match
    if (combined.includes(q)) return true;

    // 2. Compact comparison without whitespace / hyphens (e.g. 'digital ocean' <-> 'digitalocean')
    const qCompact = q.replace(/[\s\-_]+/g, '');
    const combinedCompact = combined.replace(/[\s\-_]+/g, '');
    if (combinedCompact.includes(qCompact)) return true;

    // 3. Cloud Provider Aliases
    const aliasGroups = [
      ['digitalocean', 'digital ocean', 'do', 'droplet'],
      ['aws', 'amazon', 'amazon web services', 'ec2'],
      ['gcp', 'google', 'google cloud', 'google cloud platform'],
      ['oracle', 'oci', 'oracle cloud'],
      ['upcloud', 'up cloud'],
      ['azure', 'microsoft azure', 'msft'],
    ];

    for (const group of aliasGroups) {
      const queryMatchesGroup = group.some((alias) => q.includes(alias) || alias.includes(q));
      if (queryMatchesGroup) {
        const itemMatchesGroup = group.some((alias) => combined.includes(alias) || combinedCompact.includes(alias.replace(/\s+/g, '')));
        if (itemMatchesGroup) return true;
      }
    }

    // 4. Multi-word match (all typed words match product data)
    const terms = q.split(/\s+/).filter(Boolean);
    if (terms.length > 1 && terms.every((t) => combined.includes(t) || combinedCompact.includes(t))) {
      return true;
    }

    return false;
  }

  function renderProducts() {
    let list = state.products;
    const query = state.searchQuery.trim();

    // When searching, search across the entire catalog
    if (query) {
      list = list.filter((p) => matchesSearch(p, query));
      if (el.catalogTitle) {
        el.catalogTitle.textContent = `Search results for "${query}"`;
      }
      if (el.productCountBadge) {
        el.productCountBadge.textContent = `${list.length} found`;
      }
    } else {
      // Filter by Category when not searching
      if (state.activeCategory !== 'all') {
        list = list.filter((p) => String(p.category_id) === state.activeCategory);
      }
      if (el.catalogTitle) {
        el.catalogTitle.textContent = 'Your recent activity';
      }
      if (el.productCountBadge) {
        el.productCountBadge.textContent = `${list.length} available`;
      }
    }

    el.productsGrid.innerHTML = '';

    if (list.length === 0) {
      el.emptyCatalog.classList.remove('hidden');
      return;
    }
    el.emptyCatalog.classList.add('hidden');

    list.forEach((p) => {
      const card = document.createElement('div');
      card.className = 'apple-product-card';
      card.dataset.productId = p.id;

      const logoSrc = resolveCloudLogo(p);
      const isOutOfStock = p.stock === 0;

      // Apple Tag (e.g., "Saved for you ›", "Instant Stock ›", "Low Stock ›")
      let tagText = 'Saved for you';
      let tagIcon = '🔖';
      if (p.stock > 0 && p.stock <= 2) {
        tagText = 'Low Stock';
        tagIcon = '⚡';
      } else if (p.stock > 0) {
        tagText = 'Instant Stock';
        tagIcon = '⚡';
      } else {
        tagText = 'Restock Soon';
        tagIcon = '⏳';
      }

      card.innerHTML = `
        <div class="card-top-tag">
          <span class="tag-icon">${tagIcon}</span>
          <span>${tagText}</span>
          <span class="tag-chevron">›</span>
        </div>
        <div class="card-logo-container">
          <img src="${logoSrc}" alt="${escapeHtml(p.name)}" class="card-cloud-logo" loading="lazy">
        </div>
        <div class="card-bottom-info">
          <h3 class="card-item-title" title="${escapeHtml(p.name)}">${escapeHtml(p.name)}</h3>
          <div class="card-meta-line">
            <span class="card-price-text">$${parseFloat(p.price).toFixed(2)}</span>
            <div class="card-stock-dot-wrap">
              <span class="stock-indicator-dot ${isOutOfStock ? 'out' : ''}"></span>
              <span>${isOutOfStock ? 'Sold out' : `${p.stock} left`}</span>
            </div>
          </div>
        </div>
      `;

      // Card tap opens Apple Product Sheet
      card.addEventListener('click', () => {
        openProductSheet(p);
      });

      el.productsGrid.appendChild(card);
    });
  }

  // --- Product Sheet Modal ---
  function openProductSheet(prod) {
    state.selectedProduct = prod;
    state.modalQuantity = 1;

    // Centered Floating Logo
    if (el.modalLogoImg) {
      el.modalLogoImg.src = resolveCloudLogo(prod);
      el.modalLogoImg.alt = prod.name;
    }

    el.modalCategory.textContent = `${prod.category_icon || '📦'} ${prod.category_name}`;
    el.modalTitle.textContent = prod.name;
    el.modalPrice.textContent = `$${parseFloat(prod.price).toFixed(2)}`;
    el.modalDescription.textContent = prod.description || 'Verified working digital accounts delivered instantly upon payment.';

    // Rating Badge
    if (el.modalRatingBadge) {
      if (prod.review_count && prod.review_count > 0) {
        el.modalRatingBadge.textContent = `⭐ ${parseFloat(prod.average_rating || 5.0).toFixed(1)} (${prod.review_count})`;
        el.modalRatingBadge.classList.remove('hidden');
      } else {
        el.modalRatingBadge.textContent = `⭐ 5.0`;
        el.modalRatingBadge.classList.remove('hidden');
      }
    }

    // Stock Badge & Out of Stock Alert Box
    let stockText = `${prod.stock} in stock`;
    if (prod.stock === 0) {
      stockText = 'Out of Stock';
      el.modalStockBadge.className = 'apple-badge-stock stock-out';
      el.modalOutOfStockBox?.classList.remove('hidden');
      el.modalQtyRow?.classList.add('hidden');
      el.modalActionFooter?.classList.add('hidden');
      if (el.modalStockAlertBtn) {
        el.modalStockAlertBtn.disabled = false;
        el.modalStockAlertBtn.textContent = '🔔 Notify When Back in Stock';
      }
    } else {
      stockText = 'In Stock';
      el.modalStockBadge.className = 'apple-badge-stock';
      el.modalOutOfStockBox?.classList.add('hidden');
      el.modalQtyRow?.classList.remove('hidden');
      el.modalActionFooter?.classList.remove('hidden');
      el.modalAddToCartBtn.disabled = false;
      el.modalBuyNowBtn.disabled = false;
    }
    el.modalStockBadge.textContent = stockText;

    updateModalQuantityDisplay();
    openModal(el.productModal);
  }

  function updateModalQuantityDisplay() {
    if (!state.selectedProduct) return;
    el.modalQtyValue.textContent = state.modalQuantity;
    const total = parseFloat(state.selectedProduct.price) * state.modalQuantity;
    el.modalQtySubtotal.textContent = `Total: $${total.toFixed(2)}`;
  }

  el.modalQtyMinus.addEventListener('click', () => {
    if (state.modalQuantity > 1) {
      state.modalQuantity--;
      haptic('light');
      updateModalQuantityDisplay();
    }
  });

  el.modalQtyPlus.addEventListener('click', () => {
    if (!state.selectedProduct) return;
    if (state.modalQuantity < state.selectedProduct.stock) {
      state.modalQuantity++;
      haptic('light');
      updateModalQuantityDisplay();
    } else {
      showToast(`Only ${state.selectedProduct.stock} available in stock`, 'normal');
    }
  });

  // Restock notification alert click
  if (el.modalStockAlertBtn) {
    el.modalStockAlertBtn.addEventListener('click', async () => {
      if (!state.selectedProduct) return;
      haptic('medium');
      el.modalStockAlertBtn.disabled = true;
      el.modalStockAlertBtn.textContent = 'Setting alert...';
      try {
        const res = await api('/stock-alert', {
          method: 'POST',
          body: JSON.stringify({
            product_id: state.selectedProduct.id,
            init_data: state.initData || undefined,
            telegram_id: state.telegramId || undefined,
          }),
        });
        el.modalStockAlertBtn.textContent = '🔔 Notification Active!';
        showToast(res.message || 'Alert set! You will be notified in Telegram upon restock.', 'success');
        haptic('success');
      } catch (err) {
        el.modalStockAlertBtn.disabled = false;
        el.modalStockAlertBtn.textContent = '🔔 Notify When Back in Stock';
        showToast(err.message, 'error');
        haptic('error');
      }
    });
  }

  el.modalAddToCartBtn.addEventListener('click', async () => {
    if (!state.selectedProduct) return;
    await quickAddToCart(state.selectedProduct.id, state.modalQuantity);
    closeModal();
  });

  el.modalBuyNowBtn.addEventListener('click', async () => {
    if (!state.selectedProduct) return;
    await quickAddToCart(state.selectedProduct.id, state.modalQuantity);
    closeModal();
    openCartSheet();
  });

  // --- Shopping Cart Operations ---
  async function quickAddToCart(productId, quantity = 1) {
    haptic('medium');
    try {
      const res = await api('/cart/add', {
        method: 'POST',
        body: JSON.stringify({
          product_id: productId,
          quantity: quantity,
          init_data: state.initData || undefined,
          telegram_id: state.telegramId || undefined,
        }),
      });

      showToast(`Added ${quantity > 1 ? quantity + ' items' : 'item'} to cart 🛒`, 'success');
      haptic('success');
      await fetchCart();
    } catch (err) {
      showToast(err.message, 'error');
      haptic('error');
    }
  }

  async function fetchCart() {
    try {
      const cartData = await api('/cart');
      state.cart = cartData;
      renderCartUI();
    } catch (err) {
      console.warn('Cart load error:', err);
    }
  }

  function renderCartUI() {
    const c = state.cart;
    const count = c.total_items || 0;

    // Badges & Floating Dock
    if (count > 0) {
      el.cartBadge.textContent = count;
      el.cartBadge.classList.remove('hidden');
      el.stickyCheckoutBar.classList.remove('hidden');
      el.stickyTotalAmount.textContent = `$${parseFloat(c.final_amount || 0).toFixed(2)}`;
    } else {
      el.cartBadge.classList.add('hidden');
      el.stickyCheckoutBar.classList.add('hidden');
    }

    // Modal List
    el.cartModalItemCount.textContent = `${count} item${count === 1 ? '' : 's'}`;
    el.cartItemsList.innerHTML = '';

    if (!c.items || c.items.length === 0) {
      el.cartItemsList.classList.add('hidden');
      el.cartSummaryCard.classList.add('hidden');
      el.emptyCartView.classList.remove('hidden');
      el.executeCheckoutBtn.disabled = true;
      return;
    }

    el.emptyCartView.classList.add('hidden');
    el.cartItemsList.classList.remove('hidden');
    el.cartSummaryCard.classList.remove('hidden');
    el.executeCheckoutBtn.disabled = false;

    c.items.forEach((item) => {
      const row = document.createElement('div');
      row.className = 'cart-item-row';

      // Find product to resolve its logo
      const prod = state.products.find((p) => p.id === item.product_id);
      const logoSrc = resolveCloudLogo(prod);

      row.innerHTML = `
        <div class="cart-item-thumb-box">
          <img src="${logoSrc}" alt="" class="cart-item-thumb">
        </div>
        <div class="item-left">
          <span class="item-title">${escapeHtml(item.product_name)}</span>
          <span class="item-sub">$${parseFloat(item.unit_price).toFixed(2)} each</span>
        </div>
        <div class="item-right">
          <div class="apple-stepper">
            <button class="step-btn btn-cart-dec" data-id="${item.product_id}" data-qty="${item.quantity - 1}">&minus;</button>
            <span class="step-count">${item.quantity}</span>
            <button class="step-btn btn-cart-inc" data-id="${item.product_id}" data-qty="${item.quantity + 1}">&plus;</button>
          </div>
          <span class="item-price">$${parseFloat(item.subtotal).toFixed(2)}</span>
          <button class="btn-remove-item" data-remove-id="${item.product_id}" title="Remove">&times;</button>
        </div>
      `;

      // Stepper clicks
      row.querySelector('.btn-cart-dec').addEventListener('click', () => updateCartQty(item.product_id, item.quantity - 1));
      row.querySelector('.btn-cart-inc').addEventListener('click', () => updateCartQty(item.product_id, item.quantity + 1));
      row.querySelector('.btn-remove-item').addEventListener('click', () => removeCartItem(item.product_id));

      el.cartItemsList.appendChild(row);
    });

    // Summary Card
    el.cartSubtotalAmount.textContent = `$${parseFloat(c.subtotal).toFixed(2)}`;
    let channelDiscount = parseFloat(c.discount_amount || 0);
    let couponDiscount = state.appliedCoupon ? parseFloat(state.appliedCoupon.discount_amount || 0) : 0;
    let totalDiscount = channelDiscount + couponDiscount;

    if (totalDiscount > 0) {
      el.cartDiscountRow.classList.remove('hidden');
      if (state.appliedCoupon && channelDiscount > 0) {
        el.cartDiscountLabel.textContent = `🎟️ Promo (${state.appliedCoupon.code}) + 🎁 10% Off`;
      } else if (state.appliedCoupon) {
        el.cartDiscountLabel.textContent = `🎟️ Promo Code (${state.appliedCoupon.code})`;
      } else {
        el.cartDiscountLabel.textContent = `🎁 10% First Order Discount`;
      }
      el.cartDiscountAmount.textContent = `-$${totalDiscount.toFixed(2)}`;
    } else {
      el.cartDiscountRow.classList.add('hidden');
    }

    const finalAmount = Math.max(0, parseFloat(c.subtotal || 0) - totalDiscount);
    el.cartFinalAmount.textContent = `$${finalAmount.toFixed(2)}`;
    el.btnCheckoutTotal.textContent = `$${finalAmount.toFixed(2)}`;
  }

  // --- Promo Code / Coupon Application ---
  if (el.applyCouponBtn) {
    el.applyCouponBtn.addEventListener('click', async () => {
      const code = (el.couponInput?.value || '').trim();
      if (!code) {
        showToast('Please enter a coupon code', 'normal');
        return;
      }
      haptic('medium');
      el.applyCouponBtn.disabled = true;
      el.applyCouponBtn.textContent = '...';
      try {
        const res = await api('/coupon/validate', {
          method: 'POST',
          body: JSON.stringify({
            code: code,
            cart_subtotal: state.cart.subtotal,
            init_data: state.initData || undefined,
            telegram_id: state.telegramId || undefined,
          }),
        });

        if (res.valid) {
          state.appliedCoupon = res;
          el.couponStatusMsg.className = 'coupon-status-msg success';
          const valStr = res.discount_type === 'PERCENTAGE' ? `${res.discount_value}%` : `$${res.discount_value}`;
          el.couponStatusMsg.textContent = `🎉 Promo ${res.code} applied! (${valStr} off: -$${parseFloat(res.discount_amount).toFixed(2)})`;
          el.couponStatusMsg.classList.remove('hidden');
          renderCartUI();
          showToast(`Coupon ${res.code} applied!`, 'success');
          haptic('success');
        } else {
          state.appliedCoupon = null;
          el.couponStatusMsg.className = 'coupon-status-msg error';
          el.couponStatusMsg.textContent = res.message || 'Invalid coupon code';
          el.couponStatusMsg.classList.remove('hidden');
          renderCartUI();
          haptic('error');
        }
      } catch (err) {
        state.appliedCoupon = null;
        el.couponStatusMsg.className = 'coupon-status-msg error';
        el.couponStatusMsg.textContent = err.message;
        el.couponStatusMsg.classList.remove('hidden');
        renderCartUI();
        haptic('error');
      } finally {
        el.applyCouponBtn.disabled = false;
        el.applyCouponBtn.textContent = 'Apply';
      }
    });
  }

  async function updateCartQty(productId, newQty) {
    haptic('light');
    try {
      await api('/cart/update', {
        method: 'POST',
        body: JSON.stringify({
          product_id: productId,
          quantity: newQty,
          init_data: state.initData || undefined,
          telegram_id: state.telegramId || undefined,
        }),
      });
      await fetchCart();
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function removeCartItem(productId) {
    haptic('light');
    try {
      await api('/cart/remove', {
        method: 'POST',
        body: JSON.stringify({
          product_id: productId,
          init_data: state.initData || undefined,
          telegram_id: state.telegramId || undefined,
        }),
      });
      showToast('Item removed', 'normal');
      await fetchCart();
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  el.clearCartBtn.addEventListener('click', async () => {
    haptic('medium');
    try {
      await api('/cart/clear', {
        method: 'POST',
        body: JSON.stringify({
          init_data: state.initData || undefined,
          telegram_id: state.telegramId || undefined,
        }),
      });
      state.appliedCoupon = null;
      if (el.couponInput) el.couponInput.value = '';
      if (el.couponStatusMsg) el.couponStatusMsg.classList.add('hidden');
      showToast('Cart cleared', 'normal');
      await fetchCart();
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  function openCartSheet() {
    renderCartUI();
    openModal(el.cartModal);
  }

  el.stickyCheckoutBtn.addEventListener('click', openCartSheet);
  el.continueShoppingBtn.addEventListener('click', closeModal);

  // Payment Method Selection in Cart
  function selectPaymentMethod(activeOption) {
    [el.cryptoMethodOption, el.balanceMethodOption].forEach((opt) => {
      if (opt) {
        const isMatch = (opt === activeOption);
        opt.classList.toggle('active', isMatch);
        const radio = opt.querySelector('input');
        if (radio) radio.checked = isMatch;
      }
    });
    haptic('selection');
  }

  if (el.cryptoMethodOption) {
    el.cryptoMethodOption.addEventListener('click', () => selectPaymentMethod(el.cryptoMethodOption));
  }
  if (el.balanceMethodOption) {
    el.balanceMethodOption.addEventListener('click', () => selectPaymentMethod(el.balanceMethodOption));
  }

  // --- Checkout Execution ---
  el.executeCheckoutBtn.addEventListener('click', async () => {
    haptic('heavy');
    const selectedMethod = document.querySelector('input[name="payment_method"]:checked')?.value || 'crypto';

    el.executeCheckoutBtn.disabled = true;
    el.executeCheckoutBtn.textContent = 'Processing...';

    try {
      const res = await api('/checkout', {
        method: 'POST',
        body: JSON.stringify({
          payment_method: selectedMethod,
          coupon_code: state.appliedCoupon ? state.appliedCoupon.code : undefined,
          init_data: state.initData || undefined,
          telegram_id: state.telegramId || undefined,
        }),
      });

      closeModal();
      state.appliedCoupon = null;
      if (el.couponInput) el.couponInput.value = '';
      if (el.couponStatusMsg) el.couponStatusMsg.classList.add('hidden');
      await fetchCart();

      // OPTION A: STORE BALANCE (Instant Fulfillment)
      if (res.payment_method === 'balance' && res.status === 'fulfilled') {
        openVaultModal(res.credentials, res.public_order_id);
        haptic('success');
        if (state.user) {
          state.user.balance = (parseFloat(state.user.balance) - parseFloat(res.amount)).toFixed(2);
          renderUserProfile();
        }
        return;
      }

      // OPTION B: BINANCE PAY CHECKOUT
      openCryptoPaymentModal(res);

    } catch (err) {
      showToast(err.message, 'error');
      haptic('error');
    } finally {
      el.executeCheckoutBtn.disabled = false;
      el.executeCheckoutBtn.innerHTML = `Proceed to Payment • <span id="btnCheckoutTotal">$${parseFloat(state.cart.final_amount || 0).toFixed(2)}</span>`;
    }
  });

  // --- Crypto Payment Modal & Live Polling ---
  function openCryptoPaymentModal(orderData) {
    state.currentPaymentOrder = orderData;
    el.payModalOrderId.textContent = `Order #${orderData.public_order_id}`;
    el.payModalAmount.textContent = `$${parseFloat(orderData.amount).toFixed(2)}`;

    if (orderData.payment_url) {
      el.payInvoiceLink.href = orderData.payment_url;
      el.payInvoiceLink.classList.remove('hidden');
    } else {
      el.payInvoiceLink.classList.add('hidden');
    }

    el.trackerStatusTitle.textContent = 'Awaiting Confirmation';
    el.trackerStatusSubtitle = 'Monitoring the blockchain for incoming transaction...';

    openModal(el.paymentModal);

    // Auto-poll status every 6 seconds
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = setInterval(pollOrderStatus, 6000);
  }

  async function pollOrderStatus() {
    if (!state.currentPaymentOrder) return;
    try {
      const order = await api(`/orders/${state.currentPaymentOrder.order_id}`);
      if (order.status === 'fulfilled' || order.status === 'paid') {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        closeModal();
        openVaultModal(order.delivered_credentials, order.public_order_id);
        haptic('success');
      } else if (order.status === 'cancelled' || order.status === 'expired') {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        showToast('Order was cancelled or expired.', 'error');
        closeModal();
      }
    } catch (err) {
      console.warn('Poll status error:', err);
    }
  }

  el.checkPaymentStatusBtn.addEventListener('click', async () => {
    haptic('medium');
    el.checkPaymentStatusBtn.textContent = 'Checking...';
    await pollOrderStatus();
    el.checkPaymentStatusBtn.textContent = '🔄 Check Status Now';
  });

  el.cancelOrderBtn.addEventListener('click', async () => {
    if (!state.currentPaymentOrder) return;
    haptic('medium');
    try {
      await api(`/orders/${state.currentPaymentOrder.order_id}/cancel`, {
        method: 'POST',
        body: JSON.stringify({
          init_data: state.initData || undefined,
          telegram_id: state.telegramId || undefined,
        }),
      });
      showToast('Order cancelled and reserved stock restored.', 'normal');
      closeModal();
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  // --- Digital Credentials Vault Modal ---
  function openVaultModal(credentialsList, orderId) {
    el.vaultCredentialsContent.innerHTML = '';
    const allText = (credentialsList || []).join('\n\n');

    if (!credentialsList || credentialsList.length === 0) {
      el.vaultCredentialsContent.innerHTML = '<p style="color: var(--text-muted); font-size: 0.82rem;">Your credentials have been dispatched. Check My Orders or your Telegram bot DM.</p>';
    } else {
      credentialsList.forEach((cred, index) => {
        const field = document.createElement('div');
        field.className = 'credential-field';
        field.innerHTML = `
          <span class="credential-value">${escapeHtml(cred)}</span>
          <button class="btn-field-copy" title="Copy">📋</button>
        `;

        field.querySelector('.btn-field-copy').addEventListener('click', () => {
          copyToClipboard(cred, 'Credential copied!');
        });

        el.vaultCredentialsContent.appendChild(field);
      });
    }

    el.copyAllCredentialsBtn.onclick = () => {
      copyToClipboard(allText, 'All credentials copied to clipboard! 📋');
    };

    openModal(el.vaultModal);
  }

  el.vaultDoneBtn.addEventListener('click', closeModal);

  // --- Order History Drawer ---
  async function openOrdersDrawer() {
    haptic('light');
    try {
      const data = await api('/orders');
      const orders = data.orders || [];

      el.ordersList.innerHTML = '';
      if (orders.length === 0) {
        el.emptyOrdersView.classList.remove('hidden');
      } else {
        el.emptyOrdersView.classList.add('hidden');
        orders.forEach((o) => {
          const card = document.createElement('div');
          card.className = 'order-card';

          const dateStr = new Date(o.created_at).toLocaleDateString(undefined, {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          });

          let credPreview = '';
          if (o.status === 'fulfilled' && o.delivered_items && o.delivered_items.length > 0) {
            credPreview = `
              <div class="order-credentials-preview">
                <strong>🔑 Credentials:</strong><br>
                ${escapeHtml(o.delivered_items.join('\n'))}
              </div>
            `;
          }

          card.innerHTML = `
            <div class="order-top">
              <span class="order-id">#${o.public_order_id}</span>
              <span class="order-status-badge status-${o.status}">${o.status.replace('_', ' ')}</span>
            </div>
            <div class="order-details-text">
              ${o.product_name} • <strong>$${parseFloat(o.amount).toFixed(2)}</strong> • ${dateStr}
            </div>
            ${credPreview}
          `;

          el.ordersList.appendChild(card);
        });
      }

      openModal(el.ordersModal);
    } catch (err) {
      showToast('Failed to load orders: ' + err.message, 'error');
    }
  }

  // --- Profile Drawer ---
  function openProfileDrawer() {
    haptic('light');
    renderUserProfile();
    openModal(el.profileModal);
  }

  el.userChipBtn.addEventListener('click', openProfileDrawer);

  el.copyRefLinkBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (!state.user) return;
    const botUser = state.store?.support_username || 'CloudDealsBot';
    const rawCode = state.user.referral_code || state.user.telegram_id;
    const code = String(rawCode).startsWith('ref_') ? rawCode : `ref_${rawCode}`;
    const link = `https://t.me/${botUser}?start=${code}`;
    copyToClipboard(link, 'Referral link copied! 🎁');
  });

  el.referralActionCard.addEventListener('click', () => {
    if (!state.user) return;
    haptic('light');
    const botUser = state.store?.support_username || 'CloudDealsBot';
    const rawCode = state.user.referral_code || state.user.telegram_id;
    const code = String(rawCode).startsWith('ref_') ? rawCode : `ref_${rawCode}`;
    const link = `https://t.me/${botUser}?start=${code}`;
    const shareText = encodeURIComponent('🔥 Check out Cloud Deals for instant cloud accounts, keys & subscriptions!');
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${shareText}`;
    if (tg?.openTelegramLink) {
      tg.openTelegramLink(shareUrl);
    } else {
      window.open(shareUrl, '_blank');
    }
  });

  el.supportActionCard.addEventListener('click', () => {
    haptic('light');
    const sup = state.store?.support_username || '';
    if (sup) {
      if (tg?.openTelegramLink) {
        tg.openTelegramLink(`https://t.me/${sup.lstrip ? sup.replace('@', '') : sup}`);
      } else {
        window.open(`https://t.me/${sup.replace('@', '')}`, '_blank');
      }
    } else {
      showToast('Contact support via bot chat.', 'normal');
    }
  });

  el.topupActionCard.addEventListener('click', () => {
    haptic('light');
    showToast('Send /start in the bot chat and tap Top-up to add balance! 💳', 'normal');
  });

  // --- Navigation Dock Handlers ---
  function setActiveDockBtn(activeBtn) {
    document.querySelectorAll('.apple-dock-tab').forEach((b) => b.classList.remove('active'));
    if (activeBtn) {
      activeBtn.classList.add('active');
    }
  }

  if (el.dockCatalogBtn) {
    el.dockCatalogBtn.addEventListener('click', () => {
      haptic('light');
      setActiveDockBtn(el.dockCatalogBtn);
      closeModal();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  if (el.dockProductsBtn) {
    el.dockProductsBtn.addEventListener('click', () => {
      haptic('light');
      setActiveDockBtn(el.dockProductsBtn);
      closeModal();
      const main = document.getElementById('mainContent');
      if (main) {
        main.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }

  if (el.dockCartBtn) {
    el.dockCartBtn.addEventListener('click', () => {
      haptic('light');
      setActiveDockBtn(el.dockCartBtn);
      openCartSheet();
    });
  }

  if (el.dockOrdersBtn) {
    el.dockOrdersBtn.addEventListener('click', () => {
      haptic('light');
      setActiveDockBtn(el.dockOrdersBtn);
      openOrdersDrawer();
    });
  }

  if (el.dockProfileBtn) {
    el.dockProfileBtn.addEventListener('click', () => {
      haptic('light');
      setActiveDockBtn(el.dockProfileBtn);
      openProfileDrawer();
    });
  }

  // Circular Search Button on Right (Matching Apple reference)
  if (el.dockSearchBtn) {
    el.dockSearchBtn.addEventListener('click', () => {
      haptic('light');
      closeModal();
      window.scrollTo({ top: 0, behavior: 'smooth' });

      // Highlight the search box with glow animation & focus input
      const box = document.querySelector('.apple-search-box');
      if (box) {
        box.classList.remove('apple-search-pulse');
        void box.offsetWidth;
        box.classList.add('apple-search-pulse');
      }

      if (el.searchInput) {
        setTimeout(() => {
          el.searchInput.focus();
          if (el.searchInput.value) {
            el.searchInput.select();
          }
        }, 120);
      }
    });
  }

  // --- Search & Filters ---
  function onSearchChange() {
    state.searchQuery = el.searchInput ? el.searchInput.value : '';
    if (el.clearSearchBtn) {
      el.clearSearchBtn.classList.toggle('hidden', !state.searchQuery);
    }
    if (state.searchQuery.trim()) {
      // Searching across entire store: update category pill visuals to 'all'
      state.activeCategory = 'all';
      el.categoriesBar.querySelectorAll('.cat-pill').forEach((b) => {
        b.classList.toggle('active', b.dataset.categoryId === 'all');
      });
    }
    renderProducts();
  }

  if (el.searchInput) {
    ['input', 'keyup', 'change', 'search'].forEach((evt) => {
      el.searchInput.addEventListener(evt, onSearchChange);
    });
    // On mobile Enter key, blur to dismiss virtual keyboard
    el.searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        el.searchInput.blur();
      }
    });
  }

  if (el.clearSearchBtn) {
    el.clearSearchBtn.addEventListener('click', () => {
      if (el.searchInput) el.searchInput.value = '';
      state.searchQuery = '';
      el.clearSearchBtn.classList.add('hidden');
      renderProducts();
      if (el.searchInput) el.searchInput.focus();
    });
  }

  if (el.resetFiltersBtn) {
    el.resetFiltersBtn.addEventListener('click', () => {
      state.searchQuery = '';
      state.activeCategory = 'all';
      if (el.searchInput) el.searchInput.value = '';
      if (el.clearSearchBtn) el.clearSearchBtn.classList.add('hidden');
      renderCategories();
      renderProducts();
    });
  }

  // --- Dev User Switcher (For Previewing in Desktop Browsers) ---
  if (el.devSwitchUserBtn) {
    el.devSwitchUserBtn.addEventListener('click', () => {
      const newId = parseInt(el.devUserIdInput.value, 10);
      if (newId) {
        state.telegramId = newId;
        state.initData = '';
        state.token = null;
        try {
          sessionStorage.removeItem('cloud_deals_jwt');
        } catch (e) {}
        showToast(`Switched preview user to Telegram ID: ${newId}`, 'success');
        initAuth();
      }
    });
  }

  // --- Clipboard Utility ---
  function copyToClipboard(text, successMessage = 'Copied!') {
    if (!text) return;
    navigator.clipboard
      .writeText(text)
      .then(() => {
        haptic('light');
        showToast(successMessage, 'success');
      })
      .catch(() => {
        // Fallback
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
        showToast(successMessage, 'success');
      });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // --- App Initialization ---
  initAuth();
})();
