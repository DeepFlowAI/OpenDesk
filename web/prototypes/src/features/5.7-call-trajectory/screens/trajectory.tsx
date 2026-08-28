import { RecordsBackdrop } from "../components/records-backdrop"
import { TrajectoryDrawer } from "../components/trajectory-drawer"

export function CallTrajectoryBusinessScreen() {
  return (
    <RecordsBackdrop>
      <TrajectoryDrawer mode="business" />
    </RecordsBackdrop>
  )
}

export function CallTrajectoryTechnicalScreen() {
  return (
    <RecordsBackdrop>
      <TrajectoryDrawer mode="technical" />
    </RecordsBackdrop>
  )
}
