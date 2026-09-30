FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
# Build a standalone Node server (see svelte.config.js) instead of Vercel output.
ENV ADAPTER=node
RUN npm run build

ENV NODE_ENV=production
EXPOSE 3000

CMD ["node", "build"]
