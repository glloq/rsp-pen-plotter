import { createI18n } from 'vue-i18n'
import en from './locales/en.json'
import fr from './locales/fr.json'

const browser = navigator.language.startsWith('fr') ? 'fr' : 'en'

export const i18n = createI18n({
  legacy: false,
  locale: browser,
  fallbackLocale: 'en',
  messages: { en, fr },
})
