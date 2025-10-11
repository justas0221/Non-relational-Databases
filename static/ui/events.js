document.addEventListener('DOMContentLoaded', () => {
  const listEl = document.getElementById('events');
  const qIn = document.getElementById('q');
  const btn = document.getElementById('searchBtn');
  const authUserEl = document.getElementById('authUser');
  const logoutBtn = document.getElementById('logoutBtn');

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

  async function load(q) {
    listEl.innerHTML = 'Loading...';
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    params.set('limit', '1000');
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
      c.innerHTML = `<h3>${escapeHtml(ev.title || 'Untitled')}</h3>
                     <div class="meta">📅 ${eventDate}</div>
                     <div style="margin-top:8px">
                       <a href="/ui/event?eventId=${encodeURIComponent(ev._id)}" class="btn primary">View & Buy tickets</a>
                     </div>`;
      listEl.appendChild(c);
    });
  }

  btn.addEventListener('click', () => load(qIn.value.trim()));
  load('');
  updateCartBadge();
});

function escapeHtml(s){ return String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }