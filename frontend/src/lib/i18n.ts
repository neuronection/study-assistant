import i18next from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from '@/locales/en.json'

export const initI18n = () =>
  i18next.use(initReactI18next).init({
    lng: 'en',
    fallbackLng: 'en',
    defaultNS: 'translation',
    resources: {
      en: { translation: en },
    },
    interpolation: {
      escapeValue: false,
    },
  })
