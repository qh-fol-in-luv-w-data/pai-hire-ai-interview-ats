FROM node:20-alpine AS builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=builder /frontend/dist /usr/share/nginx/html
COPY frontend/code.html frontend/report_print.html /usr/share/nginx/html/
COPY frontend_nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8000
