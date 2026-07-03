import type { Metadata } from 'next'

export const metadata: Metadata = {
  description: 'Customer service chat',
}

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
