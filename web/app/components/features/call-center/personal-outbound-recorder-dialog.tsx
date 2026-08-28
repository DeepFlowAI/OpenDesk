'use client'

import { useEffect, useRef, useState } from 'react'
import { IconMicrophone, IconPlayerStop } from '@tabler/icons-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { encodeMonoWav } from '@/lib/audio-wav'

type RecorderRuntime = {
  context: AudioContext
  source: MediaStreamAudioSourceNode
  processor: ScriptProcessorNode
  gain: GainNode
  stream: MediaStream
  chunks: Float32Array[]
  sampleRate: number
}

export function PersonalOutboundRecorderDialog({
  open,
  type,
  onOpenChange,
  onSave,
  saving,
}: {
  open: boolean
  type: 'opening' | 'closing'
  onOpenChange: (open: boolean) => void
  onSave: (file: File) => Promise<void>
  saving: boolean
}) {
  const { locale } = useLocaleStore()
  const [state, setState] = useState<'ready' | 'recording' | 'preview'>('ready')
  const [elapsed, setElapsed] = useState(0)
  const [duration, setDuration] = useState(0)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [listened, setListened] = useState(false)
  const [deviceName, setDeviceName] = useState('')
  const runtimeRef = useRef<RecorderRuntime | null>(null)
  const stopRef = useRef<() => void>(() => undefined)
  const minSeconds = type === 'opening' ? 3 : 2

  const cleanupRuntime = () => {
    const runtime = runtimeRef.current
    if (!runtime) return
    runtime.processor.disconnect()
    runtime.source.disconnect()
    runtime.gain.disconnect()
    runtime.stream.getTracks().forEach((track) => track.stop())
    void runtime.context.close()
    runtimeRef.current = null
  }

  const reset = () => {
    cleanupRuntime()
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(null)
    setFile(null)
    setListened(false)
    setElapsed(0)
    setDuration(0)
    setState('ready')
  }

  useEffect(() => () => cleanupRuntime(), [])

  useEffect(() => {
    if (state !== 'recording') return
    const startedAt = Date.now()
    const timer = window.setInterval(() => {
      const seconds = (Date.now() - startedAt) / 1000
      setElapsed(seconds)
      if (seconds >= 30) stopRef.current()
    }, 100)
    return () => window.clearInterval(timer)
  }, [state])

  const stop = () => {
    const runtime = runtimeRef.current
    if (!runtime) return
    const totalSamples = runtime.chunks.reduce((total, chunk) => total + chunk.length, 0)
    const samples = new Float32Array(totalSamples)
    let offset = 0
    runtime.chunks.forEach((chunk) => {
      samples.set(chunk, offset)
      offset += chunk.length
    })
    const seconds = totalSamples / runtime.sampleRate
    const wav = encodeMonoWav(samples, runtime.sampleRate)
    const nextFile = new File([wav], `${type}-${Date.now()}.wav`, { type: 'audio/wav' })
    const url = URL.createObjectURL(nextFile)
    cleanupRuntime()
    setFile(nextFile)
    setPreviewUrl(url)
    setDuration(seconds)
    setElapsed(seconds)
    setState('preview')
    if (seconds >= 30) toast.info(t('personalAuto.recordingLimit', locale))
  }
  stopRef.current = stop

  const start = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof AudioContext === 'undefined') {
      toast.error(t('personalAuto.recordingUnsupported', locale))
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const context = new AudioContext()
      const source = context.createMediaStreamSource(stream)
      const processor = context.createScriptProcessor(4096, 1, 1)
      const gain = context.createGain()
      gain.gain.value = 0
      const chunks: Float32Array[] = []
      processor.onaudioprocess = (event) => {
        chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)))
      }
      source.connect(processor)
      processor.connect(gain)
      gain.connect(context.destination)
      runtimeRef.current = { context, source, processor, gain, stream, chunks, sampleRate: context.sampleRate }
      setDeviceName(stream.getAudioTracks()[0]?.label ?? t('personalAuto.defaultMicrophone', locale))
      setState('recording')
      setElapsed(0)
    } catch {
      toast.error(t('personalAuto.microphoneDenied', locale))
    }
  }

  const save = async () => {
    if (!file || duration < minSeconds || !listened) return
    try {
      await onSave(file)
      reset()
      onOpenChange(false)
    } catch {
      // The parent reports the upload error; keep the preview available for retry.
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => {
      if (state === 'recording' || saving) return
      if (!next) reset()
      onOpenChange(next)
    }}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t(type === 'opening' ? 'personalAuto.recordOpening' : 'personalAuto.recordClosing', locale)}</DialogTitle>
          <DialogDescription>{t('personalAuto.recordDescription', locale, { min: minSeconds })}</DialogDescription>
        </DialogHeader>
        <div className="rounded-xl border border-border bg-muted/20 p-5 text-center">
          {state === 'ready' && <><IconMicrophone className="mx-auto text-muted-foreground" size={32} /><p className="mt-3 text-sm text-muted-foreground">{t('personalAuto.recordReady', locale)}</p></>}
          {state === 'recording' && <><span className="mx-auto block h-3 w-3 animate-pulse rounded-full bg-destructive" /><p className="mt-3 font-mono text-2xl font-semibold">{elapsed.toFixed(1)}s</p><p className="mt-1 text-xs text-muted-foreground">{deviceName}</p><div className="mx-auto mt-4 flex h-10 max-w-xs items-center justify-center gap-1" aria-hidden>{Array.from({ length: 24 }, (_, index) => <span key={index} className="w-1 rounded-full bg-primary/60" style={{ height: `${12 + ((index * 13) % 28)}px` }} />)}</div></>}
          {state === 'preview' && previewUrl && <><audio className="w-full" controls src={previewUrl} onPlay={() => setListened(true)} /><p className="mt-2 text-xs text-muted-foreground">{duration.toFixed(1)}s · {duration < minSeconds ? t('personalAuto.recordTooShort', locale, { min: minSeconds }) : t(listened ? 'personalAuto.listened' : 'personalAuto.listenRequired', locale)}</p></>}
        </div>
        <DialogFooter>
          {state === 'ready' && <Button onClick={() => void start()}><IconMicrophone size={16} />{t('personalAuto.startRecording', locale)}</Button>}
          {state === 'recording' && <Button variant="destructive" onClick={stop}><IconPlayerStop size={16} />{t('personalAuto.stopRecording', locale)}</Button>}
          {state === 'preview' && <><Button variant="outline" disabled={saving} onClick={reset}>{t('personalAuto.recordAgain', locale)}</Button><Button disabled={!listened || duration < minSeconds || saving} onClick={() => void save()}>{t(saving ? 'personalAuto.savingRecording' : 'personalAuto.saveRecording', locale)}</Button></>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
