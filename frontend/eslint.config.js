import js from '@eslint/js'
import i18next from 'eslint-plugin-i18next'
import reactHooks from 'eslint-plugin-react-hooks'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'coverage', 'node_modules'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    plugins: {
      'react-hooks': reactHooks,
      i18next,
    },
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      'i18next/no-literal-string': [
        'error',
        {
          mode: 'jsx-text-only',
          ignore: [
            '^[0-9$&@:/\\-+*=<>|~^%.,;:()\\[\\]"\'`!؟? ]*$',
            '^Study Assistant$',
          ],
        },
      ],
    },
  },
  {
    files: ['src/**/*.test.{ts,tsx}', 'src/test/**'],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      'i18next/no-literal-string': 'off',
    },
  },
)
