import { redirect } from 'next/navigation'

export default function LegacyMyOutboundTargetsPage() {
  redirect('/workspace/call?view=outbound-tasks')
}
