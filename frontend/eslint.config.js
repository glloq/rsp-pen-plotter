// ESLint flat config: catches errors, leaves style to Prettier.
import js from '@eslint/js'
import vue from 'eslint-plugin-vue'
import vueParser from 'vue-eslint-parser'
import tsParser from '@typescript-eslint/parser'
import tsPlugin from '@typescript-eslint/eslint-plugin'
import prettier from 'eslint-config-prettier'
import globals from 'globals'

export default [
  {
    ignores: [
      'dist/**',
      'node_modules/**',
      'coverage/**',
      'src/domain/api-types.ts',
      '**/*.config.js',
      '**/*.config.ts',
    ],
  },
  js.configs.recommended,
  ...vue.configs['flat/recommended'],
  {
    files: ['**/*.{ts,vue}'],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tsParser,
        ecmaVersion: 2022,
        sourceType: 'module',
        extraFileExtensions: ['.vue'],
      },
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.es2022,
      },
    },
    plugins: {
      '@typescript-eslint': tsPlugin,
    },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/no-explicit-any': 'off',
      'vue/multi-word-component-names': 'off',
      'vue/no-v-html': 'off',
      'vue/attribute-hyphenation': 'off',
      'vue/v-on-event-hyphenation': 'off',
      'vue/html-self-closing': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/html-indent': 'off',
      'vue/html-closing-bracket-newline': 'off',
      'vue/first-attribute-linebreak': 'off',
    },
  },
  {
    // Shared-draft idiom (deliberate, documented): each of these edit
    // draft-card components receives a reactive slice of a draft
    // singleton (``bitmap`` / ``typo`` / ``draft`` / ``pen``) from its
    // parent and mutates it directly — the parent owns the lifecycle and
    // every card is one facet of the SAME object, so ``defineModel`` /
    // emit round-trips would only add indirection without changing
    // ownership. ``vue/no-mutating-props`` is therefore disabled for
    // exactly these files; any NEW component mutating a prop still gets
    // flagged by the recommended preset above. Refactoring the idiom
    // itself stays tracked as the v2.0 hygiene follow-up (TODO 6.2).
    files: [
      'src/components/ProfilePenFields.vue',
      'src/components/edit/image/BasicAdjustmentsCard.vue',
      'src/components/edit/image/FiltersCard.vue',
      'src/components/edit/image/LevelsCard.vue',
      'src/components/edit/image/TransformCard.vue',
      'src/components/edit/render/ColorCountSlider.vue',
      'src/components/edit/render/DualRangeSlider.vue',
      'src/components/edit/render/MasterStyleParams.vue',
      'src/components/edit/source/PaletteCard.vue',
      'src/components/edit/source/TypographyCard.vue',
      'src/components/edit/style/PostProcessCard.vue',
      'src/components/edit/svg/SegmentationCountCard.vue',
      'src/components/edit/svg/SegmentationMethodCard.vue',
    ],
    rules: {
      'vue/no-mutating-props': 'off',
    },
  },
  prettier,
]
