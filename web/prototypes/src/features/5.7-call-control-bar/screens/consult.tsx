import { ProposedBar } from "../components/call-bar";
import { CallWorkspaceShell } from "../components/shell";

export function CallControlConsultScreen() {
  return (
    <CallWorkspaceShell tone="warning" callBar={<ProposedBar state="consult" />} />
  );
}
