import { useMutation, useQuery } from '@tanstack/react-query'
import { BookOpen, Plus, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { createCourseType, listCourseTypes, listCourses, listSkills } from '@/lib/api'

import { SkillsEditor } from './SkillsPage'

export function SkillsTab() {
  const { t } = useTranslation()
  const skills = useQuery({ queryKey: ['skills'], queryFn: listSkills })
  const courseTypes = useQuery({ queryKey: ['course-types'], queryFn: listCourseTypes })
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const [editing, setEditing] = useState<{ key: string; name: string } | null>(null)
  const [courseId, setCourseId] = useState<number | null>(null)
  const [newType, setNewType] = useState<{ key: string; name: string } | null>(null)

  const addType = useMutation({
    mutationFn: (body: { key: string; name: string }) => createCourseType(body),
    onSuccess: async () => {
      setNewType(null)
      await courseTypes.refetch()
    },
  })

  if (editing) {
    return (
      <SkillsEditor
        skillKey={editing.key}
        name={editing.name}
        courseId={courseId}
        onBack={() => setEditing(null)}
      />
    )
  }

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground text-sm">{t('settings.skillsHint')}</p>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <label className="text-muted-foreground">{t('settings.scopeCourse')}</label>
        <select
          className="bg-surface border-border rounded-md border px-2 py-1.5"
          value={courseId ?? ''}
          onChange={(event) => setCourseId(event.target.value === '' ? null : Number(event.target.value))}
        >
          <option value="">{t('settings.noCourse')}</option>
          {(courses.data ?? []).map((course) => (
            <option key={course.id} value={course.id}>
              {course.title}
            </option>
          ))}
        </select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('settings.courseTypes')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1">
          {(courseTypes.data ?? []).map((entry) => (
            <div key={entry.id} className="border-border flex items-center gap-2 rounded-md border px-3 py-2 text-xs">
              <span className="bg-subtle text-muted-foreground rounded px-2 py-0.5">{entry.key}</span>
              <span className="min-w-0 flex-1 truncate">{entry.name}</span>
              <span className="text-muted-foreground truncate text-[11px]">{entry.description}</span>
            </div>
          ))}
          {newType ? (
            <form
              className="flex gap-1 pt-1"
              onSubmit={(event) => {
                event.preventDefault()
                if (newType.key.trim() && newType.name.trim()) {
                  addType.mutate({ key: newType.key.trim(), name: newType.name.trim() })
                }
              }}
            >
              <input
                className="bg-surface border-border w-28 rounded-md border px-2 py-1 text-xs"
                placeholder={t('settings.typeKey')}
                value={newType.key}
                onChange={(event) => setNewType({ ...newType, key: event.target.value })}
              />
              <input
                className="bg-surface border-border flex-1 rounded-md border px-2 py-1 text-xs"
                placeholder={t('settings.typeName')}
                value={newType.name}
                onChange={(event) => setNewType({ ...newType, name: event.target.value })}
              />
              <Button type="submit" size="sm" disabled={addType.isPending}>
                {t('settings.addType')}
              </Button>
            </form>
          ) : (
            <Button variant="ghost" size="sm" onClick={() => setNewType({ key: '', name: '' })}>
              <Plus aria-hidden />
              {t('settings.newType')}
            </Button>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('settings.skills')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1">
          {(skills.data ?? []).map((skill) => (
            <div
              key={skill.key}
              className="border-border flex items-center gap-3 rounded-md border px-3 py-2"
            >
              <BookOpen className="text-muted-foreground size-4 shrink-0" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">
                  {skill.name}
                  <span className="text-muted-foreground ml-2 rounded-full bg-subtle px-2 py-0.5 text-[10px]">
                    {skill.task}
                  </span>
                </p>
                <p className="text-muted-foreground truncate text-xs">{skill.description}</p>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setEditing({ key: skill.key, name: skill.name })}
              >
                <Sparkles aria-hidden />
                {t('settings.editSkill')}
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
