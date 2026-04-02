import { createRouter, createWebHistory } from "vue-router";
import Rankings from "./views/Rankings.vue";

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: "/", redirect: "/rankings" },
    { path: "/rankings", name: "rankings", component: Rankings },
    {
      path: "/genre",
      name: "genre",
      component: () => import("./views/Genre.vue"),
    },
    {
      path: "/insights",
      name: "insights",
      component: () => import("./views/Insights.vue"),
    },
    {
      path: "/qa",
      name: "qa",
      component: () => import("./views/QA.vue"),
    },
    {
      path: "/adx",
      name: "adx",
      component: () => import("./views/AdxCreatives.vue"),
    },
  ],
});
