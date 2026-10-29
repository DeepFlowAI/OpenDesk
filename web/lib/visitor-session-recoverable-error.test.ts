import { describe, expect, it } from 'vitest'

import {
  isRecoverableVisitorSessionError,
  visitorRecoveryTelemetryLevel,
} from './visitor-session-recoverable-error'

describe('isRecoverableVisitorSessionError', () => {
  it('treats HTTP 401 as recoverable', () => {
    expect(isRecoverableVisitorSessionError(
      { response: { status: 401 }, message: 'Request failed with status code 401' },
      { context: 'http' },
    )).toBe(true)
    expect(isRecoverableVisitorSessionError('HTTP 401', { context: 'http', status: 401 })).toBe(true)
  })

  it('does not treat a bare 401 mention without a real 401 status as recoverable', () => {
    expect(isRecoverableVisitorSessionError('HTTP 401', { context: 'http' })).toBe(false)
    expect(isRecoverableVisitorSessionError(
      'upstream returned 401',
      { context: 'http', status: 500 },
    )).toBe(false)
    expect(isRecoverableVisitorSessionError(
      { response: { status: 500 }, message: 'upstream returned 401' },
      { context: 'http' },
    )).toBe(false)
  })

  it('excludes 5xx before matching session copy', () => {
    expect(isRecoverableVisitorSessionError(
      '{"detail":"Invalid or expired visitor session"}',
      { context: 'http', status: 500 },
    )).toBe(false)
  })

  it('matches expired visitor session copy only with HTTP 401', () => {
    expect(isRecoverableVisitorSessionError(
      '{"detail":"Invalid or expired visitor session"}',
      { context: 'http', status: 401 },
    )).toBe(true)
    expect(isRecoverableVisitorSessionError(
      '{"detail":"Invalid or expired visitor session"}',
      { context: 'http' },
    )).toBe(false)
    expect(isRecoverableVisitorSessionError(
      new Error('Invalid or expired visitor session'),
      { context: 'http' },
    )).toBe(false)
  })

  it('does not treat HTTP 422 mentioning visitor_session_token as recoverable', () => {
    expect(isRecoverableVisitorSessionError(
      '{"detail":"visitor_session_token is required"}',
      { context: 'http', status: 422 },
    )).toBe(false)
    expect(isRecoverableVisitorSessionError(
      { response: { status: 422 }, message: 'visitor_session_token invalid' },
      { context: 'http' },
    )).toBe(false)
  })

  it('matches socket auth and join session codes', () => {
    expect(isRecoverableVisitorSessionError('UNAUTHORIZED', {
      context: 'socket_join',
      code: 'UNAUTHORIZED',
    })).toBe(true)
    expect(isRecoverableVisitorSessionError('visitor_session_required', {
      context: 'socket_join',
      code: 'visitor_session_required',
    })).toBe(true)
    expect(isRecoverableVisitorSessionError(new Error('Invalid visitor session'), {
      context: 'socket_connect',
    })).toBe(true)
    expect(isRecoverableVisitorSessionError(new Error('visitor_session_token required'), {
      context: 'socket_connect',
    })).toBe(true)
  })

  it('does not treat join NOT_FOUND as remint-recoverable', () => {
    expect(isRecoverableVisitorSessionError('NOT_FOUND', {
      context: 'socket_join',
      code: 'NOT_FOUND',
    })).toBe(false)
    expect(isRecoverableVisitorSessionError('NOT_FOUND', {
      context: 'http',
      code: 'NOT_FOUND',
    })).toBe(false)
    expect(isRecoverableVisitorSessionError({ response: { status: 404 } }, { context: 'http' })).toBe(false)
  })

  it('does not treat business or server failures as recoverable', () => {
    expect(isRecoverableVisitorSessionError('INTERNAL', { context: 'socket_join', code: 'INTERNAL' })).toBe(false)
    expect(isRecoverableVisitorSessionError({ response: { status: 500 } }, { context: 'http' })).toBe(false)
    expect(isRecoverableVisitorSessionError('FORBIDDEN', { context: 'socket_join', code: 'FORBIDDEN' })).toBe(false)
    expect(isRecoverableVisitorSessionError(new Error('OpenAgent stream timed out'), { context: 'http' })).toBe(false)
  })
})

describe('visitorRecoveryTelemetryLevel', () => {
  it('warns while self-heal can still run and errors once it is exhausted', () => {
    expect(visitorRecoveryTelemetryLevel({ recoverable: true })).toBe('warn')
    expect(visitorRecoveryTelemetryLevel({ recoverable: true, recoveryExhausted: false })).toBe('warn')
    expect(visitorRecoveryTelemetryLevel({ recoverable: true, recoveryExhausted: true })).toBe('error')
    expect(visitorRecoveryTelemetryLevel({ recoverable: false })).toBe('error')
  })
})
