'use client'

import { useCallback, useEffect, useMemo } from 'react'
import { DateTimeInput, TimeInput } from '@/components/ui/time-input'
import { cn } from '@/lib/utils'
import { FieldType, SELECT_FIELD_TYPES, TREE_FIELD_TYPES } from '@/types/field-enums'
import { OptionListEditor, type OptionItem } from './option-list-editor'
import { TreeNodeEditor, type TreeNodeItem } from './tree-node-editor'

type TypeConfig = Record<string, unknown>

type FieldTypeConfigProps = {
  fieldType: FieldType
  config: TypeConfig
  onConfigChange: (config: TypeConfig) => void
  options?: OptionItem[]
  onOptionsChange?: (options: OptionItem[]) => void
  treeNodes?: TreeNodeItem[]
  onTreeNodesChange?: (nodes: TreeNodeItem[]) => void
  className?: string
}

function normalizeMultiDefault(raw: unknown): string[] {
  if (Array.isArray(raw)) {
    return raw.filter((x): x is string => typeof x === 'string')
  }
  if (typeof raw === 'string' && raw.trim()) {
    return raw.split(',').map((s) => s.trim()).filter(Boolean)
  }
  return []
}

function SelectDefaultSingle({
  config,
  options,
  onChange,
  inputClassName,
}: {
  config: TypeConfig
  options: OptionItem[]
  onChange: (key: string, value: unknown) => void
  inputClassName: string
}) {
  const raw = (config.default_value as string) ?? ''
  const optionValues = new Set(options.map((o) => o.value))
  const selectValue = optionValues.has(raw) ? raw : ''

  useEffect(() => {
    if (raw && !options.some((o) => o.value === raw)) {
      onChange('default_value', null)
    }
  }, [options, raw, onChange])

  return (
    <ConfigField label="默认值">
      <select
        value={selectValue}
        onChange={(e) => onChange('default_value', e.target.value || null)}
        className={cn(inputClassName, 'w-[400px] max-w-full')}
      >
        <option value="">无（不设置默认）</option>
        {options.map((opt, index) => (
          <option key={`${opt.value}-${index}`} value={opt.value}>
            {opt.label || opt.value}
          </option>
        ))}
      </select>
    </ConfigField>
  )
}

function SelectDefaultMulti({
  config,
  options,
  onChange,
}: {
  config: TypeConfig
  options: OptionItem[]
  onChange: (key: string, value: unknown) => void
}) {
  const selected = useMemo(() => {
    const normalized = normalizeMultiDefault(config.default_value)
    const valid = new Set(options.map((o) => o.value))
    return normalized.filter((v) => valid.has(v))
  }, [config.default_value, options])

  useEffect(() => {
    const normalized = normalizeMultiDefault(config.default_value)
    const filtered = normalized.filter((v) => options.some((o) => o.value === v))
    if (filtered.length !== normalized.length) {
      onChange('default_value', filtered.length ? filtered : null)
    }
  }, [options, config.default_value, onChange])

  const toggle = useCallback(
    (v: string) => {
      const next = selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v]
      onChange('default_value', next.length ? next : null)
    },
    [selected, onChange],
  )

  return (
    <ConfigField label="默认值">
      {options.length === 0 ? (
        <p className="text-sm text-muted-foreground">请先添加选项</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {options.map((opt, index) => (
            <label
              key={`${opt.value}-${index}`}
              className={cn(
                'inline-flex cursor-pointer items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm transition-colors',
                selected.includes(opt.value)
                  ? 'border-primary bg-primary/5 text-foreground/80'
                  : 'border-border text-muted-foreground',
              )}
            >
              <input
                type="checkbox"
                checked={selected.includes(opt.value)}
                onChange={() => toggle(opt.value)}
                className="sr-only"
              />
              {opt.color && (
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: opt.color }} />
              )}
              {opt.label || opt.value}
            </label>
          ))}
        </div>
      )}
    </ConfigField>
  )
}

