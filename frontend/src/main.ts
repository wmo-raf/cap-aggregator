import { createApp } from "vue";

import App from "@/App.vue";
import "@/assets/main.css";
import { initTheme } from "@/composables/useTheme";
import { router } from "@/router";

// The shell template applies the stored theme pre-paint; re-running here is
// idempotent and covers any entry path that skipped the boot script.
initTheme();

createApp(App).use(router).mount("#capagg-explorer");
