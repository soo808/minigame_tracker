<script setup lang="ts">
import { computed } from "vue";
import GameCard, { type GameEntry } from "./GameCard.vue";

export type ChartCol = { key: string; title: string; chart: string };

const props = defineProps<{
  cols: readonly ChartCol[];
  charts: Record<string, { entries: GameEntry[] }>;
  platform: "wx" | "dy";
  endDate: string | null;
}>();

const emit = defineEmits<{ pick: [appid: string] }>();

const RANKS = Array.from({ length: 100 }, (_, i) => i + 1);
const ZONE_AFTER = new Set([10, 30, 50, 100]);

const rankMaps = computed(() => {
  const out: Record<string, Map<number, GameEntry>> = {};
  for (const c of props.cols) {
    const entries = props.charts[c.key]?.entries ?? [];
    const m = new Map<number, GameEntry>();
    for (const e of entries) {
      if (e.rank != null && !e.is_dropped) m.set(e.rank, e);
    }
    out[c.key] = m;
  }
  return out;
});

function getEntry(chartKey: string, rank: number): GameEntry | undefined {
  return rankMaps.value[chartKey]?.get(rank);
}
</script>

<template>
  <div class="sync-board">
    <div class="hdr-row">
      <header
        v-for="c in cols"
        :key="c.key"
        class="hdr-cell"
      >
        {{ c.title }}
      </header>
    </div>

    <template v-for="r in RANKS" :key="r">
      <div class="rank-row">
        <div
          v-for="c in cols"
          :key="c.key"
          class="rank-cell"
        >
          <GameCard
            v-if="getEntry(c.key, r)"
            :entry="getEntry(c.key, r)!"
            :platform="platform"
            :chart="c.chart"
            :end-date="endDate"
            fill-row
            @click="emit('pick', getEntry(c.key, r)!.appid)"
          />
          <div v-else class="cell-empty" />
        </div>
      </div>
      <div
        v-if="ZONE_AFTER.has(r)"
        class="zone-break-full"
        aria-hidden="true"
      />
    </template>
  </div>
</template>

<style scoped>
.sync-board {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.hdr-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr);
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}

.hdr-cell {
  margin: 0;
  padding: 12px 14px;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: #0f172a;
  border-right: 1px solid #e2e8f0;
}

.hdr-cell:last-child {
  border-right: none;
}

.rank-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr);
  align-items: stretch;
  border-bottom: 1px solid #f1f5f9;
}

.rank-cell {
  min-width: 0;
  min-height: 0;
  padding: 4px 6px;
  display: flex;
  align-items: stretch;
  border-right: 1px solid #f1f5f9;
}

.rank-cell:last-child {
  border-right: none;
}

.cell-empty {
  flex: 1;
  width: 100%;
  min-height: 56px;
  margin: 2px 0;
  border-radius: 10px;
  background: #fafafa;
  border: 1px dashed #e2e8f0;
  box-sizing: border-box;
}

.zone-break-full {
  width: 100%;
  border: none;
  border-top: 1px dashed #94a3b8;
  margin: 0;
  opacity: 0.9;
}

@media (max-width: 1024px) {
  .hdr-row,
  .rank-row {
    grid-template-columns: 1fr;
  }

  .hdr-cell {
    border-right: none;
    border-bottom: 1px solid #e2e8f0;
  }

  .hdr-cell:last-child {
    border-bottom: none;
  }

  .rank-cell {
    border-right: none;
    border-bottom: 1px solid #f1f5f9;
  }

  .rank-cell:last-child {
    border-bottom: none;
  }
}
</style>
