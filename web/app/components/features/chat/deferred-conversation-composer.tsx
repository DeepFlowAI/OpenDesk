'use client'

import { AgentChatRuntimeProvider, type DeferredConversationSendResult, type ResolvedConversationForSend } from '@/components/assistant-ui/agent-chat-runtime'
import { AgentComposer } from '@/components/assistant-ui/agent-composer'
import type { Conversation } from '@/models/conversation'
import type { SatisfactionConversationState } from '@/models/satisfaction-survey'
import type { Socket } from 'socket.io-client'
import type { Locale } from '@/context/locale-store'

type Props = {
  conversation: Conversation
  socket: Socket | null
  locale: Locale
  disabled?: boolean
  disabledReason?: string | null
  resolveConversationForSend: () => Promise<ResolvedConversationForSend>
  onResolved?: (conversation: Conversation, result: DeferredConversationSendResult) => void | Promise<void>
}

const noInviteSatisfactionState: SatisfactionConversationState = {
  can_invite: false,
  disabled_reason: 'agent_invite_disabled',
  needs_confirmation: false,
  record: null,
  summary: {
    status: 'none',
    labels: [],
    invited_at: null,
    submitted_at: null,
    config_version: null,
  },
}

const noop = () => {}
const noopAsync = async () => {}

export function DeferredConversationComposer({
  conversation,
  socket,
  locale,
  disabled = false,
  disabledReason = null,
  resolveConversationForSend,
  onResolved,
}: Props) {
  return (
    <AgentChatRuntimeProvider
      socket={socket}
      conversation={conversation}
      locale={locale}
      isClosed={false}
      isTyping={false}
      visitorTypingContent=""
      hasMore={false}
      loadingMore={false}
      historyAvailable={false}
      historyConversations={[]}
      historyHasMore={false}
      historyLoading={false}
      historyLoaded={false}
      historyError={false}
      historyLimitReached={false}
      onLoadMore={noop}
      onLoadHistory={noopAsync}
      onEndConversation={noop}
      onCreateTicket={noop}
      canCreateTicket={false}
      canPinConversation={false}
      pinningConversation={false}
      onTogglePinConversation={noop}
      canLockConversationTimeout={false}
      lockingConversationTimeout={false}
      onToggleConversationTimeoutLock={noop}
      canTransfer={false}
      canEndConversation={false}
      canInviteCollaborator={false}
      canSendPublicReply={!disabled}
      canCreateInternalNote={false}
      composerReadOnlyReason={null}
      canStartNewConversation={!disabled}
      startNewConversationDisabledReason={disabledReason}
      startingNewConversation={false}
      onStartNewConversation={noop}
      onTransferred={noop}
      onCollaborationInvitationSent={noop}
      satisfactionState={noInviteSatisfactionState}
      satisfactionLoading={false}
      satisfactionSending={false}
      onSendSatisfaction={async () => false}
      emojiConfig={null}
      readStatusEnabled={true}
      resolveConversationForSend={resolveConversationForSend}
      onDeferredConversationResolved={onResolved}
    >
      <AgentComposer
        disabled={disabled}
        disabledReason={disabledReason}
        socket={socket}
      />
    </AgentChatRuntimeProvider>
  )
}
