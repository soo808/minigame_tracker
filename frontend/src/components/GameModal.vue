<script setup lang="ts">
import * as echarts from "echarts";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { apiUrl } from "../config";

const props = defineProps<{
  appid: string | null;
  platform: "wx" | "dy";
}>();

const emit = defineEmits<{ close: [] }>();

const root = ref<HTMLDivElement | null>(null);
const chartEl = ref<HTMLDivElement | null>(null);
let ec: echarts.ECharts | null = null;

const title = ref("");
const developer = ref("");
const icon = ref<string | null>(null);
const tags = ref<string[]>([]);
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
    color: ["#58a6ff", "#a371f7", "#f0883e"],
    legend: { textStyle: { color: "#8b949e" }, top: 0 },
    grid: { left: 48, right: 16, top: 36, bottom: 28 },
    tooltip: {
      trigger: "axis",
      textStyle: { fontSize: 12 },
    },
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: { color: "#8b949e", fontSize: 10 },
    },
    yAxis: {
      type: "value",
      inverse: true,
      name: "名次",
      nameTextStyle: { color: "#8b949e", fontSize: 11 },
      axisLabel: { color: "#8b949e" },
      splitLine: { lineStyle: { color: "#21262d" } },
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
        <img v-if="icon" class="big-icon" :src="icon" alt="" />
        <div v-else class="big-icon ph" />
        <div>
          <h2>{{ title }}</h2>
          <p v-if="developer" class="dev">{{ developer }}</p>
          <div v-if="tags.length" class="tags">
            <span v-for="(t, i) in tags" :key="i" class="tag">{{ t }}</span>
          </div>
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
  background: rgba(1, 4, 9, 0.72);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 24px;
}
.panel {
  position: relative;
  width: min(920px, 100%);
  max-height: 90vh;
  overflow: auto;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 14px;
  padding: 24px 24px 20px;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.45);
}
.close {
  position: absolute;
  top: 12px;
  right: 14px;
  border: none;
  background: transparent;
  color: #8b949e;
  font-size: 26px;
  line-height: 1;
  cursor: pointer;
}
.close:hover {
  color: #e6edf3;
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
}
.big-icon.ph {
  background: #21262d;
}
h2 {
  margin: 0 0 6px;
  font-size: 1.35rem;
  font-weight: 700;
}
.dev {
  margin: 0;
  font-size: 13px;
  color: #8b949e;
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
  background: #21262d;
  color: #8b949e;
}
.section-title {
  margin: 20px 0 8px;
  font-size: 13px;
  color: #8b949e;
}
.chart {
  width: 100%;
  height: 320px;
}
</style>
