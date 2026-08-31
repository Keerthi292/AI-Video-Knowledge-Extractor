class ThemeStore {
	value: 'light' | 'dark' = $state('light');

	apply(next: 'light' | 'dark') {
		this.value = next;
		document.documentElement.setAttribute('data-theme', next);
		try {
			localStorage.setItem('theme', next);
		} catch {
			// localStorage unavailable - theme just won't persist
		}
	}

	toggle() {
		this.apply(this.value === 'dark' ? 'light' : 'dark');
	}

	init() {
		let stored: string | null = null;
		try {
			stored = localStorage.getItem('theme');
		} catch {
			// ignore
		}
		const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
		this.apply(stored === 'dark' || stored === 'light' ? stored : prefersDark ? 'dark' : 'light');
	}
}

export const theme = new ThemeStore();
