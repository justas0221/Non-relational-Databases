// Sis skriptas ikelia ivykio informacija, bilietus ir vartotojus,
// leidzia pasirinkti bilietus ir sukurti uzsakyma (/orders),
// dabar su papildomu bilietu filtravimu pagal kaina ir vietą (pvz. GA).

document.addEventListener('DOMContentLoaded', () => {
  // nuskaityti parametruose perduota eventId
  const params = new URLSearchParams(location.search);
  const eventId = params.get('eventId');

  // DOM elementai, i kuriuos rasysime turini
  const titleEl = document.getElementById('title');
  const infoEl = document.getElementById('info');
  const ticketsEl = document.getElementById('tickets');
  const dropdownEl = document.getElementById('ticketsDropdown');
  const userSel = document.getElementById('userSelect');
  const form = document.getElementById('buyForm');

  // Filtrų elementai
  const filterSeat = document.getElementById('filterSeat');
  const filterMin = document.getElementById('filterMin');
  const filterMax = document.getElementById('filterMax');
  const applyBtn = document.getElementById('applyFilters');

  if (!eventId) {
    // jei nera pasirinkto ivykio pranesimas ir nutraukimas
    if (infoEl) infoEl.textContent = 'No event selected';
    return;
  }

  // kainos eurais
  const currencyFormatter = new Intl.NumberFormat(undefined, { style: 'currency', currency: 'EUR' });

   // pakeicia numeri i valiutos string arba grazina null jei neimanoma
  function formatPrice(n) {
    if (n === null || n === undefined || isNaN(Number(n))) return null;
    return currencyFormatter.format(Number(n));
  }

  // sukuria arba grazina elementa kuriame rodoma uzsakymo suma (order total)
  function ensureTotalElement() {
    let el = document.getElementById('orderTotal');
    if (!el && form) {
      el = document.createElement('div');
      el.id = 'orderTotal';
      el.style.marginTop = '10px';
      el.style.fontWeight = '700';
      el.style.fontSize = '15px';
      // padeti pries .actions (jei egzistuoja)
      form.querySelector('.actions')?.before(el);
    }
    return el;
  }

   // Apskaiciuoja ir atnaujina uzsakymo suma pagal pazymetus bilietus ir GA kiekius
  function updateTotal() {
    const totalEl = ensureTotalElement();
    if (!totalEl) return;
    try {
      let total = 0;
      if (dropdownEl && window.getComputedStyle(dropdownEl).display !== 'none') {
          // mobiliuju telefonu versija: bandom parsinti kaina is pasirinkimo teksto (best-effort)
        Array.from(dropdownEl.selectedOptions).forEach(opt => {
          const m = opt.textContent.match(/€\s?([0-9.,]+)/);
          if (m) total += Number(m[1].replace(',', '.'));
        });
      } else {
        const checked = Array.from(form.querySelectorAll('input[name="ticket"]:checked'));
        checked.forEach(i => {
          const p = Number(i.dataset.price || 0);
          if (!isNaN(p)) total += p;
        });
      }
      totalEl.textContent = total > 0 ? `Order total: ${formatPrice(total)}` : 'Order total: —';
    } catch (err) {
      console.error('updateTotal error', err);
      totalEl.textContent = 'Order total: —';
    }
  }
 // Užkrauna ivykio metaduomenis (pavadinima, data, vieta)
  async function loadEvent() {
    try {
      let ev = null;
      try {
        // jei serveris palaiko /events/<id> - bandome tiesiogiai
        const rId = await fetch('/events/' + encodeURIComponent(eventId));
        if (rId.ok) ev = await rId.json();
      } catch (err) { /* ignore ir krentame i fallback */ }


      if (!ev) {
        // fallback: uzkrauname saraša ir randame pagal id
        const resp = await fetch('/events?limit=1000');
        if (!resp.ok) { infoEl.textContent = 'Failed to load event'; return; }
        const je = await resp.json();
        ev = (je.data || []).find(e => e._id === eventId);
      }

      if (!ev) { infoEl.textContent = 'Event not found'; return; }
      // atvaizduojame pavadinima ir data bei vieta

      titleEl.textContent = ev.title || 'Event';
      const when = ev.eventDate ? new Date(ev.eventDate).toLocaleString() : '';
      infoEl.innerHTML = `<div>${when}</div><div class="meta">${escapeHtml(ev.location || '')}</div>`;
      // uzkrauname bilietus ir vartotojus lygiagreciai
      await Promise.all([loadTickets(), loadUsers()]);
    } catch (err) {
      console.error('loadEvent error', err);
      infoEl.textContent = 'Error loading event (see console)';
    }
  }

    // Uzkrauna bilietus is serverio, rusiuoja ir atvaizduoja juos sąsajoje
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

      // Rusiavimas: GA pirmas, tada pagal seat/type
      data.sort((a, b) => {
        const aGA = Boolean(a.isGeneralAdmission || (a.type && String(a.type).toLowerCase().includes('ga')));
        const bGA = Boolean(b.isGeneralAdmission || (b.type && String(b.type).toLowerCase().includes('ga')));
        if (aGA !== bGA) return aGA ? -1 : 1;
        const aKey = (a.seat || a.type || '').toString().toUpperCase();
        const bKey = (b.seat || b.type || '').toString().toUpperCase();
        return aKey.localeCompare(bKey, undefined, { numeric: true, sensitivity: 'base' });
      });

      // atvaizdavimas: kiekvienam bilietui sukuriamas korteles elementatas dropdown opcija
      data.forEach(t => {
         // paruosiame kaina ir teksta
        const priceNum = (typeof t.price === 'number') ? t.price : (isNaN(Number(t.price)) ? null : Number(t.price));
        const priceLabel = priceNum !== null ? formatPrice(priceNum) : 'Price unavailable';

        const d = document.createElement('div');
        d.className = 'ticket';
        const checkboxId = 'ticket_' + (t._id || Math.random().toString(36).slice(2,9));
        const seat = t.seat ? ` • ${escapeHtml(t.seat)}` : '';
        const desc = t.description ? `<div class="meta">${escapeHtml(t.description)}</div>` : '';
        d.innerHTML = `<label for="${checkboxId}">
                        <input type="checkbox" id="${checkboxId}" name="ticket" value="${encodeURIComponent(t._id)}" data-price="${priceNum ?? ''}" />
                        <div style="flex:1">
                          <div><strong>${escapeHtml(t.type||'Ticket')}</strong>${seat}</div>
                          ${desc}
                        </div>
                        <div class="meta">${priceLabel}</div>
                      </label>`;
        ticketsEl.appendChild(d);

        
        // mobiliuju telefonu versija: prideti opciją i dropdown (su kainos tekstu)
        if (dropdownEl) {
          const opt = document.createElement('option');
          opt.value = t._id;
          opt.textContent = `${t.type || 'Ticket'}${t.seat ? ' • ' + t.seat : ''} ${priceLabel !== null ? priceLabel : ''}`;
          dropdownEl.appendChild(opt);
        }
      });

      // atnaujiname suma kai keiciasi pasirinkimai
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

  // Uzkrauna vartotoju sarasa i "Buy as user" select'a
  async function loadUsers() {
    try {
      userSel.innerHTML = '<option value="">Select user</option>';
      const r = await fetch('/users?limit=1000');
      if (!r.ok) { userSel.innerHTML = '<option>failed</option>'; return; }
      const j = await r.json();
      (j.data || []).forEach(u => {
        const o = document.createElement('option');
        o.value = u._id;
        o.textContent = `${u.name || u.email} (${u.email})`;
        userSel.appendChild(o);
      });
    } catch (err) {
      console.error('loadUsers error', err);
      userSel.innerHTML = '<option>failed</option>';
    }
  }

  // Apdorojame formos submit: surenkame pasirinkimus ir siunciame uzsakyma i /orders
  if (applyBtn) {
    applyBtn.addEventListener('click', ev => {
      ev.preventDefault();
      loadTickets();
    });
  }

  // Užsakymo pateikimas
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const userId = userSel.value;
    if (!userId) { alert('Select a user'); return; }


    // surinkti pasirinktas bilietų id vertes (mobile arba desktop)
    let checked = [];
    try {
      if (dropdownEl && window.getComputedStyle(dropdownEl).display !== 'none') {
        checked = Array.from(dropdownEl.selectedOptions).map(o => o.value);
      } else {
        checked = Array.from(form.querySelectorAll('input[name="ticket"]:checked')).map(i => decodeURIComponent(i.value));
      }
    } catch (err) {
      console.error('collect tickets error', err);
    }

    if (!checked.length) { alert('Select one or more tickets'); return; }

    const payload = { userId, items: checked.map(tid => ({ ticketId: tid })) };
    try {
      const r = await fetch('/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (r.status === 201) {
        alert('Order created');
        location.reload();
        return;
      }
      const text = await r.text().catch(() => '<no body>');
      alert('Failed: ' + r.status + '\n' + text);
    } catch (err) {
      console.error('create order error', err);
      alert('Error creating order (see console)');
    }
  });

  // Pradinis uzkrovimas
  loadEvent();
});

// Nedidele apsauga prieš XSS ir pakeicia specialius simbolius i HTML entity
function escapeHtml(s){ return String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
