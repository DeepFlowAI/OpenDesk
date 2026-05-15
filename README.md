<div align="center">

# OpenDesk

**Open-source full-stack customer support platform** — tickets, multi-channel inbox, conversation routing, visual flow designer, unified field system.

<p align="center">
  <a href="https://hub.docker.com/r/deepflowagent/opendesk-api">Docker Hub</a> ·
  <a href="./docker/README.md">Self-hosting</a> ·
  <a href="https://github.com/DeepFlowAI/OpenDesk/issues">Issues</a>
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

## ✨ Features

- **Multi-channel inbox** — web chat, voice, email, and more, unified into one agent workspace.
- **Visual flow designer** — drag-and-drop routing rules and IVR voice flows; no code required.
- **Powerful ticket system** — fully customizable fields, layouts, and lifecycle.
- **Real-time agent workspace** — live chat, call center, ticket queue, all in a single SPA.
- **Unified field system** — share field definitions across users, organizations, tickets, and conversation summaries.
- **Multi-tenant ready** — single-tenant out of the box; the Enterprise edition adds platform-level tenant management.
- **Production-grade stack** — FastAPI · async SQLAlchemy 2.0 · PostgreSQL · Redis · Next.js 15 · React 19.

## 🚀 Quick Start

```bash
git clone https://github.com/DeepFlowAI/OpenDesk.git
cd OpenDesk/docker
cp .env.example .env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env

docker compose up -d        # bundles PostgreSQL + Redis by default
```

Open <http://localhost:3000> and sign in:

| Field    | Default      |
| -------- | ------------ |
| Tenant   | `default`    |
| Username | `admin`      |
| Password | `Admin123456`   |

> ⚠️ **Change the password immediately after first login in any non-local deployment.**

### Bring your own database / Redis

Edit `COMPOSE_PROFILES=` in `.env` to drop the bundled service(s), then set `DATABASE_URL` / `REDIS_URL`. The command stays `docker compose up -d`. Full deployment guide (4 modes · production checklist · nginx reverse proxy · backup) → **[docker/README.md](docker/README.md)**.

## 🛠️ Local Development

```bash
# Backend
cd server && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env.dev   # set DATABASE_URL / REDIS_URL to your local instances
uvicorn app.main:app --reload --port 5001

# Frontend
cd web && npm install
cp .env.example .env.dev
npm run dev
```

| Service             | URL                          |
| ------------------- | ---------------------------- |
| Frontend            | http://localhost:3000        |
| Backend API         | http://localhost:5001        |
| API docs (Swagger)  | http://localhost:5001/docs   |

## 🧭 Pages

| Section | Routes |
| --- | --- |
| **Auth** | `/login` · `/login/forgot-password` |
| **Admin** | `/employees` · `/employee-groups` · `/flow-studio` · `/channels` · `/session-routing` · `/service-hours` · `/system-settings` |
| **Agent workspace** | `/workspace/chat` · `/workspace/call` · `/workspace/records` |

## 🧩 Architecture

```
┌─────────────────────────┐    ┌─────────────────────────┐
│  Next.js 15 + React 19  │◄──►│   FastAPI + Socket.IO   │
│  (web)                  │    │   (api)                 │
└─────────────────────────┘    └────────────┬────────────┘
                                            │
                          ┌─────────────────┼─────────────────┐
                          ▼                 ▼                 ▼
                  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                  │ PostgreSQL 15│  │   Redis 7    │  │ Object store │
                  │ (data)       │  │ (cache+pub)  │  │ (uploads)    │
                  └──────────────┘  └──────────────┘  └──────────────┘
```

Backend follows a strict **Router → Service → Repository → Model** layering with Pydantic schemas for I/O. Closed-source extensions (e.g. multi-tenant management) plug in via a convention-based loader at `app/extensions/`.

## 🏢 Editions

| Edition         | Tenants                              | Tenant management API           |
| --------------- | ------------------------------------ | ------------------------------- |
| **Community**   | Single auto-provisioned `default`    | —                               |
| **Enterprise**  | Multi-tenant                         | `/api/v1/tenants` (closed)      |

The Community edition (this repository) is feature-complete for single-organization deployments. The Enterprise extension adds the platform-level tenant CRUD API for SaaS operators.

## 🤝 Contributing

Issues, discussions, and pull requests are welcome. Before opening a PR please make sure tests pass:

```bash
cd server && pytest
```

## 📜 License

OpenDesk is released under the [GNU Affero General Public License v3.0](LICENSE).
