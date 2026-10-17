import { createApp } from 'vue'

import App from './App.vue'
import { setupDirectives } from './directives'
import router from './router'
import pinia from './stores'

import 'element-plus/theme-chalk/dark/css-vars.css'

const app = createApp(App)

// Pinia first: the permission directives resolve their store during mount.
app.use(pinia)
app.use(router)
setupDirectives(app)

app.mount('#app')
