FROM node:22-alpine AS build

WORKDIR /app
COPY frontend_mger/package.json frontend_mger/package-lock.json ./
RUN npm ci
RUN npm install --no-save --package-lock=false @rolldown/binding-linux-x64-musl@1.1.5
COPY frontend_mger/ ./

ARG VITE_ADMIN_API_BASE_URL=http://127.0.0.1:8020/api/admin/v1
ENV VITE_ADMIN_API_BASE_URL=${VITE_ADMIN_API_BASE_URL}
RUN npm run build

FROM nginx:1.27-alpine
COPY frontend_mger/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
