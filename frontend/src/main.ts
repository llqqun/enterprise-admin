import * as ElementPlusIcons from '@element-plus/icons-vue'
import { createApp, type Component } from 'vue'

import App from './App.vue'
import { setupDirectives } from './directives'
import router from './router'
import pinia from './stores'

import 'element-plus/theme-chalk/dark/css-vars.css'
import './styles/index.scss'

const app = createApp(App)

// Icons are registered globally because the sidebar renders whatever icon name the
// backend sent (`menu.meta.icon`), resolved through `<component :is="...">`. There
// is no import statement to auto-generate for a name that only exists at runtime.
for (const [name, component] of Object.entries(ElementPlusIcons)) {
  app.component(name, component as Component)
}

// Pinia first: the permission directives resolve their store during mount.
app.use(pinia)
app.use(router)
setupDirectives(app)

app.mount('#app')
