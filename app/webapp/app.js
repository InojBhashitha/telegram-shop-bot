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
    try {
      if (tg.setHeaderColor) tg.setHeaderColor('#000000');
      if (tg.setBackgroundColor) tg.setBackgroundColor('#000000');
    } catch (e) {}
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
    currencySymbol: '$',
    selectedProduct: null,
    modalQuantity: 1,
    activeModal: null,
    currentPaymentOrder: null,
    pollTimer: null,
    adminState: {
      activeTab: 'analytics',
      products: [],
      orders: [],
    },
  };

  // --- DOM Elements Cache ---
  const el = {
    storeTitle: document.getElementById('storeTitle'),
    storeTagline: document.getElementById('storeTagline'),
    storeLogo: document.getElementById('storeLogo'),
    trustWarrantyChip: document.getElementById('trustWarrantyChip'),
    trustVouchesChip: document.getElementById('trustVouchesChip'),
    trustSupportChip: document.getElementById('trustSupportChip'),
    warrantyHoursText: document.getElementById('warrantyHoursText'),
    vouchText: document.getElementById('vouchText'),
    featuredShowcaseCard: document.getElementById('featuredShowcaseCard'),
    spotlightCategory: document.getElementById('spotlightCategory'),
    spotlightTitle: document.getElementById('spotlightTitle'),
    spotlightSubtitle: document.getElementById('spotlightSubtitle'),
    spotlightPrice: document.getElementById('spotlightPrice'),
    spotlightStockChip: document.getElementById('spotlightStockChip'),
    spotlightLogoImg: document.getElementById('spotlightLogoImg'),
    spotlightGlowAura: document.getElementById('spotlightGlowAura'),
    spotlightBuyBtn: document.getElementById('spotlightBuyBtn'),
    spotlightViewBtn: document.getElementById('spotlightViewBtn'),
    userChipBtn: document.getElementById('userChipBtn'),
    userAvatar: document.getElementById('userAvatar'),
    userName: document.getElementById('userName'),
    userBalance: document.getElementById('userBalance'),
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
    modalBulkCard: document.getElementById('modalBulkCard'),
    modalBulkTiersGrid: document.getElementById('modalBulkTiersGrid'),
    modalBulkSavingsHint: document.getElementById('modalBulkSavingsHint'),
    modalBulkActiveTier: document.getElementById('modalBulkActiveTier'),
    modalBulkSavedAmt: document.getElementById('modalBulkSavedAmt'),
    modalEffectiveUnitPrice: document.getElementById('modalEffectiveUnitPrice'),
    modalActionFooter: document.getElementById('modalActionFooter'),
    modalAddToCartBtn: document.getElementById('modalAddToCartBtn'),
    modalBuyNowBtn: document.getElementById('modalBuyNowBtn'),
    closeProductModal: document.getElementById('closeProductModal'),


    cartModal: document.getElementById('cartModal'),
    cartModalItemCount: document.getElementById('cartModalItemCount'),
    cartItemsList: document.getElementById('cartItemsList'),
    emptyCartView: document.getElementById('emptyCartView'),
    cartSubtotalAmount: document.getElementById('cartSubtotalAmount'),
    cartBulkDiscountRow: document.getElementById('cartBulkDiscountRow'),
    cartBulkDiscountLabel: document.getElementById('cartBulkDiscountLabel'),
    cartBulkDiscountAmount: document.getElementById('cartBulkDiscountAmount'),
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
    supportActionCard: document.getElementById('supportActionCard'),
    closeProfileModal: document.getElementById('closeProfileModal'),

    // Top-Up Modal
    topupModal: document.getElementById('topupModal'),
    closeTopupModal: document.getElementById('closeTopupModal'),
    topupCurrentBalText: document.getElementById('topupCurrentBalText'),
    customTopupInput: document.getElementById('customTopupInput'),
    topupPayAmtDisplay: document.getElementById('topupPayAmtDisplay'),
    topupBonusAmtDisplay: document.getElementById('topupBonusAmtDisplay'),
    topupTotalCreditDisplay: document.getElementById('topupTotalCreditDisplay'),
    confirmTopupBtn: document.getElementById('confirmTopupBtn'),
    btnTopupAmount: document.getElementById('btnTopupAmount'),

    // Navigation Dock & Search
    dockCatalogBtn: document.getElementById('dockCatalogBtn'),
    dockProductsBtn: document.getElementById('dockProductsBtn'),
    dockOrdersBtn: document.getElementById('dockOrdersBtn'),
    dockCartBtn: document.getElementById('dockCartBtn'),
    dockSearchBtn: document.getElementById('dockSearchBtn'),
    searchSection: document.getElementById('searchSection'),

    // Dev preview
    devPreviewBar: document.getElementById('devPreviewBar'),
    devUserIdInput: document.getElementById('devUserIdInput'),
    devSwitchUserBtn: document.getElementById('devSwitchUserBtn'),
    toastContainer: document.getElementById('toastContainer'),

    // Admin Suite Elements
    dockAdminBtn: document.getElementById('dockAdminBtn'),
    adminSuiteActionCard: document.getElementById('adminSuiteActionCard'),
    adminModal: document.getElementById('adminModal'),
    closeAdminModal: document.getElementById('closeAdminModal'),
    adminSecAnalytics: document.getElementById('adminSecAnalytics'),
    adminSecInventory: document.getElementById('adminSecInventory'),
    adminSecOrders: document.getElementById('adminSecOrders'),
    adminSecBroadcast: document.getElementById('adminSecBroadcast'),
    adminRevToday: document.getElementById('adminRevToday'),
    adminOrdersToday: document.getElementById('adminOrdersToday'),
    adminRev7d: document.getElementById('adminRev7d'),
    adminOrders7d: document.getElementById('adminOrders7d'),
    adminRevLifetime: document.getElementById('adminRevLifetime'),
    adminOrdersLifetime: document.getElementById('adminOrdersLifetime'),
    adminCustomerCount: document.getElementById('adminCustomerCount'),
    adminTotalStock: document.getElementById('adminTotalStock'),
    adminFulfillmentRate: document.getElementById('adminFulfillmentRate'),
    adminActiveProductsCount: document.getElementById('adminActiveProductsCount'),
    adminStockAlertsBox: document.getElementById('adminStockAlertsBox'),
    adminStockAlertsList: document.getElementById('adminStockAlertsList'),
    adminTopSellersList: document.getElementById('adminTopSellersList'),
    btnAdminOpenNewProductModal: document.getElementById('btnAdminOpenNewProductModal'),
    adminProductSearchInput: document.getElementById('adminProductSearchInput'),
    adminProductsList: document.getElementById('adminProductsList'),
    adminOrderSearchInput: document.getElementById('adminOrderSearchInput'),
    btnAdminRefreshOrders: document.getElementById('btnAdminRefreshOrders'),
    adminOrdersVaultList: document.getElementById('adminOrdersVaultList'),
    adminBroadcastMessageInput: document.getElementById('adminBroadcastMessageInput'),
    btnAdminSendBroadcast: document.getElementById('btnAdminSendBroadcast'),

    // Admin Sub-Modals
    adminRestockModal: document.getElementById('adminRestockModal'),
    closeAdminRestockModal: document.getElementById('closeAdminRestockModal'),
    restockProductTitle: document.getElementById('restockProductTitle'),
    restockProductId: document.getElementById('restockProductId'),
    restockCredsInput: document.getElementById('restockCredsInput'),
    btnAdminSubmitRestock: document.getElementById('btnAdminSubmitRestock'),

    adminNewProductModal: document.getElementById('adminNewProductModal'),
    closeAdminNewProductModal: document.getElementById('closeAdminNewProductModal'),
    newProdCategorySelect: document.getElementById('newProdCategorySelect'),
    newProdNameInput: document.getElementById('newProdNameInput'),
    newProdPriceInput: document.getElementById('newProdPriceInput'),
    newProdDescInput: document.getElementById('newProdDescInput'),
    newProdStockInput: document.getElementById('newProdStockInput'),
    btnAdminSubmitNewProduct: document.getElementById('btnAdminSubmitNewProduct'),
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
    if (!el.toastContainer) return;
    haptic(type === 'error' ? 'error' : 'light');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icon = type === 'success' ? '✓' : (type === 'error' ? '✕' : 'ℹ');
    toast.innerHTML = `<span class="toast-icon">${icon}</span><span>${message}</span>`;
    el.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translate3d(0, -12px, 0) scale(0.95)';
      toast.style.transition = 'all 0.22s cubic-bezier(0.16, 1, 0.3, 1)';
      setTimeout(() => toast.remove(), 230);
    }, 2800);
  }

  // --- Dynamic White-Label Theming & Helpers ---
  function formatMoney(amount) {
    const sym = state.currencySymbol || state.store?.currency_symbol || '$';
    const val = parseFloat(amount || 0);
    if (val < 0) {
      return `-${sym}${Math.abs(val).toFixed(2)}`;
    }
    return `${sym}${val.toFixed(2)}`;
  }

  function formatPriceHtml(amount) {
    const sym = state.currencySymbol || state.store?.currency_symbol || '$';
    const val = parseFloat(amount || 0);
    const sign = val < 0 ? '-' : '';
    const formattedNum = Math.abs(val).toFixed(2);
    return `<span class="price-currency">${sign}${escapeHtml(sym)}</span><span class="price-amount">${formattedNum}</span>`;
  }

  function hexToRgb(hex) {
    if (!hex) return null;
    let c = String(hex).replace('#', '').trim();
    if (c.length === 3) {
      c = c.split('').map(x => x + x).join('');
    }
    if (c.length !== 6) return null;
    const num = parseInt(c, 16);
    if (isNaN(num)) return null;
    return {
      r: (num >> 16) & 255,
      g: (num >> 8) & 255,
      b: num & 255,
    };
  }

  function lightenColor(r, g, b, percent = 20) {
    const factor = 1 + percent / 100;
    const nr = Math.min(255, Math.round(r * factor));
    const ng = Math.min(255, Math.round(g * factor));
    const nb = Math.min(255, Math.round(b * factor));
    return `rgb(${nr}, ${ng}, ${nb})`;
  }

  function applyStoreTheme(store) {
    if (!store) return;

    if (store.currency_symbol) {
      state.currencySymbol = store.currency_symbol;
    }

    // Document Title & Header Brand
    if (store.name) {
      document.title = `${store.name} — Store`;
      if (el.storeTitle) {
        el.storeTitle.textContent = store.name;
      }
    }

    if (store.tagline && el.storeTagline) {
      el.storeTagline.textContent = store.tagline;
    }

    if (el.storeLogo) {
      if (store.logo_url) {
        el.storeLogo.src = store.logo_url;
        el.storeLogo.classList.remove('hidden');
      } else {
        el.storeLogo.classList.add('hidden');
      }
    }

    if (el.warrantyHoursText && store.warranty_hours) {
      el.warrantyHoursText.textContent = `${store.warranty_hours}h Warranty`;
    }

    if (el.vouchText && store.vouch_channel) {
      el.vouchText.textContent = `Verified Vouches`;
    }

    // Dynamic Accent Color Injection
    if (store.accent_color) {
      const rgb = hexToRgb(store.accent_color);
      if (rgb) {
        const root = document.documentElement;
        const tint = lightenColor(rgb.r, rgb.g, rgb.b, 20);
        const pillBg = `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.18)`;
        const glow = `0 8px 24px rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.35)`;

        root.style.setProperty('--apple-blue', store.accent_color);
        root.style.setProperty('--apple-accent', store.accent_color);
        root.style.setProperty('--apple-blue-tint', tint);
        root.style.setProperty('--apple-blue-pill', pillBg);
        root.style.setProperty('--apple-accent-rgb', `${rgb.r}, ${rgb.g}, ${rgb.b}`);
        root.style.setProperty('--accent-glow', glow);
      }
    }
  }

  async function loadStoreConfig() {
    try {
      const data = await api('/config');
      if (data && data.store) {
        state.store = Object.assign(state.store || {}, data.store);
        applyStoreTheme(data.store);
      }
    } catch (e) {
      // Non-critical background fallback
    }
  }


  // --- Modal & Drawer Management with Fluid Transitions & Touch Gestures ---
  function openModal(modalEl) {
    if (state.activeModal) {
      if (state.activeModal === modalEl) return;
      state.activeModal.classList.add('hidden');
      state.activeModal.classList.remove('sheet-closing');
    }
    modalEl.style.transform = '';
    modalEl.classList.remove('sheet-closing');
    modalEl.classList.remove('hidden');

    el.modalOverlay.classList.remove('overlay-closing');
    el.modalOverlay.classList.remove('hidden');
    el.modalOverlay.style.opacity = '';

    state.activeModal = modalEl;
    document.body.style.overflow = 'hidden';

    // Telegram Back Button Hook
    if (tg?.BackButton) {
      tg.BackButton.show();
      tg.BackButton.onClick(handleTgBackClick);
    }
    haptic('medium');
  }

  function closeModal(callback) {
    const modal = state.activeModal;
    if (!modal) {
      if (typeof callback === 'function') callback();
      return;
    }

    modal.classList.add('sheet-closing');
    el.modalOverlay.classList.add('overlay-closing');

    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }

    if (tg?.BackButton) {
      tg.BackButton.hide();
      tg.BackButton.offClick(handleTgBackClick);
    }
    haptic('light');

    setTimeout(() => {
      modal.classList.add('hidden');
      modal.classList.remove('sheet-closing');
      modal.style.transform = '';
      el.modalOverlay.classList.add('hidden');
      el.modalOverlay.classList.remove('overlay-closing');
      el.modalOverlay.style.opacity = '';
      document.body.style.overflow = '';
      if (state.activeModal === modal) {
        state.activeModal = null;
      }
      if (typeof callback === 'function') callback();
    }, 200);
  }

  function handleTgBackClick() {
    closeModal();
  }

  // Touch Drag-to-Dismiss Gesture for Apple Bottom Sheets
  function attachDragToDismiss(sheetEl) {
    if (!sheetEl) return;
    const dragTarget = sheetEl.querySelector('.sheet-drag-handle') || sheetEl.querySelector('.sheet-header');
    if (!dragTarget) return;

    let startY = 0;
    let currentY = 0;
    let isDragging = false;
    let startTime = 0;

    dragTarget.addEventListener('touchstart', (e) => {
      if (e.touches.length !== 1) return;
      startY = e.touches[0].clientY;
      currentY = startY;
      startTime = Date.now();
      isDragging = true;
      sheetEl.style.transition = 'none';
      el.modalOverlay.style.transition = 'none';
    }, { passive: true });

    dragTarget.addEventListener('touchmove', (e) => {
      if (!isDragging || e.touches.length !== 1) return;
      const touchY = e.touches[0].clientY;
      const deltaY = touchY - startY;

      if (deltaY > 0) {
        currentY = touchY;
        sheetEl.style.transform = `translate3d(0, ${deltaY}px, 0)`;
        const opacity = Math.max(0.15, 1 - deltaY / 320);
        el.modalOverlay.style.opacity = String(opacity);
      } else {
        // Elastic pull-up resistance
        sheetEl.style.transform = `translate3d(0, ${deltaY * 0.12}px, 0)`;
      }
    }, { passive: true });

    dragTarget.addEventListener('touchend', () => {
      if (!isDragging) return;
      isDragging = false;
      const deltaY = currentY - startY;
      const duration = Date.now() - startTime;
      const velocity = deltaY / Math.max(1, duration);

      sheetEl.style.transition = 'transform 0.24s cubic-bezier(0.16, 1, 0.3, 1)';
      el.modalOverlay.style.transition = 'opacity 0.24s ease';

      if (deltaY > 85 || (velocity > 0.45 && deltaY > 25)) {
        closeModal();
      } else {
        sheetEl.style.transform = 'translate3d(0, 0, 0)';
        el.modalOverlay.style.opacity = '1';
        setTimeout(() => {
          sheetEl.style.transition = '';
          el.modalOverlay.style.transition = '';
        }, 240);
      }
    });
  }

  // Attach touch drag gestures to all bottom sheets
  document.querySelectorAll('.apple-bottom-sheet').forEach(attachDragToDismiss);

  // Overlay click closes current open modal
  el.modalOverlay.addEventListener('click', () => closeModal());
  el.closeProductModal.addEventListener('click', () => closeModal());
  el.closeCartModal.addEventListener('click', () => closeModal());
  el.closePaymentModal.addEventListener('click', () => closeModal());
  el.closeVaultModal.addEventListener('click', () => closeModal());
  el.closeOrdersModal.addEventListener('click', () => closeModal());
  el.closeProfileModal.addEventListener('click', () => closeModal());
  if (el.closeAdminModal) el.closeAdminModal.addEventListener('click', () => closeModal());
  if (el.closeAdminRestockModal) el.closeAdminRestockModal.addEventListener('click', () => closeModal(() => openAdminModal('inventory')));
  if (el.closeAdminNewProductModal) el.closeAdminNewProductModal.addEventListener('click', () => closeModal(() => openAdminModal('inventory')));

  // Trust Chip click actions
  if (el.trustWarrantyChip) {
    el.trustWarrantyChip.addEventListener('click', () => {
      const hours = state.store?.warranty_hours || 24;
      showToast(`🛡️ All products are backed by a ${hours}-hour replacement guarantee.`, 'success');
    });
  }

  if (el.trustVouchesChip) {
    el.trustVouchesChip.addEventListener('click', () => {
      const ch = state.store?.vouch_channel;
      if (ch) {
        const clean = ch.replace('@', '');
        const url = `https://t.me/${clean}`;
        if (tg?.openTelegramLink) {
          tg.openTelegramLink(url);
        } else {
          window.open(url, '_blank');
        }
      } else {
        showToast('🔒 100% verified working accounts with automated delivery', 'normal');
      }
    });
  }

  if (el.trustSupportChip) {
    el.trustSupportChip.addEventListener('click', () => {
      const sup = state.store?.support_username;
      if (sup) {
        const clean = sup.replace('@', '');
        const url = `https://t.me/${clean}`;
        if (tg?.openTelegramLink) {
          tg.openTelegramLink(url);
        } else {
          window.open(url, '_blank');
        }
      } else {
        showToast('💬 24/7 automated delivery & support active.', 'normal');
      }
    });
  }

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

      applyStoreTheme(state.store);
      renderUserProfile();
      await fetchCatalog();
      await fetchCart();

      // Show dev preview bar if not running inside Telegram WebApp
      const urlParams = new URLSearchParams(window.location.search);
      const hideDev = urlParams.get('hide_dev') === '1';
      if (!state.initData && el.devPreviewBar && !hideDev) {
        el.devPreviewBar.classList.remove('hidden');
        el.devUserIdInput.value = state.telegramId;
      }

      if (urlParams.get('open_admin') === '1') {
        setTimeout(() => openAdminModal('analytics'), 400);
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
    el.userBalance.textContent = formatMoney(u.balance);

    // Profile drawer
    el.profAvatar.textContent = initials;
    el.profName.textContent = displayName;
    el.profUsername.textContent = u.username ? `@${u.username}` : 'No username';
    el.profId.textContent = `Telegram ID: ${u.telegram_id}`;
    el.profBalance.textContent = formatMoney(u.balance);
    el.methodBalanceSub.textContent = `Available: ${formatMoney(u.balance)} • Zero Confirmation Wait`;


    // Admin Suite Access
    const isAdmin = Boolean(u.is_admin);
    if (el.dockAdminBtn) {
      el.dockAdminBtn.classList.toggle('hidden', !isAdmin);
    }
    if (el.adminSuiteActionCard) {
      el.adminSuiteActionCard.classList.toggle('hidden', !isAdmin);
    }
  }



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

    // Category click handler with smooth center scrolling
    el.categoriesBar.querySelectorAll('.cat-pill').forEach((btn) => {
      btn.addEventListener('click', () => {
        haptic('selection');
        el.categoriesBar.querySelectorAll('.cat-pill').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        btn.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
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

  function resolveProviderColor(prod) {
    const name = (prod?.name || '').toLowerCase();
    const cat = (prod?.category_name || '').toLowerCase();
    const haystack = `${name} ${cat}`;

    if (haystack.includes('oracle') || haystack.includes('oci')) {
      return 'radial-gradient(circle, rgba(248, 0, 0, 0.32) 0%, transparent 70%)';
    }
    if (haystack.includes('aws') || haystack.includes('amazon')) {
      return 'radial-gradient(circle, rgba(255, 153, 0, 0.32) 0%, transparent 70%)';
    }
    if (haystack.includes('digitalocean') || haystack.includes('digital ocean') || haystack.includes('do ')) {
      return 'radial-gradient(circle, rgba(0, 128, 255, 0.32) 0%, transparent 70%)';
    }
    if (haystack.includes('google') || haystack.includes('gcp')) {
      return 'radial-gradient(circle, rgba(66, 133, 244, 0.32) 0%, transparent 70%)';
    }
    if (haystack.includes('upcloud')) {
      return 'radial-gradient(circle, rgba(123, 31, 162, 0.32) 0%, transparent 70%)';
    }
    if (haystack.includes('azure') || haystack.includes('microsoft')) {
      return 'radial-gradient(circle, rgba(0, 120, 212, 0.32) 0%, transparent 70%)';
    }
    return 'radial-gradient(circle, rgba(41, 151, 255, 0.25) 0%, transparent 70%)';
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

    // Dynamic Featured Hero Spotlight Card
    if (el.featuredShowcaseCard) {
      if (!query && state.activeCategory === 'all' && state.products.length > 0) {
        const featured = state.products.find((p) => p.stock > 0) || state.products[0];
        if (featured) {
          el.featuredShowcaseCard.classList.remove('hidden');
          if (el.spotlightCategory) el.spotlightCategory.textContent = featured.category_name || 'Cloud Account';
          if (el.spotlightTitle) el.spotlightTitle.textContent = featured.name;
          if (el.spotlightSubtitle) {
            el.spotlightSubtitle.textContent = featured.description || 'Instant automated credential delivery • Verified working with 24h warranty';
          }
          if (el.spotlightPrice) el.spotlightPrice.textContent = formatMoney(featured.price);
          if (el.spotlightStockChip) {
            el.spotlightStockChip.textContent = featured.stock > 0 ? `⚡ ${featured.stock} Ready in Vault` : '⏳ Restocking Soon';
          }
          if (el.spotlightLogoImg) {
            el.spotlightLogoImg.src = resolveCloudLogo(featured);
            el.spotlightLogoImg.alt = featured.name;
          }
          if (el.spotlightGlowAura) {
            el.spotlightGlowAura.style.background = resolveProviderColor(featured);
          }

          el.featuredShowcaseCard.onclick = () => {
            openProductSheet(featured);
          };

          if (el.spotlightBuyBtn) {
            el.spotlightBuyBtn.onclick = async (e) => {
              e.stopPropagation();
              if (featured.stock > 0) {
                await quickAddToCart(featured.id, 1);
                openCartSheet();
              } else {
                openProductSheet(featured);
              }
            };
          }
          if (el.spotlightViewBtn) {
            el.spotlightViewBtn.onclick = (e) => {
              e.stopPropagation();
              openProductSheet(featured);
            };
          }
        } else {
          el.featuredShowcaseCard.classList.add('hidden');
        }
      } else {
        el.featuredShowcaseCard.classList.add('hidden');
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
      const glowStyle = resolveProviderColor(p);

      // Apple Tag (e.g., "Saved for you", "Instant Stock", "Low Stock")
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
          <span class="card-tag-badge">${tagIcon} ${tagText}</span>
        </div>
        <div class="card-logo-container" style="--provider-glow: ${glowStyle};">
          <div class="card-ambient-glow"></div>
          <img src="${logoSrc}" alt="${escapeHtml(p.name)}" class="card-cloud-logo" loading="lazy">
        </div>
        <div class="card-bottom-info">
          <h3 class="card-item-title" title="${escapeHtml(p.name)}">${escapeHtml(p.name)}</h3>
          <div class="card-meta-line">
            <div class="card-price-block">
              <span class="card-price-text">${formatPriceHtml(p.price)}</span>
              <div class="card-stock-dot-wrap">
                <span class="stock-indicator-dot ${isOutOfStock ? 'out' : ''}"></span>
                <span>${isOutOfStock ? 'Sold out' : `${p.stock} left`}</span>
              </div>
            </div>
            <button class="card-quick-buy-btn ${isOutOfStock ? 'disabled' : ''}" data-product-id="${p.id}" title="${isOutOfStock ? 'Out of Stock' : 'Quick Add to Bag'}">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M5 12h14"/></svg>
            </button>
          </div>
        </div>
      `;

      // Quick Buy button tap
      const quickBuyBtn = card.querySelector('.card-quick-buy-btn');
      if (quickBuyBtn && !isOutOfStock) {
        quickBuyBtn.addEventListener('click', async (e) => {
          e.stopPropagation();
          quickBuyBtn.classList.add('added');
          quickBuyBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>`;
          await quickAddToCart(p.id, 1);
          // Pop animation on cart badge
          if (el.cartBadge) {
            el.cartBadge.classList.remove('pop');
            void el.cartBadge.offsetWidth;
            el.cartBadge.classList.add('pop');
          }
          setTimeout(() => {
            quickBuyBtn.classList.remove('added');
            quickBuyBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M5 12h14"/></svg>`;
          }, 800);
        });
      }

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
    if (el.modalLogoPreview) {
      el.modalLogoPreview.style.background = resolveProviderColor(prod);
    }

    el.modalCategory.textContent = `${prod.category_icon || '📦'} ${prod.category_name}`;
    el.modalTitle.textContent = prod.name;
    el.modalPrice.textContent = formatMoney(prod.price);
    el.modalDescription.textContent = prod.description || 'Verified working digital accounts delivered instantly upon payment.';



    // Stock Badge & Out of Stock Alert Box
    let stockText = `${prod.stock} in stock`;
    if (prod.stock === 0) {
      stockText = 'Out of Stock';
      el.modalStockBadge.className = 'apple-badge-stock stock-out';
      el.modalOutOfStockBox?.classList.remove('hidden');
      el.modalBulkCard?.classList.add('hidden');
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

      // Populate Wholesale Volume Pricing Tiers Grid
      if (el.modalBulkCard && el.modalBulkTiersGrid) {
        const tiers = (prod.bulk_tiers || []).filter((t) => t.discount_percent > 0);
        if (tiers.length > 0 && prod.stock >= 3) {
          el.modalBulkTiersGrid.innerHTML = '';
          tiers.forEach((t) => {
            const pill = document.createElement('div');
            pill.className = `bulk-tier-pill ${t.discount_percent >= 20 ? 'vip' : ''}`;
            pill.dataset.minQty = t.min_qty;
            pill.innerHTML = `
              <span class="tier-qty-label">${t.min_qty}+ pcs</span>
              <span class="tier-price-val">${t.unit_price}</span>
              <span class="tier-badge-pill ${t.discount_percent >= 20 ? 'vip' : ''}">${t.badge}</span>
            `;
            pill.addEventListener('click', () => {
              if (prod.stock >= t.min_qty) {
                state.modalQuantity = t.min_qty;
                haptic('medium');
                updateModalQuantityDisplay();
              } else {
                showToast(`Only ${prod.stock} items currently in stock`, 'normal');
              }
            });
            el.modalBulkTiersGrid.appendChild(pill);
          });
          el.modalBulkCard.classList.remove('hidden');
        } else {
          el.modalBulkCard.classList.add('hidden');
        }
      }
    }
    el.modalStockBadge.textContent = stockText;

    updateModalQuantityDisplay();
    openModal(el.productModal);
  }

  function updateModalQuantityDisplay() {
    if (!state.selectedProduct) return;
    const qty = state.modalQuantity;
    el.modalQtyValue.textContent = qty;

    const unitPrice = parseFloat(state.selectedProduct.price);
    const rawTotal = unitPrice * qty;

    // Determine applicable bulk tier
    let discountPct = 0;
    let activeTierLabel = '';
    const tiers = state.selectedProduct.bulk_tiers || [];
    const sortedTiers = [...tiers].filter((t) => t.discount_percent > 0).sort((a, b) => b.min_qty - a.min_qty);
    for (const t of sortedTiers) {
      if (qty >= t.min_qty) {
        discountPct = t.discount_percent;
        activeTierLabel = t.badge;
        break;
      }
    }

    // Highlight active tier pills
    if (el.modalBulkTiersGrid) {
      const pills = el.modalBulkTiersGrid.querySelectorAll('.bulk-tier-pill');
      pills.forEach((p) => {
        const minQ = parseInt(p.dataset.minQty, 10);
        if (qty >= minQ) {
          p.classList.add('active');
        } else {
          p.classList.remove('active');
        }
      });
    }

    if (discountPct > 0) {
      const discountAmt = Math.round((rawTotal * discountPct) / 100 * 100) / 100;
      const finalTotal = Math.max(0.01, rawTotal - discountAmt);
      const effectiveUnit = finalTotal / qty;

      el.modalQtySubtotal.textContent = `Total: ${formatMoney(finalTotal)}`;
      if (el.modalEffectiveUnitPrice) {
        el.modalEffectiveUnitPrice.textContent = `(${formatMoney(effectiveUnit)}/ea • -${discountPct}% OFF)`;
        el.modalEffectiveUnitPrice.classList.remove('hidden');
      }
      if (el.modalBulkSavingsHint && el.modalBulkActiveTier && el.modalBulkSavedAmt) {
        el.modalBulkActiveTier.textContent = `Wholesale (${activeTierLabel}):`;
        el.modalBulkSavedAmt.textContent = formatMoney(discountAmt);
        el.modalBulkSavingsHint.classList.remove('hidden');
      }
    } else {
      el.modalQtySubtotal.textContent = `Total: ${formatMoney(rawTotal)}`;
      if (el.modalEffectiveUnitPrice) {
        el.modalEffectiveUnitPrice.classList.add('hidden');
      }
      if (el.modalBulkSavingsHint) {
        el.modalBulkSavingsHint.classList.add('hidden');
      }
    }
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
    const origText = el.modalAddToCartBtn.textContent;
    el.modalAddToCartBtn.textContent = 'Added to Bag ✓';
    await quickAddToCart(state.selectedProduct.id, state.modalQuantity);
    setTimeout(() => {
      closeModal();
      el.modalAddToCartBtn.textContent = origText;
    }, 450);
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
          token: state.token || undefined,
        }),
      });

      showToast(`Added ${quantity > 1 ? quantity + ' items' : 'item'} to bag 🛒`, 'success');
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
      el.stickyTotalAmount.textContent = formatMoney(c.final_amount);
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

      let bulkBadgeHtml = '';
      if (item.bulk_discount && parseFloat(item.bulk_discount) > 0) {
        bulkBadgeHtml = `<span class="cart-item-bulk-badge">📉 ${escapeHtml(item.bulk_tier || 'Wholesale Tier')} (-${formatMoney(item.bulk_discount)})</span>`;
      } else if (item.next_tier_hint) {
        bulkBadgeHtml = `<span class="cart-item-upsell-hint">💡 ${escapeHtml(item.next_tier_hint)}</span>`;
      }

      row.innerHTML = `
        <div class="cart-item-thumb-box">
          <img src="${logoSrc}" alt="" class="cart-item-thumb">
        </div>
        <div class="item-left">
          <span class="item-title">${escapeHtml(item.product_name)}</span>
          <span class="item-sub">${formatMoney(item.unit_price)} each</span>
          ${bulkBadgeHtml}
        </div>
        <div class="item-right">
          <div class="apple-stepper">
            <button class="step-btn btn-cart-dec" data-id="${item.product_id}" data-qty="${item.quantity - 1}">&minus;</button>
            <span class="step-count">${item.quantity}</span>
            <button class="step-btn btn-cart-inc" data-id="${item.product_id}" data-qty="${item.quantity + 1}">&plus;</button>
          </div>
          <span class="item-price">${formatMoney(item.subtotal)}</span>
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
    const rawSubtotal = parseFloat(c.raw_subtotal || c.subtotal || 0);
    const bulkSavings = parseFloat(c.bulk_discount_amount || 0);

    el.cartSubtotalAmount.textContent = formatMoney(rawSubtotal);

    // Wholesale volume savings line
    if (bulkSavings > 0 && el.cartBulkDiscountRow && el.cartBulkDiscountAmount) {
      el.cartBulkDiscountRow.classList.remove('hidden');
      el.cartBulkDiscountAmount.textContent = `-${formatMoney(bulkSavings)}`;
    } else if (el.cartBulkDiscountRow) {
      el.cartBulkDiscountRow.classList.add('hidden');
    }

    const finalAmount = Math.max(0, parseFloat(c.subtotal ?? (rawSubtotal - bulkSavings)));
    el.cartFinalAmount.textContent = formatMoney(finalAmount);
    el.btnCheckoutTotal.textContent = formatMoney(finalAmount);
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
          token: state.token || undefined,
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
          token: state.token || undefined,
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
          token: state.token || undefined,
        }),
      });
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
          init_data: state.initData || undefined,
          telegram_id: state.telegramId || undefined,
          token: state.token || undefined,
        }),
      });

      closeModal();
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
      el.executeCheckoutBtn.innerHTML = `Proceed to Payment • <span id="btnCheckoutTotal">${formatMoney(state.cart.final_amount)}</span>`;
    }
  });

  // --- Crypto Payment Modal & Live Polling ---
  function openCryptoPaymentModal(orderData) {
    state.currentPaymentOrder = orderData;
    el.payModalOrderId.textContent = `Order #${orderData.public_order_id}`;
    el.payModalAmount.textContent = formatMoney(orderData.amount);

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

        const copyBtn = field.querySelector('.btn-field-copy');
        copyBtn.addEventListener('click', () => {
          copyToClipboard(cred, 'Credential copied!');
          copyBtn.textContent = '✓';
          copyBtn.classList.add('copied');
          setTimeout(() => {
            copyBtn.textContent = '📋';
            copyBtn.classList.remove('copied');
          }, 1200);
        });

        el.vaultCredentialsContent.appendChild(field);
      });
    }

    el.copyAllCredentialsBtn.onclick = () => {
      copyToClipboard(allText, 'All credentials copied to clipboard! 📋');
      const orig = el.copyAllCredentialsBtn.textContent;
      el.copyAllCredentialsBtn.textContent = '✓ Copied All';
      el.copyAllCredentialsBtn.classList.add('copied');
      setTimeout(() => {
        el.copyAllCredentialsBtn.textContent = orig;
        el.copyAllCredentialsBtn.classList.remove('copied');
      }, 1200);
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
            const rawDelivered = o.delivered_items.join('\n');
            credPreview = `
              <div class="order-credentials-preview">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                  <strong style="color:var(--text-primary);font-size:12px;">🔑 Delivered Credentials:</strong>
                  <button type="button" class="btn btn-ghost copy-order-creds-btn" data-creds="${escapeHtml(rawDelivered)}" style="padding:2px 8px;font-size:11px;min-height:unset;height:24px;border:1px solid rgba(255,255,255,0.12);border-radius:6px;cursor:pointer;">📋 Copy</button>
                </div>
                <div style="font-family:var(--font-mono);font-size:11px;line-height:1.45;word-break:break-all;color:var(--text-secondary);white-space:pre-wrap;">${escapeHtml(rawDelivered)}</div>
              </div>
            `;
          }

          card.innerHTML = `
            <div class="order-top">
              <span class="order-id">#${escapeHtml(o.public_order_id)}</span>
              <span class="order-status-badge status-${escapeHtml(o.status)}">${escapeHtml(o.status.replace('_', ' '))}</span>
            </div>
            <div class="order-details-text">
              ${escapeHtml(o.product_name)} • <strong>${formatMoney(o.amount)}</strong> • ${escapeHtml(dateStr)}
            </div>
            ${credPreview}
          `;

          el.ordersList.appendChild(card);
        });

        el.ordersList.querySelectorAll('.copy-order-creds-btn').forEach(btn => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const textToCopy = btn.getAttribute('data-creds') || '';
            copyToClipboard(textToCopy, 'Credentials copied to clipboard! 📋');
            const orig = btn.textContent;
            btn.textContent = '✓ Copied';
            setTimeout(() => {
              btn.textContent = orig;
            }, 1200);
          });
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

  el.supportActionCard.addEventListener('click', () => {
    haptic('light');
    const sup = state.store?.support_username || '';
    if (sup) {
      const cleanUser = sup.replace('@', '');
      if (tg?.openTelegramLink) {
        tg.openTelegramLink(`https://t.me/${cleanUser}`);
      } else {
        window.open(`https://t.me/${cleanUser}`, '_blank');
      }
    } else {
      showToast('Contact support via bot chat.', 'normal');
    }
  });

  // --- Wallet Top-Up & Deposit Bonus Modal Handlers ---
  function calculateDepositBonus(amount) {
    const amt = parseFloat(amount) || 0;
    let pct = 0;
    let label = '';
    if (amt >= 100) {
      pct = 15.0;
      label = '+15% VIP Bonus';
    } else if (amt >= 50) {
      pct = 10.0;
      label = '+10% Mega Bonus';
    } else if (amt >= 20) {
      pct = 7.5;
      label = '+7.5% Pro Bonus';
    } else if (amt >= 10) {
      pct = 5.0;
      label = '+5% Starter Bonus';
    }
    const bonus = Math.round((amt * pct / 100) * 100) / 100;
    return {
      amount: amt,
      bonus: bonus,
      percent: pct,
      label: label,
      total: Math.round((amt + bonus) * 100) / 100,
    };
  }

  function updateTopupCalculation(amount) {
    const calc = calculateDepositBonus(amount);
    if (el.topupPayAmtDisplay) el.topupPayAmtDisplay.textContent = formatMoney(calc.amount);
    if (el.topupBonusAmtDisplay) {
      if (calc.bonus > 0) {
        el.topupBonusAmtDisplay.textContent = `+${formatMoney(calc.bonus)} (${calc.label})`;
        el.topupBonusAmtDisplay.style.color = '#ff9f0a';
      } else {
        el.topupBonusAmtDisplay.textContent = `${formatMoney(0)} (Standard)`;
        el.topupBonusAmtDisplay.style.color = 'var(--text-secondary)';
      }
    }
    if (el.topupTotalCreditDisplay) el.topupTotalCreditDisplay.textContent = formatMoney(calc.total);
    if (el.btnTopupAmount) el.btnTopupAmount.textContent = formatMoney(calc.amount);
  }

  function openTopupModal() {
    if (el.topupCurrentBalText && state.user) {
      el.topupCurrentBalText.textContent = formatMoney(state.user.balance);
    }
    updateTopupCalculation(10);
    document.querySelectorAll('.preset-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.amt === '10');
    });
    if (el.customTopupInput) el.customTopupInput.value = 10;
    openModal(el.topupModal);
  }

  if (el.topupActionCard) {
    el.topupActionCard.addEventListener('click', () => {
      haptic('light');
      openTopupModal();
    });
  }

  if (el.closeTopupModal) {
    el.closeTopupModal.addEventListener('click', closeModal);
  }

  document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      haptic('light');
      document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const amt = parseFloat(btn.dataset.amt) || 10;
      if (el.customTopupInput) el.customTopupInput.value = amt;
      updateTopupCalculation(amt);
    });
  });

  if (el.customTopupInput) {
    el.customTopupInput.addEventListener('input', () => {
      let val = el.customTopupInput.value.replace(/[^0-9.]/g, '');
      const parts = val.split('.');
      if (parts.length > 2) val = parts[0] + '.' + parts.slice(1).join('');
      el.customTopupInput.value = val;
      const amt = parseFloat(val) || 0;
      document.querySelectorAll('.preset-btn').forEach(b => {
        b.classList.toggle('active', parseFloat(b.dataset.amt) === amt);
      });
      updateTopupCalculation(amt);
    });
  }

  if (el.confirmTopupBtn) {
    el.confirmTopupBtn.addEventListener('click', async () => {
      haptic('heavy');
      const amt = parseFloat(el.customTopupInput?.value) || 10;
      if (amt < 1.0) {
        showToast('Minimum deposit is $1.00', 'error');
        return;
      }
      el.confirmTopupBtn.disabled = true;
      el.confirmTopupBtn.textContent = 'Generating Crypto Invoice...';

      try {
        const res = await api('/topup', {
          method: 'POST',
          body: JSON.stringify({
            amount: amt,
            currency: 'USD',
            init_data: state.initData || undefined,
            telegram_id: state.telegramId || undefined,
            token: state.token || undefined,
          }),
        });

        closeModal();
        if (res.payment_url) {
          if (tg?.openTelegramLink && res.payment_url.startsWith('https://t.me/')) {
            tg.openTelegramLink(res.payment_url);
          } else if (tg?.openLink) {
            tg.openLink(res.payment_url);
          } else {
            window.open(res.payment_url, '_blank');
          }
          const bonusMsg = parseFloat(res.bonus_amount) > 0 ? ` (+${res.bonus_percent}% bonus of +$${res.bonus_amount} included!)` : '';
          showToast(`Top-up invoice created! Pay via crypto to receive your balance${bonusMsg} 🚀`, 'success');
        }
      } catch (err) {
        showToast(err.message, 'error');
        haptic('error');
      } finally {
        el.confirmTopupBtn.disabled = false;
        el.confirmTopupBtn.innerHTML = `💳 Pay with Crypto • <span id="btnTopupAmount">$${amt.toFixed(2)}</span>`;
        el.btnTopupAmount = document.getElementById('btnTopupAmount');
      }
    });
  }

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


  if (el.dockAdminBtn) {
    el.dockAdminBtn.addEventListener('click', () => {
      haptic('light');
      setActiveDockBtn(el.dockAdminBtn);
      openAdminModal('analytics');
    });
  }

  if (el.adminSuiteActionCard) {
    el.adminSuiteActionCard.addEventListener('click', () => {
      haptic('light');
      closeModal(() => {
        openAdminModal('analytics');
      });
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

  // =========================================================================
  // MERCHANT ADMIN SUITE MODULE
  // =========================================================================

  function openAdminModal(tab = 'analytics') {
    if (!state.user?.is_admin) {
      showToast('Administrative privileges required.', 'error');
      return;
    }
    openModal(el.adminModal);
    switchAdminTab(tab);
  }

  function switchAdminTab(tabName) {
    state.adminState.activeTab = tabName;

    // Update tab bar active classes
    const tabBtns = el.adminModal?.querySelectorAll('.admin-nav-tab') || [];
    tabBtns.forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-admin-tab') === tabName);
    });

    // Hide all view panels
    const panels = {
      analytics: el.adminSecAnalytics,
      inventory: el.adminSecInventory,
      orders: el.adminSecOrders,
      broadcast: el.adminSecBroadcast,
    };

    Object.entries(panels).forEach(([name, panelEl]) => {
      if (panelEl) {
        panelEl.classList.toggle('hidden', name !== tabName);
      }
    });

    // Load data for active panel
    if (tabName === 'analytics') {
      loadAdminAnalytics();
    } else if (tabName === 'inventory') {
      loadAdminProducts();
    } else if (tabName === 'orders') {
      loadAdminOrders();
    }
  }

  // --- 1. Analytics & KPI Pulse ---
  async function loadAdminAnalytics() {
    try {
      const res = await api('/admin/analytics');
      const o = res.overview || {};

      if (el.adminRevToday) el.adminRevToday.textContent = formatMoney(o.revenue_today || 0);
      if (el.adminOrdersToday) el.adminOrdersToday.textContent = `${o.orders_today || 0} orders`;
      if (el.adminRev7d) el.adminRev7d.textContent = formatMoney(o.revenue_7d || 0);
      if (el.adminOrders7d) el.adminOrders7d.textContent = `${o.orders_7d || 0} orders`;
      if (el.adminRevLifetime) el.adminRevLifetime.textContent = formatMoney(o.lifetime_revenue || 0);
      if (el.adminOrdersLifetime) el.adminOrdersLifetime.textContent = `${o.lifetime_orders || 0} orders`;
      if (el.adminCustomerCount) el.adminCustomerCount.textContent = `${o.lifetime_customers || 0} customers`;
      if (el.adminTotalStock) el.adminTotalStock.textContent = String(o.total_available_stock || 0);
      if (el.adminFulfillmentRate) el.adminFulfillmentRate.textContent = `${o.fulfillment_rate || 100}% OK`;
      if (el.adminActiveProductsCount) el.adminActiveProductsCount.textContent = `${o.active_products || 0} active products`;

      // Low Stock Alerts
      const alerts = res.low_stock_alerts || [];
      if (alerts.length > 0 && el.adminStockAlertsBox) {
        el.adminStockAlertsBox.classList.remove('hidden');
        if (el.adminStockAlertsList) {
          el.adminStockAlertsList.innerHTML = alerts.map((a) => `
            <div class="admin-prod-card" style="border-color: rgba(255, 69, 58, 0.3);">
              <div class="admin-prod-info">
                <div class="admin-prod-name">${escapeHtml(a.name)}</div>
                <div class="admin-prod-meta">
                  <span class="stock-tag out">${a.stock ?? a.available ?? 0} units remaining</span>
                </div>
              </div>
              <button type="button" class="btn-admin-action primary btn-quick-restock" data-product-id="${a.id}" data-product-name="${escapeHtml(a.name)}">⚡ Restock</button>
            </div>
          `).join('');

          el.adminStockAlertsList.querySelectorAll('.btn-quick-restock').forEach((b) => {
            b.addEventListener('click', () => {
              const pid = b.getAttribute('data-product-id');
              const pname = b.getAttribute('data-product-name');
              openRestockModal(pid, pname);
            });
          });
        }
      } else if (el.adminStockAlertsBox) {
        el.adminStockAlertsBox.classList.add('hidden');
      }

      // Top Sellers
      const tops = res.top_products || [];
      if (el.adminTopSellersList) {
        if (tops.length === 0) {
          el.adminTopSellersList.innerHTML = '<div class="admin-loading-row">No orders recorded in the last 7 days yet.</div>';
        } else {
          el.adminTopSellersList.innerHTML = tops.map((tp, idx) => `
            <div class="admin-prod-card">
              <div class="admin-prod-info">
                <div class="admin-prod-name">#${idx + 1} ${escapeHtml(tp.name)}</div>
                <div class="admin-prod-meta">
                  <span>${tp.units} sold</span>
                  <span>•</span>
                  <span>${formatMoney(tp.revenue)} revenue</span>
                </div>
              </div>
            </div>
          `).join('');
        }
      }
    } catch (err) {
      showToast('Error loading analytics: ' + err.message, 'error');
    }
  }

  // --- 2. Products & Inventory Management ---
  async function loadAdminProducts() {
    if (!el.adminProductsList) return;
    el.adminProductsList.innerHTML = '<div class="admin-loading-row">Loading inventory...</div>';

    try {
      const res = await api('/admin/products');
      state.adminState.products = res.products || [];
      state.adminState.categories = res.categories || [];

      // Populate category dropdown in New Product modal
      if (el.newProdCategorySelect) {
        el.newProdCategorySelect.innerHTML = (res.categories || []).map((c) => `
          <option value="${c.id}">${c.icon || '📦'} ${escapeHtml(c.name)}</option>
        `).join('');
      }

      renderAdminProductsList();
    } catch (err) {
      el.adminProductsList.innerHTML = `<div class="admin-loading-row" style="color:var(--apple-red);">Failed to load products: ${escapeHtml(err.message)}</div>`;
    }
  }

  function renderAdminProductsList() {
    if (!el.adminProductsList) return;
    const query = (el.adminProductSearchInput?.value || '').trim().toLowerCase();

    let prods = state.adminState.products || [];
    if (query) {
      prods = prods.filter((p) =>
        p.name.toLowerCase().includes(query) ||
        (p.category_name && p.category_name.toLowerCase().includes(query))
      );
    }

    if (prods.length === 0) {
      el.adminProductsList.innerHTML = '<div class="admin-loading-row">No products found matching your filter.</div>';
      return;
    }

    el.adminProductsList.innerHTML = prods.map((p) => {
      const stock = p.stock || 0;
      let stockClass = 'in';
      let stockText = `${stock} in stock`;
      if (stock === 0) {
        stockClass = 'out';
        stockText = 'Out of Stock';
      } else if (stock <= 3) {
        stockClass = 'low';
        stockText = `${stock} low stock`;
      }

      return `
        <div class="admin-prod-card" data-product-id="${p.id}">
          <div class="admin-prod-info">
            <div class="admin-prod-name">${escapeHtml(p.name)}</div>
            <div class="admin-prod-meta">
              <span>${p.category_icon || '📦'} ${escapeHtml(p.category_name || 'General')}</span>
              <span>•</span>
              <span class="stock-tag ${stockClass}">${stockText}</span>
              <span>•</span>
              <span style="font-weight:700; color:var(--text-primary);">${formatMoney(p.price)}</span>
              ${!p.active ? '<span class="stock-tag out" style="opacity:0.8;">Hidden</span>' : ''}
            </div>
          </div>
          <div class="admin-prod-actions">
            <button type="button" class="btn-admin-action primary btn-admin-restock" data-product-id="${p.id}" data-product-name="${escapeHtml(p.name)}">⚡ Restock</button>
            <button type="button" class="btn-admin-action btn-admin-toggle" data-product-id="${p.id}">${p.active ? '👁️ Hide' : '👁️ Show'}</button>
          </div>
        </div>
      `;
    }).join('');

    // Wire action buttons
    el.adminProductsList.querySelectorAll('.btn-admin-restock').forEach((b) => {
      b.addEventListener('click', () => {
        openRestockModal(b.getAttribute('data-product-id'), b.getAttribute('data-product-name'));
      });
    });

    el.adminProductsList.querySelectorAll('.btn-admin-toggle').forEach((b) => {
      b.addEventListener('click', async () => {
        const pid = b.getAttribute('data-product-id');
        try {
          haptic('medium');
          const res = await api(`/admin/products/${pid}/toggle`, { method: 'PATCH' });
          showToast(res.message, 'success');
          await loadAdminProducts();
          await fetchCatalog();
        } catch (e) {
          showToast('Toggle failed: ' + e.message, 'error');
        }
      });
    });
  }

  function openRestockModal(productId, productName) {
    if (el.restockProductId) el.restockProductId.value = productId;
    if (el.restockProductTitle) el.restockProductTitle.textContent = `Restock ${productName}`;
    if (el.restockCredsInput) el.restockCredsInput.value = '';
    openModal(el.adminRestockModal);
  }

  async function handleAdminSubmitRestock() {
    const pid = parseInt(el.restockProductId?.value, 10);
    const content = el.restockCredsInput?.value?.trim();

    if (!pid || !content) {
      showToast('Please paste at least one credential or key to add to stock.', 'warning');
      return;
    }

    try {
      haptic('medium');
      if (el.btnAdminSubmitRestock) {
        el.btnAdminSubmitRestock.disabled = true;
        el.btnAdminSubmitRestock.textContent = 'Encrypting & Storing...';
      }

      const res = await api('/admin/products/stock', {
        method: 'POST',
        body: JSON.stringify({ product_id: pid, content }),
      });

      showToast(`Added ${res.added_count} items! ${res.subscribers_notified} alert subscribers notified.`, 'success');
      closeModal(() => {
        openAdminModal('inventory');
      });
      await fetchCatalog();
    } catch (e) {
      showToast('Restock failed: ' + e.message, 'error');
    } finally {
      if (el.btnAdminSubmitRestock) {
        el.btnAdminSubmitRestock.disabled = false;
        el.btnAdminSubmitRestock.textContent = '🔒 Encrypt & Add to Stock';
      }
    }
  }

  async function handleAdminSubmitNewProduct() {
    const catId = parseInt(el.newProdCategorySelect?.value, 10);
    const name = el.newProdNameInput?.value?.trim();
    const price = parseFloat(el.newProdPriceInput?.value);
    const desc = el.newProdDescInput?.value?.trim() || '';
    const stock = el.newProdStockInput?.value?.trim() || '';

    if (!catId || !name || isNaN(price) || price <= 0) {
      showToast('Please provide a valid category, name, and positive price.', 'warning');
      return;
    }

    try {
      haptic('medium');
      if (el.btnAdminSubmitNewProduct) {
        el.btnAdminSubmitNewProduct.disabled = true;
        el.btnAdminSubmitNewProduct.textContent = 'Creating...';
      }

      const res = await api('/admin/products', {
        method: 'POST',
        body: JSON.stringify({
          category_id: catId,
          name,
          price,
          description: desc,
          initial_stock: stock,
        }),
      });

      showToast(res.message, 'success');
      closeModal(() => {
        openAdminModal('inventory');
      });
      await fetchCatalog();
    } catch (e) {
      showToast('Product creation failed: ' + e.message, 'error');
    } finally {
      if (el.btnAdminSubmitNewProduct) {
        el.btnAdminSubmitNewProduct.disabled = false;
        el.btnAdminSubmitNewProduct.textContent = '✨ Create & Publish Product';
      }
    }
  }



  // --- 4. Orders Vault & Customer Support Refunds ---
  async function loadAdminOrders() {
    if (!el.adminOrdersVaultList) return;
    el.adminOrdersVaultList.innerHTML = '<div class="admin-loading-row">Loading orders vault...</div>';

    const search = (el.adminOrderSearchInput?.value || '').trim();
    const qParam = search ? `?search=${encodeURIComponent(search)}` : '';

    try {
      const res = await api(`/admin/orders${qParam}`);
      state.adminState.orders = res.orders || [];

      if (state.adminState.orders.length === 0) {
        el.adminOrdersVaultList.innerHTML = '<div class="admin-loading-row">No orders found.</div>';
        return;
      }

      el.adminOrdersVaultList.innerHTML = state.adminState.orders.map((o) => {
        const dateStr = new Date(o.created_at).toLocaleString();
        const custName = o.customer.username ? `@${o.customer.username}` : (o.customer.name || `User #${o.customer.telegram_id}`);
        const isRefunded = o.status.toLowerCase() === 'refunded';

        let credsHtml = '';
        if (o.delivered_credentials && o.delivered_credentials.length > 0) {
          credsHtml = `
            <div class="admin-order-creds-box">
              <div style="font-size:10px; font-weight:700; color:var(--text-tertiary); margin-bottom:4px; text-transform:uppercase; letter-spacing:0.5px;">Decrypted Delivered Credentials:</div>
              <div style="font-family:var(--font-mono); font-size:11px; color:#30d158; word-break:break-all; max-height:80px; overflow-y:auto; line-height:1.4;">
                ${o.delivered_credentials.map((c) => escapeHtml(c)).join('<br>')}
              </div>
            </div>
          `;
        }

        return `
          <div class="admin-order-card" data-order-id="${o.id}">
            <div class="admin-order-top">
              <div>
                <span class="order-id-badge">#${escapeHtml(o.public_order_id)}</span>
                <span style="font-size:11px; color:var(--text-secondary); margin-left:6px;">${dateStr}</span>
              </div>
              <span class="order-status-badge status-${escapeHtml(o.status.toLowerCase())}">${escapeHtml(o.status.toUpperCase())}</span>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center;">
              <div>
                <div style="font-size:13px; font-weight:700; color:var(--text-primary);">${escapeHtml(o.product.name)}</div>
                <div style="font-size:11px; color:var(--text-secondary);">Customer: <strong>${escapeHtml(custName)}</strong> (ID: ${o.customer.telegram_id})</div>
              </div>
              <div style="font-size:15px; font-weight:800; color:var(--text-primary);">${formatMoney(o.amount)}</div>
            </div>

            ${credsHtml}

            <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:4px;">
              ${!isRefunded ? `
                <button type="button" class="btn-admin-action btn-admin-refund" data-order-id="${o.id}" data-amount="${o.amount}" style="color:var(--apple-orange); border-color:rgba(255,159,10,0.3);">
                  💸 1-Click Balance Refund
                </button>
              ` : `
                <span style="font-size:11px; color:var(--apple-orange); font-weight:600;">✓ Refunded to customer balance</span>
              `}
            </div>
          </div>
        `;
      }).join('');

      // Wire refund button
      el.adminOrdersVaultList.querySelectorAll('.btn-admin-refund').forEach((b) => {
        b.addEventListener('click', async () => {
          const oid = b.getAttribute('data-order-id');
          const amt = b.getAttribute('data-amount');
          if (!confirm(`Are you sure you want to refund ${formatMoney(amt)} to the customer's wallet balance? This action cannot be undone.`)) {
            return;
          }

          try {
            haptic('medium');
            b.disabled = true;
            b.textContent = 'Refunding...';
            const res = await api(`/admin/orders/${oid}/refund`, { method: 'POST' });
            showToast(res.message, 'success');
            await loadAdminOrders();
          } catch (e) {
            showToast('Refund failed: ' + e.message, 'error');
            b.disabled = false;
            b.textContent = '💸 1-Click Balance Refund';
          }
        });
      });
    } catch (err) {
      el.adminOrdersVaultList.innerHTML = `<div class="admin-loading-row" style="color:var(--apple-red);">Failed to load orders: ${escapeHtml(err.message)}</div>`;
    }
  }

  // --- 5. Broadcast Announcement ---
  async function handleAdminSendBroadcast() {
    const msg = el.adminBroadcastMessageInput?.value?.trim();
    if (!msg) {
      showToast('Please type an announcement message to broadcast.', 'warning');
      return;
    }

    if (!confirm('Are you sure you want to broadcast this message to ALL store customers on Telegram?')) {
      return;
    }

    try {
      haptic('heavy');
      if (el.btnAdminSendBroadcast) {
        el.btnAdminSendBroadcast.disabled = true;
        el.btnAdminSendBroadcast.textContent = '📡 Delivering announcement...';
      }

      const res = await api('/admin/broadcast', {
        method: 'POST',
        body: JSON.stringify({ message: msg }),
      });

      showToast(res.message, 'success');
      if (el.adminBroadcastMessageInput) el.adminBroadcastMessageInput.value = '';
    } catch (e) {
      showToast('Broadcast failed: ' + e.message, 'error');
    } finally {
      if (el.btnAdminSendBroadcast) {
        el.btnAdminSendBroadcast.disabled = false;
        el.btnAdminSendBroadcast.textContent = '🚀 Send Broadcast Now';
      }
    }
  }

  // --- Admin Event Listeners Binding ---
  if (el.adminModal) {
    el.adminModal.querySelectorAll('.admin-nav-tab').forEach((tabBtn) => {
      tabBtn.addEventListener('click', () => {
        haptic('selection');
        const tabName = tabBtn.getAttribute('data-admin-tab');
        if (tabName) switchAdminTab(tabName);
      });
    });
  }

  if (el.btnAdminOpenNewProductModal) {
    el.btnAdminOpenNewProductModal.addEventListener('click', () => {
      if (el.newProdNameInput) el.newProdNameInput.value = '';
      if (el.newProdPriceInput) el.newProdPriceInput.value = '';
      if (el.newProdDescInput) el.newProdDescInput.value = '';
      if (el.newProdStockInput) el.newProdStockInput.value = '';
      openModal(el.adminNewProductModal);
    });
  }
  if (el.btnAdminSubmitNewProduct) {
    el.btnAdminSubmitNewProduct.addEventListener('click', handleAdminSubmitNewProduct);
  }

  if (el.btnAdminSubmitRestock) {
    el.btnAdminSubmitRestock.addEventListener('click', handleAdminSubmitRestock);
  }



  if (el.adminProductSearchInput) {
    el.adminProductSearchInput.addEventListener('input', () => {
      renderAdminProductsList();
    });
  }

  if (el.adminOrderSearchInput) {
    let orderDebounce = null;
    el.adminOrderSearchInput.addEventListener('input', () => {
      clearTimeout(orderDebounce);
      orderDebounce = setTimeout(() => {
        loadAdminOrders();
      }, 300);
    });
  }

  if (el.btnAdminRefreshOrders) {
    el.btnAdminRefreshOrders.addEventListener('click', () => {
      haptic('light');
      loadAdminOrders();
    });
  }

  if (el.btnAdminSendBroadcast) {
    el.btnAdminSendBroadcast.addEventListener('click', handleAdminSendBroadcast);
  }

  // --- Clipboard Utility ---
  function copyToClipboard(text, successMessage = 'Copied!') {
    if (!text) return;
    if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard
        .writeText(text)
        .then(() => {
          haptic('light');
          showToast(successMessage, 'success');
        })
        .catch(() => {
          fallbackCopy(text, successMessage);
        });
    } else {
      fallbackCopy(text, successMessage);
    }
  }

  function fallbackCopy(text, successMessage) {
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.top = '0';
      ta.style.left = '0';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      const success = document.execCommand('copy');
      ta.remove();
      if (success) {
        haptic('light');
        showToast(successMessage, 'success');
      } else {
        showToast('Please copy manually', 'normal');
      }
    } catch {
      showToast('Please copy manually', 'normal');
    }
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
  loadStoreConfig();
  initAuth();
})();
