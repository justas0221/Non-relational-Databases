document.addEventListener('DOMContentLoaded', () => {
  fetch('/auth/me').then(r => r.json()).then(me => {
    if (!me.authenticated) {
      location.href = '/login';
    } else {
      const authUserEl = document.getElementById('authUser');
      if (authUserEl) authUserEl.textContent = `Logged in (${me.userType || 'user'})`;
      const logoutBtn = document.getElementById('logoutBtn');
      if (logoutBtn) logoutBtn.addEventListener('click', async () => { try { await fetch('/auth/logout',{method:'POST'});} catch(e){} location.href='/login'; });
      initPage();
    }
  }).catch(() => location.href = '/login');

  function initPage() {
  const params = new URLSearchParams(location.search);
  const eventId = params.get('eventId');

  const titleEl = document.getElementById('title');
  const subtitleEl = document.getElementById('subtitle');
  const infoEl = document.getElementById('info');
  const ticketsEl = document.getElementById('tickets');
  const dropdownEl = document.getElementById('ticketsDropdown');
  const form = document.getElementById('buyForm');

  const filterSeat = document.getElementById('filterSeat');
  const filterMin = document.getElementById('filterMin');
  const filterMax = document.getElementById('filterMax');
  const applyBtn = document.getElementById('applyFilters');
  const resetBtn = document.getElementById('resetFilters');

  if (!eventId) {
    titleEl.textContent = 'No event selected';
    subtitleEl.textContent = '';
    if (infoEl) infoEl.style.display = 'none';
    return;
  }

  const currencyFormatter = new Intl.NumberFormat(undefined, { style: 'currency', currency: 'EUR' });

  function formatPrice(n) {
    if (n === null || n === undefined || isNaN(Number(n))) return null;
    return currencyFormatter.format(Number(n));
  }

  function ensureTotalElement() {
    let el = document.getElementById('orderTotal');
    if (!el && form) {
      el = document.createElement('div');
      el.id = 'orderTotal';
      el.style.marginTop = '10px';
      el.style.fontWeight = '700';
      el.style.fontSize = '15px';
      form.querySelector('.actions')?.before(el);
    }
    return el;
  }

  function updateTotal() {
    const totalEl = ensureTotalElement();
    if (!totalEl) return;
    try {
      let total = 0;
      const gaQtyInput = document.getElementById('gaQty');
      if (gaQtyInput) {
        const qty = Math.max(1, Math.min(Number(gaQtyInput.value)||1, Number(gaQtyInput.max)||1));
        const price = Number(gaQtyInput.dataset.price || 0);
        total += qty * price;
      }
      const checked = Array.from(form.querySelectorAll('input[name="ticket"]:checked'));
      checked.forEach(i => { const p = Number(i.dataset.price || 0); if(!isNaN(p)) total += p; });
      totalEl.textContent = total > 0 ? `Order total: ${formatPrice(total)}` : 'Order total: —';
    } catch (err) {
      console.error('updateTotal error', err);
      totalEl.textContent = 'Order total: —';
    }
  }
  async function loadEvent() {
    try {
      let ev = null;
      try {
        const rId = await fetch('/events/' + encodeURIComponent(eventId));
        if (rId.ok) ev = await rId.json();
      } catch (err) { }


      if (!ev) {
        const resp = await fetch('/events?limit=1000');
        if (!resp.ok) { infoEl.textContent = 'Failed to load event'; return; }
        const je = await resp.json();
        ev = (je.data || []).find(e => e._id === eventId);
      }

      if (!ev) { 
        titleEl.textContent = 'Event not found';
        subtitleEl.textContent = '';
        infoEl.style.display = 'none'; 
        return; 
      }
      
      const categoryBadge = ev.category ? `<span style="display:inline-block;background:#6c757d;color:#fff;font-size:13px;padding:4px 10px;border-radius:12px;margin-left:10px;">${escapeHtml(ev.category)}</span>` : '';
      titleEl.innerHTML = `${escapeHtml(ev.title || 'Event')}${categoryBadge}`;
      const when = ev.eventDate ? new Date(ev.eventDate).toLocaleString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
      }) : '';
      subtitleEl.textContent = when;
      
      if (ev.location || ev.description) {
        infoEl.innerHTML = `${ev.location ? `📍 ${escapeHtml(ev.location)}` : ''}${ev.description ? `<br>ℹ️ ${escapeHtml(ev.description)}` : ''}`;
        infoEl.style.display = 'flex';
      } else {
        infoEl.style.display = 'none';
      }
  await loadTickets();
    } catch (err) {
      console.error('loadEvent error', err);
      titleEl.textContent = 'Error loading event';
      subtitleEl.textContent = 'See console for details';
      infoEl.style.display = 'none';
    }
  }

  async function loadTickets() {
    try {
      ticketsEl.innerHTML = 'Loading tickets...';
      if (dropdownEl) dropdownEl.innerHTML = '';

      const query = new URLSearchParams({ eventId, limit: 1000 });
      if (filterSeat?.value) query.append('seat', filterSeat.value.trim());
      if (filterMin?.value) query.append('minPrice', filterMin.value.trim());
      if (filterMax?.value) query.append('maxPrice', filterMax.value.trim());

      const r = await fetch('/tickets?' + query.toString());
      if (!r.ok) { ticketsEl.textContent = 'Failed to load tickets'; return; }
      const j = await r.json();
      let data = j.data || [];
      ticketsEl.innerHTML = '';

      if (!data.length) {
        ticketsEl.innerHTML = '<div class="meta">No tickets available</div>';
        if (dropdownEl) dropdownEl.innerHTML = '';
        updateTotal();
        return;
      }

      data.sort((a, b) => {
        const aGA = Boolean(a.isGeneralAdmission || (a.type && String(a.type).toLowerCase().includes('ga')));
        const bGA = Boolean(b.isGeneralAdmission || (b.type && String(b.type).toLowerCase().includes('ga')));
        if (aGA !== bGA) return aGA ? -1 : 1;
        const aKey = (a.seat || a.type || '').toString().toUpperCase();
        const bKey = (b.seat || b.type || '').toString().toUpperCase();
        return aKey.localeCompare(bKey, undefined, { numeric: true, sensitivity: 'base' });
      });

      const gaTickets = data.filter(t => t.type && String(t.type).toUpperCase()==='GA');
      const seatTickets = data.filter(t => !(t.type && String(t.type).toUpperCase()==='GA'));
      if (gaTickets.length) {
        const gaAvail = gaTickets.reduce((s,x)=> s + (x.available || 1), 0);
        const priceNum = (typeof gaTickets[0].price === 'number') ? gaTickets[0].price : Number(gaTickets[0].price)||0;
        const priceLabel = formatPrice(priceNum);
        const gaDiv = document.createElement('div');
        gaDiv.className='ticket';
        gaDiv.innerHTML = `<div class="ticket-info" style="display:flex;flex-direction:column;gap:6px">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:12px">
              <div class="ticket-type" style="font-size:16px">General Admission</div>
              <div class="meta" style="font-weight:600">${priceLabel}</div>
            </div>
            <div style="display:flex;align-items:center;flex-wrap:wrap;gap:12px;margin-top:4px">
              <label style="display:flex;align-items:center;gap:6px">Quantity:
                <input type="number" id="gaQty" data-price="${priceNum}" min="1" max="${gaAvail}" value="1" style="width:80px;padding:4px">
              </label>
              <span class="meta" style="background:#eef;padding:4px 10px;border-radius:14px;font-size:12px">Available: ${gaAvail}</span>
              <button type="button" id="gaAddBtn" class="btn secondary" style="padding:6px 12px">Add to Cart</button>
            </div>
          </div>`;
        ticketsEl.appendChild(gaDiv);
        const gaAddBtn = gaDiv.querySelector('#gaAddBtn');
        gaAddBtn?.addEventListener('click', async () => {
          const qtyInput = document.getElementById('gaQty');
          const qty = Math.max(1, Math.min(Number(qtyInput.value)||1, Number(qtyInput.max)||1));
          gaAddBtn.disabled = true;
          try {
            const r = await fetch('/cart/items', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ticketId:'GA', quantity: qty, eventId})});
            if(!r.ok){
              const text = await r.text().catch(()=>'<no body>');
              alert('Add GA to cart failed: '+r.status+'\n'+text);
            } else { showCartToast('GA tickets added'); updateCartBadge(); }
          } catch(err){ console.error('ga add error', err); }
          finally { gaAddBtn.disabled = false; }
        });
      }
      seatTickets.forEach(t => {
        const priceNum = (typeof t.price === 'number') ? t.price : (isNaN(Number(t.price)) ? null : Number(t.price));
        const priceLabel = priceNum !== null ? formatPrice(priceNum) : 'Price unavailable';
        const d = document.createElement('div');
        d.className='ticket';
        const checkboxId = 'ticket_' + (t._id || Math.random().toString(36).slice(2,9));
        const desc = t.description ? `<div class="meta">${escapeHtml(t.description)}</div>` : '';
        d.innerHTML = `<label for="${checkboxId}">
            <input type="checkbox" id="${checkboxId}" name="ticket" value="${encodeURIComponent(t._id)}" data-price="${priceNum ?? ''}" />
            <div class="ticket-info">
              <div class="ticket-type">${escapeHtml(t.type||'Ticket')}</div>
              ${t.seat ? `<div class="ticket-seat">${escapeHtml(t.seat)}</div>` : ''}
              ${desc}
            </div>
            <div class="meta">${priceLabel}</div>
          </label>`;
        ticketsEl.appendChild(d);
      });

      ticketsEl.querySelectorAll('input[name="ticket"]').forEach(chk => {
        chk.addEventListener('change', updateTotal);
      });
      if (dropdownEl) dropdownEl.addEventListener('change', updateTotal);

      updateTotal();
    } catch (err) {
      console.error('loadTickets error', err);
      ticketsEl.textContent = 'Error loading tickets (see console)';
    }
  }

  if (applyBtn) {
    applyBtn.addEventListener('click', ev => {
      ev.preventDefault();
      loadTickets();
    });
  }

  if (resetBtn) {
    resetBtn.addEventListener('click', ev => {
      ev.preventDefault();
      filterSeat.value = '';
      filterMin.value = '';
      filterMax.value = '';
      loadTickets();
    });
  }

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    let checked = [];
    try {
      checked = Array.from(form.querySelectorAll('input[name="ticket"]:checked')).map(i => decodeURIComponent(i.value));
    } catch (err) {
      console.error('collect tickets error', err);
    }
    
    if (!checked.length) { 
      alert('Select at least one ticket'); 
      return; 
    }
    
    // Add each selected ticket to cart
    let successCount = 0;
    let failCount = 0;
    
    for (const ticketId of checked) {
      try {
        const r = await fetch('/cart/items', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ticketId })
        });
        
        if (r.ok) {
          successCount++;
        } else {
          failCount++;
          console.error(`Failed to add ticket ${ticketId}:`, r.status);
        }
      } catch (err) {
        failCount++;
        console.error(`Error adding ticket ${ticketId}:`, err);
      }
    }
    
    if (successCount > 0) {
      showCartToast(`${successCount} ticket(s) added to cart`);
      updateCartBadge();
      // Uncheck all checkboxes
      form.querySelectorAll('input[name="ticket"]:checked').forEach(chk => chk.checked = false);
      updateTotal();
    }
    
    if (failCount > 0) {
      alert(`${failCount} ticket(s) could not be added (already reserved or sold)`);
    }
    
    // Reload tickets to refresh availability
    await loadTickets();
  });

  loadEvent();
  updateCartBadge();
  }
});

function escapeHtml(s){ return String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

function showCartToast(msg){
  let t = document.getElementById('cartToast');
  if(!t){
    t = document.createElement('div');
    t.id='cartToast';
    t.style.position='fixed';
    t.style.bottom='20px';
    t.style.right='20px';
    t.style.background='rgba(0,0,0,0.75)';
    t.style.color='#fff';
    t.style.padding='8px 14px';
    t.style.borderRadius='4px';
    t.style.fontSize='14px';
    t.style.zIndex='9999';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.style.opacity='1';
  setTimeout(()=>{t.style.transition='opacity .4s'; t.style.opacity='0';}, 1600);
}

async function updateCartBadge(){
  try {
    const r = await fetch('/cart');
    if(!r.ok) return;
    const j = await r.json();
    let badge = document.getElementById('cartBadge');
    if(!badge){
      const cartLink = document.querySelector('a[href="/ui/cart"]');
      if(cartLink){
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
    }
    if(badge) badge.textContent = j.count || 0;
  } catch(err){}
}
