// Small composable so components don't have to know about the uiMode
// store internals just to check a flag. Returns a computed so flag
// changes propagate reactively into v-if / v-show.

import { computed, type ComputedRef } from 'vue'
import { useUiModeStore } from '../stores/uiMode'

export function useFeatureFlag(name: string): ComputedRef<boolean> {
  const ui = useUiModeStore()
  return computed(() => ui.isFlagEnabled(name))
}
