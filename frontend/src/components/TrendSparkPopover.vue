<script setup lang="ts">
import * as echarts from "echarts";
import { onBeforeUnmount, ref, watch } from "vue";
import { apiUrl } from "../config";

const props = defineProps<{
  appid: string;
  platform: "wx" | "dy" | "yyb";
  dbChart: string;
  endDate?: string | null;
  /** ▲1 / ▼2 or em dash */
  triggerLabel: string;
  triggerClass: string;
}>();

const show = ref(false);
const pos = ref({ left: 0, top: 0 });
let hideTimer: ReturnType<typeof setTimeout> | null = null;
const chartEl = ref<HTMLDivElement | null>(null);
let inst: echarts.ECharts | null = null;
let loadedKey = "";

function clearHide() {
  if (hideTimer != null) {
    clearTimeout(hideTimer);
    hideTimer = null;
  }
}

function disposeChart() {
  inst?.dispose();
  inst = null;
}

function scheduleHide() {
  hideTimer = setTimeout(() => {
    show.value = false;
    disposeChart();
    loadedKey = "";
  }, 150);
}

function onTriggerEnter(ev: MouseEvent) {
  clearHide();
  const el = ev.currentTarget as HTMLElement;
  const r = el.getBoundingClientRect();
  const w = 236;
  const h = 132;
  let left = r.right + 8;
  let top = r.top + r.height / 2 - h / 2;
  if (left + w > window.innerWidth - 8) {
    left = r.left - w - 8;
  }
  if (top < 8) top = 8;
  if (top + h > window.innerHeight - 8) top = window.innerHeight - h - 8;
  pos.value = { left, top };
  show.value = true;
  void loadChart();
}

function onTriggerLeave() {
  scheduleHide();
}

function onPopEnter() {
  clearHide();
}

function onPopLeave() {
  scheduleHide();
}

async function loadChart() {
  const key = `${props.appid}|${props.platform}|${props.dbChart}|${props.endDate ?? ""}`;
  if (loadedKey === key && inst) return;
  loadedKey = key;
  const u = new URL(apiUrl(`game/${props.appid}/sparkline`));
  u.searchParams.set("chart", props.dbChart);
  u.searchParams.set("platform", props.platform);
  u.searchParams.set("days", "7");
  if (props.endDate) u.searchParams.set("end_date", props.endDate);
  try {
    const res = await fetch(u.href);
    if (!res.ok) return;
    const data = await res.json();
    const pts = (data.points || []) as { date: string; rank: number }[];
    if (!chartEl.value) return;
    disposeChart();
    if (pts.length === 0) return;
    inst = echarts.init(chartEl.value, undefined, { renderer: "canvas" });
    const ranks = pts.map((p) => p.rank);
    inst.setOption({
      grid: { left: 40, right: 12, top: 8, bottom: 22 },
      xAxis: {
        type: "category",
        data: pts.map((p) => p.date),
        axisLabel: { fontSize: 9, color: "#64748b" },
      },
      yAxis: {
        type: "value",
        inverse: true,
        name: "名次",
        nameTextStyle: { fontSize: 10, color: "#64748b" },
        min: "dataMin",
        max: "dataMax",
        axisLabel: { fontSize: 9, color: "#64748b" },
        splitLine: { lineStyle: { color: "#e2e8f0" } },
      },
      series: [
        {
          type: "line",
          data: ranks,
          smooth: true,
          symbol: "circle",
          symbolSize: 4,
          lineStyle: { width: 2, color: "#2563eb" },
          areaStyle: { color: "rgba(37,99,235,0.08)" },
        },
      ],
      tooltip: {
        trigger: "axis",
        textStyle: { fontSize: 12, color: "#0f172a" },
        backgroundColor: "#fff",
        borderColor: "#e2e8f0",
        formatter: (items: { data: number; axisValue: string }[]) => {
          const i = items[0];
          if (!i) return "";
          return `${i.axisValue}<br/>名次 ${i.data}`;
        },
      },
    });
  } catch {
    loadedKey = "";
  }
}

watch(
  () => [props.appid, props.platform, props.dbChart, props.endDate],
  () => {
    if (show.value) {
      disposeChart();
      loadedKey = "";
      void loadChart();
    }
  },
);

onBeforeUnmount(() => {
  clearHide();
  disposeChart();
});
</script>

<template>
  <div class="trend-wrap" @click.stop>
    <span
      class="trend-trigger"
      :class="triggerClass"
      @mouseenter="onTriggerEnter"
      @mouseleave="onTriggerLeave"
    >
      {{ triggerLabel }}
    </span>
    <Teleport to="body">
      <div
        v-show="show"
        class="trend-pop"
        :style="{ left: pos.left + 'px', top: pos.top + 'px' }"
        @mouseenter="onPopEnter"
        @mouseleave="onPopLeave"
      >
        <div ref="chartEl" class="trend-chart" />
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.trend-wrap {
  flex-shrink: 0;
  width: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.trend-trigger {
  font-size: 12px;
  font-weight: 600;
  cursor: default;
  user-select: none;
  padding: 4px 6px;
  border-radius: 6px;
  min-width: 36px;
  text-align: center;
}
.trend-trigger.up {
  color: #15803d;
}
.trend-trigger.down {
  color: #dc2626;
}
.trend-trigger.dash {
  color: #94a3b8;
  font-weight: 500;
}
.trend-pop {
  position: fixed;
  z-index: 9999;
  width: 236px;
  height: 132px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
  padding: 4px;
  box-sizing: border-box;
  pointer-events: auto;
}
.trend-chart {
  width: 100%;
  height: 100%;
}
</style>
