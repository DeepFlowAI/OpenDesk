import { CurrentCompactGlobalBar } from "../components/call-bar";
import { TicketsWorkspaceShell } from "../components/shell";

export function CallControlGlobalScreen() {
  return (
    <TicketsWorkspaceShell callBar={<CurrentCompactGlobalBar />} />
  );
}
