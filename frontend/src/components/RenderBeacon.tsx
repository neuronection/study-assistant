import { useEffect } from 'react'

import { signalShellRendered } from '@/lib/render-beacon'

export function RenderBeacon() {
  useEffect(() => {
    signalShellRendered()
  }, [])
  return null
}
