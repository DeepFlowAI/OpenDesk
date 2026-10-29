'use client'
import { useParams } from 'next/navigation'
import { QualityReviewDetailView } from '@/app/components/features/quality/quality-review-detail'

export default function QualityReviewDetailPage() {
  const { planId, reviewId } = useParams<{ planId: string; reviewId: string }>()
  return <QualityReviewDetailView planId={Number(planId)} reviewId={Number(reviewId)} />
}
