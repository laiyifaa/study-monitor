FROM node:20-alpine AS build

WORKDIR /app
COPY package.json .
# 使用国内 npm 镜像源加速安装
RUN npm install --registry=https://registry.npmmirror.com
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# nginx配置在docker-compose中通过volume挂载，或构建时从context复制
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
