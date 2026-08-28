import { IdleCallBar, OutboundExecShell } from "../components/shell";
import { ExecPageHeader, PreviewPanel, TargetListPane } from "../components/target-ui";
import { TARGETS } from "../fixtures";

export function OutboundExecPreviewPanelScreen() {
  return (
    <OutboundExecShell callBar={<IdleCallBar />}>
      <ExecPageHeader />
      <div className="flex min-h-0 flex-1">
        <TargetListPane targets={TARGETS} selectedId={2} />
        <PreviewPanel target={TARGETS[1]} />
      </div>
    </OutboundExecShell>
  );
}
