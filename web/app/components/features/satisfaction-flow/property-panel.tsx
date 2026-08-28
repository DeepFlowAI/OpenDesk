'use client'

import { IconArrowDown, IconArrowUp, IconPlus, IconTrash } from '@tabler/icons-react'
import { useState } from 'react'
import type { Node } from '@xyflow/react'
import { newOption, type SatisfactionOption, type SatisfactionPrompt, type SatisfactionQuestionData } from '@/models/satisfaction-flow'
import { useAudioAsset, useUploadAudioAsset } from '@/service/use-audio-assets'

type Target = { id: string; label: string; type: string }
type ConditionGroup = {
  id: string
  name: string
  logic: 'AND' | 'OR'
  conditions: Array<{
    question_node_id: string
    operator: 'eq' | 'neq' | 'is_answered'
    option_id: string | null
  }>
}

function nodeTypeLabel(type: string | undefined): string {
  switch (type) {
    case 'start': return '开始'
    case 'play': return '播放提示'
    case 'question': return '评价问题'
    case 'condition': return '条件判断'
    case 'end': return '结束'
    default: return type ?? ''
  }
}

function generatedQuestionPrompt(name: string, options: SatisfactionOption[]): string {
  const choices = options
    .filter((option) => option.label.trim())
    .map((option) => `${option.label}请按 ${option.dtmf}`)
    .join('，')
  return `${name || '请评价本次服务'}。${choices}。`
}

function PromptEditor({ value, allowAuto = false, autoText, onChange }: {
  value: SatisfactionPrompt
  allowAuto?: boolean
  autoText?: string
  onChange: (value: SatisfactionPrompt) => void
}) {
  const upload = useUploadAudioAsset()
  const [uploadError, setUploadError] = useState<string | null>(null)
  const assetId = value.kind === 'audio' && value.asset_id > 0 ? value.asset_id : null
  const asset = useAudioAsset(assetId)
  return (
    <div className="space-y-2">
      <select
        value={value.kind}
        onChange={(event) => {
          const kind = event.target.value as SatisfactionPrompt['kind']
          onChange(kind === 'audio'
            ? { kind, asset_id: 0 }
            : { kind, text: kind === 'auto_tts' ? (autoText || '请根据提示按键评价。') : '' })
        }}
        className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm"
      >
        {allowAuto && <option value="auto_tts">自动生成 TTS</option>}
        <option value="tts">自定义 TTS</option>
        <option value="audio">音频文件</option>
      </select>
      {value.kind === 'audio' ? (
        <div className="space-y-2">
          <input
            type="file"
            accept="audio/mpeg,audio/wav,audio/x-wav"
            disabled={upload.isPending}
            onChange={async (event) => {
              const file = event.target.files?.[0]
              event.target.value = ''
              if (!file) return
              setUploadError(null)
              try {
                const uploaded = await upload.mutateAsync(file)
                onChange({ kind: 'audio', asset_id: uploaded.id })
              } catch {
                setUploadError('上传失败，请检查文件格式后重试')
              }
            }}
            className="block w-full text-xs file:mr-2 file:rounded-md file:border file:border-border file:bg-background file:px-2 file:py-1.5"
          />
          {upload.isPending && <p className="text-xs text-muted-foreground">上传中…</p>}
          {asset.data?.name && <p className="break-all text-xs text-muted-foreground">{asset.data.name}</p>}
          {asset.data?.preview_url && <audio controls src={asset.data.preview_url} className="h-9 w-full" />}
          {uploadError && <p className="text-xs text-destructive">{uploadError}</p>}
        </div>
      ) : (
        <textarea
          value={value.text}
          readOnly={value.kind === 'auto_tts'}
          maxLength={1000}
          onChange={(event) => onChange({ kind: value.kind, text: event.target.value })}
          className="min-h-24 w-full rounded-md border border-border bg-background p-3 text-sm read-only:bg-muted/50"
        />
      )}
    </div>
  )
}

function OutletSelect({ label, value, targets, onChange }: {
  label: string
  value: string | null
  targets: Target[]
  onChange: (target: string | null) => void
}) {
  return (
    <label className="grid grid-cols-[90px_1fr] items-center gap-2 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <select value={value ?? ''} onChange={(event) => onChange(event.target.value || null)} className="h-8 rounded-md border border-border bg-background px-2">
        <option value="">未连接</option>
        {targets.map((target) => <option key={target.id} value={target.id}>{target.label}</option>)}
      </select>
    </label>
  )
}

