const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export type ServerCommand =
  | { type: 'pl'; time: number }
  | { type: 'pa'; time: number }
  | { type: 'sp'; time: number }
  | { type: 'cf'; fi: number }
  | { type: 'ua'; users: { conn_id: number; user_data: { name: string } }[] }
  | { type: 'uc'; user: { conn_id: number; user_data: { name: string } } }
  | { type: 'ud'; conn_id: number }
  | { type: 'unknown'; raw: string };

function parseCommand(raw: string): ServerCommand {
  const [prefix, ...rest] = raw.split(' ');
  const payload = rest.join(' ');
  switch (prefix) {
    case 'pl':
      return { type: 'pl', time: parseFloat(payload) };
    case 'pa':
      return { type: 'pa', time: parseFloat(payload) };
    case 'sp':
      return { type: 'sp', time: parseFloat(payload) };
    case 'cf':
      return { type: 'cf', fi: parseInt(payload, 10) };
    case 'ua': {
      try {
        const parsed = JSON.parse(payload);
        // Server may send either a plain array or {users: [...]} (UsersListSchema)
        const users = Array.isArray(parsed) ? parsed : parsed.users;
        return { type: 'ua', users };
      } catch {
        return { type: 'unknown', raw };
      }
    }
    case 'uc': {
      try {
        const user = JSON.parse(payload);
        return { type: 'uc', user };
      } catch {
        return { type: 'unknown', raw };
      }
    }
    case 'ud':
      return { type: 'ud', conn_id: parseInt(payload, 10) };
    default:
      return { type: 'unknown', raw };
  }
}

export interface RoomSocket {
  send: (cmd: string) => void;
  close: () => void;
  onMessage: (handler: (cmd: ServerCommand) => void) => void;
  onOpen: (handler: () => void) => void;
  onClose: (handler: () => void) => void;
  ready: () => boolean;
}

export function connectRoomSocket(roomId: string): RoomSocket {
  const wsUrl = API_BASE.replace(/^http/, 'ws') + `/rooms/${roomId}/ws`;
  let ws: WebSocket | null = null;
  const msgHandlers: ((cmd: ServerCommand) => void)[] = [];
  const openHandlers: (() => void)[] = [];
  const closeHandlers: (() => void)[] = [];
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let closed = false;

  function open(): void {
    if (closed) return;
    ws = new WebSocket(wsUrl);
    ws.onopen = () => {
      openHandlers.forEach((h) => h());
    };
    ws.onmessage = (ev) => {
      const cmd = parseCommand(String(ev.data));
      msgHandlers.forEach((h) => h(cmd));
    };
    ws.onclose = () => {
      closeHandlers.forEach((h) => h());
      if (!closed && reconnectTimer === null) {
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null;
          open();
        }, 2000);
      }
    };
    ws.onerror = () => {
      ws?.close();
    };
  }

  open();

  return {
    send(cmd: string) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(cmd);
      }
    },
    close() {
      closed = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      ws?.close();
      ws = null;
    },
    onMessage(handler) {
      msgHandlers.push(handler);
    },
    onOpen(handler) {
      openHandlers.push(handler);
    },
    onClose(handler) {
      closeHandlers.push(handler);
    },
    ready() {
      return ws !== null && ws.readyState === WebSocket.OPEN;
    },
  };
}
