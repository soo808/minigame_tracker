<script setup lang="ts">
import GameCard, { type GameEntry } from "./GameCard.vue";

defineProps<{
  title: string;
  entries: GameEntry[];
  platform: "wx" | "dy";
  chart: string;
  endDate?: string | null;
}>();

const emit = defineEmits<{ pick: [appid: string] }>();
</script>

<template>
  <section class="col">
    <header class="hdr">{{ title }}</header>
    <div class="list">
      <GameCard
        v-for="e in entries"
        :key="e.appid + String(e.rank) + String(e.is_dropped)"
        :entry="e"
        :platform="platform"
        :chart="chart"
        :end-date="endDate"
        @click="emit('pick', e.appid)"
      />
    </div>
  </section>
</template>

<style scoped>
.col {
  background: rgba(22, 27, 34, 0.65);
  border: 1px solid #30363d;
  border-radius: 12px;
  min-height: 200px;
  display: flex;
  flex-direction: column;
}
.hdr {
  padding: 12px 14px;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: #e6edf3;
  border-bottom: 1px solid #30363d;
  background: rgba(13, 17, 23, 0.5);
}
.list {
  padding: 6px 4px 12px;
  max-height: min(72vh, 900px);
  overflow-y: auto;
}
</style>
