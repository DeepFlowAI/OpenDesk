'use client'

import { use } from 'react'
import { ChannelForm } from '../form'

export default function EditChannelPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return <ChannelForm channelId={Number(id)} />
}