function QuestionOptions({ options, promptKind, onChange }: {
  options: SatisfactionOption[]
  promptKind: SatisfactionPrompt['kind']
  onChange: (options: SatisfactionOption[]) => void
}) {
  const replacePreset = (count: 2 | 3 | 5 | 'custom') => {
    const labels = count === 2 ? ['不满意', '满意'] : count === 3 ? ['不满意', '一般', '满意'] : count === 5 ? ['非常不满意', '不满意', '一般', '满意', '非常满意'] : ['', '']
    onChange(labels.map((label, index) => newOption(label, String(index + 1))))
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {([2, 3, 5, 'custom'] as const).map((preset) => <button key={preset} type="button" onClick={() => replacePreset(preset)} className="rounded-md border border-border px-2 py-1 text-xs hover:bg-muted">{preset === 'custom' ? '自定义' : `${preset} 档`}</button>)}
      </div>
      {promptKind !== 'auto_tts' && <p className="rounded-md bg-warning/10 p-2 text-xs text-warning-foreground">按键映射变化后，请核对调查话术。</p>}
      {options.map((option, index) => (
        <div key={option.id} className="grid grid-cols-[36px_1fr_auto] gap-2">
          <select value={option.dtmf} onChange={(event) => onChange(options.map((item, itemIndex) => itemIndex === index ? { ...item, dtmf: event.target.value } : item))} className="h-9 rounded-md border border-border bg-background text-center text-sm">
            {Array.from({ length: 10 }, (_value, digit) => <option key={digit}>{digit}</option>)}
          </select>
          <input value={option.label} maxLength={30} onChange={(event) => onChange(options.map((item, itemIndex) => itemIndex === index ? { ...item, label: event.target.value } : item))} className="h-9 rounded-md border border-border bg-background px-2 text-sm" />
          <div className="flex items-center">
            <button type="button" disabled={index === 0} onClick={() => { const next = [...options]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; onChange(next) }} aria-label="上移选项" className="p-1 disabled:opacity-30"><IconArrowUp size={15} /></button>
            <button type="button" disabled={index === options.length - 1} onClick={() => { const next = [...options]; [next[index], next[index + 1]] = [next[index + 1], next[index]]; onChange(next) }} aria-label="下移选项" className="p-1 disabled:opacity-30"><IconArrowDown size={15} /></button>
            <button type="button" disabled={options.length <= 2} onClick={() => onChange(options.filter((_item, itemIndex) => itemIndex !== index))} aria-label="删除选项" className="p-1 text-destructive disabled:opacity-30"><IconTrash size={15} /></button>
          </div>
        </div>
      ))}
      <button type="button" disabled={options.length >= 10} onClick={() => { const used = new Set(options.map((option) => option.dtmf)); const digit = Array.from({ length: 10 }, (_value, index) => String(index)).find((value) => !used.has(value)); if (digit) onChange([...options, newOption('', digit)]) }} className="flex items-center gap-1 rounded-md border border-border px-2 py-1.5 text-xs disabled:opacity-40"><IconPlus size={14} /> 添加选项</button>
    </div>
  )
}

