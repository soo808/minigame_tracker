<script setup lang="ts">
import * as echarts from "echarts";
import { onMounted, onBeforeUnmount, ref, watch } from "vue";
import { apiUrl } from "../config";

const platform = ref<"wx" | "dy" | "yyb">("wx");
const selectedDate = ref<string | null>(null);
const dates = ref<string[]>([]);
const loading = ref(false);
const err = ref("");

interface GameEntry {
  appid: string;
  name: string;
  icon_url: string | null;
  genre_major: string | null;
  rank?: number;
  delta?: number;
  days_on_chart?: number;
}

interface InsightsPayload {
  date: string | null;
  platform: string;
  new_entries: GameEntry[];
  dropped: GameEntry[];
  genre_distribution: { genre: string; count: number }[];
  rank_movers: (GameEntry & {
    today_rank: number;
    prev_rank: number;
    delta: number;
  })[];
  tag_heat: { tag: string; count: number }[];
}

const payload = ref<InsightsPayload | null>(null);

const genreChartEl = ref<HTMLDivElement | null>(null);
const tagChartEl = ref<HTMLDivElement | null>(null);
let genreChart: echarts.ECharts | null = null;
let tagChart: echarts.ECharts | null = null;

async function loadDates() {
  const u = new URL(apiUrl("dates"));
  u.searchParams.set("platform", platform.value);
  const res = await fetch(u.href);
  if (!res.ok) return;
  const data = await res.json();
  dates.value = data.dates || [];
  if (!selectedDate.value && dates.value.length) selectedDate.value = dates.value[0];
}

async function loadInsights() {
  loading.value = true;
  err.value = "";
  try {
    const u = new URL(apiUrl("insights"));
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

function renderGenreChart() {
  if (!genreChartEl.value || !payload.value?.genre_distribution.length) return;
  if (!genreChart) genreChart = echarts.init(genreChartEl.value);
  const data = payload.value.genre_distribution.map((d) => ({
    name: d.genre,
    value: d.count,
  }));
  genreChart.setOption({
    tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
    legend: {
      orient: "vertical",
      right: 8,
      top: "center",
      textStyle: { fontSize: 13 },
    },
    series: [
      {
        type: "pie",
        radius: ["40%", "70%"],
        center: ["40%", "50%"],
        data,
        label: { show: false },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: "rgba(0,0,0,0.2)",
          },
        },
      },
    ],
    color: [
      "#2563eb",
      "#7c3aed",
      "#ea580c",
      "#059669",
      "#d97706",
      "#dc2626",
      "#6b7280",
    ],
  });
}

function renderTagChart() {
  if (!tagChartEl.value || !payload.value?.tag_heat.length) return;
  if (!tagChart) tagChart = echarts.init(tagChartEl.value);
  const tags = [...payload.value.tag_heat].reverse();
  tagChart.setOption({
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: 80, right: 16, top: 8, bottom: 8 },
    xAxis: {
      type: "value",
      axisLabel: { color: "#64748b" },
      splitLine: { lineStyle: { color: "#e2e8f0" } },
    },
    yAxis: {
      type: "category",
      data: tags.map((t) => t.tag),
      axisLabel: { color: "#475569", fontSize: 12 },
    },
    series: [
      {
        type: "bar",
        data: tags.map((t) => t.count),
        itemStyle: { color: "#2563eb", borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: "right", color: "#475569", fontSize: 11 },
      },
    ],
  });
}

watch(payload, () => {
  setTimeout(() => {
    renderGenreChart();
    renderTagChart();
  }, 50);
});

watch(platform, async () => {
  selectedDate.value = null;
  await loadDates();
  await loadInsights();
});

watch(selectedDate, () => loadInsights());

function onResize() {
  genreChart?.resize();
  tagChart?.resize();
}

onMounted(async () => {
  await loadDates();
  await loadInsights();
  window.addEventListener("resize", onResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize);
  genreChart?.dispose();
  tagChart?.dispose();
});
</script>

