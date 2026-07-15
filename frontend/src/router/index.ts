import { createRouter, createWebHistory } from "vue-router";

// The Django shell serves every path under /explorer/, so history-mode URLs
// survive full reloads and are deep-linkable. Views are lazy so heavy
// dependencies (MapLibre) chunk separately from the shell.
export const routes = [
  { path: "/", redirect: { name: "map" } },
  { path: "/map", name: "map", component: () => import("@/views/MapView.vue") },
  { path: "/table", name: "table", component: () => import("@/views/TableView.vue") },
  { path: "/authorities", name: "authorities", component: () => import("@/views/AuthoritiesView.vue") },
  { path: "/notify", name: "notify", component: () => import("@/views/NotifyView.vue") },
  { path: "/:pathMatch(.*)*", redirect: { name: "map" } },
];

export const router = createRouter({
  history: createWebHistory("/explorer/"),
  routes,
});