export function SatisfactionPropertyPanel({
  selected,
  targets,
  questions,
  edgeTarget,
  updateData,
  connect,
  remove,
}: {
  selected: Node | null
  targets: Target[]
  questions: Array<{ id: string; name: string; options: SatisfactionOption[] }>
  edgeTarget: (source: string, handle: string) => string | null
  updateData: (id: string, data: Record<string, unknown>) => void
  connect: (source: string, handle: string, target: string | null) => void
  remove: (id: string) => void
}) {
  if (!selected) return <aside className="flex w-[360px] shrink-0 items-center justify-center border-l border-border bg-white px-6 text-center text-sm text-muted-foreground">点击画布上的节点以编辑其配置</aside>
  const data = selected.data as Record<string, unknown>
  const targetOptions = targets.filter((target) => target.id !== selected.id && target.type !== 'start')
  const set = (patch: Record<string, unknown>) => updateData(selected.id, { ...data, ...patch })

  return (
    <aside className="w-[360px] shrink-0 overflow-y-auto border-l border-border bg-white">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2"><h2 className="text-base font-semibold text-foreground">{nodeTypeLabel(selected.type)}</h2><span className="rounded bg-muted px-2 py-0.5 font-mono text-xs text-muted-foreground">{selected.type}</span></div>
        {selected.type !== 'start' && <button type="button" onClick={() => remove(selected.id)} aria-label="删除节点" title="删除节点" className="text-destructive hover:text-destructive/80"><IconTrash size={17} /></button>}
      </div>
      <div className="space-y-5 px-5 py-4">
        {selected.type === 'start' && <p className="text-sm text-muted-foreground">满意度流程从这里开始。</p>}
        {selected.type === 'play' && <PromptEditor value={data.prompt as SatisfactionPrompt} onChange={(prompt) => set({ prompt })} />}
        {selected.type === 'question' && (() => {
          const question = data as unknown as SatisfactionQuestionData
          return <>
            <label className="block text-xs font-medium">问题名称<input value={question.name} maxLength={50} onChange={(event) => { const name = event.target.value; set({ name, prompt: question.prompt.kind === 'auto_tts' ? { kind: 'auto_tts', text: generatedQuestionPrompt(name, question.options) } : question.prompt }) }} className="mt-2 h-9 w-full rounded-md border border-border bg-background px-3 text-sm" /></label>
            <label className="flex items-center justify-between text-sm"><span>必答</span><input type="checkbox" checked={question.required} onChange={(event) => set({ required: event.target.checked })} /></label>
            <div><p className="mb-2 text-xs font-medium">播报内容</p><PromptEditor value={question.prompt} allowAuto autoText={generatedQuestionPrompt(question.name, question.options)} onChange={(prompt) => set({ prompt })} /></div>
            <label className="flex items-center justify-between text-sm"><span>禁止提示音期间输入</span><input type="checkbox" checked={question.barge_in_disabled} onChange={(event) => set({ barge_in_disabled: event.target.checked })} /></label>
            {question.barge_in_disabled && <p className="rounded-md bg-warning/10 p-2 text-xs text-warning-foreground">客户必须等待提示音播放完成后才能按键。</p>}
            <div><p className="mb-2 text-xs font-medium">选项与 DTMF</p><QuestionOptions options={question.options} promptKind={question.prompt.kind} onChange={(options) => set({ options, prompt: question.prompt.kind === 'auto_tts' ? { kind: 'auto_tts', text: generatedQuestionPrompt(question.name, options) } : question.prompt })} /></div>
            <label className="block text-xs font-medium">输入等待时间（秒）<input type="number" min={1} max={30} value={question.timeout_seconds} onChange={(event) => set({ timeout_seconds: Number(event.target.value) })} className="mt-2 h-9 w-full rounded-md border border-border bg-background px-3 text-sm" /></label>
            <label className="flex items-center justify-between text-sm"><span>启用重试</span><input type="checkbox" checked={question.retry.enabled} onChange={(event) => set({ retry: { ...question.retry, enabled: event.target.checked } })} /></label>
            {question.retry.enabled && <><div className="grid grid-cols-2 gap-3"><label className="text-xs">无输入次数<input type="number" min={0} max={5} value={question.retry.no_input} onChange={(event) => set({ retry: { ...question.retry, no_input: Number(event.target.value) } })} className="mt-1 h-8 w-full rounded-md border border-border px-2" /></label><label className="text-xs">无匹配次数<input type="number" min={0} max={5} value={question.retry.no_match} onChange={(event) => set({ retry: { ...question.retry, no_match: Number(event.target.value) } })} className="mt-1 h-8 w-full rounded-md border border-border px-2" /></label></div>{question.retry.no_input > 0 && <div><p className="mb-2 text-xs font-medium">无输入提示</p><PromptEditor value={question.retry.no_input_prompt ?? { kind: 'tts', text: '' }} onChange={(no_input_prompt) => set({ retry: { ...question.retry, no_input_prompt } })} /></div>}{question.retry.no_match > 0 && <div><p className="mb-2 text-xs font-medium">无匹配提示</p><PromptEditor value={question.retry.no_match_prompt ?? { kind: 'tts', text: '' }} onChange={(no_match_prompt) => set({ retry: { ...question.retry, no_match_prompt } })} /></div>}</>}
          </>
        })()}
        {selected.type === 'condition' && (() => {
          const groups = (data.groups as ConditionGroup[]) ?? []
          return <div className="space-y-3">
            {groups.map((group, index) => {
              const condition = group.conditions[0]
              const question = questions.find((item) => item.id === condition.question_node_id)
              return <div key={group.id} className="space-y-2 rounded-lg border border-border p-3">
                <input value={group.name} onChange={(event) => set({ groups: groups.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item) })} className="h-8 w-full rounded-md border border-border px-2 text-sm" />
                <select value={condition.question_node_id} onChange={(event) => set({ groups: groups.map((item, itemIndex) => itemIndex === index ? { ...item, conditions: [{ ...condition, question_node_id: event.target.value, option_id: null }] } : item) })} className="h-8 w-full rounded-md border border-border px-2 text-xs"><option value="">选择前置问题</option>{questions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
                <select value={condition.operator} onChange={(event) => set({ groups: groups.map((item, itemIndex) => itemIndex === index ? { ...item, conditions: [{ ...condition, operator: event.target.value as typeof condition.operator }] } : item) })} className="h-8 w-full rounded-md border border-border px-2 text-xs"><option value="eq">选项等于</option><option value="neq">选项不等于</option><option value="is_answered">已回答</option></select>
                {condition.operator !== 'is_answered' && <select value={condition.option_id ?? ''} onChange={(event) => set({ groups: groups.map((item, itemIndex) => itemIndex === index ? { ...item, conditions: [{ ...condition, option_id: event.target.value || null }] } : item) })} className="h-8 w-full rounded-md border border-border px-2 text-xs"><option value="">选择选项</option>{question?.options.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}</select>}
              </div>
            })}
            <button type="button" disabled={!questions.length || groups.length >= 20} onClick={() => { const question = questions[0]; set({ groups: [...groups, { id: `group_${crypto.randomUUID()}`, name: `条件 ${groups.length + 1}`, logic: 'AND', conditions: [{ question_node_id: question.id, operator: 'is_answered', option_id: null }] }] }) }} className="flex items-center gap-1 rounded-md border border-border px-2 py-1.5 text-xs disabled:opacity-40"><IconPlus size={14} /> 添加条件组</button>
          </div>
        })()}
        {selected.type === 'end' && <><label className="block text-xs font-medium">完成类型<select value={String(data.completion_type ?? 'completed')} onChange={(event) => set({ completion_type: event.target.value })} className="mt-2 h-9 w-full rounded-md border border-border bg-background px-3 text-sm"><option value="completed">正常完成</option><option value="incomplete">未完成结束</option></select></label><label className="flex items-center justify-between text-sm"><span>结束前播放</span><input type="checkbox" checked={data.pre_play != null} onChange={(event) => set({ pre_play: event.target.checked ? { kind: 'tts', text: '感谢您的评价，祝您生活愉快。' } : null })} /></label>{data.pre_play != null && <PromptEditor value={data.pre_play as SatisfactionPrompt} onChange={(pre_play) => set({ pre_play })} />}</>}

        <div className="space-y-2 border-t border-border pt-4">
          <p className="text-xs font-semibold">出口</p>
          {(selected.type === 'start' || selected.type === 'play') && <OutletSelect label="下一步" value={edgeTarget(selected.id, 'next')} targets={targetOptions} onChange={(target) => connect(selected.id, 'next', target)} />}
          {selected.type === 'question' && [['answered', '已回答'], ['no_input', '无输入'], ['no_match', '无匹配'], ['error', '错误']].map(([handle, label]) => <OutletSelect key={handle} label={label} value={edgeTarget(selected.id, handle)} targets={targetOptions} onChange={(target) => connect(selected.id, handle, target)} />)}
          {selected.type === 'condition' && ([...(((data.groups as ConditionGroup[]) ?? []).map((group) => [group.id, group.name] as const)), ['default', '默认'] as const]).map(([handle, label]) => <OutletSelect key={handle} label={label} value={edgeTarget(selected.id, handle)} targets={targetOptions} onChange={(target) => connect(selected.id, handle, target)} />)}
        </div>
      </div>
    </aside>
  )
}
