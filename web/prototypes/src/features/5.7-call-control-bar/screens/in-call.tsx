import { ProposedBar } from "../components/call-bar";
import { CallWorkspaceShell } from "../components/shell";

export function CallControlInCallScreen() {
  return (
    <CallWorkspaceShell callBar={<ProposedBar />} />
  );
}