/**
 * Renders type-specific configuration controls for a field definition.
 * Used in admin "create/edit custom field" forms.
 *
 * Each field_type has its own configuration form defined in §3.2–§3.16
 * of the global field type spec document.
 */
export function FieldTypeConfig({
  fieldType,
  config,
  onConfigChange,
  options = [],
  onOptionsChange,
  treeNodes = [],
  onTreeNodesChange,
  className,
}: FieldTypeConfigProps) {
  const set = useCallback(
    (key: string, value: unknown) => onConfigChange({ ...config, [key]: value }),
    [config, onConfigChange],
  )

  const isSelect = (SELECT_FIELD_TYPES as readonly string[]).includes(fieldType)
  const isTree = (TREE_FIELD_TYPES as readonly string[]).includes(fieldType)

  return (
    <div className={cn('space-y-4', className)}>
      {fieldType === FieldType.SINGLE_LINE_TEXT && (
        <TextLikeConfig config={config} onChange={set} maxLengthDefault={256} maxLengthMax={2048} />
      )}

      {fieldType === FieldType.MULTI_LINE_TEXT && (
        <TextLikeConfig config={config} onChange={set} maxLengthDefault={2000} maxLengthMax={65535} />
      )}

      {fieldType === FieldType.NUMBER && <NumberConfig config={config} onChange={set} />}

      {fieldType === FieldType.DATE && (
        <p className="text-sm text-muted-foreground">日期类型无额外配置项</p>
      )}

      {fieldType === FieldType.TIME && <TimeConfig config={config} onChange={set} />}

      {fieldType === FieldType.DATETIME && (
        <ConfigField label="默认值">
          <DateTimeInput
            value={(config.default_value as string) ?? ''}
            onChange={(e) => set('default_value', e.target.value || null)}
            className={inputClass}
          />
        </ConfigField>
      )}

      {isSelect && (
        <>
          <ConfigField label="选项列表">
            <OptionListEditor options={options} onChange={onOptionsChange ?? (() => {})} />
          </ConfigField>
          {fieldType === FieldType.SINGLE_SELECT && (
            <SelectDefaultSingle config={config} options={options} onChange={set} inputClassName={inputClass} />
          )}
          {fieldType === FieldType.MULTI_SELECT && (
            <SelectDefaultMulti config={config} options={options} onChange={set} />
          )}
        </>
      )}

      {isTree && (
        <>
          <ConfigField label="树形节点">
            <TreeNodeEditor nodes={treeNodes} onChange={onTreeNodesChange ?? (() => {})} />
          </ConfigField>
          <ConfigField label="仅可选叶子节点">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={(config.leaf_only as boolean) ?? false}
                onChange={(e) => set('leaf_only', e.target.checked)}
                className="h-4 w-4 rounded border-border"
              />
              启用后仅叶子节点可被选中
            </label>
          </ConfigField>
          {fieldType === FieldType.MULTI_SELECT_TREE && (
            <ConfigField label="最多可选数">
              <input
                type="number"
                min={1}
                value={(config.max_selections as number) ?? ''}
                onChange={(e) => set('max_selections', e.target.value ? Number(e.target.value) : null)}
                placeholder="不限"
                className={cn(inputClass, 'w-[160px]')}
              />
            </ConfigField>
          )}
        </>
      )}

      {fieldType === FieldType.EMAIL && (
        <TextLikeConfig config={config} onChange={set} maxLengthDefault={254} maxLengthMax={254} />
      )}

      {fieldType === FieldType.PHONE && (
        <TextLikeConfig config={config} onChange={set} maxLengthDefault={32} maxLengthMax={32} showDefault />
      )}

      {fieldType === FieldType.URL && (
        <TextLikeConfig config={config} onChange={set} maxLengthDefault={2048} maxLengthMax={2048} />
      )}

      {fieldType === FieldType.FILE && <FileConfig config={config} onChange={set} />}

      {fieldType === FieldType.RICH_TEXT && <RichTextConfig config={config} onChange={set} />}
    </div>
  )
}

