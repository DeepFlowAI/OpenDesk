<div align="center">

# OpenDesk

**开源全栈客服平台** — 工单 · 多渠道接入 · 对话路由 · 可视化流程设计 · 统一字段体系。

<p align="center">
  <a href="https://hub.docker.com/r/deepflowagent/opendesk-api">Docker Hub</a> ·
  <a href="./docker/README.md">自托管部署</a> ·
  <a href="https://github.com/DeepFlowAI/OpenDesk/issues">反馈问题</a>
</p>

<p align="center">
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-AGPL--3.0-blue?style=flat-square"></a>
  <a href="https://hub.docker.com/r/deepflowagent/opendesk-api"><img alt="Docker pulls (api)" src="https://img.shields.io/docker/pulls/deepflowagent/opendesk-api?style=flat-square&label=api%20pulls"></a>
  <a href="https://hub.docker.com/r/deepflowagent/opendesk-web"><img alt="Docker pulls (web)" src="https://img.shields.io/docker/pulls/deepflowagent/opendesk-web?style=flat-square&label=web%20pulls"></a>
  <a href="https://github.com/DeepFlowAI/OpenDesk/releases"><img alt="Latest release" src="https://img.shields.io/github/v/release/DeepFlowAI/OpenDesk?style=flat-square"></a>
  <a href="https://github.com/DeepFlowAI/OpenDesk/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/DeepFlowAI/OpenDesk?style=flat-square"></a>
</p>

<p align="center">
  <a href="./README.md"><img alt="English" src="https://img.shields.io/badge/English-d9d9d9?style=flat-square"></a>
  <a href="./README.zh-CN.md"><img alt="简体中文" src="https://img.shields.io/badge/%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-d9d9d9?style=flat-square"></a>
</p>

</div>

## ✨ 特性

- **多渠道统一收件箱** — 网页对话、语音、邮件等多渠道汇入同一坐席工作台。
- **可视化流程设计** — 拖拽式路由规则与 IVR 语音流程，无需代码。
- **强大的工单系统** — 字段、布局、生命周期完全自定义。
- **实时坐席工作台** — 在线对话、呼叫中心、工单队列同屏。
- **统一字段体系** — 用户、组织、工单、对话纪要共享同一套字段定义。
- **天然多租户** — 开箱即用的单租户；企业版扩展支持平台级租户管理。
- **生产级技术栈** — FastAPI · 异步 SQLAlchemy 2.0 · PostgreSQL · Redis · Next.js 15 · React 19。

## 🚀 快速开始

```bash
git clone https://github.com/DeepFlowAI/OpenDesk.git
cd OpenDesk/docker
cp .env.example .env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env

docker compose up -d        # 默认自带 PostgreSQL + Redis
```

打开 <http://localhost:3000>，使用以下账号登录：

| 字段     | 默认值       |
| -------- | ------------ |
| 企业 ID  | `default`    |
| 账号     | `admin`      |
| 密码     | `Admin123456`   |

> ⚠️ **任何非本地环境，首次登录后请立即修改密码。**

### 使用自己的数据库 / Redis

编辑 `.env` 里的 `COMPOSE_PROFILES=` 排除对应内嵌服务，再设置 `DATABASE_URL` / `REDIS_URL`，命令仍然是 `docker compose up -d`。完整部署指南（4 种模式 · 生产清单 · nginx 反代 · 备份）见 **[docker/README.md](docker/README.md)**。

## 🛠️ 本地开发

```bash
# 后端
cd server && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env.dev   # 修改 DATABASE_URL / REDIS_URL 指向本地实例
uvicorn app.main:app --reload --port 5001

# 前端
cd web && npm install
cp .env.example .env.dev
npm run dev
```

| 服务                | 地址                         |
| ------------------- | ---------------------------- |
| 前端                | http://localhost:3000        |
| 后端 API            | http://localhost:5001        |
| API 文档 (Swagger)  | http://localhost:5001/docs   |

## 🧭 页面路由

| 分组 | 路由 |
| --- | --- |
| **登录** | `/login` · `/login/forgot-password` |
| **管理后台** | `/employees` · `/employee-groups` · `/flow-studio` · `/channels` · `/session-routing` · `/service-hours` · `/system-settings` |
| **客服工作台** | `/workspace/chat` · `/workspace/call` · `/workspace/records` |

## 🧩 架构

```
┌─────────────────────────┐    ┌─────────────────────────┐
│  Next.js 15 + React 19  │◄──►│   FastAPI + Socket.IO   │
│  (web)                  │    │   (api)                 │
└─────────────────────────┘    └────────────┬────────────┘
                                            │
                          ┌─────────────────┼─────────────────┐
                          ▼                 ▼                 ▼
                  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                  │ PostgreSQL 15│  │   Redis 7    │  │   对象存储   │
                  │ (业务数据)   │  │ (缓存+发布)  │  │  (文件上传)  │
                  └──────────────┘  └──────────────┘  └──────────────┘
```

后端严格遵循 **Router → Service → Repository → Model** 分层，输入输出由 Pydantic Schema 约束。闭源扩展模块（如多租户管理）通过 `app/extensions/` 下的约定式加载器自动注册，无需改动开源代码。

## 🏢 版本对比

| 版本           | 租户                                   | 租户管理 API                       |
| -------------- | -------------------------------------- | ---------------------------------- |
| **社区版**     | 自动建一个 `default` 单租户            | —                                  |
| **企业版**     | 多租户                                 | `/api/v1/tenants`（闭源扩展）      |

社区版（即本仓库）对单组织部署是功能完整的。企业版扩展为 SaaS 运营方提供平台级租户增删改查 API。

## 🤝 贡献

欢迎提交 Issue、Discussion 与 Pull Request。提交 PR 前请确保测试通过：

```bash
cd server && pytest
```

## 📜 协议

OpenDesk 采用 [GNU Affero 通用公共许可证 v3.0](LICENSE) 开源。
