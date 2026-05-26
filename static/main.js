/* Nexus Games — front-end glue (server-driven, no localStorage cart) */

const NEXUS = (() => {
    const state = {
        csrfToken: window.NEXUS_CSRF || null,
        user: null,
    };

    // ── Toasts ─────────────────────────────────────────────────
    function ensureToastContainer() {
        let c = document.getElementById('toast-container');
        if (!c) {
            c = document.createElement('div');
            c.id = 'toast-container';
            c.className = 'toast-container';
            document.body.appendChild(c);
        }
        return c;
    }
    function toast(message, type = 'info', timeoutMs = 3000) {
        const c = ensureToastContainer();
        const t = document.createElement('div');
        t.className = `toast ${type}`;
        t.textContent = message;
        c.appendChild(t);
        setTimeout(() => {
            t.classList.add('fade');
            setTimeout(() => t.remove(), 450);
        }, timeoutMs);
    }

    // ── Fetch wrapper ──────────────────────────────────────────
    async function api(path, opts = {}) {
        const headers = Object.assign(
            { 'Content-Type': 'application/json' },
            opts.headers || {},
            state.csrfToken ? { 'X-CSRF-Token': state.csrfToken } : {}
        );
        const res = await fetch(path, {
            method: opts.method || 'GET',
            headers,
            credentials: 'same-origin',
            body: opts.body ? JSON.stringify(opts.body) : undefined,
        });
        let data;
        try { data = await res.json(); }
        catch { data = { success: false, message: `HTTP ${res.status}` }; }
        return { ok: res.ok, status: res.status, data };
    }

    // ── Auth check / nav setup ─────────────────────────────────
    async function checkAuth(redirectToLogin = true) {
        try {
            const { data } = await api('/api/user');
            if (data.csrf_token) state.csrfToken = data.csrf_token;
            if (!data.logged_in) {
                state.user = null;
                if (redirectToLogin) window.location.href = '/login';
                return null;
            }
            state.user = data.user;
            paintNav();
            return data.user;
        } catch (err) {
            console.error('Auth check failed:', err);
            if (redirectToLogin) window.location.href = '/login';
            return null;
        }
    }

    function paintNav() {
        const userInfo = document.getElementById('user-info');
        if (userInfo && state.user) {
            const adminBadge = state.user.is_admin
                ? '<span class="admin-badge">ADMIN</span>' : '';
            userInfo.innerHTML = `Welcome, <span class="nav-user">${escapeHtml(state.user.username)}</span> ${adminBadge}`;
        }
        const adminLink = document.getElementById('nav-admin');
        if (adminLink) adminLink.style.display = state.user && state.user.is_admin ? 'inline' : 'none';
    }

    // ── Cart count badge ───────────────────────────────────────
    async function refreshCartCount() {
        const badge = document.getElementById('cart-count');
        if (!badge) return;
        const { data } = await api('/api/cart');
        badge.textContent = data.success ? data.count : 0;
    }

    // ── Product grid (index.html) ──────────────────────────────
    let searchDebounce;
    function setupStoreFilters() {
        const grid = document.getElementById('product-grid');
        if (!grid) return;

        const filters = {
            search: '',
            category: '',
            min_price: '',
            max_price: '',
            sort: 'title',
        };

        const search = document.getElementById('search-bar');
        const cat = document.getElementById('filter-category');
        const minP = document.getElementById('filter-min-price');
        const maxP = document.getElementById('filter-max-price');
        const sort = document.getElementById('filter-sort');

        loadCategories();
        loadProducts();

        if (search) {
            search.addEventListener('input', e => {
                clearTimeout(searchDebounce);
                filters.search = e.target.value.trim();
                searchDebounce = setTimeout(loadProducts, 300);
            });
        }
        [cat, minP, maxP, sort].forEach(el => {
            if (!el) return;
            el.addEventListener('change', () => {
                filters.category  = cat ? cat.value : '';
                filters.min_price = minP ? minP.value : '';
                filters.max_price = maxP ? maxP.value : '';
                filters.sort      = sort ? sort.value : 'title';
                loadProducts();
            });
        });

        async function loadCategories() {
            if (!cat) return;
            const { data } = await api('/api/products/categories');
            if (data.success) {
                cat.innerHTML = '<option value="">All categories</option>' +
                    data.categories.map(c =>
                        `<option value="${escapeAttr(c)}">${escapeHtml(c)}</option>`
                    ).join('');
            }
        }

        async function loadProducts() {
            showSkeletons(grid, 6);
            const qs = new URLSearchParams();
            Object.entries(filters).forEach(([k, v]) => { if (v) qs.append(k, v); });
            const { data } = await api(`/api/products?${qs.toString()}`);
            if (!data.success) {
                grid.innerHTML = `<div class="empty"><h3>Failed to load products</h3></div>`;
                return;
            }
            renderProductGrid(grid, data.products);
        }
    }

    function showSkeletons(container, count) {
        let html = '<div class="skeleton-grid">';
        for (let i = 0; i < count; i++) {
            html += `<div class="skeleton-card">
                <div class="skel skel-img"></div>
                <div class="skel skel-line"></div>
                <div class="skel skel-line w-60"></div>
                <div class="skel skel-line w-40"></div>
                <div class="skel skel-btn"></div>
            </div>`;
        }
        html += '</div>';
        container.innerHTML = html;
    }

    function renderProductGrid(grid, products) {
        if (!products.length) {
            grid.innerHTML = `
                <div class="empty">
                    <div class="icon">🎮</div>
                    <h3>No games found</h3>
                    <p>Try a different search or clear your filters.</p>
                </div>`;
            return;
        }
        grid.innerHTML = '';
        products.forEach(p => {
            const stockLabel = p.stock <= 0
                ? '<p class="stock-bad">Out of stock</p>'
                : p.stock < 5 ? `<p class="stock-bad">Only ${p.stock} left!</p>` : '';
            const btnDisabled = p.stock <= 0 ? 'disabled' : '';
            const card = document.createElement('div');
            card.className = 'card';
            card.innerHTML = `
                <img class="product-image" src="/static/${encodeURI(p.image)}" alt="${escapeAttr(p.title)}" loading="lazy">
                <h3>${escapeHtml(p.title)}</h3>
                <div class="category">${escapeHtml(p.category)}</div>
                <div class="price">$${Number(p.price).toFixed(2)}</div>
                ${stockLabel}
                <div class="card-actions">
                    <button class="btn-add btn-block" data-add="${p.id}" ${btnDisabled}>Add to Cart</button>
                    <a class="btn-secondary btn-block" href="/product?id=${p.id}">View Details</a>
                </div>`;
            grid.appendChild(card);
        });
        grid.querySelectorAll('[data-add]').forEach(btn => {
            btn.addEventListener('click', () => addToCart(parseInt(btn.dataset.add, 10)));
        });
    }

    // ── Cart actions ───────────────────────────────────────────
    async function addToCart(productId) {
        const { data, status } = await api('/api/cart', { method: 'POST', body: { product_id: productId } });
        if (data.success) {
            toast('Added to cart', 'success');
            refreshCartCount();
        } else if (status === 401) {
            toast('Please log in to shop', 'error');
            window.location.href = '/login';
        } else {
            toast(data.message || 'Could not add to cart', 'error');
        }
    }

    async function removeFromCart(cartItemId) {
        const { data } = await api(`/api/cart/${cartItemId}`, { method: 'DELETE' });
        if (data.success) {
            toast('Removed', 'info');
            return true;
        }
        toast(data.message || 'Could not remove', 'error');
        return false;
    }

    async function clearCart() {
        const { data } = await api('/api/cart', { method: 'DELETE' });
        if (data.success) {
            toast('Cart cleared', 'info');
            return true;
        }
        toast(data.message || 'Could not clear cart', 'error');
        return false;
    }

    // ── Cart page render ───────────────────────────────────────
    async function renderCartPage() {
        const list = document.getElementById('cart-items');
        const totalEl = document.getElementById('cart-total');
        const checkoutBtn = document.getElementById('checkout-btn');
        if (!list) return;

        list.innerHTML = '<div class="empty"><span class="spinner"></span> Loading cart…</div>';
        const { data } = await api('/api/cart');
        if (!data.success) {
            list.innerHTML = `<div class="empty"><h3>Could not load cart</h3></div>`;
            return;
        }
        if (data.items.length === 0) {
            list.innerHTML = `
                <div class="empty">
                    <div class="icon">🛒</div>
                    <h3>Your cart is empty</h3>
                    <p>Browse the store to add some games.</p>
                    <p style="margin-top: 14px;"><a class="btn-add" href="/home">Shop now</a></p>
                </div>`;
            if (totalEl) totalEl.textContent = '0.00';
            if (checkoutBtn) checkoutBtn.style.display = 'none';
            return;
        }
        if (checkoutBtn) checkoutBtn.style.display = 'inline-block';
        list.innerHTML = '<div class="cart-list">' + data.items.map(it => `
            <div class="cart-row">
                <img src="/static/${encodeURI(it.image)}" alt="${escapeAttr(it.title)}" loading="lazy">
                <div class="info">
                    <h4>${escapeHtml(it.title)}</h4>
                    <div class="meta">${escapeHtml(it.category)}</div>
                </div>
                <div class="price">$${Number(it.price).toFixed(2)}</div>
                <button class="link-btn" data-remove="${it.cart_item_id}">Remove</button>
            </div>`).join('') + '</div>';
        if (totalEl) totalEl.textContent = Number(data.total).toFixed(2);
        list.querySelectorAll('[data-remove]').forEach(b => {
            b.addEventListener('click', async () => {
                const ok = await removeFromCart(parseInt(b.dataset.remove, 10));
                if (ok) { renderCartPage(); refreshCartCount(); }
            });
        });
    }

    // ── HTML helpers ───────────────────────────────────────────
    function escapeHtml(v) {
        return String(v ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }
    const escapeAttr = escapeHtml;

    return {
        state, api, toast, checkAuth, refreshCartCount,
        setupStoreFilters, addToCart, removeFromCart, clearCart,
        renderCartPage, escapeHtml, escapeAttr,
    };
})();

window.NEXUS = NEXUS;
