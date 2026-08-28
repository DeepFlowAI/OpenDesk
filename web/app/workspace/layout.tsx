import type { Metadata } from 'next'
import WorkspaceLayoutClient from './workspace-layout-client'

export const metadata: Metadata = {
  title: '工作台-OpenDesk',
}

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return <WorkspaceLayoutClient>{children}</WorkspaceLayoutClient>
}
