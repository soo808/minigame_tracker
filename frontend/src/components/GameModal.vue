<script setup lang="ts">
import * as echarts from "echarts";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { apiUrl } from "../config";
import { resolveIconSrc } from "../iconSrc";

const props = defineProps<{
  appid: string | null;
  platform: "wx" | "dy" | "yyb";
}>();

const emit = defineEmits<{ close: [] }>();

const root = ref<HTMLDivElement | null>(null);
const chartEl = ref<HTMLDivElement | null>(null);
let ec: echarts.ECharts | null = null;

const title = ref("");
const developer = ref("");
const icon = ref<string | null>(null);
const tags = ref<string[]>([]);
const description = ref("");
const genreMajor = ref("");
const genreMinor = ref("");
const chartPayload = ref<Record<string, { label: string; series: { date: string; rank: number }[] }>>({});

async function load() {
  if (!props.appid) return;
  const u = new URL(apiUrl(`game/${props.appid}`));
  u.searchParams.set("platform", props.platform);
  u.searchParams.set("days", "30");
  const res = await fetch(u.href);
  if (!res.ok) return;
  const data = await res.json();
  title.value = data.name;
  developer.value = data.developer || "";
  icon.value = data.icon_url;
  tags.value = Array.isArray(data.tags) ? data.tags : [];
  description.value = data.description || "";
  genreMajor.value = data.genre_major || "";
  genreMinor.value = data.genre_minor || "";
  chartPayload.value = data.charts || {};
  renderChart();
}

function renderChart() {
  if (!chartEl.value) return;
  const charts = chartPayload.value;
  const keys = Object.keys(charts);
  if (!keys.length) return;
  if (!ec) ec = echarts.init(chartEl.value);
  const dateSet = new Set<string>();
  for (const k of keys) {
    for (const p of charts[k].series || []) dateSet.add(p.date);
  }
  const dates = [...dateSet].sort();
  const series = keys.map((k) => {
    const s = charts[k].series || [];
    const byDate = new Map(s.map((p) => [p.date, p.rank]));
    return {
      name: charts[k].label || k,
      type: "line",
      smooth: true,
      showSymbol: false,
      connectNulls: true,
      data: dates.map((d) => (byDate.has(d) ? byDate.get(d)! : null)),
    };
  });
  ec.setOption({
    color: ["#2563eb", "#7c3aed", "#ea580c"],
    legend: { textStyle: { color: "#475569" }, top: 0 },
    grid: { left: 48, right: 16, top: 36, bottom: 28 },
    tooltip: {
      trigger: "axis",
      textStyle: { fontSize: 12, color: "#0f172a" },
      backgroundColor: "#fff",
      borderColor: "#e2e8f0",
    },
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: { color: "#64748b", fontSize: 10 },
    },
    yAxis: {
      type: "value",
      inverse: true,
      name: "名次",
      nameTextStyle: { color: "#64748b", fontSize: 11 },
      axisLabel: { color: "#64748b" },
      splitLine: { lineStyle: { color: "#e2e8f0" } },
    },
    series,
  });
}

function onOverlayClick(e: MouseEvent) {
  if (e.target === root.value) emit("close");
}

onMounted(load);
watch(
  () => [props.appid, props.platform],
  () => load(),
);

onBeforeUnmount(() => {
  ec?.dispose();
  ec = null;
});
</script>

<template>
  <div v-if="appid" ref="root" class="overlay" @click="onOverlayClick">
    <div class="panel" @click.stop>
      <button type="button" class="close" aria-label="关闭" @click="emit('close')">
        ×
      </button>
      <div class="head">
        <img v-if="icon" class="big-icon" :src="resolveIconSrc(icon)" alt="" />
        <div v-else class="big-icon ph" />
        <div>
          <h2>{{ title }}</h2>
          <p v-if="developer" class="dev">{{ developer }}</p>
          <div v-if="tags.length" class="tags">
            <span v-for="(t, i) in tags" :key="i" class="tag">{{ t }}</span>
          </div>
          <p v-if="genreMajor || genreMinor" class="genre-line">
            <span v-if="genreMajor">大类：{{ genreMajor }}</span>
            <span v-if="genreMinor"> · 小类：{{ genreMinor }}</span>
          </p>
          <p v-if="description" class="desc">{{ description }}</p>
        </div>
      </div>
      <p class="section-title">近 30 日排名走势</p>
      <div ref="chartEl" class="chart" />
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 24px;
  backdrop-filter: blur(4px);
}
.panel {
  position: relative;
  width: min(920px, 100%);
  max-height: 90vh;
  overflow: auto;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 24px 24px 20px;
  box-shadow: 0 25px 50px -12px rgba(15, 23, 42, 0.2);
}
.close {
  position: absolute;
  top: 12px;
  right: 14px;
  border: none;
  background: transparent;
  color: #64748b;
  font-size: 26px;
  line-height: 1;
  cursor: pointer;
}
.close:hover {
  color: #0f172a;
}
.head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 8px;
}
.big-icon {
  width: 72px;
  height: 72px;
  border-radius: 16px;
  object-fit: cover;
  border: 1px solid #e2e8f0;
}
.big-icon.ph {
  background: #f1f5f9;
}
h2 {
  margin: 0 0 6px;
  font-size: 1.35rem;
  font-weight: 700;
  color: #0f172a;
}
.dev {
  margin: 0;
  font-size: 13px;
  color: #64748b;
}
.tags {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 6px;
  background: #f1f5f9;
  color: #475569;
  border: 1px solid #e2e8f0;
}
.genre-line {
  margin: 8px 0 0;
  font-size: 12px;
  color: #475569;
}
.desc {
  margin: 8px 0 0;
  font-size: 13px;
  color: #334155;
  line-height: 1.5;
}
.section-title {
  margin: 20px 0 8px;
  font-size: 13px;
  color: #64748b;
}
.chart {
  width: 100%;
  height: 320px;
}
</style>
