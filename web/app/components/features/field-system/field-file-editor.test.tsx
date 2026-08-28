import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { FieldFileEditor } from '@/app/components/features/field-system/field-file-editor'
import { FieldValueEditor } from '@/app/components/features/field-system/field-value-editor'
import { FieldType } from '@/types/field-enums'

function renderEditor(locale: 'en' | 'zh') {
  const queryClient = new QueryClient()
  return renderToStaticMarkup(
    <QueryClientProvider client={queryClient}>
      <FieldFileEditor
        value={null}
        onChange={() => undefined}
        placeholder={locale === 'en' ? 'Upload file' : '请上传'}
        locale={locale}
      />
    </QueryClientProvider>,
  )
}

describe('FieldFileEditor', () => {
  it('uses the localized default placeholder from the field value editor', () => {
    const queryClient = new QueryClient()
    const html = renderToStaticMarkup(
      <QueryClientProvider client={queryClient}>
        <FieldValueEditor
          fieldType={FieldType.FILE}
          value={null}
          onChange={() => undefined}
          locale="en"
        />
      </QueryClientProvider>,
    )

    expect(html).toContain('Upload file')
    expect(html).not.toContain('请上传')
  })

  it('renders visitor upload guidance in English', () => {
    const html = renderEditor('en')

    expect(html).toContain('Upload file')
    expect(html).toContain('Click to select or drag files here')
  })

  it('keeps the Chinese upload guidance for Chinese visitors', () => {
    const html = renderEditor('zh')

    expect(html).toContain('请上传')
    expect(html).toContain('点击选择或拖拽文件到此处')
  })
})
