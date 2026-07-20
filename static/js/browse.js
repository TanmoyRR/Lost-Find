document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('search-input');
    const filterSelects = document.querySelectorAll('.filter-select');
    const postsContainer = document.getElementById('posts-container');
    const loadingEl = document.getElementById('loading-indicator');
    const errorEl = document.getElementById('error-indicator');
    const emptyEl = document.getElementById('empty-state');
    const resultsInfo = document.getElementById('results-info');

    if (!postsContainer) return;

    let debounceTimer;
    let currentRequest = null;

    function fetchPosts() {
        const params = new URLSearchParams();
        if (searchInput) params.set('q', searchInput.value);
        filterSelects.forEach(sel => {
            if (sel.value) params.set(sel.name, sel.value);
        });

        if (loadingEl) loadingEl.classList.remove('hidden');
        if (errorEl) errorEl.classList.add('hidden');
        if (emptyEl) emptyEl.classList.add('hidden');

        if (currentRequest) currentRequest.abort();
        const controller = new AbortController();
        currentRequest = controller;

        fetch(`/api/posts/?${params.toString()}`, { signal: controller.signal })
            .then(r => r.json())
            .then(data => {
                if (loadingEl) loadingEl.classList.add('hidden');
                if (data && data.posts) {
                    renderPosts(data.posts);
                    if (resultsInfo) {
                        resultsInfo.textContent = `${data.count || data.posts.length} post${(data.count || data.posts.length) !== 1 ? 's' : ''} found`;
                    }
                    if (data.posts.length === 0 && emptyEl) emptyEl.classList.remove('hidden');
                }
            })
            .catch(err => {
                if (err.name === 'AbortError') return;
                if (loadingEl) loadingEl.classList.add('hidden');
                if (errorEl) errorEl.classList.remove('hidden');
                if (postsContainer) postsContainer.innerHTML = '';
            });
    }

    function renderPosts(posts) {
        if (!postsContainer) return;
        if (!posts || posts.length === 0) {
            postsContainer.innerHTML = '<div class="col-span-full text-center py-16 text-gray-400"><i class="bi bi-inbox text-5xl block mb-4"></i><p class="text-lg font-medium text-gray-500 mb-1">No posts found</p><p class="text-sm">Try adjusting your filters or search terms</p></div>';
            return;
        }
        let html = '';
        posts.forEach(p => {
            const typeLabel = p.type || p.post_type || 'unknown';
            const statusLabel = p.status || 'open';
            const locationName = p.location || p.location_name || 'N/A';
            const dateStr = p.date || p.date_lost_found || '';
            const imageUrl = p.image || '';
            html += `
                <a href="/post/${p.id}/" class="block bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden hover:shadow-lg hover:-translate-y-1 transition-all duration-300 group">
                    ${imageUrl ? `<div class="h-48 bg-gray-100 overflow-hidden"><img src="${imageUrl}" alt="${p.title}" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"></div>` : `<div class="h-48 bg-gradient-to-br from-indigo-50 to-purple-50 flex items-center justify-center"><i class="bi bi-image text-5xl text-gray-300"></i></div>`}
                    <div class="p-4">
                        <div class="flex items-center gap-2 mb-2">
                            <span class="text-xs font-medium px-2 py-0.5 rounded-full ${typeLabel === 'lost' ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-700'}">${typeLabel}</span>
                            <span class="text-xs font-medium px-2 py-0.5 rounded-full ${statusLabel === 'open' ? 'bg-amber-100 text-amber-700' : statusLabel === 'resolved' ? 'bg-emerald-100 text-emerald-700' : 'bg-blue-100 text-blue-700'}">${statusLabel}</span>
                        </div>
                        <h3 class="font-semibold text-gray-800 text-sm mb-1 line-clamp-1">${p.title}</h3>
                        <p class="text-xs text-gray-500 line-clamp-2">${p.description || ''}</p>
                        <div class="flex items-center gap-3 mt-3 text-xs text-gray-400">
                            <span><i class="bi bi-geo-alt mr-1"></i>${locationName}</span>
                            <span><i class="bi bi-calendar mr-1"></i>${dateStr}</span>
                        </div>
                    </div>
                </a>
            `;
        });
        postsContainer.innerHTML = html;
    }

    if (searchInput) {
        searchInput.addEventListener('input', function() {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(fetchPosts, 300);
        });
    }
    filterSelects.forEach(sel => {
        sel.addEventListener('change', fetchPosts);
    });
});