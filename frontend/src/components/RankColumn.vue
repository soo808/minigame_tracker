<script setup lang="ts">
import GameCard, { type GameEntry } from "./GameCard.vue";

/** 第 10 / 30 / 50 名之后画虚线，区分 1–10、11–30、31–50、51–100 区段 */
const zoneBreakRanks = new Set([10, 30, 50]);

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
      <template v-for="e in entries" :key="e.appid + String(e.rank) + String(e.is_dropped)">
        <GameCard
          :entry="e"
          :platform="platform"
          :chart="chart"
          :end-date="endDate"
          @click="emit('pick', e.appid)"
        />
        <div
          v-if="e.rank != null && zoneBreakRanks.has(e.rank)"
          class="zone-break"
          aria-hidden="true"
        />
      </template>
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

.zone-break {
  margin: 6px 10px 8px;
  border: none;
  border-top: 1px dashed #94a3b8;
  opacity: 0.85;
}
</style>
