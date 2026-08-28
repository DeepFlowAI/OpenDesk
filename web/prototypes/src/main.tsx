import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { OutboundScriptScreens } from "./features/5.2-outbound-script";
import { WebSdkFormMessageScreens } from "./features/5.2-web-sdk-form-message";
import { LingoMasterScreens } from "./features/5.3-lingomaster";
import { AutoOutboundScreens } from "./features/5.4-auto-outbound";
import { SmsSingleSendScreens } from "./features/5.4-sms-single-send";
import { EmbeddedPagesScreens } from "./features/5.5-embedded-pages";
import { LearningExamsScreens } from "./features/5.6-learning-exams";
import { SmsBulkSendScreens } from "./features/5.6-sms-bulk-send";
import { SchedulingCenterScreens } from "./features/5.7-scheduling-center";
import { SchedulingMyScreens } from "./features/5.7-scheduling-my";
import { SchedulingRulesScreens } from "./features/5.7-scheduling-rules";
import { CallTrajectoryScreens } from "./features/5.7-call-trajectory";
import "./styles.css";

export interface PrototypeScreen {
  id: string;
  title: string;
  description: string;
  render: () => ReactNode;
}

const screens: PrototypeScreen[] = [
  ...OutboundScriptScreens,
  ...WebSdkFormMessageScreens,
  ...LingoMasterScreens,
  ...AutoOutboundScreens,
  ...SmsSingleSendScreens,
  ...EmbeddedPagesScreens,
  ...LearningExamsScreens,
  ...SmsBulkSendScreens,
  ...SchedulingCenterScreens,
  ...SchedulingRulesScreens,
  ...SchedulingMyScreens,
  ...CallTrajectoryScreens,
];
const requestedScreen = new URLSearchParams(window.location.search).get("screen");
const currentScreen = screens.find((screen) => screen.id === requestedScreen);

function Catalog() {
  return (
    <main className="min-h-screen bg-surface px-8 py-10">
      <div className="mx-auto max-w-5xl">
        <div className="mb-8">
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            OpenDesk · React prototypes
          </div>
          <h1 className="font-display text-3xl font-bold tracking-tight">静态原型目录</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
            每个 Screen 是一个固定页面状态。目录链接只用于定位评审页面，不模拟产品交互。
          </p>
        </div>
        <div className="grid grid-cols-2 gap-4">
          {screens.map((screen, index) => (
            <a
              key={screen.id}
              href={`?screen=${encodeURIComponent(screen.id)}`}
              className="group rounded-xl border border-border bg-background p-5 transition-colors hover:border-foreground/30"
            >
              <div className="mb-6 flex items-center justify-between">
                <span className="font-mono text-xs text-muted-foreground">{screen.id}</span>
                <span className="flex h-7 w-7 items-center justify-center rounded-md bg-muted text-xs font-semibold">
                  {String(index + 1).padStart(2, "0")}
                </span>
              </div>
              <h2 className="font-display text-base font-semibold">{screen.title}</h2>
              <p className="mt-2 text-sm leading-5 text-muted-foreground">{screen.description}</p>
            </a>
          ))}
        </div>
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {currentScreen ? (
      <div data-prototype-screen={currentScreen.id}>{currentScreen.render()}</div>
    ) : (
      <Catalog />
    )}
  </StrictMode>
);