// ── Shared input class ──

const inputClass =
  'h-10 w-full rounded-lg border border-border bg-transparent px-3 text-sm text-foreground/80 outline-none placeholder:text-muted-foreground focus:border-ring'

// ── Config field wrapper ──

function ConfigField({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm font-medium text-foreground/80">
        {label}
        {required && <span className="text-destructive"> *</span>}
      </label>
      {children}
    </div>
  )
}

// ── Text-like config (single_line_text, multi_line_text, email, phone, url) ──

function TextLikeConfig({
  config,
  onChange,
  maxLengthDefault,
  maxLengthMax,
  showDefault = false,
}: {
  config: TypeConfig
  onChange: (key: string, value: unknown) => void
  maxLengthDefault: number
  maxLengthMax: number
  showDefault?: boolean
}) {
  return (
    <>
      <ConfigField label="最大长度" required>
        <input
          type="number"
          min={1}
          max={maxLengthMax}
          value={(config.max_length as number) ?? maxLengthDefault}
          onChange={(e) => onChange('max_length', Number(e.target.value))}
          className={cn(inputClass, 'w-[160px]')}
        />
      </ConfigField>
      <ConfigField label="占位符">
        <input
          type="text"
          value={(config.placeholder as string) ?? ''}
          onChange={(e) => onChange('placeholder', e.target.value || null)}
          placeholder="输入框占位提示文案"
          className={cn(inputClass, 'w-[400px] max-w-full')}
        />
      </ConfigField>
      {showDefault && (
        <ConfigField label="默认值">
          <input
            type="text"
            value={(config.default_value as string) ?? ''}
            onChange={(e) => onChange('default_value', e.target.value || null)}
            className={cn(inputClass, 'w-[400px] max-w-full')}
          />
        </ConfigField>
      )}
    </>
  )
}

// ── Number config ──

function NumberConfig({
  config,
  onChange,
}: {
  config: TypeConfig
  onChange: (key: string, value: unknown) => void
}) {
  return (
    <>
      <ConfigField label="小数位数">
        <input
          type="number"
          min={0}
          max={10}
          value={(config.decimal_places as number) ?? 0}
          onChange={(e) => onChange('decimal_places', Number(e.target.value))}
          className={cn(inputClass, 'w-[160px]')}
        />
      </ConfigField>
      <div className="flex gap-4">
        <ConfigField label="最小值">
          <input
            type="number"
            value={(config.min_value as number) ?? ''}
            onChange={(e) => onChange('min_value', e.target.value ? Number(e.target.value) : null)}
            placeholder="不限"
            className={cn(inputClass, 'w-[160px]')}
          />
        </ConfigField>
        <ConfigField label="最大值">
          <input
            type="number"
            value={(config.max_value as number) ?? ''}
            onChange={(e) => onChange('max_value', e.target.value ? Number(e.target.value) : null)}
            placeholder="不限"
            className={cn(inputClass, 'w-[160px]')}
          />
        </ConfigField>
      </div>
      <ConfigField label="单位后缀">
        <input
          type="text"
          maxLength={16}
          value={(config.unit_suffix as string) ?? ''}
          onChange={(e) => onChange('unit_suffix', e.target.value || null)}
          placeholder="如：元、%、kg"
          className={cn(inputClass, 'w-[160px]')}
        />
      </ConfigField>
      <ConfigField label="默认值">
        <input
          type="number"
          value={(config.default_value as number) ?? ''}
          onChange={(e) => onChange('default_value', e.target.value ? Number(e.target.value) : null)}
          className={cn(inputClass, 'w-[160px]')}
        />
      </ConfigField>
    </>
  )
}

// ── Time config ──

