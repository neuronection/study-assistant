import { Outlet, useLocation } from '@tanstack/react-router'
import { motion } from 'framer-motion'
import { useEffect, useState, type ReactNode } from 'react'

import { useMotionPresets } from '@/lib/motion'

export function RouteFade({ children }: { children?: ReactNode }) {
  const location = useLocation()
  const presets = useMotionPresets()
  const areaKey = `/${location.pathname.split('/')[1] ?? ''}`
  const [settled, setSettled] = useState(false)
  useEffect(() => {
    setSettled(true)
  }, [])
  const { initial, animate, transition } = presets.route
  return (
    <motion.div
      key={areaKey}
      initial={settled ? initial : false}
      animate={animate}
      transition={transition}
    >
      {children ?? <Outlet />}
    </motion.div>
  )
}
