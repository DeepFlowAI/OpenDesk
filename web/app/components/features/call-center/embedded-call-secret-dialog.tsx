'use client'

import { useState } from 'react'
import { IconCheck, IconCopy, IconShieldLock } from '@tabler/icons-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'


type EmbeddedCallSecretDialogProps = {
  open: boolean
  secret: string | null
  isZh: boolean
  onClose: () => void
}

export function EmbeddedCallSecretDialog({
  open,
  secret,
  isZh,
  onClose,
}: EmbeddedCallSecretDialogProps) {
  const [copied, setCopied] = useState(false)
  if (!open || !secret) return null

  const copy = async () => {
    await navigator.clipboard.writeText(secret)
    setCopied(true)
    toast.success(isZh ? 'Secret 已复制' : 'Secret copied')
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4">
      <div className="w-full max-w-lg rounded-xl border border-border bg-background p-6 shadow-xl" role="dialog" aria-modal="true">
        <div className="flex items-center gap-2">
          <IconShieldLock className="text-success" />
          <h2 className="text-base font-semibold">{isZh ? '请保存 Server Secret' : 'Save the server secret'}</h2>
        </div>
        <p className="mt-3 text-sm text-muted-foreground">
          {isZh ? '此 Secret 仅完整展示一次。请立即保存到第三方服务端。' : 'This secret is shown once. Store it on the host server now.'}
        </p>
        <div className="mt-4 break-all rounded-lg border border-border bg-muted/40 p-3 font-mono text-sm">{secret}</div>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={copy}>
            {copied ? <IconCheck /> : <IconCopy />}
            {isZh ? '复制' : 'Copy'}
          </Button>
          <Button type="button" onClick={onClose}>{isZh ? '我已安全保存' : 'I saved it securely'}</Button>
        </div>
      </div>
    </div>
  )
}
