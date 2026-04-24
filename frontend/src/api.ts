const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface Room {
  room_id: string;
  name: string;
  img_link: string;
  description: string;
}

export interface RoomWatching extends Room {
  files: [number, string][];
  curr_fi: number;
  video: string | null;
}

export interface User {
  name: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserRoom {
  conn_id: number;
  user_data: User;
}

class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      ...(init.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export async function getMe(): Promise<User> {
  return request<User>('/auth/me');
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const body = new URLSearchParams();
  body.append('username', username);
  body.append('password', password);
  return request<TokenResponse>('/auth', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
}

export async function listRooms(): Promise<Room[]> {
  return request<Room[]>('/rooms');
}

export async function getRoom(roomId: string): Promise<RoomWatching> {
  return request<RoomWatching>(`/rooms/${roomId}`);
}

export async function deleteRoom(roomId: string): Promise<void> {
  return request<void>(`/rooms/${roomId}`, { method: 'DELETE' });
}

export async function createRoomLink(data: {
  name: string;
  img_link: string;
  description: string;
  video_link: string;
}): Promise<Room> {
  const body = new FormData();
  body.append('name', data.name);
  body.append('img_link', data.img_link);
  body.append('description', data.description);
  body.append('video_link', data.video_link);
  return request<Room>('/rooms/link', { method: 'POST', body });
}

export async function createRoomTorrent(data: {
  name: string;
  img_link: string;
  description: string;
  torrent_file: File;
}): Promise<Room> {
  const body = new FormData();
  body.append('name', data.name);
  body.append('img_link', data.img_link);
  body.append('description', data.description);
  body.append('torrent_file', data.torrent_file);
  return request<Room>('/rooms/torrent', { method: 'POST', body });
}

export async function updateRoomLink(
  roomId: string,
  data: {
    name: string;
    img_link: string;
    description: string;
    video_link?: string;
  }
): Promise<Room> {
  const body = new FormData();
  body.append('name', data.name);
  body.append('img_link', data.img_link);
  body.append('description', data.description);
  if (data.video_link) body.append('video_link', data.video_link);
  return request<Room>(`/rooms/${roomId}/link`, { method: 'PUT', body });
}

export async function updateRoomTorrent(
  roomId: string,
  data: {
    name: string;
    img_link: string;
    description: string;
    torrent_file?: File;
  }
): Promise<Room> {
  const body = new FormData();
  body.append('name', data.name);
  body.append('img_link', data.img_link);
  body.append('description', data.description);
  if (data.torrent_file) body.append('torrent_file', data.torrent_file);
  return request<Room>(`/rooms/${roomId}/torrent`, { method: 'PUT', body });
}

export function getVideoUrl(roomId: string, fi: number): string {
  return `${API_BASE}/rooms/files/${roomId}/${fi}`;
}

export { ApiError };
