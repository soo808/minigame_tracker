<script setup lang="ts">
import * as echarts from "echarts";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { apiUrl } from "../config";

const props = defineProps<{
  appid: string;
  platform: "wx" | "dy";
  dbChart: string;
  endDate?: string | null;
}>();

const el = ref<HTMLDivElement | null>(null);
let inst: echarts.ECharts | null = null;

async function load() {
  const u = new URL(apiUrl(`game/${props.appid}/sparkline`));
  u.searchParams.set("chart", props.dbChart);
  u.searchParams.set("platform", props.platform);
  u.searchParams.set("days", "7");
  if (props.endDate) u.searchParams.set("end_date", props.endDate);
  const res = await fetch(u.href);
  if (!res.ok) return;
  const data = await res.json();
  const pts = (data.points || []) as { date: string; rank: number }[];
  if (!el.value) return;
  if (!inst) inst = echarts.init(el.value, undefined, { renderer: "canvas" });
  const ranks = pts.map((p) => p.rank);
  inst.setOption({
    grid: { left: 0, right: 0, top: 2, bottom: 2 },
    xAxis: { type: "category", show: false, data: pts.map((p) => p.date) },
    yAxis: { type: "value", show: false, inverse: true, min: "dataMin", max: "dataMax" },
    series: [
      {
        type: "line",
        data: ranks,
        smooth: true,
        symbol: "none",
        lineStyle: { width: 1.5, color: "#2563eb" },
        areaStyle: { color: "rgba(37,99,235,0.12)" },
      },
    ],
    tooltip: {
      trigger: "axis",
      formatter: (items: { data: number; axisValue: string }[]) => {
        const i = items[0];
        if (!i) return "";
        return `${i.axisValue}<br/>名次 ${i.data}`;
      },
    },
  });
}

onMounted(() => {
  load();
});
watch(
  () => [props.appid, props.platform, props.dbChart, props.endDate],
  () => load(),
);

onBeforeUnmount(() => {
  inst?.dispose();
  inst = null;
});
</script>

<template>
  <div ref="el" class="spark" />
</template>

<style scoped>
.spark {
  width: 72px;
  height: 28px;
}
</style>
