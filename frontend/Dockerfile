FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html ./
COPY frontend/src ./src
ARG VITE_API_BASE=http://localhost:8000
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm install && npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
