function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function loadUsers(){
  try {
    const hasPhone = document.getElementById('hasPhoneFilter')?.value || '';
    const q = document.getElementById('qFilter')?.value?.trim() || '';

    // build query params for first request
    const params1 = new URLSearchParams();
    if (hasPhone) params1.set('hasPhone', hasPhone);
    if (q) params1.set('q', q);

    const url1 = '/users' + (params1.toString() ? ('?' + params1.toString()) : '');
    const resp1 = await fetch(url1);
    if(!resp1.ok){
      const text = await resp1.text().catch(()=>"<no body>");
      alert('Failed loading users: ' + resp1.status + ' ' + text);
      return;
    }
    const j1 = await resp1.json();
    let users = j1.data || [];
    const total = (j1.meta && typeof j1.meta.total === 'number') ? j1.meta.total : users.length;

    // if server returned a partial page, fetch all using total as limit
    if (users.length < total) {
      const params2 = new URLSearchParams({ limit: String(total) });
      if (hasPhone) params2.set('hasPhone', hasPhone);
      if (q) params2.set('q', q);
      const resp2 = await fetch('/users?' + params2.toString());
      if(!resp2.ok){
        const text = await resp2.text().catch(()=>"<no body>");
        alert('Failed loading all users: ' + resp2.status + ' ' + text);
        return;
      }
      const j2 = await resp2.json();
      users = j2.data || users;
      document.getElementById('meta').textContent = `page ${j2.meta.page} • limit ${j2.meta.limit} • total ${j2.meta.total}`;
    } else {
      document.getElementById('meta').textContent = `page ${j1.meta?.page ?? 1} • limit ${j1.meta?.limit ?? users.length} • total ${j1.meta?.total ?? users.length}`;
    }

    const tbody = document.querySelector('#usersTable tbody');
    tbody.innerHTML = '';
    users.forEach(u => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="font-family:monospace">${escapeHtml(u._id || '')}</td>
        <td>${escapeHtml(u.name||'')}</td>
        <td>${escapeHtml(u.email||'')}</td>
        <td>${escapeHtml(u.phoneNumber||'')}</td>
        <td>
          <button class="editBtn" data-id="${escapeHtml(u._id||'')}">Edit</button>
          <button class="delBtn" data-id="${escapeHtml(u._id||'')}" style="color:#a00">Delete</button>
        </td>`;
      tbody.appendChild(tr);
    });

    // attach delegation listeners for edit/delete buttons
    tbody.querySelectorAll('.editBtn').forEach(b => b.addEventListener('click', () => editUser(b.dataset.id)));
    tbody.querySelectorAll('.delBtn').forEach(b => b.addEventListener('click', () => deleteUser(b.dataset.id)));

  } catch (err) {
    console.error('loadUsers error', err);
    alert('Error loading users (see console).');
  }
}

// create user: omit empty phoneNumber
async function createUserHandler(e){
  e.preventDefault();
  const name = document.getElementById('name').value.trim();
  const email = document.getElementById('email').value.trim();
  const phoneNumber = document.getElementById('phoneNumber').value.trim();
  if(!name || !email){ alert('name and email required'); return; }

  const payload = { name, email };
  if (phoneNumber) payload.phoneNumber = phoneNumber;

  try {
    const resp = await fetch('/users', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    if(resp.status === 201){
      e.target.reset();
      loadUsers();
      return;
    }
    const text = await resp.text().catch(()=>"<no body>");
    alert(`Failed: ${resp.status} ${resp.statusText}\n\n${text}`);
  } catch(err) {
    console.error('create user error', err);
    alert('Failed to create user (see console).');
  }
}

async function editUser(id){
  try {
    const resp = await fetch('/users/' + encodeURIComponent(id));
    if(!resp.ok){ alert('Unable to load user'); return; }
    const u = await resp.json();
    const name = prompt('Name', u.name || '');
    if(name === null) return;
    const email = prompt('Email', u.email || '');
    if(email === null) return;
    const phoneNumber = prompt('Phone', u.phoneNumber || '');
    if(phoneNumber === null) return;

    // build patch payload, omit phoneNumber when empty to trigger unset on server
    const payload = { name, email };
    if (phoneNumber) payload.phoneNumber = phoneNumber;
    const r = await fetch('/users/' + encodeURIComponent(id), {
      method: 'PATCH',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    if(!r.ok){
      const j = await r.json().catch(()=>({error:'failed'}));
      alert('Failed: ' + (j.error || JSON.stringify(j)));
    }
    loadUsers();
  } catch(err) {
    console.error('editUser error', err);
    alert('Error editing user (see console).');
  }
}

async function deleteUser(id){
  if(!confirm('Delete user ' + id + ' ?')) return;
  try {
    const r = await fetch('/users/' + encodeURIComponent(id), {method: 'DELETE'});
    if(!r.ok){
      const j = await r.json().catch(()=>({error:'failed'}));
      alert('Failed: ' + (j.error || JSON.stringify(j)));
    } else {
      loadUsers();
    }
  } catch(err) {
    console.error('deleteUser error', err);
    alert('Error deleting user (see console).');
  }
}

// wire up controls once DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('createForm');
  if (form) form.addEventListener('submit', createUserHandler);

  const refreshBtn = document.getElementById('refreshBtn');
  if (refreshBtn) refreshBtn.addEventListener('click', loadUsers);

  const applyBtn = document.getElementById('applyFilters');
  if (applyBtn) applyBtn.addEventListener('click', (e) => { e.preventDefault(); loadUsers(); });

  const hasPhoneSel = document.getElementById('hasPhoneFilter');
  if (hasPhoneSel) hasPhoneSel.addEventListener('change', loadUsers);

  loadUsers();
});