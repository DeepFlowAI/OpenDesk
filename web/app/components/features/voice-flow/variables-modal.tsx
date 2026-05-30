'use client'
import { IconCopy, IconX } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useSystemVariables } from '@/service/use-system-variables'
import { useLocaleStore } from '@/context/locale-store'

export function VariablesModal({
  flowVariables,
  onClose,
}: {
  flowVariables: { name: string; source_node_id: string }[]
  onClose: () => void
}) {
  const { locale } = useLocaleStore()
  const { data } = useSystemVariables()

  const onCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toast.success('已复制')
    } catch {
      toast.error('复制失败')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-[640px] max-w-[90vw] rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h3 className="flex items-center gap-2 text-base font-semibold">
            <span className="font-mono text-muted-foreground">{'{ }'}</span>
            变量参考
          </h3>
          <button type="button" onClick={onClose} className="text-foreground/60 hover:text-foreground">
            <IconX size={18} />
          </button>
        </div>
        <p className="px-5 pt-3 text-xs text-foreground/60">
          在「信息判定」等节点中可直接选择或输入以下变量名。
        </p>

        <div className="grid grid-cols-[1fr_2fr_60px] gap-2 border-b border-border px-5 py-2 text-xs font-semibold text-foreground/70">
          <div>变量名</div>
          <div>说明</div>
          <div className="text-right">复制</div>
        </div>

        <div className="max-h-[400px] overflow-y-auto px-5 py-2">
          {(data?.items ?? []).map((v) => (
            <div
              key={v.name}
              className="grid grid-cols-[1fr_2fr_60px] items-center gap-2 border-b border-border/50 py-2 text-sm last:border-b-0"
            >
              <code className="rounded bg-purple-50 px-1.5 py-0.5 font-mono text-xs text-purple-700">
                {v.name}
              </code>
              <span className="text-foreground/80">
                {locale === 'zh' ? v.display_name_zh : v.display_name_en}：
                {locale === 'zh' ? v.description_zh : v.description_en}
              </span>
              <button
                type="button"
                onClick={() => onCopy(v.name)}
                className="ml-auto text-foreground/60 hover:text-foreground"
                aria-label="复制"
              >
                <IconCopy size={14} />
              </button>
            </div>
          ))}

          {flowVariables.length > 0 && (
            <>
              <p className="mt-3 mb-1 text-xs font-semibold text-foreground/70">流程变量</p>
              {flowVariables.map((v) => (
                <div
                  key={v.name}
                  className="grid grid-cols-[1fr_2fr_60px] items-center gap-2 border-b border-border/50 py-2 text-sm last:border-b-0"
                >
                  <code className="rounded bg-amber-50 px-1.5 py-0.5 font-mono text-xs text-amber-700">
                    {v.name}
                  </code>
                  <span className="text-foreground/80">由节点 {v.source_node_id} 收集</span>
                  <button
                    type="button"
                    onClick={() => onCopy(v.name)}
                    className="ml-auto text-foreground/60 hover:text-foreground"
                    aria-label="复制"
                  >
                    <IconCopy size={14} />
                  </button>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
