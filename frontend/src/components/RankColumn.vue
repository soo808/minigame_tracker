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
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  min-height: 200px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.hdr {
  padding: 12px 14px;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: #0f172a;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
}
.list {
  padding: 6px 4px 12px;
}
</style>
