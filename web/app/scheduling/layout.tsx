import type { Metadata } from 'next'
import SchedulingLayoutClient from './scheduling-layout-client'

export const metadata: Metadata = {
  title: '排班中心-OpenDesk',
}

export default function SchedulingLayout({ children }: { children: React.ReactNode }) {
  return <SchedulingLayoutClient>{children}</SchedulingLayoutClient>
}
