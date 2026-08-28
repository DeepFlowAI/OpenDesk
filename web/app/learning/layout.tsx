import type { Metadata } from 'next'
import LearningLayoutClient from './learning-layout-client'

export const metadata: Metadata = {
  title: '学习中心-OpenDesk',
}

export default function LearningLayout({ children }: { children: React.ReactNode }) {
  return <LearningLayoutClient>{children}</LearningLayoutClient>
}
