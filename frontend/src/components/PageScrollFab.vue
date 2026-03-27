<script setup lang="ts">
function scrollToTop() {
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function scrollToBottom() {
  window.scrollTo({
    top: document.documentElement.scrollHeight,
    behavior: "smooth",
  });
}
</script>

<template>
  <div class="fab-wrap">
    <button
      type="button"
      class="fab-btn"
      aria-label="回到顶部"
      @click="scrollToTop"
    >
      <svg
        class="fab-icon"
        viewBox="0 0 48 48"
        width="48"
        height="48"
        aria-hidden="true"
      >
        <!-- 正三角尖端朝上，横线在尖端（顶部） -->
        <path
          class="fab-tri"
          d="M24 14 L38 34 L10 34 Z"
          fill="#93c5fd"
          stroke="#3b82f6"
          stroke-width="2"
          stroke-linejoin="round"
        />
        <line
          class="fab-bar"
          x1="16"
          y1="14"
          x2="32"
          y2="14"
          stroke="#ffffff"
          stroke-width="3"
          stroke-linecap="round"
        />
      </svg>
    </button>
    <button
      type="button"
      class="fab-btn"
      aria-label="滚动到底部"
      @click="scrollToBottom"
    >
      <svg
        class="fab-icon"
        viewBox="0 0 48 48"
        width="48"
        height="48"
        aria-hidden="true"
      >
        <!-- 倒三角尖端朝下，横线在尖端（底部） -->
        <path
          class="fab-tri"
          d="M24 34 L10 14 L38 14 Z"
          fill="#93c5fd"
          stroke="#3b82f6"
          stroke-width="2"
          stroke-linejoin="round"
        />
        <line
          class="fab-bar"
          x1="16"
          y1="34"
          x2="32"
          y2="34"
          stroke="#ffffff"
          stroke-width="3"
          stroke-linecap="round"
        />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.fab-wrap {
  position: fixed;
  right: 20px;
  bottom: calc(24px + env(safe-area-inset-bottom, 0px));
  z-index: 10050;
  display: flex;
  flex-direction: column;
  gap: 10px;
  pointer-events: none;
}
.fab-btn {
  pointer-events: auto;
  width: 52px;
  height: 52px;
  padding: 0;
  border: none;
  border-radius: 12px;
  background: rgba(37, 99, 235, 0.1);
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.12);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition:
    background 0.15s,
    box-shadow 0.15s,
    transform 0.12s;
}
.fab-btn:hover {
  background: rgba(37, 99, 235, 0.18);
  box-shadow: 0 6px 18px rgba(37, 99, 235, 0.22);
}
.fab-btn:active {
  transform: scale(0.96);
}
.fab-btn:focus {
  outline: none;
}
.fab-btn:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 3px;
}
.fab-icon {
  display: block;
}
</style>
