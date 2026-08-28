# OpenDesk React 原型

这里是与生产 Next.js 路由隔离的静态 React 原型查看器。完整约定见 `需求文档/React 原型规范.md`。

```bash
cd web
npm run prototype
```

打开首页可查看 Screen 目录，也可以通过 `?screen={screen-id}` 直接打开某个静态状态。

```bash
npm run prototype:check
npm run prototype:build
npm run prototype:shot
```

`prototype:shot` 会在 `web/prototypes/screenshots/` 生成本地 PNG（需要本地安装 Playwright 浏览器）。截图是可再生成的评审产物，不是原型真源。
