'use client'
/**
 * In-call control state machine for the agent's own call.
 *
 * Wraps the backend `/agents/me/current-call/*` endpoints and tracks the
 * agent-facing call mode (single / hold / consult / conference / transferring).
 * Mute flips the local WebRTC audio track via `setMuted` and asks the backend
 * to gate the agent's leg. Either half failing can leave the button describing
 * a state the agent is not in — on a SIP handset there is no local track at
 * all, and un-muting can succeed locally while the leg stays gated — so both
 * cases surface rather than resolve silently.
 *
 * This hook is intentionally decoupled from the phase machine in
 * `call-center-runtime` so the universal call-bar shell — and later the
 * supervisor-monitor variant — can reuse the same control surface.
 */
import { useCallback, useState } from 'react'
import { toast } from 'sonner'

import {
  conferenceAdd,
  conferenceEndAll,
  conferenceLeave,
  conferenceMerge,
  conferenceRemove,
  endConsult,
  holdCurrentCall,
  setCurrentCallMute,
  startConsult,
  transferCurrentCall,
  unholdCurrentCall,
  type CallControlResult,
  type CallControlTarget,
  type ConsultTargetType,
} from '@/service/use-call-center'

/** Agent-facing call mode. */
export type CallControlMode =
  | 'single'
  | 'hold'
  | 'consult_ringing'
  | 'consult_active'
  | 'conference_ringing'
  | 'conference'
  | 'transferring'
  | 'ended'

export type ConsultTarget = {
  target_type: ConsultTargetType
  target_id?: number | null
  number?: string | null
  target_name?: string
}

/** Applies mute to the local audio track. Returns false when there is none —
 *  an agent on a SIP handset — so the caller knows the backend is the only
 *  thing that can mute them. */
type SetMuted = (muted: boolean) => boolean

/**
 * Turn a thrown ky error into a user-facing message. Prefers the backend's
 * own `message` (e.g. "目标坐席未绑定 SIP 分机") so the agent sees the real
 * reason; falls back to status-specific or generic text. Async because ky
 * exposes the error body only via `response.json()`.
 */
async function controlErrorMessage(e: unknown, fallback: string): Promise<string> {
  const response = (e as { response?: Response })?.response
  if (response) {
    try {
      const body = (await response.clone().json()) as { message?: unknown }
      if (typeof body?.message === 'string' && body.message.trim()) {
        return body.message
      }
    } catch {
      // Body wasn't JSON or was already consumed — fall through.
    }
  }
  const status = response?.status
  if (status === 501) return '当前通话服务暂不支持此操作'
  if (status === 403) return '没有执行此操作的权限'
  return fallback
}

