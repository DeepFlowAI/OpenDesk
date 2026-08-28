import { ProposedBar } from "../components/call-bar";
import { CallWorkspaceShell } from "../components/shell";

export function CallControlConferenceScreen() {
  return (
    <CallWorkspaceShell callBar={<ProposedBar state="conference" />} />
  );
}
