import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { MotionConfig } from 'framer-motion'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import 'katex/dist/katex.min.css'
import 'mathlive/static.css'

import { router } from '@/app/router'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { RenderBeacon } from '@/components/RenderBeacon'
import { installGlobalErrorSurface } from '@/lib/boot-errors'
import { initI18n } from '@/lib/i18n'

import './index.css'

installGlobalErrorSurface()

void initI18n()

const queryClient = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <MotionConfig reducedMotion="user">
          <RenderBeacon />
          <RouterProvider router={router} />
        </MotionConfig>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>
)
