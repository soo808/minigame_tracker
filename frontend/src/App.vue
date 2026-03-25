<script setup lang="ts">
import Rankings from "./views/Rankings.vue";
</script>

<template>
  <Rankings />
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
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  background: linear-gradient(160deg, #0f1419 0%, #1a2332 45%, #0d1117 100%);
  color: #e6edf3;
}
#app {
  min-height: 100vh;
}
</style>
