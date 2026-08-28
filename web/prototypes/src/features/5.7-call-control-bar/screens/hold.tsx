import { ProposedMutedHoldBar } from "../components/call-bar";
import { CallWorkspaceShell } from "../components/shell";

export function CallControlHoldScreen() {
  return (
    <CallWorkspaceShell tone="warning" callBar={<ProposedMutedHoldBar />} />
  );
}
