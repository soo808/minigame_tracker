<script setup lang="ts">
import TrendSparkPopover from "./TrendSparkPopover.vue";
import { resolveIconSrc } from "../iconSrc";

export type GameEntry = {
  rank: number | null;
  appid: string;
  name: string;
  icon_url?: string | null;
  developer?: string | null;
  tags?: string[] | null;
  genre_major?: string | null;
  genre_minor?: string | null;
  /** 分类筛选/聚合视图下的展示序号（优先于 rank） */
  display_rank?: number;
  is_new: boolean;
  is_dropped: boolean;
  rank_delta: number | null;
};

const props = withDefaults(
  defineProps<{
    entry: GameEntry;
    platform: "wx" | "dy" | "yyb";
    chart: string;
    endDate?: string | null;
    /** 与同行三列对齐时拉满网格行高 */
    fillRow?: boolean;
    /** 周/月榜或筛选列表：不展示趋势区 */
    showTrend?: boolean;
  }>(),
  { fillRow: false, showTrend: true },
);

function rankLabel(): number | null {
  if (props.entry.display_rank != null) return props.entry.display_rank;
  return props.entry.rank;
}

const emit = defineEmits<{ click: [] }>();

function deltaText(): string | null {
  const d = props.entry.rank_delta;
  if (d == null) return null;
  if (d < 0) return `▲${Math.abs(d)}`;
  if (d > 0) return `▼${d}`;
  return null;
}

function deltaClass(): string {
  const d = props.entry.rank_delta;
  if (d == null) return "";
  return d < 0 ? "up" : "down";
}

function trendTriggerClass(): string {
  if (props.entry.is_dropped) return "";
  if (deltaText()) return deltaClass();
  return "dash";
}

function trendTriggerLabel(): string {
  if (props.entry.is_dropped) return "";
  return deltaText() ?? "—";
}
</script>

<template>
  <div
    class="card"
    :class="{ dropped: entry.is_dropped, fillRow }"
    @click="emit('click')"
  >
    <span v-if="rankLabel() != null" class="rank">{{ rankLabel() }}</span>
    <span v-else class="rank dim">—</span>
    <img
      v-if="entry.icon_url"
      class="icon"
      :src="resolveIconSrc(entry.icon_url)"
      alt=""
      loading="lazy"
    />
    <div v-else class="icon placeholder" />
    <div class="main">
      <div class="title-row">
        <span class="name">{{ entry.name }}</span>
        <span v-if="entry.is_new" class="pill new">新</span>
        <span v-if="entry.is_dropped" class="pill out">出</span>
      </div>
      <div v-if="entry.developer" class="sub">{{ entry.developer }}</div>
      <div v-if="entry.tags?.length" class="tags">
        <span v-for="(t, i) in entry.tags.slice(0, 6)" :key="i" class="tag">{{
          t
        }}</span>
      </div>
    </div>
    <div v-if="showTrend && !entry.is_dropped" class="spark-wrap">
      <TrendSparkPopover
        :appid="entry.appid"
        :platform="platform"
        :db-chart="chart"
        :end-date="endDate"
        :trigger-label="trendTriggerLabel()"
        :trigger-class="trendTriggerClass()"
      />
    </div>
  </div>
</template>

<style scoped>
.card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 8px;
  border-radius: 10px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.15s, border-color 0.15s;
}
.card:hover {
  background: rgba(59, 130, 246, 0.08);
  border-color: rgba(37, 99, 235, 0.25);
}
.card.dropped {
  opacity: 0.55;
}
.rank {
  width: 22px;
  font-weight: 700;
  font-size: 13px;
  color: #64748b;
  flex-shrink: 0;
}
.rank.dim {
  color: #94a3b8;
}
.icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  object-fit: cover;
  flex-shrink: 0;
  border: 1px solid #e2e8f0;
}
.icon.placeholder {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
}
.main {
  flex: 1;
  min-width: 0;
}
.title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.name {
  font-weight: 600;
  font-size: 14px;
  color: #0f172a;
  line-height: 1.3;
}
.sub {
  font-size: 12px;
  color: #64748b;
  margin-top: 2px;
}
.tags {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.tag {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f1f5f9;
  color: #475569;
  border: 1px solid #e2e8f0;
}
.pill {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 5px;
  border-radius: 4px;
}
.pill.new {
  background: rgba(22, 163, 74, 0.12);
  color: #15803d;
}
.pill.out {
  background: #f1f5f9;
  color: #64748b;
}
.spark-wrap {
  flex-shrink: 0;
  align-self: center;
}

.card.fillRow {
  align-self: stretch;
  width: 100%;
  height: 100%;
  min-height: 100%;
  box-sizing: border-box;
}

.card.fillRow .main {
  flex: 1;
  min-height: 0;
}

.card.fillRow .spark-wrap {
  align-self: center;
}
</style>
