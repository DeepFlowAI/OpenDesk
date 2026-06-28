;(function () {
  'use strict'

  var VERSION = '0.1.0'
  var GLOBAL_NAME = 'OpenDesk'

  if (window[GLOBAL_NAME] && window[GLOBAL_NAME]._isOpenDeskSdk) return

  var currentScript = document.currentScript
  var scriptSrc = currentScript && currentScript.src ? currentScript.src : ''
  var instances = {}
  var defaultChannelKey = null

  function getScriptBaseUrl() {
    if (!scriptSrc) return window.location.origin
    try {
      return new URL(scriptSrc, window.location.href).origin
    } catch (_) {
      return window.location.origin
    }
  }

  function normalizeAppBaseUrl(value) {
    var raw = value || getScriptBaseUrl()
    try {
      var url = new URL(raw, window.location.href)
      if (value && url.pathname && url.pathname !== '/' && !/\.[a-z0-9]+$/i.test(url.pathname)) {
        return (url.origin + url.pathname).replace(/\/+$/, '')
      }
      return url.origin
    } catch (_) {
      return window.location.origin
    }
  }

  function normalizeApiBaseUrl(value, appBaseUrl) {
    var raw = value || (appBaseUrl + '/api')
    try {
      var url = new URL(raw, window.location.href)
      return (url.origin + url.pathname).replace(/\/+$/, '')
    } catch (_) {
      return appBaseUrl.replace(/\/+$/, '') + '/api'
    }
  }

  function baseOrigin(baseUrl) {
    try {
      return new URL(baseUrl, window.location.href).origin
    } catch (_) {
      return window.location.origin
    }
  }

  function createInstanceId() {
    if (window.crypto && window.crypto.getRandomValues) {
      var bytes = new Uint8Array(12)
      window.crypto.getRandomValues(bytes)
      return 'od_' + Array.prototype.map.call(bytes, function (b) {
        return b.toString(16).padStart(2, '0')
      }).join('')
    }
    return 'od_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10)
  }

  function isMobileViewport() {
    return window.matchMedia ? window.matchMedia('(max-width: 767px)').matches : window.innerWidth < 768
  }

  function clampNumber(value, fallback, min, max) {
    var n = Number(value)
    if (!Number.isFinite(n)) n = fallback
    if (Number.isFinite(min)) n = Math.max(min, n)
    if (Number.isFinite(max)) n = Math.min(max, n)
    return n
  }

  function validPosition(value) {
    return ['bottom-right', 'bottom-left', 'top-right', 'top-left'].indexOf(value) !== -1
      ? value
      : 'bottom-right'
  }

  function createSdkError(code, message, detail) {
    return { code: code, message: message, detail: detail }
  }

  function readDeviceId() {
    var key = 'opendesk:telemetry:device_id'
    try {
      var existing = window.localStorage.getItem(key)
      if (existing) return existing
      var fresh = createInstanceId()
      window.localStorage.setItem(key, fresh)
      return fresh
    } catch (_) {
      return createInstanceId()
    }
  }

  function trackSdkEvent(instance, name, props, level) {
    if (!instance || !instance.channelKey || !instance.apiBaseUrl) return
    try {
      var batch = {
        common: {
          session_id: instance.instanceId,
          device_id: readDeviceId(),
          release: VERSION,
          url: window.location.href,
          user_agent: navigator.userAgent,
          viewport: window.innerWidth + 'x' + window.innerHeight,
          sdk_name: 'opendesk-js',
          sdk_version: VERSION,
          ts_offset_ms: 0,
        },
        events: [{
          name: name,
          ts: Date.now(),
          level: level || 'info',
          props: props || null,
          metrics: null,
        }],
      }
      var url = instance.apiBaseUrl + '/v1/public/channels/' + encodeURIComponent(instance.channelKey) + '/telemetry/events'
      var body = JSON.stringify(batch)
      if (navigator.sendBeacon) {
        var ok = navigator.sendBeacon(url, new Blob([body], { type: 'application/json' }))
        if (ok) return
      }
      fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body,
        credentials: 'omit',
        keepalive: true,
      }).catch(function () {})
    } catch (_) {}
  }

  function callSafely(fn, arg) {
    if (typeof fn !== 'function') return
    try {
      fn(arg)
    } catch (error) {
      setTimeout(function () {
        throw error
      }, 0)
    }
  }

  function normalizeMetadata(value) {
    return normalizePlainObject(value, 8192)
  }

  function normalizePlainObject(value, maxLength) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null
    try {
      var json = JSON.stringify(value)
      if (!json || json.length > maxLength) return null
      var parsed = JSON.parse(json)
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
      return parsed
    } catch (_) {
      return null
    }
  }

  function normalizeContextToken(value) {
    if (typeof value !== 'string') return null
    var token = value.trim()
    return token ? token : null
  }

  function normalizeContextObject(value) {
    return normalizePlainObject(value, 16384)
  }

  function normalizeVisitor(value) {
    if (!value || typeof value !== 'object') return null
    var visitor = {}
    if (typeof value.name === 'string') {
      var name = value.name.trim()
      if (name) visitor.name = name.slice(0, 64)
    }
    var customer = normalizeContextObject(value.customer)
    if (customer) visitor.customer = customer
    var metadata = normalizeMetadata(value.metadata)
    if (metadata) visitor.metadata = metadata
    return Object.keys(visitor).length ? visitor : null
  }

  function buildOptions(options) {
    var launcher = options.launcher || {}
    var windowOptions = options.window || {}
    var appBaseUrl = normalizeAppBaseUrl(options.appBaseUrl || options.baseUrl)
    return {
      channelKey: String(options.channelKey || '').trim(),
      baseUrl: appBaseUrl,
      appBaseUrl: appBaseUrl,
      apiBaseUrl: normalizeApiBaseUrl(options.apiBaseUrl, appBaseUrl),
      locale: options.locale || 'auto',
      visitor: normalizeVisitor(options.visitor),
      contextToken: normalizeContextToken(options.contextToken),
      sessionSummary: normalizeContextObject(options.sessionSummary),
      preload: options.preload !== false,
      launcher: {
        visible: launcher.visible !== false,
        position: validPosition(launcher.position),
        offsetX: clampNumber(launcher.offsetX, 24, 0, 160),
        offsetY: clampNumber(launcher.offsetY, 24, 0, 160),
        zIndex: clampNumber(launcher.zIndex, 2147483000, 1, 2147483647),
      },
      window: {
        width: clampNumber(windowOptions.width, 400, 280, 960),
        height: clampNumber(windowOptions.height, 640, 360, 1200),
        minWidth: clampNumber(windowOptions.minWidth, 360, 240, 960),
        minHeight: clampNumber(windowOptions.minHeight, 520, 320, 1200),
        maxWidth: Number.isFinite(Number(windowOptions.maxWidth)) ? Number(windowOptions.maxWidth) : null,
        maxHeight: Number.isFinite(Number(windowOptions.maxHeight)) ? Number(windowOptions.maxHeight) : null,
      },
      callbacks: {
        onReady: options.onReady,
        onOpen: options.onOpen,
        onClose: options.onClose,
        onError: options.onError,
        onWarning: options.onWarning,
      },
    }
  }

  function makeStyles(zIndex, backgroundColor, iconColor) {
    return [
      ':host{all:initial}',
      '.od-root,.od-root *{box-sizing:border-box}',
      '.od-launcher{position:fixed;width:56px;height:56px;border:0;border-radius:999px;display:flex;align-items:center;justify-content:center;background:' + backgroundColor + ';color:' + iconColor + ';box-shadow:0 16px 36px rgba(15,23,42,.22),0 4px 12px rgba(15,23,42,.12);cursor:pointer;z-index:' + zIndex + ';transition:transform .15s ease,box-shadow .15s ease,opacity .15s ease}',
      '.od-launcher:hover{transform:translateY(-1px);box-shadow:0 20px 44px rgba(15,23,42,.24),0 6px 16px rgba(15,23,42,.14)}',
      '.od-launcher:focus-visible{outline:3px solid rgba(59,130,246,.45);outline-offset:3px}',
      '.od-launcher svg{width:26px;height:26px;display:block}',
      '.od-window{position:fixed;overflow:hidden;border:1px solid rgba(15,23,42,.12);border-radius:14px;background:transparent;box-shadow:0 24px 64px rgba(15,23,42,.22),0 8px 24px rgba(15,23,42,.14);z-index:' + (zIndex + 1) + ';display:block;opacity:0;visibility:hidden;pointer-events:none;transform:translateY(8px) scale(.98);transition:opacity .16s ease,transform .16s ease,visibility 0s linear .16s}',
      '.od-window.od-open{opacity:1;visibility:visible;pointer-events:auto;transform:none;transition:opacity .16s ease,transform .16s ease,visibility 0s}',
      '.od-frame{width:100%;height:100%;border:0;display:block;background:transparent}',
      '@media (max-width:767px){.od-launcher,.od-window{display:none!important}}',
    ].join('\n')
  }

  function scheduleIdle(callback) {
    if (window.requestIdleCallback) {
      return {
        type: 'idle',
        id: window.requestIdleCallback(callback, { timeout: 2000 }),
      }
    }
    return {
      type: 'timeout',
      id: window.setTimeout(callback, 600),
    }
  }

  function cancelIdle(handle) {
    if (!handle) return
    if (handle.type === 'idle' && window.cancelIdleCallback) {
      window.cancelIdleCallback(handle.id)
      return
    }
    window.clearTimeout(handle.id)
  }

  function OpenDeskInstance(rawOptions) {
    this.options = buildOptions(rawOptions)
    this.channelKey = this.options.channelKey
    this.baseUrl = this.options.appBaseUrl
    this.appBaseUrl = this.options.appBaseUrl
    this.apiBaseUrl = this.options.apiBaseUrl
    this.baseOrigin = baseOrigin(this.appBaseUrl)
    this.instanceId = createInstanceId()
    this.channel = null
    this.host = null
    this.root = null
    this.styleNode = null
    this.launcher = null
    this.panel = null
    this.iframe = null
    this.destroyed = false
    this.failed = false
    this.frameReady = false
    this.pendingOpen = false
    this.preloadScheduled = false
    this.preloadHandle = null
    this.state = {
      channelKey: this.channelKey,
      instanceId: this.instanceId,
      ready: false,
      open: false,
      mobileUnsupported: isMobileViewport(),
    }

    this.handleMessage = this.handleMessage.bind(this)
    this.handleResize = this.handleResize.bind(this)
    window.addEventListener('message', this.handleMessage)
    window.addEventListener('resize', this.handleResize)
    this.track('sdk_init', {
      preload: this.options.preload,
      launcher_visible: this.options.launcher.visible,
      mobile_unsupported: this.state.mobileUnsupported,
    })
    this.load()
  }

  OpenDeskInstance.prototype.getState = function () {
    return {
      channelKey: this.state.channelKey,
      instanceId: this.state.instanceId,
      ready: this.state.ready,
      open: this.state.open,
      mobileUnsupported: this.state.mobileUnsupported,
    }
  }

  OpenDeskInstance.prototype.track = function (name, props, level) {
    trackSdkEvent(this, name, props, level)
  }

  OpenDeskInstance.prototype.emitError = function (error) {
    callSafely(this.options.callbacks.onError, error)
  }

  OpenDeskInstance.prototype.emitWarning = function (warning) {
    callSafely(this.options.callbacks.onWarning, warning)
  }

  OpenDeskInstance.prototype.fail = function (error) {
    this.failed = true
    window.removeEventListener('message', this.handleMessage)
    window.removeEventListener('resize', this.handleResize)
    this.emitError(error)
    if (instances[this.channelKey] === this) delete instances[this.channelKey]
    if (defaultChannelKey === this.channelKey) defaultChannelKey = null
  }

  OpenDeskInstance.prototype.load = function () {
    var self = this
    if (!this.channelKey) {
      this.fail(createSdkError('INVALID_OPTIONS', 'OpenDesk.init requires a non-empty channelKey.'))
      return
    }

    fetch(this.apiBaseUrl + '/v1/public/channels/' + encodeURIComponent(this.channelKey), {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'omit',
    })
      .then(function (response) {
        if (response.status === 404) {
          throw createSdkError('CHANNEL_NOT_FOUND', 'OpenDesk channel was not found.')
        }
        if (!response.ok) {
          throw createSdkError('CONFIG_LOAD_FAILED', 'Failed to load OpenDesk channel config.', {
            status: response.status,
          })
        }
        return response.json()
      })
      .then(function (channel) {
        if (self.destroyed) return
        self.channel = channel
        self.state.ready = true
        self.state.mobileUnsupported = isMobileViewport()
        self.track('sdk_config_loaded', {
          open_agent_enabled: Boolean(channel.config && channel.config.open_agent_enabled),
          assist_panel_enabled: Boolean(channel.config && channel.config.assist_panel_enabled),
        })
        if (!self.state.mobileUnsupported) self.render()
        callSafely(self.options.callbacks.onReady, self.getState())
        self.schedulePreload()
        if (self.pendingOpen) self.open()
      })
      .catch(function (error) {
        if (self.destroyed) return
        self.track('sdk_config_failed', {
          code: error && error.code ? error.code : 'CONFIG_LOAD_FAILED',
        }, 'error')
        if (error && error.code) {
          self.fail(error)
          return
        }
        self.fail(createSdkError('CONFIG_LOAD_FAILED', 'Failed to load OpenDesk channel config.', error))
      })
  }

  OpenDeskInstance.prototype.ensureRoot = function () {
    if (this.root) return

    this.host = document.createElement('div')
    this.host.setAttribute('data-opendesk-instance', this.instanceId)
    document.body.appendChild(this.host)

    var shadow = this.host.attachShadow ? this.host.attachShadow({ mode: 'open' }) : this.host
    this.root = document.createElement('div')
    this.root.className = 'od-root'
    this.styleNode = document.createElement('style')
    shadow.appendChild(this.styleNode)
    shadow.appendChild(this.root)
  }

  OpenDeskInstance.prototype.render = function () {
    if (this.destroyed || !this.channel) return
    this.ensureRoot()

    var config = this.channel.config || {}
    var backgroundColor = config.embed_button_bg_color || '#111827'
    var iconColor = config.embed_button_icon_color || '#ffffff'
    this.styleNode.textContent = makeStyles(this.options.launcher.zIndex, backgroundColor, iconColor)

    if (this.options.launcher.visible && !this.launcher) {
      this.launcher = document.createElement('button')
      this.launcher.type = 'button'
      this.launcher.className = 'od-launcher'
      this.launcher.setAttribute('aria-label', 'Open chat')
      this.launcher.innerHTML = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M18 3a4 4 0 0 1 4 4v8a4 4 0 0 1-4 4h-4.724l-4.762 2.857a1 1 0 0 1-1.508-.743l-.006-.114v-2h-1a4 4 0 0 1-3.995-3.8l-.005-.2v-8a4 4 0 0 1 4-4zm-4 9h-6a1 1 0 0 0 0 2h6a1 1 0 0 0 0-2m2-4h-8a1 1 0 1 0 0 2h8a1 1 0 0 0 0-2" fill="currentColor"/></svg>'
      this.launcher.addEventListener('click', this.toggle.bind(this))
      this.root.appendChild(this.launcher)
    }

    this.applyLayout()
  }

  OpenDeskInstance.prototype.applyLayout = function () {
    var mobile = isMobileViewport()
    this.state.mobileUnsupported = mobile
    if (mobile) {
      if (this.launcher) this.launcher.style.display = 'none'
      if (this.state.open) this.close()
      return
    }

    var position = this.options.launcher.position
    var offsetX = this.options.launcher.offsetX
    var offsetY = this.options.launcher.offsetY
    var isRight = position.indexOf('right') !== -1
    var isBottom = position.indexOf('bottom') !== -1

    if (this.launcher && this.options.launcher.visible) {
      this.launcher.style.display = 'flex'
      this.launcher.style.left = isRight ? 'auto' : offsetX + 'px'
      this.launcher.style.right = isRight ? offsetX + 'px' : 'auto'
      this.launcher.style.top = isBottom ? 'auto' : offsetY + 'px'
      this.launcher.style.bottom = isBottom ? offsetY + 'px' : 'auto'
    }

    if (!this.panel) return

    var viewportWidth = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0)
    var viewportHeight = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0)
    var launcherReserve = this.options.launcher.visible ? 72 : 0
    var edgeGap = 24
    var availableWidth = Math.max(240, viewportWidth - edgeGap * 2)
    var availableHeight = Math.max(240, viewportHeight - edgeGap - offsetY - launcherReserve)
    var maxWidth = this.options.window.maxWidth || Math.min(480, availableWidth)
    var maxHeight = this.options.window.maxHeight || availableHeight
    maxWidth = Math.max(240, Math.min(maxWidth, availableWidth))
    maxHeight = Math.max(240, Math.min(maxHeight, availableHeight))

    var minWidth = Math.min(this.options.window.minWidth, maxWidth)
    var minHeight = Math.min(this.options.window.minHeight, maxHeight)
    var width = clampNumber(this.options.window.width, 400, minWidth, maxWidth)
    var height = clampNumber(this.options.window.height, 640, minHeight, maxHeight)
    var verticalOffset = offsetY + launcherReserve

    this.panel.style.width = Math.round(width) + 'px'
    this.panel.style.height = Math.round(height) + 'px'
    this.panel.style.left = isRight ? 'auto' : offsetX + 'px'
    this.panel.style.right = isRight ? offsetX + 'px' : 'auto'
    this.panel.style.top = isBottom ? 'auto' : verticalOffset + 'px'
    this.panel.style.bottom = isBottom ? verticalOffset + 'px' : 'auto'
    this.panel.style.transformOrigin = (isBottom ? 'bottom' : 'top') + ' ' + (isRight ? 'right' : 'left')
  }

  OpenDeskInstance.prototype.schedulePreload = function () {
    if (
      this.preloadScheduled ||
      this.panel ||
      this.destroyed ||
      this.failed ||
      !this.options.preload ||
      !this.state.ready ||
      this.state.mobileUnsupported ||
      isMobileViewport()
    ) {
      return
    }

    var self = this
    this.preloadScheduled = true
    this.preloadHandle = scheduleIdle(function () {
      self.preloadHandle = null
      if (
        self.destroyed ||
        self.failed ||
        self.panel ||
        !self.state.ready ||
        isMobileViewport()
      ) {
        return
      }
      self.ensurePanel()
    })
  }

  OpenDeskInstance.prototype.ensurePanel = function () {
    if (this.panel) return
    this.ensureRoot()

    this.panel = document.createElement('div')
    this.panel.className = 'od-window'

    this.iframe = document.createElement('iframe')
    this.iframe.className = 'od-frame'
    this.iframe.title = this.channel ? this.channel.name + ' chat' : 'OpenDesk chat'
    this.iframe.allow = 'clipboard-write'
    this.iframe.referrerPolicy = 'strict-origin-when-cross-origin'
    this.iframe.src = this.buildChatUrl(true)
    this.iframe.addEventListener('error', this.handleIframeError.bind(this))

    this.panel.appendChild(this.iframe)
    this.root.appendChild(this.panel)
    this.applyLayout()
  }

  OpenDeskInstance.prototype.buildChatUrl = function (embed) {
    var url = new URL(this.appBaseUrl + '/chat/' + encodeURIComponent(this.channelKey), window.location.href)
    if (embed) {
      url.searchParams.set('embed', '1')
      url.searchParams.set('opendesk_instance', this.instanceId)
      url.searchParams.set('preload', '1')
      if (this.options.locale && this.options.locale !== 'auto') {
        url.searchParams.set('locale', this.options.locale)
      }
    } else if (this.options.contextToken) {
      url.searchParams.set('contextToken', this.options.contextToken)
    }
    return url.toString()
  }

  OpenDeskInstance.prototype.open = function () {
    if (this.destroyed || this.failed) return this
    if (isMobileViewport()) {
      this.track('sdk_open_mobile_tab')
      window.open(this.buildChatUrl(false), '_blank', 'noopener,noreferrer')
      return this
    }
    if (!this.state.ready) {
      this.pendingOpen = true
      return this
    }

    this.pendingOpen = false
    this.ensurePanel()
    if (this.state.open) return this

    this.state.open = true
    this.panel.classList.add('od-open')
    this.applyLayout()
    this.postFrameOpen()
    this.track('sdk_open')
    callSafely(this.options.callbacks.onOpen, this.getState())
    return this
  }

  OpenDeskInstance.prototype.close = function () {
    if (this.destroyed) return this
    if (!this.state.open) return this

    this.state.open = false
    if (this.panel) this.panel.classList.remove('od-open')
    this.track('sdk_close')
    callSafely(this.options.callbacks.onClose, this.getState())
    return this
  }

  OpenDeskInstance.prototype.toggle = function () {
    return this.state.open ? this.close() : this.open()
  }

  OpenDeskInstance.prototype.isOpen = function () {
    return this.state.open
  }

  OpenDeskInstance.prototype.updateContext = function (context) {
    if (!context || typeof context !== 'object') {
      this.emitError(createSdkError('INVALID_CONTEXT', 'updateContext requires a context object.'))
      return this
    }
    if (Object.prototype.hasOwnProperty.call(context, 'contextToken')) {
      this.options.contextToken = normalizeContextToken(context.contextToken)
    }
    if (Object.prototype.hasOwnProperty.call(context, 'sessionSummary')) {
      this.options.sessionSummary = normalizeContextObject(context.sessionSummary)
    }
    if (context.visitor && typeof context.visitor === 'object') {
      this.options.visitor = normalizeVisitor(context.visitor)
    }
    this.postFrameMessage('update_context', { active: this.state.open })
    this.track('sdk_context_updated', {
      has_context_token: Boolean(this.options.contextToken),
      has_session_summary: Boolean(this.options.sessionSummary),
      has_visitor: Boolean(this.options.visitor),
    })
    return this
  }

  OpenDeskInstance.prototype.destroy = function () {
    if (this.destroyed) return
    this.close()
    this.destroyed = true
    cancelIdle(this.preloadHandle)
    this.preloadHandle = null
    window.removeEventListener('message', this.handleMessage)
    window.removeEventListener('resize', this.handleResize)
    if (this.host && this.host.parentNode) this.host.parentNode.removeChild(this.host)
    if (instances[this.channelKey] === this) delete instances[this.channelKey]
    if (defaultChannelKey === this.channelKey) defaultChannelKey = null
  }

  OpenDeskInstance.prototype.handleResize = function () {
    if (!this.destroyed) this.applyLayout()
  }

  OpenDeskInstance.prototype.handleIframeError = function (event) {
    this.track('sdk_iframe_failed', null, 'error')
    this.emitError(createSdkError('IFRAME_LOAD_FAILED', 'Failed to load OpenDesk chat iframe.', event))
  }

  OpenDeskInstance.prototype.postFrameMessage = function (type, extra) {
    if (!this.iframe || !this.iframe.contentWindow) return
    var payload = {
      source: 'opendesk-sdk',
      type: type,
      instanceId: this.instanceId,
      visitor: this.options.visitor,
      contextToken: this.options.contextToken,
      sessionSummary: this.options.sessionSummary,
    }
    if (extra) {
      Object.keys(extra).forEach(function (key) {
        payload[key] = extra[key]
      })
    }
    this.iframe.contentWindow.postMessage(payload, this.baseOrigin)
  }

  OpenDeskInstance.prototype.postFrameInit = function () {
    this.postFrameMessage('init', {
      preload: !this.state.open,
      active: this.state.open,
    })
  }

  OpenDeskInstance.prototype.postFrameOpen = function () {
    if (!this.frameReady) return
    this.postFrameMessage('open', { active: true })
  }

  OpenDeskInstance.prototype.handleMessage = function (event) {
    if (this.destroyed || event.origin !== this.baseOrigin) return
    var data = event.data
    if (!data || data.source !== 'opendesk-chat' || data.instanceId !== this.instanceId) return

    if (data.type === 'ready') {
      this.frameReady = true
      this.track('sdk_iframe_ready')
      this.postFrameInit()
      return
    }
    if (data.type === 'close') {
      this.track('sdk_iframe_close_requested')
      this.close()
      return
    }
    if (data.type === 'error') {
      this.track('sdk_iframe_error', {
        code: data.code || 'IFRAME_LOAD_FAILED',
      }, 'error')
      this.emitError(createSdkError(data.code || 'IFRAME_LOAD_FAILED', data.message || 'OpenDesk chat iframe reported an error.', data))
      return
    }
    if (data.type === 'warning') {
      this.track('sdk_iframe_warning', {
        code: data.code || 'CONTEXT_PARTIAL_ACCEPTED',
      }, 'warn')
      this.emitWarning(createSdkError(data.code || 'CONTEXT_PARTIAL_ACCEPTED', data.message || 'OpenDesk chat iframe reported a warning.', data))
    }
  }

  function init(options) {
    var rawOptions = options || {}
    var channelKey = String(rawOptions.channelKey || '').trim()
    if (!channelKey) {
      var error = createSdkError('INVALID_OPTIONS', 'OpenDesk.init requires a non-empty channelKey.')
      callSafely(rawOptions.onError, error)
      throw new Error(error.message)
    }
    if (instances[channelKey] && !instances[channelKey].destroyed && !instances[channelKey].failed) {
      return instances[channelKey]
    }

    var instance = new OpenDeskInstance(rawOptions)
    instances[channelKey] = instance
    defaultChannelKey = channelKey
    return instance
  }

  function get(channelKey) {
    var key = channelKey || defaultChannelKey
    return key ? instances[key] || null : null
  }

  function destroy(channelKey) {
    var instance = get(channelKey)
    if (instance) instance.destroy()
  }

  window[GLOBAL_NAME] = {
    _isOpenDeskSdk: true,
    version: VERSION,
    init: init,
    get: get,
    destroy: destroy,
  }
})()
