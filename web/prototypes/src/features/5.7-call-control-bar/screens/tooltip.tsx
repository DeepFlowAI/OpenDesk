import { ProposedBar } from "../components/call-bar";
import { CallWorkspaceShell } from "../components/shell";

export function CallControlTooltipScreen() {
  return (
    <CallWorkspaceShell callBar={<ProposedBar tooltipOn="transfer" />} />
  );
}
