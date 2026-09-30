import nodeAdapter from '@sveltejs/adapter-node';
import vercelAdapter from '@sveltejs/adapter-vercel';

// The Docker image runs a plain Node server (`node build`); everywhere else
// (Vercel) keeps the Vercel adapter. The frontend Dockerfile sets ADAPTER=node.
const adapter = process.env.ADAPTER === 'node' ? nodeAdapter() : vercelAdapter();

const config = {
    kit: {
        adapter
    }
};

export default config;