export function useCallControl(setMuted: SetMuted) {
  const [mode, setMode] = useState<CallControlMode>('single')
  const [muted, setMutedState] = useState(false)
  const [holdStart, setHoldStart] = useState<number | null>(null)
  const [consultStart, setConsultStart] = useState<number | null>(null)
  const [consultTarget, setConsultTarget] = useState<ConsultTarget | null>(null)
  /** Which action is currently in flight, to disable duplicate submits. */
  const [pending, setPending] = useState<string | null>(null)

  const reset = useCallback(() => {
    setMode('single')
    setMutedState(false)
    setHoldStart(null)
    setConsultStart(null)
    setConsultTarget(null)
    setPending(null)
  }, [])

  /** Restore consult UI after page refresh (server still has consult state).
   *  `state` mirrors the server's consult lifecycle: a still-ringing consult
   *  restores to consult_ringing, an answered one to consult_active. */
  const restoreConsult = useCallback(
    (target?: {
      target_id?: number | null
      target_name?: string
      state?: 'ringing' | 'active'
    }) => {
      const restored = target?.state === 'ringing' ? 'consult_ringing' : 'consult_active'
      setMode((curr) =>
        curr === 'consult_active' || curr === 'consult_ringing' ? curr : restored,
      )
      setConsultStart((prev) => prev ?? Date.now())
      if (target?.target_id != null) {
        setConsultTarget({
          target_type: 'employee',
          target_id: target.target_id,
          target_name: target.target_name,
        })
      }
    },
    [],
  )

  const toggleMute = useCallback(() => {
    const next = !muted
    // Flip the local track first where there is one: it takes effect at once
    // and survives a failed request. It returns false when the agent is on a
    // device without a browser audio track, such as a SIP handset.
    const appliedLocally = setMuted(next)
    setMutedState(next)
    void setCurrentCallMute(next).catch(async (e) => {
      // The two directions do not fail the same way. Muting with a local track
      // already off leaves the agent genuinely silent, so a failed request
      // changes nothing they need to act on. Un-muting is the dangerous one:
      // the kernel may still be gating this leg, leaving them inaudible while
      // the button says they are live — the same lie in the other direction.
      if (appliedLocally && next) return
      setMutedState(!next)
      toast.error(await controlErrorMessage(e, next ? '静音失败' : '取消静音失败'))
    })
  }, [muted, setMuted])

  const toggleHold = useCallback(async () => {
    if (pending) return
    const goingOnHold = mode === 'single'
    setPending('hold')
    try {
      const res: CallControlResult = goingOnHold
        ? await holdCurrentCall()
        : await unholdCurrentCall()
      if (!res.ok) throw new Error('hold_failed')
      if (goingOnHold) {
        setMode('hold')
        setHoldStart(Date.now())
      } else {
        setMode('single')
        setHoldStart(null)
      }
    } catch (e) {
      toast.error(await controlErrorMessage(e, goingOnHold ? '保持失败' : '恢复失败'))
    } finally {
      setPending(null)
    }
  }, [mode, pending])

  const submitTransfer = useCallback(
    async (target: CallControlTarget): Promise<boolean> => {
      if (pending) return false
      setPending('transfer')
      setMode('transferring')
      try {
        const res = await transferCurrentCall(target)
        if (!res.ok) throw new Error('transfer_failed')
        // Both SIP/external (`ringing_target`) and browser WebRTC colleague
        // (`ringing_webrtc_target`) paths only start ringing here; the actual
        // handoff finishes off the request path. Stay in "转接中" and let the
        // cc.transfer_result socket event drive success/failure.
        // Do not set mode to "ended" yet: releasing this agent's media leg
        // while the target is still ringing drops the customer↔agent bridge
        // peer and the media core ends the customer call with it.
        return true
      } catch (e) {
        // Original call is preserved by the backend on failure.
        toast.error(await controlErrorMessage(e, '转接失败，客户通话仍在继续'))
        setMode('single')
        return false
      } finally {
        setPending(null)
      }
    },
    [pending],
  )

  const beginConsult = useCallback(
    async (target: ConsultTarget): Promise<boolean> => {
      if (pending) return false
      setPending('consult')
      setMode('consult_ringing')
      setConsultTarget(target)
      try {
        const res = await startConsult({
          target_type: target.target_type,
          target_id: target.target_id,
          number: target.number,
        })
        if (!res.ok) throw new Error('consult_failed')
        // A WebRTC (browser-ring) colleague target is still ringing off the
        // request path; stay in "咨询呼叫中" and let the cc.consult_result socket
        // event mark it active/failed. Other targets are treated as connected.
        if (res.note === 'ringing_webrtc_target') {
          setConsultStart(Date.now())
          return true
        }
        setMode('consult_active')
        setConsultStart(Date.now())
        return true
      } catch (e) {
        toast.error(await controlErrorMessage(e, '发起咨询失败，客户通话仍在继续'))
        setMode('single')
        setConsultTarget(null)
        return false
      } finally {
        setPending(null)
      }
    },
    [pending],
  )

  /**
   * Handle a cc.consult_result socket event from the backend (the browser-ring
   * consult resolved off the request path). On success move to consult_active;
   * on failure exit "咨询呼叫中" back to the single-customer call and toast.
   */
  const onConsultResult = useCallback(
    (result: {
      ok: boolean
      reason?: string
      target_name?: string
      ended?: boolean
      resumed?: boolean
    }) => {
      const reason = (result.reason || '').trim()
      // Target hung up (normal consult end) — leave consult UI for 1:1.
      // Also treat legacy payloads that used ok:false for this success path.
      const consultEndedNormally =
        (result.ok && result.ended) ||
        (!result.ok && /结束咨询|恢复与客户/.test(reason))
      if (consultEndedNormally) {
        setMode('single')
        setConsultTarget(null)
        setConsultStart(null)
        setPending(null)
        toast.success(reason || '对方已结束咨询，已恢复与客户通话')
        return
      }
      if (result.ok) {
        setMode((curr) => (curr === 'consult_ringing' ? 'consult_active' : curr))
        return
      }
      toast.error(reason || '发起咨询失败，客户通话仍在继续')
      setMode('single')
      setConsultTarget(null)
      setConsultStart(null)
      setPending(null)
    },
    [],
  )

  /**
   * Handle a cc.transfer_result socket event. On success the customer has been
   * handed to the colleague and this leg is released → go to the ended/wrap-up
   * flow; on failure exit "转接中" back to the single-customer call and toast.
   * Returns whether the transfer succeeded so the runtime can advance phase.
   */
  const onTransferResult = useCallback(
    (result: { ok: boolean; reason?: string }): boolean => {
      if (result.ok) {
        toast.success('通话已转接')
        setMode('ended')
        setPending(null)
        return true
      }
      toast.error(result.reason || '转接失败，客户通话仍在继续')
      setMode('single')
      setPending(null)
      return false
    },
    [],
  )

  const finishConsult = useCallback(async () => {
    if (pending) return
    setPending('consult_end')
    try {
      const res = await endConsult()
      if (!res.ok) throw new Error('consult_end_failed')
      toast.success('已结束咨询，已恢复与客户通话')
    } catch (e) {
      toast.error(await controlErrorMessage(e, '结束咨询失败'))
    } finally {
      // Whatever the outcome, return the UI to the customer call.
      setMode('single')
      setConsultStart(null)
      setConsultTarget(null)
      setPending(null)
    }
  }, [pending])

  const addParticipant = useCallback(
    async (target: ConsultTarget): Promise<boolean> => {
      if (pending) return false
      setPending('conf_add')
      // Optimistic: mirror consult/transfer — enter ringing as soon as the
      // request is sent so the call bar never looks frozen during the slow
      // unbridge/tone/originate path. cc.conference_result still owns the
      // answered → conference transition; on API failure roll back below.
      setMode('conference_ringing')
      toast(`正在呼叫 ${target.target_name ?? '参与人'}…`)
      try {
        const res = await conferenceAdd({
          target_type: target.target_type,
          target_id: target.target_id,
          number: target.number,
        })
        if (!res.ok) throw new Error('conf_add_failed')
        // Stay in conference_ringing; the room goes live when they answer
        // (cc.conference_result → onConferenceResult).
        return true
      } catch (e) {
        toast.error(await controlErrorMessage(e, '添加参与人失败'))
        setMode('single')
        return false
      } finally {
        setPending(null)
      }
    },
    [pending],
  )

  /**
   * Handle a cc.conference_result socket event: the ringing participant either
   * answered (→ conference live) or failed to connect (→ back to the two-party
   * call with a toast). Resolved off the request path by the backend.
   */
  const onConferenceResult = useCallback(
    (result: { ok: boolean; reason?: string }) => {
      if (result.ok) {
        setMode((curr) => (curr === 'conference_ringing' ? 'conference' : curr))
        toast.success('参与人已加入通话')
        return
      }
      toast.error(result.reason || '参与人未接通')
      setMode((curr) => (curr === 'conference_ringing' ? 'single' : curr))
    },
    [],
  )

  /**
   * The added participant left/hung up → the 3-way collapses back to the
   * customer 1:1 call. Driven by cc.conference_participant_left so the host's
   * bar stops showing "多方通话 3人" when the colleague is already gone.
   */
  const onConferenceParticipantLeft = useCallback(() => {
    setMode((curr) =>
      curr === 'conference' || curr === 'conference_ringing' ? 'single' : curr,
    )
    toast('参与人已离开通话')
  }, [])

  const mergeConference = useCallback(async () => {
    if (pending) return
    setPending('conf_merge')
    try {
      const res = await conferenceMerge()
      if (!res.ok) throw new Error('conf_merge_failed')
      setMode('conference')
    } catch (e) {
      toast.error(await controlErrorMessage(e, '合并多方失败'))
    } finally {
      setPending(null)
    }
  }, [pending])

  const removeParticipant = useCallback(async () => {
    if (pending) return
    setPending('conf_remove')
    try {
      await conferenceRemove()
      setMode('single')
    } catch (e) {
      toast.error(await controlErrorMessage(e, '移除参与人失败'))
    } finally {
      setPending(null)
    }
  }, [pending])

  const leaveConference = useCallback(async (): Promise<boolean> => {
    if (pending) return false
    setPending('conf_leave')
    try {
      await conferenceLeave()
      setMode('ended')
      return true
    } catch (e) {
      toast.error(await controlErrorMessage(e, '离开通话失败'))
      return false
    } finally {
      setPending(null)
    }
  }, [pending])

  const endAll = useCallback(async (): Promise<boolean> => {
    if (pending) return false
    setPending('conf_end_all')
    try {
      await conferenceEndAll()
      setMode('ended')
      return true
    } catch (e) {
      toast.error(await controlErrorMessage(e, '结束全部通话失败'))
      return false
    } finally {
      setPending(null)
    }
  }, [pending])

  return {
    mode,
    muted,
    holdStart,
    consultStart,
    consultTarget,
    pending,
    reset,
    restoreConsult,
    toggleMute,
    toggleHold,
    submitTransfer,
    beginConsult,
    onConsultResult,
    onTransferResult,
    finishConsult,
    addParticipant,
    onConferenceResult,
    onConferenceParticipantLeft,
    mergeConference,
    removeParticipant,
    leaveConference,
    endAll,
  }
}

export type CallControlApi = ReturnType<typeof useCallControl>
