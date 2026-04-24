import { getMe, ApiError } from './api.ts';

let currentUser: { name: string } | null = null;

export async function checkAuth(): Promise<{ name: string } | null> {
  try {
    const user = await getMe();
    currentUser = user;
    return user;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      currentUser = null;
      return null;
    }
    throw err;
  }
}

export function getCurrentUser(): { name: string } | null {
  return currentUser;
}

export function setCurrentUser(user: { name: string } | null): void {
  currentUser = user;
}

export async function logout(): Promise<void> {
  try {
    await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    });
  } catch {
    // ignore
  }
  currentUser = null;
  window.location.hash = '#/login';
}
