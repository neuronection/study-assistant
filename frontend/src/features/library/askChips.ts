export type AskChipKey = 'explain' | 'summarize' | 'keyTerms' | 'workedExample' | 'quizMe'

export interface AskChip {
  key: AskChipKey
  labelKey: string
  textKey: string
  textKeyMulti?: string
  quizMe?: boolean
}

export const ASK_CHIPS: AskChip[] = [
  {
    key: 'explain',
    labelKey: 'library.askChip.explain.label',
    textKey: 'library.askChip.explain.text',
    textKeyMulti: 'library.askChip.explain.textMulti',
  },
  {
    key: 'summarize',
    labelKey: 'library.askChip.summarize.label',
    textKey: 'library.askChip.summarize.text',
    textKeyMulti: 'library.askChip.summarize.textMulti',
  },
  {
    key: 'keyTerms',
    labelKey: 'library.askChip.keyTerms.label',
    textKey: 'library.askChip.keyTerms.text',
    textKeyMulti: 'library.askChip.keyTerms.textMulti',
  },
  {
    key: 'workedExample',
    labelKey: 'library.askChip.workedExample.label',
    textKey: 'library.askChip.workedExample.text',
    textKeyMulti: 'library.askChip.workedExample.textMulti',
  },
  {
    key: 'quizMe',
    labelKey: 'library.askChip.quizMe.label',
    textKey: 'library.askChip.quizMe.text',
    textKeyMulti: 'library.askChip.quizMe.textMulti',
    quizMe: true,
  },
]
