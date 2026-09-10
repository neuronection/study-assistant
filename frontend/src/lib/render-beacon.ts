let signaled = false

export function signalShellRendered(): void {
  if (signaled) return
  signaled = true
  const send = () => {
    void fetch('/api/v1/shell/rendered', { method: 'POST' })
  }
  requestAnimationFrame(() => requestAnimationFrame(send))
}
