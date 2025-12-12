document.addEventListener('DOMContentLoaded', () => {
  const listEl = document.getElementById('events');
  const qIn = document.getElementById('q');
  const btn = document.getElementById('searchBtn');
  const authUserEl = document.getElementById('authUser');
  const logoutBtn = document.getElementById('logoutBtn');
  const autocompleteList = document.getElementById('autocompleteList');
  const searchWrapper = document.querySelector('.search-input-wrapper');

  const MIN_AUTOCOMPLETE_CHARS = 2;
  let autocompleteDebounceId;
  let autocompleteController;
  let currentSuggestions = [];
  let activeSuggestionIndex = -1;

  fetch('/auth/me').then(r => r.json()).then(me => {
    if (!me.authenticated) {
      location.href = '/login';
      return;
    }
    authUserEl.textContent = `Logged in (${me.userType || 'user'})`;
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

  function clearSuggestions(){
    if(!autocompleteList) return;
    autocompleteList.innerHTML = '';
    autocompleteList.classList.remove('visible');
    currentSuggestions = [];
    activeSuggestionIndex = -1;
  }

  function setActiveSuggestion(newIndex){
    if(!autocompleteList || !currentSuggestions.length) return;
    const items = autocompleteList.querySelectorAll('.autocomplete-item');
    if(!items.length) return;
    if(newIndex < 0) newIndex = items.length - 1;
    if(newIndex >= items.length) newIndex = 0;
    items.forEach(item => item.classList.remove('active'));
    const target = items[newIndex];
    if(target){
      target.classList.add('active');
      target.scrollIntoView({block:'nearest'});
    }
    activeSuggestionIndex = newIndex;
  }

  function selectSuggestion(idx){
    const suggestion = currentSuggestions[idx];
    if(!suggestion) return;
    qIn.value = suggestion.text || '';
    clearSuggestions();
    load(qIn.value.trim());
  }

  function renderSuggestions(items){
    if(!autocompleteList) return;
    autocompleteList.innerHTML = '';
    currentSuggestions = items;
    activeSuggestionIndex = -1;
    if(!items.length){
      autocompleteList.classList.remove('visible');
      return;
    }
    items.forEach((item, idx) => {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = 'autocomplete-item';
      row.dataset.index = String(idx);
      const textSpan = document.createElement('span');
      textSpan.textContent = item.text || '';
      row.appendChild(textSpan);
      const typeSpan = document.createElement('span');
      typeSpan.className = 'autocomplete-item-type';
      typeSpan.textContent = (item.type || 'match').toUpperCase();
      row.appendChild(typeSpan);
      row.addEventListener('mousedown', (event) => {
        event.preventDefault();
        selectSuggestion(idx);
      });
      autocompleteList.appendChild(row);
    });
    autocompleteList.classList.add('visible');
  }

  async function requestAutocomplete(term){
    if(!autocompleteList) return;
    if(autocompleteController){
      autocompleteController.abort();
    }
    autocompleteController = new AbortController();
    try {
      const response = await fetch(`/search/autocomplete?q=${encodeURIComponent(term)}`, {
        signal: autocompleteController.signal
      });
      if(!response.ok){
        clearSuggestions();
        return;
      }
      const suggestions = await response.json();
      const normalized = Array.isArray(suggestions) ? suggestions : [];
      const eventMatches = normalized.filter(item => item && item.type === 'event');
      const list = (eventMatches.length ? eventMatches : normalized).slice(0, 10);
      renderSuggestions(list);
    } catch (err) {
      if (err.name === 'AbortError') return;
      console.error('Autocomplete error:', err);
    }
  }

  // ATNAUJINTA load funkcija su forceRefresh parametru
  async function load(q, forceRefresh = false) {
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

  // NAUJAS: Refresh mygtukas
  const refreshBtn = document.createElement('button');
  refreshBtn.textContent = 'Refresh';
  refreshBtn.className = 'btn secondary';
  refreshBtn.style.marginLeft = '10px';
  refreshBtn.onclick = () => {
    console.log('🔄 Force refreshing events...');
    load(qIn.value.trim(), true);
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
      setTimeout(() => load(qIn.value.trim(), true), 500);
    }
  });

  // NAUJAS: Auto refresh grįžus iš kito puslapio (back button)
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) {
      console.log('⬅️ Back button detected - refreshing...');
      setTimeout(() => load(qIn.value.trim(), true), 200);
    }
  });

  if(qIn){
    qIn.addEventListener('input', () => {
      const term = qIn.value.trim();
      if(term.length < MIN_AUTOCOMPLETE_CHARS){
        if(autocompleteController) autocompleteController.abort();
        clearSuggestions();
        return;
      }
      if(autocompleteDebounceId) clearTimeout(autocompleteDebounceId);
      autocompleteDebounceId = setTimeout(() => requestAutocomplete(term), 180);
    });

    qIn.addEventListener('keydown', (event) => {
      if(event.key === 'ArrowDown' && currentSuggestions.length){
        event.preventDefault();
        setActiveSuggestion(activeSuggestionIndex + 1);
      } else if(event.key === 'ArrowUp' && currentSuggestions.length){
        event.preventDefault();
        setActiveSuggestion(activeSuggestionIndex - 1);
      } else if(event.key === 'Enter'){
        event.preventDefault();
        if(activeSuggestionIndex >= 0){
          selectSuggestion(activeSuggestionIndex);
        } else {
          clearSuggestions();
          load(qIn.value.trim());
        }
      } else if(event.key === 'Escape'){
        clearSuggestions();
      }
    });
  }

  document.addEventListener('click', (event) => {
    if(searchWrapper && !searchWrapper.contains(event.target)){
      clearSuggestions();
    }
  });

  btn.addEventListener('click', () => {
    clearSuggestions();
    load(qIn.value.trim());
  });
  load('');
  updateCartBadge();
});

function escapeHtml(s){ return String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }