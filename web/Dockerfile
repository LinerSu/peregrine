# --- build stage ---
FROM node:20-alpine AS build
WORKDIR /app

# Frontend calls relative /api by default (nginx proxies it), so no API base needed.
ARG VITE_API_BASE=""
ENV VITE_API_BASE=$VITE_API_BASE

# Where the browser reaches the local terminal server (ttyd, started by
# scripts/terminal.sh on the host). Defaults to http://localhost:7681 in code.
ARG VITE_TERMINAL_URL=""
ENV VITE_TERMINAL_URL=$VITE_TERMINAL_URL

COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

# --- serve stage ---
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
