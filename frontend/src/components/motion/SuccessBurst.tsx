import { motion } from 'framer-motion'

import { useMotionPresets } from '@/lib/motion'
import { cn } from '@/lib/utils'

interface SuccessBurstProps {
  size?: number
  className?: string
}

export function SuccessBurst({ size = 16, className }: SuccessBurstProps) {
  const { reduced } = useMotionPresets()
  const draw = (delay: number, duration: number) =>
    reduced ? { duration: 0 } : { delay, duration, ease: 'easeOut' as const }
  return (
    <motion.svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      className={cn('text-success', className)}
      data-testid="success-burst"
    >
      <motion.circle
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="2"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={draw(0, 0.25)}
      />
      <motion.path
        d="M7 12.5l3.2 3.2L17 9"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={draw(0.15, 0.25)}
      />
    </motion.svg>
  )
}
