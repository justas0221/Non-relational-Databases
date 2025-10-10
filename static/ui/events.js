document.addEventListener('DOMContentLoaded', () => {
  const listEl = document.getElementById('events');
  const qIn = document.getElementById('q');
  const btn = document.getElementById('searchBtn');

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
      c.innerHTML = `<h3>${escapeHtml(ev.title || 'Untitled')}</h3>
                     <div>${new Date(ev.eventDate).toLocaleString()}</div>
                     <div style="margin-top:8px">
                       <a href="/ui/event?eventId=${encodeURIComponent(ev._id)}">View & Buy tickets</a>
                     </div>`;
      listEl.appendChild(c);
    });
  }

  btn.addEventListener('click', () => load(qIn.value.trim()));
  load('');
});

function escapeHtml(s){ return String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }