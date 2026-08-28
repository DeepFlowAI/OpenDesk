import type { ReactNode } from "react";
import { IconSchool } from "@tabler/icons-react";

export type LearningTab = "my" | "admin";

/**
 * Standalone full-page shell for /learning: logo + title, internal tabs
 * (exam tabs reserved for a later iteration), account menu.
 */
export function LearningShell({
  tab,
  children,
}: {
  tab?: LearningTab;
  children: ReactNode;
}) {
  return (
    <div className="flex h-full flex-col bg-muted/30 text-foreground">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <IconSchool size={22} className="text-foreground" />
            <span className="text-base font-semibold">学习中心</span>
          </div>
          {tab ? (
            <nav className="ml-6 flex items-center gap-1 self-stretch">
              <TabItem label="我的学习" active={tab === "my"} />
              <TabItem label="课程管理" active={tab === "admin"} />
              {/* Reserved slot for a future exam module (我的考试 / 考试管理); not rendered in this iteration. */}
              <span
                className="ml-2 hidden items-center rounded-md border border-dashed border-border px-2 py-1 text-[10px] text-muted-foreground/70 xl:flex"
                aria-hidden
              >
                预留：考试模块 Tab
              </span>
            </nav>
          ) : null}
        </div>
        <div className="flex items-center gap-2 text-sm">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">
            张
          </div>
          <span>张敏</span>
        </div>
      </header>
      <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
    </div>
  );
}

function TabItem({ label, active }: { label: string; active?: boolean }) {
  return (
    <div
      className={`-mb-px flex h-full items-center border-b-2 px-3 text-sm ${
        active
          ? "border-primary font-semibold text-foreground"
          : "border-transparent text-muted-foreground"
      }`}
    >
      {label}
    </div>
  );
}
