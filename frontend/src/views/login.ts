import { login, ApiError } from '../api.ts';
import { navigateTo } from '../router.ts';
import { checkAuth } from '../auth.ts';

export async function renderLogin(): Promise<void> {
  const app = document.getElementById('app');
  if (!app) return;

  const user = await checkAuth();
  if (user) {
    navigateTo('/rooms');
    return;
  }

  app.innerHTML = `
    <div class="login-container">
      <div class="login-card">
        <h1 class="login-title">Cooplook</h1>
        <p class="login-subtitle">Watch together.</p>
        <form id="login-form" class="login-form">
          <div class="form-group">
            <label for="username">Username</label>
            <input type="text" id="username" name="username" autocomplete="username" required />
          </div>
          <div class="form-group">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" autocomplete="current-password" required />
          </div>
          <div id="login-error" class="error-text"></div>
          <button type="submit" id="login-btn" class="login-submit">Sign In</button>
        </form>
      </div>
    </div>
  `;

  const style = document.createElement('style');
  style.textContent = `
    .login-container {
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1rem;
    }
    .login-card {
      background: var(--bg-elevated);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 2.5rem;
      width: 100%;
      max-width: 380px;
      box-shadow: var(--shadow);
    }
    .login-title {
      font-size: 1.75rem;
      font-weight: 700;
      text-align: center;
      margin-bottom: 0.25rem;
      letter-spacing: -0.02em;
    }
    .login-subtitle {
      text-align: center;
      color: var(--text-secondary);
      font-size: 0.9rem;
      margin-bottom: 1.5rem;
    }
    .login-form .form-group {
      margin-bottom: 1rem;
    }
    .login-form input {
      width: 100%;
    }
    .login-submit {
      width: 100%;
      margin-top: 0.5rem;
      padding: 0.75rem;
      font-size: 1rem;
    }
    .login-submit .loader {
      width: 1rem;
      height: 1rem;
      display: inline-block;
      vertical-align: middle;
      margin-right: 0.5rem;
    }
  `;
  app.appendChild(style);

  const form = document.getElementById('login-form') as HTMLFormElement | null;
  const errorEl = document.getElementById('login-error');
  const btn = document.getElementById('login-btn') as HTMLButtonElement | null;

  if (!form || !btn) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    errorEl && (errorEl.textContent = '');
    const username = (form.elements.namedItem('username') as HTMLInputElement).value;
    const password = (form.elements.namedItem('password') as HTMLInputElement).value;

    btn.disabled = true;
    const originalText = btn.textContent || '';
    btn.innerHTML = '<span class="loader"></span>Signing in...';

    try {
      await login(username, password);
      navigateTo('/rooms');
    } catch (err) {
      if (err instanceof ApiError) {
        errorEl && (errorEl.textContent = err.detail);
      } else {
        errorEl && (errorEl.textContent = 'Something went wrong. Please try again.');
      }
      btn.disabled = false;
      btn.textContent = originalText;
    }
  });
}
