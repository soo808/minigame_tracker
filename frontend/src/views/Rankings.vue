<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { apiUrl } from "../config";
import type { GameEntry } from "../components/GameCard.vue";
import GameModal from "../components/GameModal.vue";
import RankColumn from "../components/RankColumn.vue";

const platform = ref<"wx" | "dy">("wx");
const dates = ref<string[]>([]);
const selectedDate = ref<string | null>(null);
const payload = ref<{
  date: string | null;
  platform: string;
  charts: Record<string, { entries: GameEntry[] }>;
} | null>(null);
const modalAppid = ref<string | null>(null);
const loading = ref(false);
const err = ref("");

const wxCols = [
  { key: "renqi", title: "微信 · 人气榜", chart: "popularity" },
  { key: "changxiao", title: "微信 · 畅销榜", chart: "bestseller" },
  { key: "changwan", title: "微信 · 畅玩榜", chart: "most_played" },
] as const;

const dyCols = [
  { key: "renqi", title: "抖音 · 人气榜", chart: "popularity" },
  { key: "changxiao", title: "抖音 · 畅销榜", chart: "bestseller" },
  { key: "xinyou", title: "抖音 · 新游榜", chart: "fresh_game" },
] as const;

const cols = computed(() => (platform.value === "wx" ? wxCols : dyCols));

function readPlatformFromUrl() {
  const q = new URLSearchParams(window.location.search).get("platform");
  if (q === "dy" || q === "wx") platform.value = q;
}

function writePlatformToUrl() {
  const u = new URL(window.location.href);
  u.searchParams.set("platform", platform.value);
  window.history.replaceState({}, "", u.toString());
}

async function loadDates() {
  err.value = "";
  try {
    const u = new URL(apiUrl("dates"));
    u.searchParams.set("platform", platform.value);
    const res = await fetch(u.href);
    if (!res.ok) throw new Error(`dates HTTP ${res.status}`);
    const data = await res.json();
    dates.value = data.dates || [];
    if (!selectedDate.value && dates.value.length) selectedDate.value = dates.value[0];
  } catch (e) {
    err.value = e instanceof Error ? e.message : String(e);
    dates.value = [];
  }
}

async function loadRankings() {
  loading.value = true;
  err.value = "";
  try {
    const u = new URL(apiUrl("rankings"));
    u.searchParams.set("platform", platform.value);
    if (selectedDate.value) u.searchParams.set("date", selectedDate.value);
    const res = await fetch(u.href);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    payload.value = await res.json();
    if (payload.value?.date) selectedDate.value = payload.value.date;
  } catch (e) {
    err.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

function goToday() {
  if (dates.value.length) selectedDate.value = dates.value[0];
  loadRankings();
}

onMounted(async () => {
  readPlatformFromUrl();
  await loadDates();
  await loadRankings();
});

watch(platform, async () => {
  writePlatformToUrl();
  await loadDates();
  await loadRankings();
});

watch(selectedDate, () => {
  loadRankings();
});
</script>

<template>
  <div class="page">
    <header class="top">
      <h1>小游戏榜单</h1>
      <div class="tabs">
        <button
          type="button"
          :class="{ on: platform === 'wx' }"
          @click="platform = 'wx'"
        >
          微信小游戏
        </button>
        <button
          type="button"
          :class="{ on: platform === 'dy' }"
          @click="platform = 'dy'"
        >
          抖音小游戏
        </button>
      </div>
      <div class="date-row">
        <label>
          日期
          <select v-model="selectedDate">
            <option v-for="d in dates" :key="d" :value="d">{{ d }}</option>
          </select>
        </label>
        <button type="button" class="ghost" @click="goToday">今日</button>
        <span v-if="loading" class="muted">加载中…</span>
        <span v-if="err" class="err">{{ err }}</span>
      </div>
    </header>

    <div v-if="payload && payload.date" class="grid">
      <RankColumn
        v-for="c in cols"
        :key="c.key"
        :title="c.title"
        :entries="payload.charts[c.key]?.entries || []"
        :platform="platform"
        :chart="c.chart"
        :end-date="payload.date"
        @pick="modalAppid = $event"
      />
    </div>
    <p v-else-if="!loading" class="empty">暂无数据。启动后端并完成采集或 POST /api/ingest。</p>

    <GameModal
      :appid="modalAppid"
      :platform="platform"
      @close="modalAppid = null"
    />
  </div>
</template>

<style scoped>
.page {
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px 20px 48px;
}
.top {
  margin-bottom: 20px;
}
h1 {
  margin: 0 0 16px;
  font-size: 1.5rem;
  font-weight: 800;
  letter-spacing: -0.02em;
}
.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.tabs button {
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid #30363d;
  background: #161b22;
  color: #8b949e;
  font-weight: 600;
  cursor: pointer;
}
.tabs button.on {
  border-color: #58a6ff;
  color: #e6edf3;
  background: rgba(88, 166, 255, 0.12);
}
.date-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.date-row label {
  font-size: 13px;
  color: #8b949e;
}
.date-row select {
  margin-left: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid #30363d;
  background: #0d1117;
  color: #e6edf3;
}
.ghost {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid #30363d;
  background: transparent;
  color: #58a6ff;
  cursor: pointer;
  font-weight: 600;
}
.muted {
  font-size: 13px;
  color: #8b949e;
}
.err {
  font-size: 13px;
  color: #f85149;
}
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}
@media (max-width: 1024px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
.empty {
  color: #8b949e;
  font-size: 14px;
}
</style>
