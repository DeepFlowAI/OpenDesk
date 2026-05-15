# OpenDesk — Docker 部署

一份 compose 文件 + 一份 `.env`，所有配置（包括是否内嵌 PostgreSQL/Redis）都在 `.env` 里控制，命令永远只是 `docker compose up -d`。

## TL;DR — 默认全部内嵌

```bash
git clone https://github.com/DeepFlowAI/OpenDesk.git
cd OpenDesk/docker
cp .env.example .env

# 必填：生成强随机 SECRET_KEY 追加到 .env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env

docker compose up -d
```

打开 <http://localhost:3000> → 用 `default / admin / Admin123456` 登录 → **立刻改密码**。

## 切换模式（编辑 `.env`）

`.env` 里有一行：

```env
COMPOSE_PROFILES=with-postgres,with-redis
```

这是 docker compose 的**内置环境变量** —— 控制哪些 profile 服务被激活。改这一行就能切模式：

| 模式 | `.env` 里的 `COMPOSE_PROFILES=` | 还需在 `.env` 设 |
|------|--------------------------------|-------------------|
| **全部内嵌**（默认，最快试玩） | `with-postgres,with-redis` | （无） |
| 外部 PG，内嵌 Redis | `with-redis` | `DATABASE_URL=...` |
| 内嵌 PG，外部 Redis | `with-postgres` | `REDIS_URL=...` |
| **全部外接**（生产推荐） | `（留空）` | `DATABASE_URL=...` 和 `REDIS_URL=...` |

无论哪种模式，启动命令永远是：

```bash
docker compose up -d
```

> 实现原理：被排除的 profile 对应服务不会启动；`api` 的 `depends_on` 设了 `required: false`，这些缺席的依赖会被自动忽略，不会报错。

## 必须配置的环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `SECRET_KEY` | ✅ | JWT 签名密钥。**留空时 compose 拒绝启动**。生成：`python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | 仅当不用内嵌 PG | `postgresql+asyncpg://USER:PASS@HOST:5432/DB` |
| `REDIS_URL` | 仅当不用内嵌 Redis | `redis://[:PASS@]HOST:6379/0` |

其它变量（端口、默认账号、SMTP、OSS 等）见 [.env.example](./.env.example)。

## 生产部署清单

- [ ] `SECRET_KEY` 用强随机值（32 字节 hex）
- [ ] `DEFAULT_ADMIN_PASSWORD` 不要使用默认值 —— 首次登录后立即修改
- [ ] 不要把 `5001`、`3000` 端口直接对外，前面用 nginx / Caddy / Traefik 反代到 https
- [ ] `PUBLIC_API_URL` / `PUBLIC_SOCKET_URL` 改成你的公网域名（浏览器侧要能访问）
- [ ] 用外部 managed PostgreSQL / Redis，不要用内嵌的（数据持久性 + 备份 + 高可用）
- [ ] 启用对象存储（`OSS_*`）支持文件上传

### nginx 反代示例

```nginx
upstream opendesk_web { server 127.0.0.1:3000; }
upstream opendesk_api { server 127.0.0.1:5001; }

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    # ssl_certificate / ssl_certificate_key ...

    location /api/ {
        proxy_pass http://opendesk_api;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Socket.IO（长连接 + WebSocket）
    location /socket.io/ {
        proxy_pass http://opendesk_api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 600s;
    }

    location / {
        proxy_pass http://opendesk_web;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

反代后 `.env` 里这两个改成 `https://your-domain.com`：

```
PUBLIC_API_URL=https://your-domain.com/api/
PUBLIC_SOCKET_URL=https://your-domain.com
```

## 升级

```bash
# 拉新版镜像
docker compose pull

# 重建（数据库迁移会自动执行，因为 AUTO_MIGRATE=true）
docker compose up -d
```

如要锁定某个版本，把 `.env` 里的 `OPENDESK_VERSION` 改成具体 tag，例如 `v0.1.0`。

## 备份内嵌数据

只在用 `--profile with-postgres` 时相关：

```bash
# 备份
docker compose exec postgres pg_dump -U opendesk opendesk | gzip > opendesk-$(date +%F).sql.gz

# 还原
gunzip -c opendesk-2026-05-06.sql.gz | docker compose exec -T postgres psql -U opendesk opendesk
```

## 故障排查

| 现象 | 排查 |
|------|------|
| `SECRET_KEY must be set` | `.env` 里没填 `SECRET_KEY`；按 README 顶部命令生成 |
| API 起来后报 connection refused | 没用 `--profile with-postgres` 也没设 `DATABASE_URL` |
| 浏览器登录后立刻 401 | `PUBLIC_API_URL` 跟 `web` 容器实际能访问的 API 地址不一致（同源问题） |
| 中文显示乱码 | `docker compose logs api`；通常是 PG locale 不对，外部库重建时加 `--locale=C.UTF-8` |
