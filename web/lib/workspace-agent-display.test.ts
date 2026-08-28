import { describe, expect, it } from 'vitest'

import { resolveVisitorSystemEventContent } from './workspace-agent-display'

describe('resolveVisitorSystemEventContent', () => {
  it.each([
    ['open_agent_bot_started', '智能助手开始接待', 'The assistant joined the conversation'],
    ['agent_assigned', '客服已接入会话', 'A support agent joined the conversation'],
    ['open_agent_handoff_success', '已为您转接人工客服', 'A support agent joined the conversation'],
    ['conversation_started', '用户发起了新会话', 'Conversation started'],
    ['conversation_ended', '客服已结束会话', 'Conversation ended'],
    ['invitation_sent', '系统在会话结束后发送了满意度邀请', 'Satisfaction invitation sent'],
    ['feedback_submitted', '访客提交了满意度评价', 'Satisfaction feedback submitted'],
    [
      'offline_message_conversation_created',
      '客服已基于留言创建会话',
      'Your message is now an online conversation. You can reply here.',
    ],
    ['queue_entered', '已进入人工客服队列', 'You are in the human support queue'],
    [
      'open_agent_handoff_failed',
      '当前人工客服繁忙，您可以继续向智能助手咨询',
      'Human support is unavailable right now. You can keep chatting with the assistant.',
    ],
  ])('localizes %s event metadata', (eventType, content, expected) => {
    expect(resolveVisitorSystemEventContent(content, { event_type: eventType }, 'en')).toBe(expected)
  })

  it.each([
    ['智能助手开始接待', 'The assistant joined the conversation'],
    ['客服已接入会话', 'A support agent joined the conversation'],
    ['已为您转接人工客服', 'A support agent joined the conversation'],
    ['用户发起了新会话', 'Conversation started'],
    ['客服发起了新会话', 'Conversation started'],
    ['客服已结束会话', 'Conversation ended'],
    ['用户已结束会话', 'Conversation ended'],
    ['系统在会话结束后发送了满意度邀请', 'Satisfaction invitation sent'],
    ['客服 1 号发送了满意度邀请', 'Satisfaction invitation sent'],
    ['访客提交了满意度评价', 'Satisfaction feedback submitted'],
    [
      '客服已基于留言创建会话',
      'Your message is now an online conversation. You can reply here.',
    ],
    ['等待客服接入...', 'You are in the human support queue'],
    [
      '当前人工客服不在线，您可以继续向智能助手咨询',
      'Human support is unavailable right now. You can keep chatting with the assistant.',
    ],
  ])('localizes legacy persisted content %s', (content, expected) => {
    expect(resolveVisitorSystemEventContent(content, undefined, 'en')).toBe(expected)
  })

  it('keeps configured or unknown system content unchanged', () => {
    expect(resolveVisitorSystemEventContent('Configured business copy', undefined, 'en')).toBe(
      'Configured business copy',
    )
  })
})
