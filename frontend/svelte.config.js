import adapter from '@sveltejs/adapter-node';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		// adapter-node: produces a standalone Node server (`node build`), used by
		// the project's Dockerfile. Swap adapters if you deploy elsewhere (e.g.
		// adapter-auto for Vercel/Netlify).
		adapter: adapter()
	}
};

export default config;
