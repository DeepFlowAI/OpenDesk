/**
 * Socket.IO event names for the call-center agent room (namespace=/chat).
 * Keep in sync with server/app/constants/call_center.py CcSocketEvent.
 */
export const CcSocketEvent = {
  CALL_INCOMING: 'cc.call_incoming',
  CALL_ANSWERED: 'cc.call_answered',
  CALL_HANGUP: 'cc.call_hangup',
  OUTBOUND_RINGING: 'cc.outbound_ringing',
  OUTBOUND_ANSWERED: 'cc.outbound_answered',
  OUTBOUND_HANGUP: 'cc.outbound_hangup',
  CONSULT_RESULT: 'cc.consult_result',
  TRANSFER_RESULT: 'cc.transfer_result',
  CONFERENCE_RESULT: 'cc.conference_result',
  CONFERENCE_PARTICIPANT_LEFT: 'cc.conference_participant_left',
  MEDIA_RECONNECT_REQUIRED: 'cc.media_reconnect_required',
  DEVICE_REGISTRATION_CHANGED: 'cc.device_registration_changed',
  WEBRTC_ICE: 'cc.webrtc.ice',
  TRANSCRIPT: 'cc.transcript',
  WRAP_UP_STARTED: 'cc.wrap_up_started',
  WRAP_UP_TIMEOUT: 'cc.wrap_up_timeout',
  CALL_RECORD_UPDATED: 'cc.call_record_updated',
} as const

export type CcSocketEventName = (typeof CcSocketEvent)[keyof typeof CcSocketEvent]
