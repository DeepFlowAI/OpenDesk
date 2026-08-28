import { act, type ComponentProps } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const settings = vi.hoisted(() => ({
  enabled: true,
  visitor_prompt: 'Custom visitor {{message}}',
  agent_prompt: 'Custom agent {{message}}',
  default_visitor_prompt: 'Current default visitor {{message}}',
  default_agent_prompt: 'Current default agent {{message}}',
}))

vi.mock('@/context/locale-store', () => ({
  useLocaleStore: () => ({ locale: 'zh' }),
}))

vi.mock('@/service/use-lingomaster', () => ({
  useLingoMasterSettings: () => ({ data: settings, isLoading: false, isError: false }),
  useUpdateLingoMasterSettings: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

vi.mock('@/utils/i18n', () => ({
  t: (key: string) => key,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@tabler/icons-react', () => ({
  IconLoader2: () => null,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: ComponentProps<'button'>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/switch', () => ({
  Switch: ({ checked, 'aria-label': ariaLabel }: { checked: boolean; 'aria-label': string }) => (
    <input type="checkbox" checked={checked} aria-label={ariaLabel} readOnly />
  ),
}))

vi.mock('@/components/ui/textarea', () => ({
  Textarea: (props: ComponentProps<'textarea'>) => <textarea {...props} />,
}))

import { LingomasterSettingsForm } from './lingomaster-settings-form'

describe('LingomasterSettingsForm', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(async () => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    await act(async () => {
      root.render(<LingomasterSettingsForm />)
    })
  })

  afterEach(async () => {
    await act(async () => root.unmount())
    container.remove()
  })

  it('restores prompts from the server-provided current defaults', async () => {
    const textareas = container.querySelectorAll('textarea')
    const resetButtons = Array.from(container.querySelectorAll('button')).filter(
      (button) => button.textContent === 'lingomaster.restoreDefault',
    )

    expect(textareas[0]?.value).toBe(settings.visitor_prompt)
    expect(textareas[1]?.value).toBe(settings.agent_prompt)

    await act(async () => resetButtons[0]?.click())
    await act(async () => resetButtons[1]?.click())

    expect(textareas[0]?.value).toBe(settings.default_visitor_prompt)
    expect(textareas[1]?.value).toBe(settings.default_agent_prompt)
  })
})
