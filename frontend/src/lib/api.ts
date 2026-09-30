import { dev } from '$app/environment';
import { env } from '$env/dynamic/public';

// PUBLIC_API_URL overrides; otherwise dev hits the local backend via .env and
// production builds talk to the Render deployment directly.
const PRODUCTION_API_URL = 'https://ai-video-knowledge-extractor.onrender.com';

const configured = env.PUBLIC_API_URL || (dev ? '' : PRODUCTION_API_URL);

// A local backend configured as "localhost" means *this* computer - but when
// the app is opened from another address (127.0.0.1, or a phone on the same
// Wi-Fi using this machine's IP), reach the backend on that same address.
function sameHostAsPage(url: string): string {
	if (typeof window === 'undefined' || !url) return url;
	try {
		const api = new URL(url);
		const pageHost = window.location.hostname;
		if (api.hostname === 'localhost' && pageHost !== 'localhost') {
			api.hostname = pageHost;
			return api.toString().replace(/\/$/, '');
		}
	} catch {
		// not an absolute URL - use as is
	}
	return url;
}

export const API_BASE = sameHostAsPage(configured);
