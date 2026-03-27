<script setup lang="ts">
import * as echarts from "echarts";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { apiUrl } from "../config";

const platform = ref<"wx" | "dy" | "yyb">("wx");
const chart = ref("popularity");
const days = ref(30);
const snapshotDate = ref(new Date().toISOString().slice(0, 10));

const platforms = [
  { key: "wx" as const, label: "微信" },
  { key: "dy" as const, label: "抖音" },
  { key: "yyb" as const, label: "应用宝" },
];

const chartMap: Record<
  string,
  { key: string; label: string }[]
> = {
  wx: [
    { key: "popularity", label: "人气榜" },
    { key: "bestseller", label: "畅销榜" },
    { key: "most_played", label: "畅玩榜" },
  ],
  dy: [
    { key: "popularity", label: "热门榜" },
    { key: "bestseller", label: "畅销榜" },
    { key: "fresh_game", label: "新游榜" },
  ],
  yyb: [
    { key: "popular", label: "热门榜" },
    { key: "bestseller", label: "畅销榜" },
    { key: "new_game", label: "新游榜" },
  ],
};

const currentCharts = computed(() => chartMap[platform.value] || []);

const pieRef = ref<HTMLDivElement | null>(null);
const bubbleRef = ref<HTMLDivElement | null>(null);
const barRef = ref<HTMLDivElement | null>(null);
const areaRef = ref<HTMLDivElement | null>(null);

let pieChart: echarts.ECharts | null = null;
let bubbleChart: echarts.ECharts | null = null;
let barChart: echarts.ECharts | null = null;
let areaChart: echarts.ECharts | null = null;

type DistItem = { genre: string; count: number; avg_rank: number };
type TagItem = { tag: string; count: number };

function renderPie(dist: DistItem[]) {
  if (!pieChart) return;
  pieChart.setOption({
    title: { text: "大类分布", left: "center", top: 8, textStyle: { fontSize: 13 } },
    tooltip: { trigger: "item", formatter: "{b}: {c}款 ({d}%)" },
    series: [
      {
        type: "pie",
        radius: ["40%", "65%"],
        data: dist.map((d) => ({ name: d.genre, value: d.count })),
        label: { formatter: "{b}\n{d}%" },
      },
    ],
  });
}

function renderBubble(dist: DistItem[]) {
  if (!bubbleChart) return;
  const genres = dist.map((d) => d.genre);
  bubbleChart.setOption({
    title: {
      text: "大类 × 平均名次 × 数量",
      left: "center",
      top: 8,
      textStyle: { fontSize: 13 },
    },
    tooltip: {
      formatter: (p: unknown) => {
        const x = p as { data: [number, number, number, string] };
        const [, avgR, cnt, name] = x.data;
        return `${name}<br/>平均名次: ${avgR}<br/>游戏数: ${cnt}`;
      },
    },
    xAxis: { type: "category", data: genres, axisLabel: { rotate: 30 } },
    yAxis: { type: "value", name: "平均名次", inverse: true },
    series: [
      {
        type: "scatter",
        data: dist.map((d, i) => [i, d.avg_rank, d.count, d.genre] as const),
        symbolSize: (val: unknown) => {
          const v = val as [number, number, number];
          const cnt = v[2];
          return Math.max(12, Math.sqrt(cnt) * 8);
        },
      },
    ],
  });
}

function renderBar(tags: TagItem[]) {
  if (!barChart) return;
  const rev = [...tags].reverse();
  barChart.setOption({
    title: { text: "标签词频 TOP20", left: "center", top: 8, textStyle: { fontSize: 13 } },
    tooltip: { trigger: "axis" },
    grid: { left: 100, right: 24, top: 40, bottom: 24 },
    xAxis: { type: "value" },
    yAxis: { type: "category", data: rev.map((t) => t.tag) },
    series: [{ type: "bar", data: rev.map((t) => t.count) }],
  });
}

function renderArea(
  trend: { dates: string[]; series: Record<string, number[]> },
  n: number,
) {
  if (!areaChart) return;
  const genres = Object.keys(trend.series);
  areaChart.setOption({
    title: {
      text: `近 ${n} 天大类趋势`,
      left: "center",
      top: 8,
      textStyle: { fontSize: 13 },
    },
    tooltip: { trigger: "axis" },
    legend: { top: 32, type: "scroll" },
    grid: { left: 48, right: 24, top: 72, bottom: 28 },
    xAxis: { type: "category", data: trend.dates },
    yAxis: { type: "value", name: "游戏数" },
    series: genres.map((g) => ({
      name: g,
      type: "line",
      stack: "total",
      areaStyle: {},
      data: trend.series[g],
    })),
  });
}

