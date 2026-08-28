import type { Metadata } from 'next'
import AdminLayoutClient from './admin-layout-client'

export const metadata: Metadata = {
  title: '管理后台-OpenDesk',
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AdminLayoutClient>{children}</AdminLayoutClient>
}
