import { getRoom, type RoomWatching } from '../api.ts';
import { navigateTo } from '../router.ts';
import { checkAuth, logout, getCurrentUser } from '../auth.ts';
import { connectRoomSocket, type RoomSocket } from '../ws.ts';
import { SyncPlayer } from '../player.ts';

export async function renderRoom(): Promise<void> {
  const app = document.getElementById('app');
  if (!app) return;

  const user = await checkAuth();
  if (!user) {
    navigateTo('/login');
    return;
  }

  const params = new URLSearchParams(window.location.hash.split('?')[1] || '');
  const roomId = params.get('id');
  if (!roomId) {
    navigateTo('/rooms');
    return;
  }

  app.innerHTML = `
    <div class="room-layout">
      <header class="room-header">
        <button class="ghost" id="back-btn">&larr; Rooms</button>
        <h1 id="room-title">...</h1>
        <div class="room-header-actions">
          <span class="rooms-user">${getCurrentUser()?.name || ''}</span>
          <button class="secondary" id="logout-btn">Logout</button>
        </div>
      </header>
      <div class="room-body">
        <div class="room-main">
          <div class="video-wrapper">
            <video id="video-player" controls preload="metadata" crossorigin="anonymous"></video>
          </div>
        </div>
        <aside class="room-sidebar">
          <div class="sidebar-section">
            <h3>Files</h3>
            <select id="file-select"></select>
          </div>
          <div class="sidebar-section">
            <h3>Users</h3>
            <ul id="user-list" class="user-list"></ul>
          </div>
        </aside>
      </div>
    </div>
  `;

  const style = document.createElement('style');
  style.textContent = `
    .room-layout { display: flex; flex-direction: column; height: 100vh; }
    .room-header {
      display: flex; align-items: center; gap: 0.75rem;
      padding: 0.75rem 1.25rem; border-bottom: 1px solid var(--border);
      background: var(--bg-secondary);
    }
    .room-header h1 { font-size: 1.1rem; font-weight: 600; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .room-header-actions { display: flex; align-items: center; gap: 0.5rem; }
    .room-body { display: flex; flex: 1; overflow: hidden; }
    .room-main { flex: 1; display: flex; flex-direction: column; background: #000; }
    .video-wrapper { flex: 1; display: flex; align-items: center; justify-content: center; position: relative; }
    .video-wrapper video { max-width: 100%; max-height: 100%; width: 100%; height: 100%; object-fit: contain; }
    .room-sidebar { width: 240px; border-left: 1px solid var(--border); background: var(--bg-secondary); display: flex; flex-direction: column; overflow-y: auto; }
    .sidebar-section { padding: 1rem; border-bottom: 1px solid var(--border); }
    .sidebar-section h3 { font-size: 0.85rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; }
    #file-select { width: 100%; background: var(--bg-hover); border-color: var(--border); color: var(--text-primary); }
    .user-list { list-style: none; }
    .user-list li { padding: 0.35rem 0; font-size: 0.9rem; color: var(--text-primary); }
    .user-list li::before { content: "•"; color: var(--accent-bright); margin-right: 0.4rem; }
    @media (max-width: 768px) {
      .room-sidebar { position: fixed; right: 0; top: 0; bottom: 0; z-index: 50; transform: translateX(100%); transition: transform var(--transition); }
      .room-sidebar.open { transform: translateX(0); }
      .room-body { position: relative; }
    }
  `;
  app.appendChild(style);

  document.getElementById('back-btn')?.addEventListener('click', () => navigateTo('/rooms'));
  document.getElementById('logout-btn')?.addEventListener('click', logout);

  let room: RoomWatching;
  let socket: RoomSocket;
  const usersMap = new Map<number, string>();

  try {
    room = await getRoom(roomId);
  } catch {
    navigateTo('/rooms');
    return;
  }

  const titleEl = document.getElementById('room-title');
  if (titleEl) titleEl.textContent = room.name;

  // Populate file select
  const fileSelect = document.getElementById('file-select') as HTMLSelectElement | null;
  if (fileSelect) {
    for (const [fi, name] of room.files) {
      const opt = document.createElement('option');
      opt.value = String(fi);
      opt.textContent = name;
      if (fi === room.curr_fi) opt.selected = true;
      fileSelect.appendChild(opt);
    }
    fileSelect.addEventListener('change', () => {
      const fi = parseInt(fileSelect.value, 10);
      if (!isNaN(fi)) {
        socket.send(`cf ${fi}`);
      }
    });
  }

  const video = document.getElementById('video-player') as HTMLVideoElement;
  if (!video) return;

  // Setup WebSocket and player
  socket = connectRoomSocket(roomId);
  void new SyncPlayer(video, roomId, socket, room.curr_fi);

  if (room.video) {
    video.src = room.video;
    video.currentTime = 0;
  }

  socket.onMessage((cmd) => {
    switch (cmd.type) {
      case 'uc': {
        const u = cmd.user;
        usersMap.set(u.conn_id, u.user_data.name);
        renderUsers();
        break;
      }
      case 'ud': {
        usersMap.delete(cmd.conn_id);
        renderUsers();
        break;
      }
      case 'ua': {
        usersMap.clear();
        for (const u of cmd.users) {
          usersMap.set(u.conn_id, u.user_data.name);
        }
        renderUsers();
        break;
      }
      case 'cf': {
        if (fileSelect) {
          fileSelect.value = String(cmd.fi);
        }
        break;
      }
    }
  });

  function renderUsers(): void {
    const list = document.getElementById('user-list');
    if (!list) return;
    if (usersMap.size === 0) {
      list.innerHTML = '<li>No users</li>';
      return;
    }
    const names = Array.from(usersMap.values());
    list.innerHTML = names
      .map((name) => '<li>' + escapeHtml(name) + '</li>')
      .join('');
  }

  renderUsers();
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
