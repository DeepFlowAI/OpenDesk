import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  submit: vi.fn(),
  submitReset: vi.fn(),
  uploadReset: vi.fn(),
}))

vi.mock('@/service/use-form-message', () => ({
  usePublicFormMessageConfig: () => ({
    data: {
      version: 1,
      config: {
        title: 'Leave a message',
        description: '',
        submit_label: 'Submit',
        success_title: 'Submitted successfully',
        success_description: 'We received your information.',
        show_ticket_number: false,
        fields: [],
      },
    },
    isLoading: false,
    isError: false,
  }),
  useSubmitPublicFormMessage: () => ({
    mutateAsync: mocks.submit,
    reset: mocks.submitReset,
    isPending: false,
    isError: false,
  }),
  useUploadPublicFormMessageFile: () => ({
    mutateAsync: vi.fn(),
    reset: mocks.uploadReset,
  }),
}))

vi.mock('@/app/components/features/field-system/field-value-editor', () => ({
  UnifiedFieldValueEditor: () => null,
}))

import { FormMessage } from './form-message'

describe('FormMessage navigation', () => {
  let container: HTMLDivElement
  let root: Root
  const onContinueConversation = vi.fn()

  beforeEach(async () => {
    mocks.submit.mockReset()
    mocks.submitReset.mockReset()
    mocks.uploadReset.mockReset()
    onContinueConversation.mockReset()
    mocks.submit.mockResolvedValue({
      ticket_id: 1,
      ticket_number: null,
      success_title: 'Submitted successfully',
      success_description: 'We received your information.',
      show_ticket_number: false,
      duplicated: false,
    })
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    await act(async () => {
      root.render(
        <FormMessage
          visitorSessionToken="visitor-session-token"
          locale="zh"
          source="bot_handoff"
          conversationPublicId="conversation-public-id"
          onContinueConversation={onContinueConversation}
        />,
      )
    })
  })

  afterEach(async () => {
    await act(async () => root.unmount())
    container.remove()
  })

  it('returns to the bot from the form and the success view', async () => {
    const backButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent?.includes('返回机器人'),
    )
    await act(async () => backButton?.click())
    expect(onContinueConversation).toHaveBeenCalledOnce()

    const submitButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === 'Submit',
    )
    await act(async () => submitButton?.click())

    const successBackButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent?.includes('返回机器人'),
    )
    expect(successBackButton).toBeTruthy()
    await act(async () => successBackButton?.click())
    expect(onContinueConversation).toHaveBeenCalledTimes(2)
  })

  it('starts a fresh submission with a new idempotency key', async () => {
    const submit = () => {
      const button = Array.from(container.querySelectorAll('button')).find(
        (candidate) => candidate.textContent === 'Submit',
      )
      expect(button).toBeTruthy()
      button?.click()
    }

    await act(async () => submit())
    const firstKey = mocks.submit.mock.calls[0]?.[0].idempotency_key

    const leaveAnotherButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '再次留言',
    )
    expect(leaveAnotherButton).toBeTruthy()
    await act(async () => leaveAnotherButton?.click())

    expect(mocks.submitReset).toHaveBeenCalledOnce()
    expect(mocks.uploadReset).toHaveBeenCalledOnce()
    await act(async () => submit())
    expect(mocks.submit.mock.calls[1]?.[0].idempotency_key).not.toBe(firstKey)
  })
})
