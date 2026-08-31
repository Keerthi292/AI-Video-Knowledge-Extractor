import { goto } from '$app/navigation';
import { API_BASE } from './api';

class AuthStore {
	token: string | null = $state(null);
	email: string | null = $state(null);
	checked = $state(false);
	view: 'login' | 'signup' = $state('login');
	emailInput = $state('');
	passwordInput = $state('');
	error: string | null = $state(null);
	loading = $state(false);

	headers(): Record<string, string> {
		return this.token ? { Authorization: `Bearer ${this.token}` } : {};
	}

	async fetch(path: string, options: RequestInit = {}) {
		const response = await fetch(`${API_BASE}${path}`, {
			...options,
			headers: { ...(options.headers as Record<string, string>), ...this.headers() }
		});
		if (response.status === 401) this.logout();
		return response;
	}

	set(token: string, email: string) {
		this.token = token;
		this.email = email;
		try {
			localStorage.setItem('auth-token', token);
		} catch {
			// ignore
		}
	}

	logout() {
		const token = this.token;
		this.token = null;
		this.email = null;
		this.emailInput = '';
		this.passwordInput = '';
		this.error = null;
		try {
			localStorage.removeItem('auth-token');
		} catch {
			// ignore
		}
		if (token) {
			fetch(`${API_BASE}/api/auth/logout`, {
				method: 'POST',
				headers: { Authorization: `Bearer ${token}` }
			}).catch(() => {});
		}
		goto('/');
	}

	async checkStored() {
		let stored: string | null = null;
		try {
			stored = localStorage.getItem('auth-token');
		} catch {
			// ignore
		}
		if (!stored) {
			this.checked = true;
			return;
		}
		this.token = stored;
		try {
			const response = await fetch(`${API_BASE}/api/auth/me`, {
				headers: { Authorization: `Bearer ${stored}` }
			});
			if (!response.ok) throw new Error('invalid session');
			const data = await response.json();
			this.email = data.email;
		} catch {
			this.token = null;
			try {
				localStorage.removeItem('auth-token');
			} catch {
				// ignore
			}
		} finally {
			this.checked = true;
		}
	}

	async submit() {
		this.loading = true;
		this.error = null;
		try {
			const path = this.view === 'login' ? '/api/auth/login' : '/api/auth/signup';
			const response = await fetch(`${API_BASE}${path}`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ email: this.emailInput, password: this.passwordInput })
			});
			const data = await response.json();
			if (!response.ok) throw new Error(data.detail ?? 'Authentication failed');
			this.set(data.token, data.email);
			this.passwordInput = '';
		} catch (err) {
			this.error = err instanceof Error ? err.message : 'Something went wrong';
		} finally {
			this.loading = false;
		}
	}
}

export const auth = new AuthStore();
