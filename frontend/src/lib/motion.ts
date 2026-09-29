export function prefersReducedMotion(): boolean {
	try {
		return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
	} catch {
		return false; // no window during SSR
	}
}

/** Transition params that collapse to instant for users who ask their OS
 * for reduced motion. */
export function motion<T extends { duration?: number; delay?: number }>(params: T): T {
	return prefersReducedMotion() ? { ...params, duration: 0, delay: 0 } : params;
}
