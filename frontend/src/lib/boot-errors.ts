function renderError(message: string, detail?: string): void {
  try {
    const root = document.getElementById('root')
    if (!root) {
      return
    }
    root.innerHTML =
      '<div style="padding:40px;font-family:ui-monospace,monospace;color:#b91c1c;' +
      'background:#fef2f2;white-space:pre-wrap;font-size:13px">' +
      '<h1 style="font-size:18px;margin:0 0 8px">Unhandled error</h1>' +
      '<div>' + escapeHtml(message) + '</div>' +
      (detail ? '<div style="margin-top:8px;color:#7f1d1d">' + escapeHtml(detail) + '</div>' : '') +
      '</div>'
  } catch {
    // ignore
  }
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

export function installGlobalErrorSurface(): void {
  window.addEventListener('error', (event) => {
    const message = event.message || 'Script error'
    const detail = event.error?.stack || event.filename + ':' + event.lineno
    console.error('global error:', event.error || message)
    renderError(message, detail)
  })
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason as Error | undefined
    console.error('unhandled rejection:', reason)
    renderError(
      reason?.message || 'Unhandled promise rejection',
      reason?.stack || String(reason)
    )
  })
}
