# Stage 1: Build
FROM node:20-alpine AS builder
ARG WEBAPP_PUBLIC_ORIGIN=https://poker.shahin8n.sbs
ENV VITE_PUBLIC_ORIGIN=${WEBAPP_PUBLIC_ORIGIN}
ENV VITE_API_URL=${WEBAPP_PUBLIC_ORIGIN}/api
WORKDIR /app
COPY package*.json ./
COPY scripts ./scripts
COPY public/favicon.ico.base64 ./public/favicon.ico.base64
RUN npm install
COPY . .
RUN npm run build

# Stage 2: Serve
FROM nginx:1.24-alpine
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
