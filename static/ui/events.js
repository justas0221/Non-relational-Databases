document.addEventListener('DOMContentLoaded', () => {
  const listEl = document.getElementById('events');
  const qIn = document.getElementById('q');
  const btn = document.getElementById('searchBtn');
  const authUserEl = document.getElementById('authUser');
  const logoutBtn = document.getElementById('logoutBtn');
  const recSection = document.getElementById('neo4jRecommendations');
  const recList = document.getElementById('neo4jRecList');
  const recStatus = document.getElementById('neo4jStatus');
  const recRefreshBtn = document.getElementById('neo4jRefresh');
  const recSourceSelect = document.getElementById('neo4jSource');
  const explainPanel = document.getElementById('neo4jExplain');
  const explainBody = document.getElementById('neo4jExplainBody');
  const explainTitle = document.getElementById('neo4jExplainTitle');
  const explainCloseBtn = document.getElementById('neo4jExplainClose');

  const RECOMMENDATION_ENDPOINTS = {
    user: (id) => `/api/recommendations/user/${id}`,
    nearby: (id) => `/api/recommendations/user/${id}/nearby`,
    deep: (id) => `/api/recommendations/user/${id}/deep`,
  };

  const RECOMMENDATION_LABELS = {
    user: 'Similar fans also liked',
    nearby: 'Events at venues you visited',
    deep: 'Deep graph wanderings',
  };

  let currentUserId = null;

  fetch('/auth/me').then(r => r.json()).then(me => {
    if (!me.authenticated) {
      location.href = '/login';
      return;
    }
    currentUserId = me.userId;
    authUserEl.textContent = `Logged in (${me.userType || 'user'})`;
    loadGraphRecommendations();
  }).catch(()=> location.href='/login');

  logoutBtn.addEventListener('click', async () => {
    try { await fetch('/auth/logout', {method:'POST'}); } catch(e){}
    location.href = '/login';
  });

  async function updateCartBadge(){
    try {
      const r = await fetch('/cart');
      if(!r.ok) return; const j = await r.json();
      let badge = document.getElementById('cartBadge');
      const cartLink = document.querySelector('a[href="/ui/cart"]');
      if(cartLink && !badge){
        badge = document.createElement('span');
        badge.id='cartBadge';
        badge.style.background='#ff0066';
        badge.style.color='#fff';
        badge.style.fontSize='10px';
        badge.style.padding='2px 5px';
        badge.style.borderRadius='10px';
        badge.style.marginLeft='4px';
        cartLink.appendChild(badge);
      }
      if(badge) badge.textContent = j.count || 0;
    } catch(err){}
  }

  // ATNAUJINTA load funkcija su forceRefresh parametru
  async function loadEvents(q, forceRefresh = false) {
    listEl.innerHTML = 'Loading...';
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    params.set('limit', '1000');
    
    // Pridėti cache bypass jei force refresh
    if (forceRefresh) {
      params.set('_refresh', Date.now());
    }
    
    try {
      const r = await fetch('/events?' + params.toString());
      if (!r.ok) { listEl.textContent = 'Failed to load events'; return; }
      const j = await r.json();
      const data = j.data || [];
      if (!data.length) { listEl.innerHTML = '<p>No events</p>'; return; }
      listEl.innerHTML = '';
      data.forEach(ev => {
        const c = document.createElement('div');
        c.className = 'card';
        const eventDate = new Date(ev.eventDate).toLocaleString('en-US', {
          weekday: 'short',
          year: 'numeric',
          month: 'short',
          day: 'numeric',
          hour: 'numeric',
          minute: '2-digit',
          hour12: true
        });
        const categoryBadge = ev.category ? `<span style="display:inline-block;background:#6c757d;color:#fff;font-size:11px;padding:3px 8px;border-radius:12px;margin-left:8px;">${escapeHtml(ev.category)}</span>` : '';
        c.innerHTML = `<h3>${escapeHtml(ev.title || 'Untitled')}${categoryBadge}</h3>
                       <div class="meta">${eventDate}</div>
                       <div style="margin-top:8px">
                         <a href="/ui/event?eventId=${encodeURIComponent(ev._id)}" class="btn primary">View & Buy tickets</a>
                       </div>`;
        listEl.appendChild(c);
      });
    } catch (err) {
      console.error('Events load error:', err);
      listEl.textContent = 'Error loading events';
    }
  }

  async function loadGraphRecommendations() {
    if (!recSection || !recList) return;
    if (!currentUserId) {
      recList.innerHTML = '';
      if (recStatus) recStatus.textContent = 'Sign in to view Neo4j suggestions.';
      return;
    }

    const source = recSourceSelect ? recSourceSelect.value : 'user';
    const endpoint = RECOMMENDATION_ENDPOINTS[source] || RECOMMENDATION_ENDPOINTS.user;
    if (recStatus) recStatus.textContent = 'Loading Neo4j recommendations...';
    recList.innerHTML = '<p>Loading graph data...</p>';

    try {
      const r = await fetch(endpoint(currentUserId));
      if (!r.ok) throw new Error('Neo4j API failed');
      const rows = await r.json();
      if (!Array.isArray(rows) || !rows.length) {
        recList.innerHTML = '<p>No recommendations yet. Interact with more events to train the graph.</p>';
        if (recStatus) recStatus.textContent = 'Graph ready but no suggestions yet.';
        return;
      }

      recList.innerHTML = '';
      rows.forEach((rec) => {
        const eventId = rec.eventId || rec.id;
        const card = document.createElement('div');
        card.className = 'card';
        card.style.padding = '12px';

        const title = document.createElement('h4');
        title.textContent = rec.title || 'Untitled event';
        title.style.margin = '0 0 6px 0';
        card.appendChild(title);

        const meta = document.createElement('div');
        meta.className = 'meta';
        meta.style.fontSize = '12px';
        const metaBits = [];
        if (rec.category) metaBits.push(rec.category);
        if (rec.eventDate) {
          const dateLabel = formatShortDate(rec.eventDate);
          if (dateLabel) metaBits.push(dateLabel);
        }
        const score = rec.score ?? rec.relevance ?? rec.deepScore;
        if (typeof score !== 'undefined') metaBits.push(`score: ${score}`);
        meta.textContent = metaBits.join(' • ');
        card.appendChild(meta);

        const actions = document.createElement('div');
        actions.style.display = 'flex';
        actions.style.flexWrap = 'wrap';
        actions.style.gap = '8px';
        actions.style.marginTop = '12px';

        const openLink = document.createElement('a');
        openLink.className = 'btn primary';
        openLink.textContent = 'View event';
        openLink.href = eventId ? `/ui/event?eventId=${encodeURIComponent(eventId)}` : '#';
        openLink.style.textDecoration = 'none';
        actions.appendChild(openLink);

        if (eventId) {
          const explainBtn = document.createElement('button');
          explainBtn.className = 'btn secondary';
          explainBtn.textContent = 'Why this?';
          explainBtn.addEventListener('click', () => explainRecommendation(eventId, rec.title));
          actions.appendChild(explainBtn);
        }

        card.appendChild(actions);
        recList.appendChild(card);
      });

      if (recStatus) {
        const label = RECOMMENDATION_LABELS[source] || 'Graph suggestions';
        recStatus.textContent = `${label} · ${recList.children.length} result${recList.children.length === 1 ? '' : 's'}`;
      }
    } catch (err) {
      console.error('Neo4j recommendations error:', err);
      recList.innerHTML = '<p class="error">Failed to load graph recommendations.</p>';
      if (recStatus) recStatus.textContent = 'Neo4j unavailable right now.';
    }
  }

  async function explainRecommendation(eventId, title) {
    if (!explainPanel || !currentUserId || !eventId) return;
    explainPanel.style.display = 'block';
    if (explainTitle) explainTitle.textContent = title ? `Why "${title}"?` : 'Recommendation insight';
    if (explainBody) explainBody.textContent = 'Loading graph path...';

    try {
      const resp = await fetch(`/api/recommendations/explain/${currentUserId}/${eventId}`);
      if (resp.status === 404) {
        if (explainBody) explainBody.textContent = 'Neo4j could not find a connecting path.';
        return;
      }
      if (!resp.ok) throw new Error('Explain fetch failed');
      const data = await resp.json();
      if (!data || !data.path) {
        if (explainBody) explainBody.textContent = 'No explanation returned.';
        return;
      }
      if (explainBody) explainBody.textContent = formatExplainPath(data.path);
    } catch (err) {
      console.error('Neo4j explain error:', err);
      if (explainBody) explainBody.textContent = 'Failed to load path explanation.';
    }
  }

  function formatExplainPath(nodes) {
    if (!Array.isArray(nodes) || !nodes.length) return 'No graph path was returned.';
    return nodes.map((node) => {
      if (!node) return '·';
      if (node.type === 'User') return `User #${node.id}`;
      if (node.type === 'Event') return `Event: ${node.title || node.id}`;
      if (node.type === 'Category') return `Category: ${node.name || node.id}`;
      return node.type || 'Node';
    }).join(' → ');
  }

  function formatShortDate(dateStr) {
    if (!dateStr) return null;
    const dt = new Date(dateStr);
    if (Number.isNaN(dt.getTime())) return null;
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  }

  // NAUJAS: Refresh mygtukas
  const refreshBtn = document.createElement('button');
  refreshBtn.textContent = 'Refresh';
  refreshBtn.className = 'btn secondary';
  refreshBtn.style.marginLeft = '10px';
  refreshBtn.onclick = () => {
    console.log('🔄 Force refreshing events...');
    loadEvents(qIn.value.trim(), true);
    loadGraphRecommendations();
  };
  
  // Pridėti refresh mygtuką šalia search mygtuko
  const searchContainer = btn.parentElement || document.querySelector('.searchbar') || document.querySelector('.controls');
  if (searchContainer) {
    searchContainer.appendChild(refreshBtn);
  }

  // NAUJAS: Auto refresh grįžus į tab'ą
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      console.log('📱 Tab became visible - auto refreshing...');
      setTimeout(() => {
        loadEvents(qIn.value.trim(), true);
        loadGraphRecommendations();
      }, 500);
    }
  });

  // NAUJAS: Auto refresh grįžus iš kito puslapio (back button)
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) {
      console.log('⬅️ Back button detected - refreshing...');
      setTimeout(() => {
        loadEvents(qIn.value.trim(), true);
        loadGraphRecommendations();
      }, 200);
    }
  });

  if (recRefreshBtn) {
    recRefreshBtn.addEventListener('click', () => loadGraphRecommendations());
  }

  if (recSourceSelect) {
    recSourceSelect.addEventListener('change', () => loadGraphRecommendations());
  }

  if (explainCloseBtn && explainPanel) {
    explainCloseBtn.addEventListener('click', () => {
      explainPanel.style.display = 'none';
      if (explainBody) explainBody.textContent = '';
    });
  }

  btn.addEventListener('click', () => loadEvents(qIn.value.trim()));
  loadEvents('');
  updateCartBadge();
});

function escapeHtml(s){ return String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }