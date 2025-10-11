document.addEventListener('DOMContentLoaded', () => {
  fetch('/auth/me').then(r=>r.json()).then(me => {
    if(!me.authenticated){ location.href='/login'; return; }
    const authUserEl = document.getElementById('authUser');
    if (authUserEl) authUserEl.textContent = `Logged in (${me.userType||'user'})`;
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) logoutBtn.addEventListener('click', async () => { try { await fetch('/auth/logout',{method:'POST'});} catch(e){} location.href='/login'; });
    loadCart();
  }).catch(()=> location.href='/login');

  const cartItemsEl = document.getElementById('cartItems');
  const cartEmptyEl = document.getElementById('cartEmpty');
  const cartTotalEl = document.getElementById('cartTotal');
  const checkoutBtn = document.getElementById('checkoutBtn');
  const clearBtn = document.getElementById('clearBtn');

  async function loadCart(){
    cartItemsEl.innerHTML = 'Loading...';
    try {
      const r = await fetch('/cart');
      if(!r.ok){ cartItemsEl.textContent='Failed to load cart'; return; }
      const j = await r.json();
      const items = j.items || [];
      if(!items.length){
        cartItemsEl.innerHTML='';
        cartEmptyEl.style.display='block';
        cartTotalEl.textContent='';
      } else {
        cartEmptyEl.style.display='none';
        cartItemsEl.innerHTML='';
        items.forEach(it => {
          const d = document.createElement('div');
          d.className='ticket';
          d.style.display='flex';
          d.style.alignItems='stretch';
          d.style.gap='12px';
          d.style.flexWrap='wrap';
          d.innerHTML = `
            <div class="ticket-info" style="flex:1 1 240px;min-width:200px;display:flex;flex-direction:column;gap:4px">
               <div class="ticket-type" style="font-weight:600">${escapeHtml(it.type || 'Ticket')}</div>
               ${it.seat ? `<div class="ticket-seat" style="font-size:12px;color:#555">${escapeHtml(it.seat)}</div>`:''}
               <div class="meta" style="font-size:11px;background:#f2f4f8;padding:6px 10px;border-radius:14px;width:fit-content">Event: ${it.eventId}</div>
            </div>
            <div style="display:flex;flex-direction:column;align-items:flex-end;justify-content:space-between;min-width:90px">
               <div class="meta" style="background:#e5e8ed;padding:8px 14px;border-radius:20px;font-weight:600">€ ${Number(it.price).toFixed(2)}</div>
               <button data-id="${it.ticketId}" class="btn secondary" style="margin-top:8px;align-self:flex-end">Remove</button>
            </div>`;
          cartItemsEl.appendChild(d);
        });
        cartItemsEl.querySelectorAll('button[data-id]').forEach(btn => btn.addEventListener('click', () => removeItem(btn.dataset.id)));
        cartTotalEl.textContent = 'Total: € ' + Number(j.total).toFixed(2) + `  (${items.length} ticket${items.length!==1?'s':''})`;
      }
    } catch(err){
      console.error('loadCart error', err);
      cartItemsEl.textContent='Error';
    }
  }

  async function removeItem(id){
    try { await fetch('/cart/items/'+encodeURIComponent(id), {method:'DELETE'}); } catch(e){}
    loadCart();
  }

  checkoutBtn.addEventListener('click', async () => {
    checkoutBtn.disabled=true;
    try {
      const r = await fetch('/cart/checkout',{method:'POST'});
      if(r.status===201){
        const j = await r.json();
        alert('Order created with id ' + (j.order?j.order._id:'?'));
        loadCart();
      } else {
        const text = await r.text().catch(()=>'<no body>');
        alert('Checkout failed: '+r.status+'\n'+text);
      }
    } catch(err){
      console.error('checkout error', err);
      alert('Checkout error (see console)');
    } finally {
      checkoutBtn.disabled=false;
    }
  });

  clearBtn.addEventListener('click', async () => {
    if(!confirm('Clear cart?')) return;
    try { await fetch('/cart/clear',{method:'POST'});} catch(e){}
    loadCart();
  });
});

function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, c => ({
    '&':'&amp;',
    '<':'&lt;',
    '>':'&gt;',
    '"':'&quot;',
    "'":'&#39;'
  }[c] || c));
}
