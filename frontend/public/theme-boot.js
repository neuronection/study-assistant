/* global window, document, localStorage */
;(() => {
  try {
    const stored = localStorage.getItem('ca.theme')
    const theme = stored === 'light' || stored === 'dark' ? stored : 'system'
    const dark =
      theme === 'dark' ||
      (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
    document.documentElement.classList.toggle('dark', dark)
  } catch {
    document.documentElement.classList.toggle(
      'dark',
      window.matchMedia('(prefers-color-scheme: dark)').matches,
    )
  }
})()