async function loadSnapshot() {
  const u = new URL(apiUrl("genre/snapshot"));
  u.searchParams.set("date", snapshotDate.value);
  u.searchParams.set("platform", platform.value);
  u.searchParams.set("chart", chart.value);
  const res = await fetch(u.href);
  if (!res.ok) return;
  const data = await res.json();
  const dist = (data.genre_distribution || []) as DistItem[];
  const tags = (data.tag_frequency || []) as TagItem[];
  renderPie(dist);
  renderBubble(dist);
  renderBar(tags);
}

async function loadTrend() {
  const u = new URL(apiUrl("genre/trend"));
  u.searchParams.set("platform", platform.value);
  u.searchParams.set("chart", chart.value);
  u.searchParams.set("days", String(days.value));
  const res = await fetch(u.href);
  if (!res.ok) return;
  const data = await res.json();
  renderArea(
    { dates: data.dates || [], series: data.series || {} },
    days.value,
  );
}

async function refresh() {
  await Promise.all([loadSnapshot(), loadTrend()]);
}

function onResize() {
  pieChart?.resize();
  bubbleChart?.resize();
  barChart?.resize();
  areaChart?.resize();
}

onMounted(() => {
  if (pieRef.value) pieChart = echarts.init(pieRef.value);
  if (bubbleRef.value) bubbleChart = echarts.init(bubbleRef.value);
  if (barRef.value) barChart = echarts.init(barRef.value);
  if (areaRef.value) areaChart = echarts.init(areaRef.value);
  window.addEventListener("resize", onResize);
  refresh();
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize);
  pieChart?.dispose();
  bubbleChart?.dispose();
  barChart?.dispose();
  areaChart?.dispose();
  pieChart = bubbleChart = barChart = areaChart = null;
});

watch([platform, chart, snapshotDate], () => {
  const list = currentCharts.value.map((c) => c.key);
  if (!list.includes(chart.value) && list.length) chart.value = list[0];
  refresh();
});

watch(days, () => loadTrend());
</script>

<template>
  <div class="genre-page">
    <div class="genre-controls">
      <div class="control-group">
        <span class="label">平台</span>
        <button
          v-for="p in platforms"
          :key="p.key"
          type="button"
          :class="['ctrl-btn', { active: platform === p.key }]"
          @click="platform = p.key"
        >
          {{ p.label }}
        </button>
      </div>
      <div class="control-group">
        <span class="label">榜单</span>
        <button
          v-for="c in currentCharts"
          :key="c.key"
          type="button"
          :class="['ctrl-btn', { active: chart === c.key }]"
          @click="chart = c.key"
        >
          {{ c.label }}
        </button>
      </div>
      <div class="control-group">
        <span class="label">快照日期</span>
        <input v-model="snapshotDate" type="date" class="date-input" />
      </div>
      <div class="control-group">
        <span class="label">趋势天数</span>
        <button
          v-for="d in [7, 30, 90]"
          :key="d"
          type="button"
          :class="['ctrl-btn', { active: days === d }]"
          @click="days = d"
        >
          {{ d }} 天
        </button>
      </div>
    </div>

    <div class="charts-grid">
      <div ref="pieRef" class="chart-card" />
      <div ref="bubbleRef" class="chart-card" />
      <div ref="barRef" class="chart-card full-width" />
      <div ref="areaRef" class="chart-card full-width area-h" />
    </div>
  </div>
</template>

<style scoped>
.genre-page {
  padding: 16px 20px 48px;
  max-width: 1280px;
  margin: 0 auto;
}
.genre-controls {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  align-items: center;
}
.control-group {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.label {
  font-size: 13px;
  color: #64748b;
  font-weight: 600;
}
.ctrl-btn {
  padding: 6px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
  color: #475569;
}
.ctrl-btn.active {
  border-color: #2563eb;
  color: #1d4ed8;
  background: rgba(37, 99, 235, 0.08);
}
.date-input {
  padding: 6px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 13px;
}
.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.chart-card {
  height: 320px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #fff;
}
.chart-card.full-width {
  grid-column: 1 / -1;
}
.area-h {
  height: 300px;
}
@media (max-width: 900px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }
}
</style>
