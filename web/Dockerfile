# The web app image. Build context is `web/` (Compose sets it).
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS build
WORKDIR /app
# Next bakes the `/api/*` rewrite into the build, so the API's address is a build argument.
ARG SUNQUOTE_API_URL=http://api:8000
ENV SUNQUOTE_API_URL=${SUNQUOTE_API_URL} \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24-alpine AS run
WORKDIR /app
ARG SUNQUOTE_API_URL=http://api:8000
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    SUNQUOTE_API_URL=${SUNQUOTE_API_URL}
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
