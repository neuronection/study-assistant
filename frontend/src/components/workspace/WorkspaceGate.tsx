import { useQuery } from '@tanstack/react-query'
import { GraduationCap } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from '@tanstack/react-router'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { listCourses } from '@/lib/api'

export function WorkspaceGate({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation()
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })

  if (courses.data !== undefined && courses.data.length === 0) {
    return (
      <div className="mx-auto max-w-xl p-8">
        <Card>
          <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
            <GraduationCap className="text-muted-foreground size-8" aria-hidden />
            <p className="text-sm font-medium">{t('workspace.gateTitle')}</p>
            <p className="text-muted-foreground text-xs">{t('workspace.gateHint')}</p>
            <Button size="sm" asChild>
              <Link to="/courses">{t('workspace.gateAction')}</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }
  return <>{children}</>
}
