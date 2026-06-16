import { createI18n } from 'vue-i18n'

export type AppLocale = 'en' | 'fr'

export const browserLocale: AppLocale =
  typeof navigator !== 'undefined' && navigator.language.startsWith('fr') ? 'fr' : 'en'

// Boot with no message catalogue baked into the main bundle — each locale
// JSON (~90 KB, 1.8 k keys) is split into its own async chunk. An operator
// only ever uses one language, so loading both eagerly doubled the i18n
// transfer + JSON.parse cost on every boot. ``ensureLocale`` loads the
// active catalogue before mount (main.ts) and the other only on a manual
// language switch (Settings › System). Fallback is the active locale itself
// so a missing key never forces the *other* (unloaded) catalogue to load.
export const i18n = createI18n({
  legacy: false,
  locale: browserLocale,
  fallbackLocale: browserLocale,
  messages: {},
})

const loaders: Record<AppLocale, () => Promise<{ default: Record<string, unknown> }>> = {
  en: () => import('./locales/en.json'),
  fr: () => import('./locales/fr.json'),
}
const loaded = new Set<AppLocale>()

/**
 * Load a locale's catalogue (idempotent) and register it on the shared i18n
 * instance. Await this before switching ``i18n.global.locale`` to ``locale``
 * so the new language renders fully translated rather than flashing raw keys.
 */
export async function ensureLocale(locale: AppLocale): Promise<void> {
  if (loaded.has(locale)) return
  const mod = await loaders[locale]()
  i18n.global.setLocaleMessage(locale, mod.default)
  loaded.add(locale)
}
