import { OnCallBar, OutboundExecShell } from "../components/shell";
import { ExecPageHeader, PreviewPanel, TargetListPane } from "../components/target-ui";
import { TARGETS } from "../fixtures";

export function OutboundExecOnCallScreen() {
  return (
    <OutboundExecShell callBar={<OnCallBar />}>
      <ExecPageHeader />
      <div className="flex min-h-0 flex-1">
        <TargetListPane targets={TARGETS} selectedId={1} />
        <PreviewPanel target={TARGETS[0]} calling />
      </div>
    </OutboundExecShell>
  );
}
