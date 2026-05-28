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
      // The v0.1 editor cards (image / render / shared) intentionally
      // mutate a reactive ``draft`` / ``preprocess`` / ``bitmap`` prop
      // because each card is one slice of the same parent draft
      // object, with the parent owning the lifecycle. Refactoring all
      // of them to ``defineModel`` / explicit emits is documented as
      // a v2.0 hygiene follow-up (TODO 6.2); for v0.2 the rule is
      // downgraded to ``warn`` so it surfaces in the dev console but
      // doesn't gate CI.
      'vue/no-mutating-props': 'warn',
    },
  },
  prettier,
]
