import { AgentShell } from "../components/agent-shell";
import { TargetDetail, TargetList } from "../components/agent-content";
import { AllScriptsDrawer, GuidedScriptDrawer } from "../components/script-drawer";

export function AgentScriptScreen({ mode }: { mode: "guided" | "all" }) {
  return (
    <AgentShell>
      <div className="flex h-full"><TargetList /><TargetDetail />{mode === "guided" ? <GuidedScriptDrawer /> : <AllScriptsDrawer />}</div>
    </AgentShell>
  );
}
