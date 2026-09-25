import { env } from '$env/dynamic/public';

// Empty = same origin; on Vercel, /api/* is rewritten to the backend service.
export const API_BASE = env.PUBLIC_API_URL ?? '';