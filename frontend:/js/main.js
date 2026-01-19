document.addEventListener('DOMContentLoaded', () => {
    initializeTheme();
    initializeCart();
    initializeSearch();
    loadFeaturedProducts();
});

// Theme Toggle
function initializeTheme() {
    const themeToggle = document.getElementById('themeToggle');
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.body.setAttribute('data-theme', savedTheme);
    
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const currentTheme = document.body.getAttribute('data-theme');
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.body.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
        });
    }
}

// Cart Sidebar
function initializeCart() {
    const cartBtn = document.getElementById('cartBtn');
    const cartSidebar = document.getElementById('cartSidebar');
    const closeCart = document.getElementById('closeCart');
    
    if (cartBtn) {
        cartBtn.addEventListener('click', () => {
            cartSidebar.classList.add('active');
        });
    }
    
    if (closeCart) {
        closeCart.addEventListener('click', () => {
            cartSidebar.classList.remove('active');
        });
    }
    
    // Close on outside click
    document.addEventListener('click', (e) => {
        if (cartSidebar && cartSidebar.classList.contains('active')) {
            if (!cartSidebar.contains(e.target) && !cartBtn.contains(e.target)) {
                cartSidebar.classList.remove('active');
            }
        }
    });
}

// Search
function initializeSearch() {
    const searchInput = document.getElementById('searchInput');
    const searchBtn = document.getElementById('searchBtn');
    const searchSuggestions = document.getElementById('searchSuggestions');
    
    let searchTimeout;
    
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            const query = e.target.value.trim();
            
            if (query.length < 2) {
                searchSuggestions.classList.remove('active');
                return;
            }
            
            searchTimeout = setTimeout(() => {
                fetchSearchSuggestions(query);
            }, 300);
        });
        
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                performSearch();
            }
        });
    }
    
    if (searchBtn) {
        searchBtn.addEventListener('click', performSearch);
    }
}

async function fetchSearchSuggestions(query) {
    try {
        const response = await fetch(`${API_CONFIG.SEARCH_SERVICE}/api/search/suggestions?q=${encodeURIComponent(query)}`);
        const data = await response.json();
        
        const searchSuggestions = document.getElementById('searchSuggestions');
        if (data.suggestions && data.suggestions.length > 0) {
            searchSuggestions.innerHTML = data.suggestions.map(suggestion => `
                <div class="suggestion-item" onclick="selectSuggestion('${suggestion}')">${suggestion}</div>
            `).join('');
            searchSuggestions.classList.add('active');
        } else {
            searchSuggestions.classList.remove('active');
        }
    } catch (error) {
        console.error('Error fetching suggestions:', error);
    }
}

function selectSuggestion(suggestion) {
    const searchInput = document.getElementById('searchInput');
    searchInput.value = suggestion;
    performSearch();
}

function performSearch() {
    const searchInput = document.getElementById('searchInput');
    const query = searchInput.value.trim();
    
    if (query) {
        window.location.href = `products.html?search=${encodeURIComponent(query)}`;
    }
}

// Load Featured Products
async function loadFeaturedProducts() {
    const container = document.getElementById('featuredProducts');
    if (!container) return;
    
    try {
        container.innerHTML = '<p style="text-align: center; padding: 40px;">Loading products...</p>';
        
        const response = await fetch(`${API_CONFIG.PRODUCT_SERVICE}/api/products/featured`);
        const products = await response.json();
        
        if (products.length === 0) {
            container.innerHTML = '<p style="text-align: center; padding: 40px; color: var(--color-text-secondary);">No featured products available</p>';
            return;
        }
        
        container.innerHTML = products.map(product => createProductCard(product)).join('');
    } catch (error) {
        console.error('Error loading featured products:', error);
        container.innerHTML = '<p style="text-align: center; padding: 40px; color: var(--color-text-secondary);">Failed to load products</p>';
    }
}

// Create Product Card
function createProductCard(product) {
    return `
        <div class="product-card" onclick="window.location.href='product.html?id=${product.id}'">
            <img src="${product.image_url || 'https://via.placeholder.com/300'}" alt="${product.name}" class="product-image">
            <div class="product-info">
                <div class="product-name">${product.name}</div>
                <div class="product-brand">${product.brand || ''}</div>
                <div class="product-price">KES ${product.price.toLocaleString()}</div>
                <button class="add-to-cart" onclick="event.stopPropagation(); addToCart(${product.id}, '${product.name}', ${product.price}, '${product.image_url || ''}')">
                    Add to Cart
                </button>
            </div>
        </div>
    `;
}

// Add to Cart Function
function addToCart(id, name, price, image) {
    cart.addItem({
        id: id,
        name: name,
        price: price,
        image_url: image
    });
}

// API Helper Functions
async function apiRequest(url, options = {}) {
    const token = localStorage.getItem('access_token');
    
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    const response = await fetch(url, {
        ...options,
        headers
    });
    
    if (response.status === 401) {
        // Token expired, redirect to login
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        window.location.href = 'login.html';
        return;
    }
    
    return response;
}

// Check Authentication
function isAuthenticated() {
    return !!localStorage.getItem('access_token');
}

function getUser() {
    const user = localStorage.getItem('user');
    return user ? JSON.parse(user) : null;
}

function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    window.location.href = 'login.html';
}

// Format Currency
function formatCurrency(amount) {
    return `KES ${amount.toLocaleString()}`;
}

// Show/Hide Loading
function showLoading(container) {
    if (container) {
        container.innerHTML = '<div style="text-align: center; padding: 40px;"><div class="spinner"></div></div>';
    }
}

function showError(container, message) {
    if (container) {
        container.innerHTML = `<p style="text-align: center; padding: 40px; color: var(--color-text-secondary);">${message}</p>`;
    }
}