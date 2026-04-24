import {
  listRooms,
  deleteRoom,
  createRoomLink,
  createRoomTorrent,
  type Room,
} from '../api.ts';
import { navigateTo } from '../router.ts';
import { checkAuth, logout, getCurrentUser } from '../auth.ts';

export async function renderRooms(): Promise<void> {
  const app = document.getElementById('app');
  if (!app) return;

  const user = await checkAuth();
  if (!user) {
    navigateTo('/login');
    return;
  }

  app.innerHTML = `
    <div class="rooms-layout">
      <header class="rooms-header">
        <h1>Rooms</h1>
        <div class="rooms-actions">
          <span class="rooms-user">${getCurrentUser()?.name || ''}</span>
          <button class="secondary" id="logout-btn">Logout</button>
          <button id="create-room-btn">+ New Room</button>
        </div>
      </header>
      <main class="rooms-grid" id="rooms-grid"></main>
    </div>
    <div id="create-modal" class="modal-overlay hidden">
      <div class="modal">
        <div class="modal-header">
          <h2>Create Room</h2>
          <button class="ghost modal-close" id="close-modal">&times;</button>
        </div>
        <div class="tabs">
          <button class="tab active" data-tab="link">Link</button>
          <button class="tab" data-tab="torrent">Torrent</button>
        </div>
        <form id="create-form-link" class="create-form">
          <div class="form-group"><label>Name</label><input name="name" required maxlength="31" /></div>
          <div class="form-group"><label>Image URL</label><input name="img_link" required /></div>
          <div class="form-group"><label>Description</label><textarea name="description" maxlength="256"></textarea></div>
          <div class="form-group"><label>Video URL</label><input name="video_link" required /></div>
          <div id="create-error-link" class="error-text"></div>
          <button type="submit">Create</button>
        </form>
        <form id="create-form-torrent" class="create-form hidden">
          <div class="form-group"><label>Name</label><input name="name" required maxlength="31" /></div>
          <div class="form-group"><label>Image URL</label><input name="img_link" required /></div>
          <div class="form-group"><label>Description</label><textarea name="description" maxlength="256"></textarea></div>
          <div class="form-group"><label>Torrent File</label><input type="file" name="torrent_file" accept=".torrent" required /></div>
          <div id="create-error-torrent" class="error-text"></div>
          <button type="submit">Create</button>
        </form>
      </div>
    </div>
  `;

  const style = document.createElement('style');
  style.textContent = `
    .rooms-layout { padding: 1.5rem; max-width: 1200px; margin: 0 auto; }
    .rooms-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; }
    .rooms-header h1 { font-size: 1.5rem; font-weight: 700; }
    .rooms-actions { display: flex; align-items: center; gap: 0.75rem; }
    .rooms-user { color: var(--text-secondary); font-size: 0.9rem; }
    .rooms-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 1rem; }
    .room-card {
      background: var(--bg-elevated);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      overflow: hidden;
      cursor: pointer;
      transition: transform var(--transition-fast), box-shadow var(--transition-fast);
    }
    .room-card:hover {
      transform: translateY(-2px);
      box-shadow: var(--shadow-glow);
      border-color: var(--accent-dark);
    }
    .room-card img {
      width: 100%;
      height: 150px;
      object-fit: cover;
      display: block;
      background: var(--bg-secondary);
    }
    .room-card-body { padding: 1rem; }
    .room-card-title { font-weight: 600; margin-bottom: 0.35rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .room-card-desc { color: var(--text-secondary); font-size: 0.8rem; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .room-card-actions { display: flex; gap: 0.5rem; margin-top: 0.75rem; }
    .room-card-actions button { padding: 0.4rem 0.8rem; font-size: 0.8rem; }
    .create-form button[type="submit"] { width: 100%; margin-top: 0.5rem; }
  `;
  app.appendChild(style);

  let rooms: Room[] = [];

  async function loadRooms(): Promise<void> {
    const grid = document.getElementById('rooms-grid');
    if (!grid) return;
    grid.innerHTML = '<div class="loader"></div>';
    try {
      rooms = await listRooms();
      if (rooms.length === 0) {
        grid.innerHTML = '<p style="color:var(--text-secondary)">No rooms yet. Create one!</p>';
        return;
      }
      grid.innerHTML = rooms
        .map(
          (r) => `
        <div class="room-card" data-id="${r.room_id}">
          <img src="${escapeHtml(r.img_link)}" alt="" loading="lazy" onerror="this.style.display='none'" />
          <div class="room-card-body">
            <div class="room-card-title">${escapeHtml(r.name)}</div>
            <div class="room-card-desc">${escapeHtml(r.description)}</div>
            <div class="room-card-actions">
              <button class="secondary join-btn" data-id="${r.room_id}">Join</button>
              <button class="ghost delete-btn" data-id="${r.room_id}">Delete</button>
            </div>
          </div>
        </div>
      `
        )
        .join('');

      grid.querySelectorAll('.room-card').forEach((card) => {
        card.addEventListener('click', (e) => {
          if ((e.target as HTMLElement).closest('button')) return;
          const id = (card as HTMLElement).dataset.id;
          if (id) navigateTo(`/room?id=${id}`);
        });
      });

      grid.querySelectorAll('.join-btn').forEach((btn) => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const id = (btn as HTMLElement).dataset.id;
          if (id) navigateTo(`/room?id=${id}`);
        });
      });

      grid.querySelectorAll('.delete-btn').forEach((btn) => {
        btn.addEventListener('click', async (e) => {
          e.stopPropagation();
          const id = (btn as HTMLElement).dataset.id;
          if (!id || !confirm('Delete this room?')) return;
          try {
            await deleteRoom(id);
            await loadRooms();
          } catch {
            alert('Failed to delete room');
          }
        });
      });
    } catch {
      grid.innerHTML = '<p style="color:var(--accent-glow)">Failed to load rooms.</p>';
    }
  }

  // Modal logic
  const modal = document.getElementById('create-modal');
  const createBtn = document.getElementById('create-room-btn');
  const closeBtn = document.getElementById('close-modal');

  createBtn?.addEventListener('click', () => modal?.classList.remove('hidden'));
  closeBtn?.addEventListener('click', () => modal?.classList.add('hidden'));
  modal?.addEventListener('click', (e) => {
    if (e.target === modal) modal.classList.add('hidden');
  });

  // Tabs
  const tabs = document.querySelectorAll('.tab');
  const linkForm = document.getElementById('create-form-link');
  const torrentForm = document.getElementById('create-form-torrent');

  tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      tabs.forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      const name = (tab as HTMLElement).dataset.tab;
      linkForm?.classList.toggle('hidden', name !== 'link');
      torrentForm?.classList.toggle('hidden', name !== 'torrent');
    });
  });

  // Submit handlers
  linkForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(linkForm as HTMLFormElement);
    const errorEl = document.getElementById('create-error-link');
    errorEl && (errorEl.textContent = '');
    try {
      const room = await createRoomLink({
        name: String(fd.get('name')),
        img_link: String(fd.get('img_link')),
        description: String(fd.get('description') || ''),
        video_link: String(fd.get('video_link')),
      });
      modal?.classList.add('hidden');
      (linkForm as HTMLFormElement).reset();
      navigateTo(`/room?id=${room.room_id}`);
    } catch (err: any) {
      errorEl && (errorEl.textContent = err.detail || 'Failed to create room');
    }
  });

  torrentForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(torrentForm as HTMLFormElement);
    const errorEl = document.getElementById('create-error-torrent');
    errorEl && (errorEl.textContent = '');
    const file = fd.get('torrent_file');
    if (!file || !(file instanceof File)) {
      errorEl && (errorEl.textContent = 'Please select a torrent file');
      return;
    }
    try {
      const room = await createRoomTorrent({
        name: String(fd.get('name')),
        img_link: String(fd.get('img_link')),
        description: String(fd.get('description') || ''),
        torrent_file: file,
      });
      modal?.classList.add('hidden');
      (torrentForm as HTMLFormElement).reset();
      navigateTo(`/room?id=${room.room_id}`);
    } catch (err: any) {
      errorEl && (errorEl.textContent = err.detail || 'Failed to create room');
    }
  });

  document.getElementById('logout-btn')?.addEventListener('click', logout);

  await loadRooms();
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
