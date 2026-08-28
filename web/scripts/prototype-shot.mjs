import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium } from "playwright";
import { createServer } from "vite";

const ROOT = resolve(import.meta.dirname, "../prototypes");
const OUTPUT = resolve(ROOT, "screenshots");
const PORT = 4173;
const SCREEN_IDS = [
  "outbound-script/template-editor",
  "outbound-script/template-preview",
  "outbound-script/agent-guided",
  "outbound-script/agent-all-scripts",
  "web-sdk-form-message/channel-service-form-mode",
  "web-sdk-form-message/channel-field-drawer",
  "web-sdk-form-message/sdk-form-desktop",
  "web-sdk-form-message/sdk-success-mobile",
  "web-sdk-form-message/ticket-detail-snapshot",
  "lingomaster/settings-overview",
  "lingomaster/settings-validation-error",
  "lingomaster/workspace-translated",
  "lingomaster/workspace-original-view",
  "lingomaster/workspace-language-picker",
  "embedded-pages/chat-settings",
  "embedded-pages/chat-edit-iframe",
  "embedded-pages/chat-edit-react",
  "embedded-pages/chat-aux-iframe",
  "embedded-pages/chat-aux-react",
  "embedded-pages/call-settings",
  "embedded-pages/call-edit-iframe",
  "embedded-pages/call-pop-system",
  "embedded-pages/call-pop-embedded",
  "call-trajectory/business",
  "call-trajectory/technical",
];

const SCREEN_VIEWPORTS = {
  "web-sdk-form-message/sdk-success-mobile": { width: 390, height: 844 },
};

await mkdir(OUTPUT, { recursive: true });

const server = await createServer({
  configFile: resolve(ROOT, "vite.config.ts"),
  server: { host: "127.0.0.1", port: PORT },
});
await server.listen();

const baseUrl = server.resolvedUrls?.local[0];
if (!baseUrl) {
  throw new Error("Prototype server did not expose a local URL");
}

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
});

try {
  for (const screenId of SCREEN_IDS) {
    await page.setViewportSize(SCREEN_VIEWPORTS[screenId] ?? { width: 1440, height: 900 });
    const fileName = `${screenId.replaceAll("/", "--")}.png`;
    await page.goto(`${baseUrl}?screen=${encodeURIComponent(screenId)}`, {
      waitUntil: "networkidle",
    });
    await page.screenshot({ path: resolve(OUTPUT, fileName) });
    console.log(`saved prototypes/screenshots/${fileName}`);
  }
} finally {
  await browser.close();
  await server.close();
}
