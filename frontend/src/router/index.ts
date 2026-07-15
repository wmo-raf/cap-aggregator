import { createRouter, createWebHistory } from "vue-router";

import AuthoritiesView from "@/views/AuthoritiesView.vue";
import MapView from "@/views/MapView.vue";
import NotifyView from "@/views/NotifyView.vue";
import TableView from "@/views/TableView.vue";

// The Django shell serves every path under /explorer/, so history-mode URLs
// survive full reloads and are deep-linkable.
export const routes = [
  { path: "/", redirect: { name: "map" } },
  { path: "/map", name: "map", component: MapView },
  { path: "/table", name: "table", component: TableView },
  { path: "/authorities", name: "authorities", component: AuthoritiesView },
  { path: "/notify", name: "notify", component: NotifyView },
  { path: "/:pathMatch(.*)*", redirect: { name: "map" } },
];

export const router = createRouter({
  history: createWebHistory("/explorer/"),
  routes,
});
