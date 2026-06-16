import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import { browserLocale, ensureLocale, i18n } from './i18n'
import './style.css'

// Load the active locale's catalogue before mounting so the first paint is
// fully translated (no flash of raw keys). The unused locale stays a lazy
// chunk fetched only on a manual language switch.
ensureLocale(browserLocale).finally(() => {
  createApp(App).use(createPinia()).use(i18n).mount('#app')
})
