import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults } from 'vitest/config'
import viteConfig from './vite.config.ts'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      exclude: [...configDefaults.exclude, 'e2e/**'],
      root: fileURLToPath(new URL('./', import.meta.url)),
      server: {
        deps: {
          // Element Plus ships its styles as side-effect imports. Left external,
          // Node's ESM loader meets `theme-chalk/base.css` and dies with
          // "Unknown file extension .css"; inlined, the imports go through Vite's
          // CSS pipeline like they do in the app.
          inline: ['element-plus'],
        },
      },
    },
  }),
)
