;(function () {
  'use strict'

  var PROTOCOL_VERSION = '1.0'
  var SDK_VERSION = '0.1.0'

  if (window.OpenDeskCall && window.OpenDeskCall._isOpenDeskCallSdk) return

  var script = document.currentScript
  var scriptOrigin = script && script.src
    ? new URL(script.src, window.location.href).origin
    : window.location.origin

  function sdkError(code, message) {
    var error = new Error(message)
    error.code = code
    return error
  }

  function randomId(prefix) {
    var bytes = new Uint8Array(12)
    if (window.crypto && window.crypto.getRandomValues) {
      window.crypto.getRandomValues(bytes)
      return prefix + Array.prototype.map.call(bytes, function (value) {
        return value.toString(16).padStart(2, '0')
      }).join('')
    }
    return prefix + Date.now().toString(36) + Math.random().toString(36).slice(2)
  }

  function resolveContainer(value) {
    if (typeof value === 'string') return document.querySelector(value)
    return value && value.nodeType === 1 ? value : null
  }

  function normalizeBase(value) {
    return new URL(value || scriptOrigin, window.location.href).origin
  }

  function validateDialPayload(payload) {
    if (!payload || typeof payload.number !== 'string' || !payload.number.trim()) {
      throw sdkError('EMBED_NUMBER_REQUIRED', 'A phone number is required')
    }
    if (payload.customBusinessInfo != null) {
      if (typeof payload.customBusinessInfo !== 'string') {
        throw sdkError('EMBED_CUSTOM_BUSINESS_INFO_INVALID', 'Custom business information must be text')
      }
      if (new TextEncoder().encode(payload.customBusinessInfo).length > 32768) {
        throw sdkError('EMBED_CUSTOM_BUSINESS_INFO_TOO_LARGE', 'Custom business information exceeds 32 KiB')
      }
    }
    return payload
  }

  function create(options) {
    options = options || {}
    var integrationKey = String(options.integrationKey || '').trim()
    var container = resolveContainer(options.container)
    if (!integrationKey) throw sdkError('EMBED_INTEGRATION_KEY_REQUIRED', 'integrationKey is required')
    if (!container) throw sdkError('EMBED_CONTAINER_NOT_FOUND', 'container was not found')
    if (typeof options.getEmbedSignature !== 'function') {
      throw sdkError('EMBED_SIGNATURE_PROVIDER_REQUIRED', 'getEmbedSignature is required')
    }

    var baseUrl = normalizeBase(options.baseUrl)
    var frameOrigin = new URL(baseUrl).origin
    var instanceId = randomId('ecinst_')
    var listeners = {}
    var pending = {}
    var destroyed = false
    var authInFlight = null
    var authRetryTimer = null
    var authFailureCount = 0
    var queuedAuthNonce = null
    var latestState = { authState: 'booting', expanded: options.display?.expanded !== false }
    var readyResolve
    var readyReject
    var readyPromise = new Promise(function (resolve, reject) {
      readyResolve = resolve
      readyReject = reject
    })

    var frame = document.createElement('iframe')
    var frameUrl = new URL('/embedded/call', baseUrl)
    frameUrl.searchParams.set('integrationKey', integrationKey)
    frameUrl.searchParams.set('v', PROTOCOL_VERSION)
    frameUrl.searchParams.set('instanceId', instanceId)
    frameUrl.searchParams.set('expanded', latestState.expanded ? '1' : '0')
    if (options.locale) frameUrl.searchParams.set('locale', options.locale)
    if (options.theme) frameUrl.searchParams.set('theme', options.theme)
    frame.src = frameUrl.toString()
    frame.title = options.title || 'OpenDesk Call'
    frame.allow = 'microphone; autoplay'
    frame.referrerPolicy = 'strict-origin-when-cross-origin'
    frame.style.width = '100%'
    frame.style.height = latestState.expanded ? '620px' : '56px'
    frame.style.minWidth = '320px'
    frame.style.border = '1px solid rgba(18, 24, 31, 0.08)'
    frame.style.borderRadius = '16px'
    frame.style.boxShadow = '0 20px 55px rgba(18, 24, 31, 0.18)'
    frame.style.overflow = 'hidden'
    frame.style.display = 'block'
    frame.style.background = 'transparent'
    container.appendChild(frame)

    function emit(name, payload) {
      var callbacks = (listeners[name] || []).slice()
      callbacks.concat((listeners['*'] || []).slice()).forEach(function (callback) {
        try { callback(payload, name) } catch (error) { setTimeout(function () { throw error }, 0) }
      })
    }

    function send(type, payload, requestId) {
      if (destroyed || !frame.contentWindow) return
      frame.contentWindow.postMessage({
        source: 'opendesk-call-host',
        protocolVersion: PROTOCOL_VERSION,
        instanceId: instanceId,
        type: type,
        requestId: requestId || null,
        payload: payload || {},
      }, frameOrigin)
    }

    function provideSignature(nonce) {
      if (authInFlight) {
        queuedAuthNonce = nonce
        return authInFlight
      }
      if (authRetryTimer) {
        clearTimeout(authRetryTimer)
        authRetryTimer = null
      }
      authInFlight = Promise.resolve(options.getEmbedSignature({
        integrationKey: integrationKey,
        origin: window.location.origin,
        nonce: nonce,
        instanceId: instanceId,
      })).then(function (result) {
        var signature = typeof result === 'string'
          ? result
          : result && (result.embedSignature || result.embed_signature)
        if (!signature) throw sdkError('EMBED_SIGNATURE_INVALID', 'Signature provider returned no signature')
        authFailureCount = 0
        send('authenticate', {
          embedSignature: signature,
          origin: window.location.origin,
          nonce: nonce,
        })
      }).catch(function (error) {
        authFailureCount += 1
        emit('error', { code: error.code || 'EMBED_SIGNATURE_FAILED', message: error.message })
        if (!destroyed && authFailureCount < 5) {
          authRetryTimer = setTimeout(function () {
            authRetryTimer = null
            provideSignature(nonce)
          }, 1000)
        } else {
          readyReject(error)
        }
      }).finally(function () {
        authInFlight = null
        if (queuedAuthNonce) {
          var nextNonce = queuedAuthNonce
          queuedAuthNonce = null
          provideSignature(nextNonce)
        }
      })
      return authInFlight
    }

    function onMessage(event) {
      if (destroyed || event.origin !== frameOrigin || event.source !== frame.contentWindow) return
      var message = event.data
      if (!message || message.source !== 'opendesk-call-frame') return
      if (message.protocolVersion !== PROTOCOL_VERSION || message.instanceId !== instanceId) return
      if (message.type === 'handshake' || message.type === 'authRequested') {
        if (message.payload && typeof message.payload.nonce === 'string') {
          provideSignature(message.payload.nonce)
        }
        return
      }
      if (message.type === 'response' && message.requestId && pending[message.requestId]) {
        var entry = pending[message.requestId]
        delete pending[message.requestId]
        clearTimeout(entry.timer)
        if (message.payload && message.payload.ok) entry.resolve(message.payload.result)
        else entry.reject(sdkError(
          message.payload?.error?.code || 'EMBED_COMMAND_FAILED',
          message.payload?.error?.message || 'Embedded call command failed',
        ))
        return
      }
      if (message.type === 'event' && message.payload) {
        var name = message.payload.name
        var payload = message.payload.payload || {}
        if (name === 'stateChanged') latestState = payload
        if (name === 'ready') readyResolve(api)
        if (name === 'resizeRequested' && payload.height) {
          frame.style.height = Math.max(56, Math.min(800, Number(payload.height))) + 'px'
        }
        emit(name, payload)
      }
    }

    function request(command, payload, timeout) {
      if (destroyed) return Promise.reject(sdkError('EMBED_DESTROYED', 'Instance was destroyed'))
      var requestId = randomId('ecreq_')
      return new Promise(function (resolve, reject) {
        pending[requestId] = {
          resolve: resolve,
          reject: reject,
          timer: setTimeout(function () {
            delete pending[requestId]
            reject(sdkError('EMBED_COMMAND_TIMEOUT', 'Embedded call command timed out'))
          }, timeout || 15000),
        }
        send('command', { name: command, payload: payload || {} }, requestId)
      })
    }

    window.addEventListener('message', onMessage)

    var api = {
      instanceId: instanceId,
      ready: function () { return readyPromise },
      dial: function (payload) {
        validateDialPayload(payload)
        if (navigator.userActivation && !navigator.userActivation.isActive) {
          return Promise.reject(sdkError(
            'EMBED_USER_ACTIVATION_REQUIRED',
            'dial must be called from an active user gesture',
          ))
        }
        api.open()
        return request('dial', payload, 30000)
      },
      prefillDialer: function (payload) {
        validateDialPayload(payload)
        api.open()
        return request('prefillDialer', payload)
      },
      setContext: function (context) { return request('setContext', context || {}) },
      open: function () {
        latestState.expanded = true
        frame.style.height = '620px'
        send('command', { name: 'open', payload: {} }, randomId('ecreq_'))
      },
      close: function () {
        latestState.expanded = false
        frame.style.height = '56px'
        send('command', { name: 'close', payload: {} }, randomId('ecreq_'))
      },
      focus: function () { frame.focus() },
      getState: function () { return Object.assign({}, latestState) },
      on: function (name, callback) {
        if (typeof callback !== 'function') return api
        ;(listeners[name] || (listeners[name] = [])).push(callback)
        return api
      },
      off: function (name, callback) {
        listeners[name] = (listeners[name] || []).filter(function (item) { return item !== callback })
        return api
      },
      destroy: function () {
        if (destroyed) return
        send('command', { name: 'destroy', payload: {} }, randomId('ecreq_'))
        destroyed = true
        if (authRetryTimer) clearTimeout(authRetryTimer)
        window.removeEventListener('message', onMessage)
        Object.keys(pending).forEach(function (id) {
          clearTimeout(pending[id].timer)
          pending[id].reject(sdkError('EMBED_DESTROYED', 'Instance was destroyed'))
        })
        pending = {}
        frame.remove()
        listeners = {}
      },
    }

    return api
  }

  window.OpenDeskCall = {
    version: SDK_VERSION,
    protocolVersion: PROTOCOL_VERSION,
    create: create,
    _isOpenDeskCallSdk: true,
  }
})()
