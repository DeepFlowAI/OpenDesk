import { OutboundExecShell, WrapUpCallBar } from "../components/shell";
import { ExecPageHeader, TargetListPane, WrapUpPanel } from "../components/target-ui";
import { TARGETS } from "../fixtures";

export function OutboundExecWrapUpScreen() {
  return (
    <OutboundExecShell callBar={<WrapUpCallBar />}>
      <ExecPageHeader />
      <div className="flex min-h-0 flex-1">
        <TargetListPane targets={TARGETS} selectedId={1} />
        <WrapUpPanel />
      </div>
    </OutboundExecShell>
  );
}
