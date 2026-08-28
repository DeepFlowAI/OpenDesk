import type { ReactNode } from "react";
import { IconHeadset, IconVolume } from "@tabler/icons-react";

export function SdkHeader() {
  return (
    <header className="flex min-h-15 shrink-0 items-center gap-3 bg-neutral-900 px-4 py-3 text-white">
      <div className="flex h-8 w-8 items-center justify-center rounded-md bg-white/10"><IconHeadset size={19} /></div>
      <h1 className="min-w-0 flex-1 truncate text-base font-semibold">官网在线咨询</h1>
      <div className="flex h-8 w-8 items-center justify-center rounded-md"><IconVolume size={18} /></div>
    </header>
  );
}

export function LegalFooter() {
  return (
    <footer className="flex items-center justify-center gap-1.5 px-4 py-1.5 text-[11px] text-muted-foreground/70">
      <span>AGPL-3.0 开源许可</span><span className="underline">查看源代码</span>
    </footer>
  );
}

export function DesktopSdkShell({ children }: { children: ReactNode }) {
  return (
    <div className="prototype-frame flex min-h-0 flex-col bg-muted">
      <div className="mx-auto flex min-h-0 w-full max-w-[720px] flex-1 flex-col bg-background shadow-xl">
        <SdkHeader />
        {children}
      </div>
      <LegalFooter />
    </div>
  );
}

export function MobileSdkShell({ children }: { children: ReactNode }) {
  return (
    <div className="prototype-frame-mobile flex min-h-0 flex-col bg-background">
      <SdkHeader />
      {children}
      <LegalFooter />
    </div>
  );
}