<template>
  <div class="page">
    <header class="top">
      <h1>洞察看板</h1>
      <div class="tabs">
        <button :class="{ on: platform === 'wx' }" type="button" @click="platform = 'wx'">
          微信小游戏
        </button>
        <button :class="{ on: platform === 'dy' }" type="button" @click="platform = 'dy'">
          抖音小游戏
        </button>
        <button :class="{ on: platform === 'yyb' }" type="button" @click="platform = 'yyb'">
          腾讯应用宝
        </button>
      </div>
      <div class="date-row">
        <label>
          日期
          <select v-model="selectedDate">
            <option v-for="d in dates" :key="d" :value="d">{{ d }}</option>
          </select>
        </label>
        <span v-if="loading" class="muted">加载中…</span>
        <span v-if="err" class="err">{{ err }}</span>
      </div>
    </header>

    <template v-if="payload && payload.date">
      <div class="row-3">
        <section class="card">
          <h2>新上榜 <span class="badge">{{ payload.new_entries.length }}</span></h2>
          <div class="entry-list">
            <div v-for="e in payload.new_entries" :key="e.appid" class="entry-row">
              <img v-if="e.icon_url" :src="e.icon_url" class="icon" alt="" />
              <div v-else class="icon ph" />
              <div class="entry-info">
                <p class="entry-name">{{ e.name }}</p>
                <p class="entry-meta">第 {{ e.rank }} 名 · {{ e.genre_major || "未分类" }}</p>
              </div>
            </div>
            <p v-if="!payload.new_entries.length" class="empty">今日无新上榜</p>
          </div>
        </section>

        <section class="card">
          <h2>跌出榜 <span class="badge drop">{{ payload.dropped.length }}</span></h2>
          <div class="entry-list">
            <div v-for="e in payload.dropped" :key="e.appid" class="entry-row">
              <img v-if="e.icon_url" :src="e.icon_url" class="icon" alt="" />
              <div v-else class="icon ph" />
              <div class="entry-info">
                <p class="entry-name">{{ e.name }}</p>
                <p class="entry-meta">
                  在榜 {{ e.days_on_chart }} 天 · {{ e.genre_major || "未分类" }}
                </p>
              </div>
            </div>
            <p v-if="!payload.dropped.length" class="empty">今日无跌出</p>
          </div>
        </section>

        <section class="card">
          <h2>大类分布</h2>
          <div ref="genreChartEl" class="pie-chart" />
          <p v-if="!payload.genre_distribution.length" class="empty">
            暂无分类数据（需先运行分类标注）
          </p>
        </section>
      </div>

      <div class="row-2">
        <section class="card">
          <h2>排名变动 TOP10</h2>
          <div class="mover-grid">
            <div v-for="m in payload.rank_movers" :key="m.appid" class="mover-card">
              <img v-if="m.icon_url" :src="m.icon_url" class="icon-sm" alt="" />
              <div v-else class="icon-sm ph" />
              <div class="mover-info">
                <p class="mover-name">{{ m.name }}</p>
                <p class="mover-rank">{{ m.prev_rank }} → {{ m.today_rank }}</p>
              </div>
              <span class="delta">+{{ m.delta }}</span>
            </div>
          </div>
          <p v-if="!payload.rank_movers.length" class="empty">暂无排名变动数据</p>
        </section>

        <section class="card">
          <h2>标签热度 TOP10</h2>
          <div ref="tagChartEl" class="bar-chart" />
          <p v-if="!payload.tag_heat.length" class="empty">暂无标签数据</p>
        </section>
      </div>
    </template>
    <p v-else-if="!loading" class="empty-page">暂无数据。请先完成榜单采集。</p>
  </div>
</template>

<style scoped>
.page {
  max-width: 1440px;
  margin: 0 auto;
  padding: 24px 24px 64px;
}
.top {
  margin-bottom: 24px;
}
h1 {
  margin: 0 0 16px;
  font-size: 1.6rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: #0f172a;
}
.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.tabs button {
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #64748b;
  font-weight: 600;
  cursor: pointer;
}
.tabs button.on {
  border-color: #2563eb;
  color: #1d4ed8;
  background: rgba(37, 99, 235, 0.08);
}
.date-row {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: #475569;
  font-weight: 500;
}
.date-row select {
  margin-left: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #0f172a;
}
.muted {
  color: #94a3b8;
}
.err {
  color: #dc2626;
}

.row-3 {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}
.row-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 20px;
  min-height: 280px;
}
.card h2 {
  margin: 0 0 14px;
  font-size: 1rem;
  font-weight: 700;
  color: #0f172a;
  display: flex;
  align-items: center;
  gap: 8px;
}
.badge {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 10px;
  background: #dbeafe;
  color: #1d4ed8;
  font-weight: 700;
}
.badge.drop {
  background: #fee2e2;
  color: #dc2626;
}
.entry-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
}
.entry-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  object-fit: cover;
  border: 1px solid #e2e8f0;
  flex-shrink: 0;
}
.icon.ph {
  background: #f1f5f9;
}
.entry-info {
  min-width: 0;
}
.entry-name {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.entry-meta {
  margin: 2px 0 0;
  font-size: 11px;
  color: #64748b;
}
.pie-chart {
  width: 100%;
  height: 260px;
}
.mover-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.mover-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}
.icon-sm {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  object-fit: cover;
  flex-shrink: 0;
}
.icon-sm.ph {
  background: #e2e8f0;
}
.mover-info {
  min-width: 0;
  flex: 1;
}
.mover-name {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: #0f172a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mover-rank {
  margin: 2px 0 0;
  font-size: 10px;
  color: #64748b;
}
.delta {
  font-size: 13px;
  font-weight: 700;
  color: #059669;
  flex-shrink: 0;
}
.bar-chart {
  width: 100%;
  height: 280px;
}
.empty {
  font-size: 13px;
  color: #94a3b8;
  margin: 8px 0 0;
}
.empty-page {
  color: #64748b;
  font-size: 14px;
  padding: 40px 0;
}

@media (max-width: 1200px) {
  .row-3 {
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 768px) {
  .row-3,
  .row-2 {
    grid-template-columns: 1fr;
  }
  .mover-grid {
    grid-template-columns: 1fr;
  }
}
</style>
