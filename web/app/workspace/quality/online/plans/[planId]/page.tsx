'use client'
import { useParams } from 'next/navigation'
import { QualityPlanForm } from '@/app/components/features/quality/plan-form'
import { useQualityPlan } from '@/service/use-quality-plans'
export default function QualityPlanDetailPage() { const { planId } = useParams<{ planId: string }>(); const { data, isLoading } = useQualityPlan(Number(planId)); return <QualityPlanForm plan={data} loading={isLoading} /> }
