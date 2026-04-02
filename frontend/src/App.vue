<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";
</script>

<template>
  <div class="app-root">
    <nav class="top-nav" aria-label="主导航">
      <RouterLink to="/rankings" active-class="active">榜单</RouterLink>
      <RouterLink to="/genre" active-class="active">玩法洞察</RouterLink>
      <RouterLink to="/insights" active-class="active">大屏洞察</RouterLink>
      <RouterLink to="/qa" active-class="active">AI 问答</RouterLink>
      <RouterLink to="/adx" active-class="active">ADX 素材</RouterLink>
    </nav>
    <RouterView />
  </div>
</template>

<style>
*,
*::before,
*::after {
  box-sizing: border-box;
}
html,
body {
  margin: 0;
  min-height: 100%;
  font-family: "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
  background: #ffffff;
  color: #0f172a;
}
#app {
  min-height: 100vh;
}
.app-root {
  min-height: 100vh;
}
.top-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  padding: 12px 20px;
  border-bottom: 1px solid #e2e8f0;
  background: #fff;
  max-width: 1280px;
  margin: 0 auto;
}
.top-nav a {
  text-decoration: none;
  color: #64748b;
  font-size: 14px;
  font-weight: 600;
}
.top-nav a:hover {
  color: #2563eb;
}
.top-nav a.active {
  color: #1d4ed8;
}
</style>
