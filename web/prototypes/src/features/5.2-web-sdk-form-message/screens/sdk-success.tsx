import { IconCheck } from "@tabler/icons-react";
import { MobileSdkShell } from "../components/sdk-shell";
import { TICKET_NUMBER } from "../fixtures";

export function SdkSuccessScreen() {
  return (
    <MobileSdkShell>
      <main className="flex flex-1 flex-col items-center justify-center px-7 pb-16 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-success/10 text-success"><IconCheck size={30} strokeWidth={2.2} /></div>
        <h2 className="mt-5 text-xl font-semibold tracking-tight">提交成功</h2>
        <p className="mt-2 max-w-[300px] text-sm leading-6 text-muted-foreground">我们已收到您的信息，会尽快与您联系。</p>
        <div className="mt-6 w-full rounded-lg border border-border bg-muted/35 px-4 py-3">
          <div className="text-xs text-muted-foreground">工单编号</div>
          <div className="mt-1 font-mono text-sm font-semibold tracking-wide">{TICKET_NUMBER}</div>
        </div>
        <p className="mt-5 text-xs leading-5 text-muted-foreground">您可以关闭此窗口，无需停留等待回复。</p>
      </main>
    </MobileSdkShell>
  );
}
