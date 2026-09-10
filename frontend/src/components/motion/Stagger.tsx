import { AnimatePresence, motion } from 'framer-motion'
import type { DragEventHandler, HTMLAttributes, ReactNode } from 'react'

import { useMotionPresets } from '@/lib/motion'

type DivAttributes = Omit<
  HTMLAttributes<HTMLDivElement>,
  | 'onDrag'
  | 'onDragStart'
  | 'onDragEnd'
  | 'onAnimationStart'
  | 'onAnimationEnd'
  | 'onAnimationIteration'
>

interface StaggerProps extends DivAttributes {
  children: ReactNode
  stagger?: number
}

export function Stagger({ children, stagger, className, ...rest }: StaggerProps) {
  const presets = useMotionPresets()
  return (
    <motion.div
      variants={presets.staggeredRows(stagger)}
      initial="hidden"
      animate="show"
      className={className}
      {...rest}
    >
      <AnimatePresence>{children}</AnimatePresence>
    </motion.div>
  )
}

interface StaggerItemProps extends DivAttributes {
  children: ReactNode
  draggable?: boolean
  onDragStart?: DragEventHandler<HTMLDivElement>
}

export function StaggerItem({ children, className, onDragStart, ...rest }: StaggerItemProps) {
  const presets = useMotionPresets()
  return (
    <motion.div
      variants={presets.row}
      className={className}
      onDragStart={onDragStart as unknown as never}
      {...rest}
    >
      {children}
    </motion.div>
  )
}