function TimeConfig({
  config,
  onChange,
}: {
  config: TypeConfig
  onChange: (key: string, value: unknown) => void
}) {
  const granularity = (config.time_granularity as string) ?? 'minute'
  return (
    <>
      <ConfigField label="时间精度">
        <select
          value={granularity}
          onChange={(e) => onChange('time_granularity', e.target.value)}
          className={cn(inputClass, 'w-[160px]')}
        >
          <option value="minute">分钟 (HH:mm)</option>
          <option value="second">秒 (HH:mm:ss)</option>
        </select>
      </ConfigField>
      <ConfigField label="默认值">
        <TimeInput
          step={granularity === 'second' ? 1 : 60}
          value={(config.default_value as string) ?? ''}
          onChange={(e) => onChange('default_value', e.target.value || null)}
          className={cn(inputClass, 'w-[160px]')}
        />
      </ConfigField>
    </>
  )
}

// ── File config ──

function FileConfig({
  config,
  onChange,
}: {
  config: TypeConfig
  onChange: (key: string, value: unknown) => void
}) {
  return (
    <>
      <ConfigField label="最多文件数量">
        <input
          type="number"
          min={1}
          value={(config.max_file_count as number) ?? 1}
          onChange={(e) => onChange('max_file_count', Number(e.target.value))}
          className={cn(inputClass, 'w-[160px]')}
        />
      </ConfigField>
      <ConfigField label="单文件最大体积 (MB)">
        <input
          type="number"
          min={1}
          value={(config.max_file_size_mb as number) ?? ''}
          onChange={(e) => onChange('max_file_size_mb', e.target.value ? Number(e.target.value) : null)}
          placeholder="不限"
          className={cn(inputClass, 'w-[160px]')}
        />
      </ConfigField>
      <ConfigField label="总文件体积上限 (MB)">
        <input
          type="number"
          min={1}
          value={(config.max_total_size_mb as number) ?? ''}
          onChange={(e) => onChange('max_total_size_mb', e.target.value ? Number(e.target.value) : null)}
          placeholder="不限"
          className={cn(inputClass, 'w-[160px]')}
        />
      </ConfigField>
      <ConfigField label="允许文件类型">
        <input
          type="text"
          value={(config.allowed_mime_types as string) ?? ''}
          onChange={(e) => onChange('allowed_mime_types', e.target.value || null)}
          placeholder="如：pdf,jpg,png（逗号分隔，空为默认）"
          className={cn(inputClass, 'w-[400px] max-w-full')}
        />
      </ConfigField>
      <ConfigField label="禁止文件类型">
        <input
          type="text"
          value={(config.blocked_mime_types as string) ?? ''}
          onChange={(e) => onChange('blocked_mime_types', e.target.value || null)}
          placeholder="如：exe,html（逗号分隔）"
          className={cn(inputClass, 'w-[400px] max-w-full')}
        />
      </ConfigField>
    </>
  )
}

// ── Rich text config ──

function RichTextConfig({
  config,
  onChange,
}: {
  config: TypeConfig
  onChange: (key: string, value: unknown) => void
}) {
  return (
    <>
      <ConfigField label="最大长度">
        <input
          type="number"
          min={1}
          value={(config.max_length as number) ?? 65535}
          onChange={(e) => onChange('max_length', Number(e.target.value))}
          className={cn(inputClass, 'w-[160px]')}
        />
      </ConfigField>
      <ConfigField label="占位符">
        <input
          type="text"
          value={(config.placeholder as string) ?? ''}
          onChange={(e) => onChange('placeholder', e.target.value || null)}
          placeholder="富文本编辑器占位提示"
          className={cn(inputClass, 'w-[400px] max-w-full')}
        />
      </ConfigField>
      <ConfigField label="格式">
        <select
          value={(config.rich_format as string) ?? 'html'}
          onChange={(e) => onChange('rich_format', e.target.value)}
          className={cn(inputClass, 'w-[160px]')}
        >
          <option value="html">HTML</option>
          <option value="markdown">Markdown</option>
        </select>
      </ConfigField>
    </>
  )
}
