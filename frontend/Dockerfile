FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json .
RUN npm install

COPY . .

# Build for production; API proxy handled by nginx at runtime
ENV VITE_API_BASE=
RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx config to proxy /api, /thumbnails, /images, /events to backend
RUN cat > /etc/nginx/conf.d/default.conf << 'NGINX'
server {
    listen 80;

    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    location ~ ^/(api|thumbnails|images|events)/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # SSE support
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
    }

    location /api {
        rewrite ^/api(/.*)$ $1 break;
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
    }
}
NGINX

EXPOSE 80
