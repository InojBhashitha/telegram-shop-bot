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
    modalTitle: document.getElementById('modalTitle'),
    modalPrice: document.getElementById('modalPrice'),
    modalDescription: document.getElementById('modalDescription'),
    modalQtyMinus: document.getElementById('modalQtyMinus'),
    modalQtyPlus: document.getElementById('modalQtyPlus'),
    modalQtyValue: document.getElementById('modalQtyValue'),
    modalQtySubtotal: document.getElementById('modalQtySubtotal'),
    modalAddToCartBtn: document.getElementById('modalAddToCartBtn'),
    modalBuyNowBtn: document.getElementById('modalBuyNowBtn'),
    closeProductModal: document.getElementById('closeProductModal'),

    cartModal: document.getElementById('cartModal'),
    cartModalItemCount: document.getElementById('cartModalItemCount'),
    cartItemsList: document.getElementById('cartItemsList'),
    emptyCartView: document.getElementById('emptyCartView'),
    cartSummaryCard: document.getElementById('cartSummaryCard'),
    cartSubtotalAmount: document.getElementById('cartSubtotalAmount'),
    cartDiscountRow: document.getElementById('cartDiscountRow'),
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
    copyRefLinkBtn: document.getElementById('copyRefLinkBtn'),
    supportActionCard: document.getElementById('supportActionCard'),
    closeProfileModal: document.getElementById('closeProfileModal'),

    // Navigation Dock
    dockCatalogBtn: document.getElementById('dockCatalogBtn'),
    dockCartBtn: document.getElementById('dockCartBtn'),
    dockOrdersBtn: document.getElementById('dockOrdersBtn'),
    dockProfileBtn: document.getElementById('dockProfileBtn'),

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
        }),
      });

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

  function renderProducts() {
    let list = state.products;

    // Filter by Category
    if (state.activeCategory !== 'all') {
      list = list.filter((p) => String(p.category_id) === state.activeCategory);
    }

    // Filter by Search
    if (state.searchQuery.trim()) {
      const q = state.searchQuery.toLowerCase();
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          (p.description && p.description.toLowerCase().includes(q)) ||
          p.category_name.toLowerCase().includes(q)
      );
    }

    el.productCountBadge.textContent = `${list.length} available`;
    el.productsGrid.innerHTML = '';

    if (list.length === 0) {
      el.emptyCatalog.classList.remove('hidden');
      return;
    }
    el.emptyCatalog.classList.add('hidden');

    list.forEach((p) => {
      const card = document.createElement('div');
      card.className = 'product-card';
      card.dataset.productId = p.id;

      // Stock indicator classes
      let stockClass = 'in-stock';
      let stockText = `${p.stock} in stock`;
      if (p.stock === 0) {
        stockClass = 'out-of-stock';
        stockText = 'Sold Out';
      } else if (p.stock <= 2) {
        stockClass = 'low-stock';
        stockText = `Only ${p.stock} left`;
      }

      card.innerHTML = `
        <div class="card-top-row">
          <span class="category-tag">${p.category_icon || '📦'} ${p.category_name}</span>
          <span class="stock-indicator ${stockClass}">
            <span class="stock-dot"></span>
            ${stockText}
          </span>
        </div>
        <div class="card-info">
          <h3 class="card-title">${p.name}</h3>
          <p class="card-desc">${p.description || 'Instant digital credentials & keys.'}</p>
        </div>
        <div class="card-perk-badge">
          <span>⚡ Instant Key Delivery</span> • <span>🛡 24h Warranty</span>
        </div>
        <div class="card-bottom-row">
          <div class="card-price-block">
            <span class="price-currency">$</span>
            <span class="price-value">${parseFloat(p.price).toFixed(2)}</span>
          </div>
          <button class="btn-card-add" ${p.stock === 0 ? 'disabled' : ''} data-add-id="${p.id}">
            🛒 Add
          </button>
        </div>
      `;

      // Card tap opens Product Sheet
      card.addEventListener('click', (e) => {
        if (e.target.closest('.btn-card-add')) return; // Handled separately
        openProductSheet(p);
      });

      // Quick Add Button
      const addBtn = card.querySelector('.btn-card-add');
      if (addBtn && p.stock > 0) {
        addBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          quickAddToCart(p.id, 1);
        });
      }

      el.productsGrid.appendChild(card);
    });
  }

  // --- Product Sheet Modal ---
  function openProductSheet(prod) {
    state.selectedProduct = prod;
    state.modalQuantity = 1;

    el.modalCategory.textContent = `${prod.category_icon || '📦'} ${prod.category_name}`;
    el.modalTitle.textContent = prod.name;
    el.modalPrice.textContent = `$${parseFloat(prod.price).toFixed(2)}`;
    el.modalDescription.textContent = prod.description || 'Verified working digital accounts delivered instantly upon payment.';

    // Stock Badge
    let stockText = `${prod.stock} in stock`;
    if (prod.stock === 0) {
      stockText = 'Out of Stock';
      el.modalStockBadge.className = 'badge badge-stock stock-out';
      el.modalStockBadge.style.color = 'var(--rose)';
      el.modalAddToCartBtn.disabled = true;
      el.modalBuyNowBtn.disabled = true;
    } else {
      el.modalStockBadge.className = 'badge badge-stock';
      el.modalStockBadge.style.color = 'var(--emerald)';
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
      row.className = 'cart-item-card';
      row.innerHTML = `
        <div class="cart-item-left">
          <span class="cart-item-title">${item.product_name}</span>
          <span class="cart-item-price">$${parseFloat(item.unit_price).toFixed(2)} each</span>
        </div>
        <div class="cart-item-right">
          <div class="qty-stepper">
            <button class="btn-step btn-cart-dec" data-id="${item.product_id}" data-qty="${item.quantity - 1}">&minus;</button>
            <span class="step-value">${item.quantity}</span>
            <button class="btn-step btn-cart-inc" data-id="${item.product_id}" data-qty="${item.quantity + 1}">&plus;</button>
          </div>
          <span class="cart-item-subtotal">$${parseFloat(item.subtotal).toFixed(2)}</span>
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
    const discount = parseFloat(c.discount_amount || 0);
    if (discount > 0) {
      el.cartDiscountRow.classList.remove('hidden');
      el.cartDiscountAmount.textContent = `-$${discount.toFixed(2)}`;
    } else {
      el.cartDiscountRow.classList.add('hidden');
    }
    el.cartFinalAmount.textContent = `$${parseFloat(c.final_amount).toFixed(2)}`;
    el.btnCheckoutTotal.textContent = `$${parseFloat(c.final_amount).toFixed(2)}`;
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
  el.cryptoMethodOption.addEventListener('click', () => {
    el.cryptoMethodOption.classList.add('active');
    el.balanceMethodOption.classList.remove('active');
    el.cryptoMethodOption.querySelector('input').checked = true;
    haptic('selection');
  });

  el.balanceMethodOption.addEventListener('click', () => {
    el.balanceMethodOption.classList.add('active');
    el.cryptoMethodOption.classList.remove('active');
    el.balanceMethodOption.querySelector('input').checked = true;
    haptic('selection');
  });

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

      // OPTION B: CRYPTO PAYMENT INVOICE
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

  el.copyRefLinkBtn.addEventListener('click', () => {
    if (!state.user) return;
    const botUser = state.store?.support_username || 'CloudDealsBot';
    const link = `https://t.me/${botUser}?start=ref_${state.user.referral_code || state.user.telegram_id}`;
    copyToClipboard(link, 'Referral link copied! 🎁');
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
  el.dockCatalogBtn.addEventListener('click', () => {
    haptic('light');
    setActiveDockBtn(el.dockCatalogBtn);
    closeModal();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  el.dockCartBtn.addEventListener('click', () => {
    haptic('light');
    setActiveDockBtn(el.dockCartBtn);
    openCartSheet();
  });

  el.dockOrdersBtn.addEventListener('click', () => {
    haptic('light');
    setActiveDockBtn(el.dockOrdersBtn);
    openOrdersDrawer();
  });

  el.dockProfileBtn.addEventListener('click', () => {
    haptic('light');
    setActiveDockBtn(el.dockProfileBtn);
    openProfileDrawer();
  });

  function setActiveDockBtn(activeBtn) {
    document.querySelectorAll('.dock-btn').forEach((b) => b.classList.remove('active'));
    activeBtn.classList.add('active');
  }

  // --- Search & Filters ---
  el.searchInput.addEventListener('input', (e) => {
    state.searchQuery = e.target.value;
    el.clearSearchBtn.classList.toggle('hidden', !state.searchQuery);
    renderProducts();
  });

  el.clearSearchBtn.addEventListener('click', () => {
    el.searchInput.value = '';
    state.searchQuery = '';
    el.clearSearchBtn.classList.add('hidden');
    renderProducts();
    el.searchInput.focus();
  });

  el.resetFiltersBtn.addEventListener('click', () => {
    state.searchQuery = '';
    state.activeCategory = 'all';
    el.searchInput.value = '';
    el.clearSearchBtn.classList.add('hidden');
    renderCategories();
    renderProducts();
  });

  // --- Dev User Switcher (For Previewing in Desktop Browsers) ---
  if (el.devSwitchUserBtn) {
    el.devSwitchUserBtn.addEventListener('click', () => {
      const newId = parseInt(el.devUserIdInput.value, 10);
      if (newId) {
        state.telegramId = newId;
        state.initData = '';
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
