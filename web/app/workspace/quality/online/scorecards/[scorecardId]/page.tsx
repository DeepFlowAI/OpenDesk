'use client'

import { useParams } from 'next/navigation'
import { ScorecardEditor } from '@/app/components/features/quality/scorecard-editor'
import { useQualityScorecard } from '@/service/use-quality-scorecards'

export default function QualityScorecardDetailPage() {
  const params = useParams<{ scorecardId: string }>()
  const id = Number(params.scorecardId)
  const { data, isLoading } = useQualityScorecard(id)
  return <ScorecardEditor scorecard={data} loading={isLoading} />
}
