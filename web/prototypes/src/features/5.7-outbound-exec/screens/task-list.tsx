import { IdleCallBar, OutboundExecShell } from "../components/shell";
import { TaskListPage } from "../components/target-ui";

export function OutboundExecTaskListScreen() {
  return (
    <OutboundExecShell callBar={<IdleCallBar />}>
      <TaskListPage />
    </OutboundExecShell>
  );
}
