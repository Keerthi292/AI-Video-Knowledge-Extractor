import { dev } from '$app/environment';
import { env } from '$env/dynamic/public';

// PUBLIC_API_URL overrides; otherwise dev hits the local backend via .env and
// production builds talk to the Render deployment directly.
const PRODUCTION_API_URL = 'https://ai-video-knowledge-extractor.onrender.com';

export const API_BASE = env.PUBLIC_API_URL || (dev ? '' : PRODUCTION_API_URL);
