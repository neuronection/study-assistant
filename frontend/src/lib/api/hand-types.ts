export interface ExerciseOrderingItem {
  id: number
  label: string
}

export const HAND_TYPE_REGISTER = [
  { name: 'ExerciseOrderingItem', source: 'exercise-struct position index', numericId: true },
  { name: 'PendingDrawing', source: 'client placeholder refs', numericId: true },
] as const
