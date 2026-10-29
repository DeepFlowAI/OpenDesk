'use client'
import { useParams } from 'next/navigation'
import { QualityWorkbenchView } from '@/app/components/features/quality/quality-workbench'

export default function QualityWorkbenchPage() {
  const { reviewId } = useParams<{ reviewId: string }>()
  return <QualityWorkbenchView reviewId={Number(reviewId)} />
}
