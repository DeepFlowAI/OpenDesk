// Empty stub used to satisfy Node-builtin imports (fs, util, ...) that some
// browser-targeted libraries (e.g. jit-viewer) reference inside dead code
// paths. The bundler still needs to resolve these specifiers even though
// the code path is unreachable in the browser.
module.exports = {}
