<script setup lang="ts">
import Sparkline from "./Sparkline.vue";

export type GameEntry = {
  rank: number | null;
  appid: string;
  name: string;
  icon_url?: string | null;
  developer?: string | null;
  tags?: string[] | null;
  is_new: boolean;
  is_dropped: boolean;
  rank_delta: number | null;
};

const props = defineProps<{
  entry: GameEntry;
  platform: "wx" | "dy";
  chart: string;
  endDate?: string | null;
}>();

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
</script>

<template>
  <div
    class="card"
    :class="{ dropped: entry.is_dropped }"
    @click="emit('click')"
  >
    <span v-if="entry.rank != null" class="rank">{{ entry.rank }}</span>
    <span v-else class="rank dim">—</span>
    <img
      v-if="entry.icon_url"
      class="icon"
      :src="entry.icon_url"
      alt=""
      loading="lazy"
    />
    <div v-else class="icon placeholder" />
    <div class="main">
      <div class="title-row">
        <span class="name">{{ entry.name }}</span>
        <span v-if="entry.is_new" class="pill new">新</span>
        <span v-if="entry.is_dropped" class="pill out">出</span>
        <span v-if="deltaText()" class="delta" :class="deltaClass()">{{
          deltaText()
        }}</span>
      </div>
      <div v-if="entry.developer" class="sub">{{ entry.developer }}</div>
      <div v-if="entry.tags?.length" class="tags">
        <span v-for="(t, i) in entry.tags.slice(0, 6)" :key="i" class="tag">{{
          t
        }}</span>
      </div>
    </div>
    <div v-if="!entry.is_dropped" class="spark-wrap">
      <Sparkline
        :appid="entry.appid"
        :platform="platform"
        :db-chart="chart"
        :end-date="endDate"
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
  background: rgba(88, 166, 255, 0.06);
  border-color: rgba(88, 166, 255, 0.2);
}
.card.dropped {
  opacity: 0.55;
}
.rank {
  width: 22px;
  font-weight: 700;
  font-size: 13px;
  color: #8b949e;
  flex-shrink: 0;
}
.rank.dim {
  color: #484f58;
}
.icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  object-fit: cover;
  flex-shrink: 0;
}
.icon.placeholder {
  background: #21262d;
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
  color: #e6edf3;
  line-height: 1.3;
}
.sub {
  font-size: 12px;
  color: #8b949e;
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
  background: #21262d;
  color: #8b949e;
}
.pill {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 5px;
  border-radius: 4px;
}
.pill.new {
  background: rgba(46, 160, 67, 0.25);
  color: #3fb950;
}
.pill.out {
  background: rgba(139, 148, 158, 0.2);
  color: #8b949e;
}
.delta {
  font-size: 12px;
  font-weight: 600;
  margin-left: 4px;
}
.delta.up {
  color: #3fb950;
}
.delta.down {
  color: #f85149;
}
.spark-wrap {
  flex-shrink: 0;
  align-self: center;
}
</style>
