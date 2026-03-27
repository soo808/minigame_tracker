<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { apiUrl } from "../config";
import type { GameEntry } from "../components/GameCard.vue";
import GameModal from "../components/GameModal.vue";
import PageScrollFab from "../components/PageScrollFab.vue";
import RankColumn from "../components/RankColumn.vue";
import RankingsSyncedGrid from "../components/RankingsSyncedGrid.vue";

const platform = ref<"wx" | "dy" | "yyb">("wx");
const dates = ref<string[]>([]);
const selectedDate = ref<string | null>(null);
const payload = ref<{
  date: string | null;
  platform: string;
  charts: Record<string, { entries: GameEntry[] }>;
} | null>(null);

const dateRange = ref<"day" | "week" | "month">("day");
/** 空数组 = 全部分类；多选为 AND */
const selectedCategories = ref<string[]>([]);
const searchQuery = ref("");

const MAX_CATEGORY_CHIPS = 30;

/** 引力 tags 形如「主类:24名」「主类 24名」；chips 按主类聚合 */
const GENRE_RANK_IN_TAG = /^(.+?)(?:[:：]\s*|\s+)\d+名$/;

function canonicalCategoryKey(tag: string): string {
  const t = tag.trim();
  if (!t) return t;
  const m = t.match(GENRE_RANK_IN_TAG);
  return m ? m[1].trim() : t;
}

const aggregateCharts = ref<Record<string, { entries: GameEntry[] }> | null>(null);
const aggregateRangeLabel = ref<{ start: string; end: string } | null>(null);

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

const yybCols = [
  { key: "popular", title: "应用宝 · 热门榜", chart: "popular" },
  { key: "bestseller", title: "应用宝 · 畅销榜", chart: "bestseller" },
  { key: "new_game", title: "应用宝 · 新游榜", chart: "new_game" },
] as const;

const cols = computed(() =>
  platform.value === "wx" ? wxCols : platform.value === "dy" ? dyCols : yybCols,
);

const searchNeedle = computed(() => searchQuery.value.trim().toLowerCase());

const useListLayout = computed(
  () =>
    dateRange.value !== "day" ||
    selectedCategories.value.length > 0 ||
    searchNeedle.value.length > 0,
);

const showTrendInGrid = computed(
  () =>
    dateRange.value === "day" &&
    selectedCategories.value.length === 0 &&
    searchNeedle.value.length === 0,
);

const gridEndDate = computed(() => {
  if (dateRange.value !== "day" && aggregateRangeLabel.value) {
    return aggregateRangeLabel.value.end;
  }
  return payload.value?.date ?? null;
});

const rawChartsForPipeline = computed((): Record<string, { entries: GameEntry[] }> => {
  if (dateRange.value === "day") {
    return payload.value?.charts ?? {};
  }
  return aggregateCharts.value ?? {};
});

function labelsForEntry(e: GameEntry): string[] {
  const raw = (e.tags ?? []).map((t) => String(t).trim()).filter(Boolean);
  if (raw.length) return raw;
  const gm = e.genre_major?.trim();
  if (gm) return [gm];
  return [];
}

function entryMatchesCategory(e: GameEntry, sel: string): boolean {
  if (sel === "全部") return true;
  const raw = (e.tags ?? []).map((t) => String(t).trim()).filter(Boolean);
  if (raw.length) {
    return raw.some((t) => canonicalCategoryKey(t) === sel);
  }
  const gm = e.genre_major?.trim() ?? "";
  return gm.length > 0 && canonicalCategoryKey(gm) === sel;
}

function entryMatchesAllSelected(e: GameEntry, sels: string[]): boolean {
  if (sels.length === 0) return true;
  return sels.every((c) => entryMatchesCategory(e, c));
}

type ColDef = (typeof wxCols)[number];

function countFilteredAcrossCharts(
  src: Record<string, { entries: GameEntry[] }>,
  colList: readonly ColDef[],
  categorySels: string[],
): number {
  let total = 0;
  for (const c of colList) {
    let entries = [...(src[c.key]?.entries ?? [])];
    entries = entries.filter((e) => !e.is_dropped);
    entries = entries.filter((e) => entryMatchesAllSelected(e, categorySels));
    entries = entries.filter(entryMatchesSearch);
    total += entries.length;
  }
  return total;
}

function categoryChipBlocked(cat: string): boolean {
  if (cat === "全部") return false;
  if (selectedCategories.value.includes(cat)) return false;
  return (
    countFilteredAcrossCharts(
      rawChartsForPipeline.value,
      cols.value,
      [...selectedCategories.value, cat],
    ) === 0
  );
}

function toggleCategory(cat: string): void {
  if (cat === "全部") {
    selectedCategories.value = [];
    return;
  }
  const i = selectedCategories.value.indexOf(cat);
  if (i >= 0) {
    selectedCategories.value = selectedCategories.value.filter((c) => c !== cat);
    return;
  }
  const next = [...selectedCategories.value, cat];
  if (
    countFilteredAcrossCharts(
      rawChartsForPipeline.value,
      cols.value,
      next,
    ) === 0
  ) {
    return;
  }
  selectedCategories.value = next;
}

function entryMatchesSearch(e: GameEntry): boolean {
  const n = searchNeedle.value;
  if (!n) return true;
  const name = (e.name ?? "").toLowerCase();
  const dev = (e.developer ?? "").toLowerCase();
  return name.includes(n) || dev.includes(n);
}

const chartDataForGrid = computed(() => {
  const src = rawChartsForPipeline.value;
  const out: Record<string, { entries: GameEntry[] }> = {};
  for (const c of cols.value) {
    let entries = [...(src[c.key]?.entries ?? [])];
    entries = entries.filter((e) => !e.is_dropped);
    entries = entries.filter((e) =>
      entryMatchesAllSelected(e, selectedCategories.value),
    );
    entries = entries.filter(entryMatchesSearch);
    entries = entries.map((e, i) => ({ ...e, display_rank: i + 1 }));
    out[c.key] = { entries };
  }
  return out;
});

const availableCategories = computed(() => {
  const src = rawChartsForPipeline.value;
  const keys = cols.value.map((c) => c.key);
  if (!keys.some((k) => src[k]?.entries?.length)) return ["全部"];
  const counts = new Map<string, number>();
  for (const c of cols.value) {
    for (const g of src[c.key]?.entries ?? []) {
      for (const lab of labelsForEntry(g)) {
        const key = canonicalCategoryKey(lab);
        if (!key) continue;
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
    }
  }
  const sorted = Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "zh-CN"))
    .map(([k]) => k)
    .slice(0, MAX_CATEGORY_CHIPS);
  return ["全部", ...sorted];
});

function droppedOnly(list: GameEntry[] | undefined): GameEntry[] {
  return (list ?? []).filter((e) => e.is_dropped);
}

function droppedFiltered(list: GameEntry[] | undefined): GameEntry[] {
  return droppedOnly(list)
    .filter((e) => entryMatchesAllSelected(e, selectedCategories.value))
    .filter(entryMatchesSearch);
}

type AggRow = {
  appid: string;
  name: string;
  icon_url?: string | null;
  developer?: string | null;
  genre_major?: string | null;
  tags?: string[] | null;
  avg_rank: number;
  appearances: number;
};

function aggregateRowToEntry(row: AggRow, displayRank: number): GameEntry {
  return {
    rank: row.avg_rank != null ? Math.round(Number(row.avg_rank)) : null,
    display_rank: displayRank,
    appid: row.appid,
    name: row.name,
    icon_url: row.icon_url ?? null,
    developer: row.developer ?? null,
    tags: row.tags ?? null,
    genre_major: row.genre_major ?? null,
    is_new: false,
    is_dropped: false,
    rank_delta: null,
  };
}

function mapAggregateResponse(data: {
  charts: Record<string, AggRow[]>;
  start_date: string;
  end_date: string;
}) {
  const out: Record<string, { entries: GameEntry[] }> = {};
  for (const c of cols.value) {
    const rows = data.charts[c.chart] ?? [];
    out[c.key] = {
      entries: rows.map((row, i) => aggregateRowToEntry(row, i + 1)),
    };
  }
  aggregateCharts.value = out;
  aggregateRangeLabel.value = { start: data.start_date, end: data.end_date };
}

function readPlatformFromUrl() {
  const q = new URLSearchParams(window.location.search).get("platform");
  if (q === "dy" || q === "wx" || q === "yyb") platform.value = q;
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

async function loadAggregate() {
  loading.value = true;
  err.value = "";
  try {
    const range = dateRange.value === "week" ? "week" : "month";
    const u = new URL(apiUrl("rankings/aggregate"));
    u.searchParams.set("platform", platform.value);
    u.searchParams.set("range", range);
    if (selectedDate.value) u.searchParams.set("end_date", selectedDate.value);
    const res = await fetch(u.href);
    if (!res.ok) throw new Error(`aggregate HTTP ${res.status}`);
    const data = await res.json();
    mapAggregateResponse(data);
  } catch (e) {
    err.value = e instanceof Error ? e.message : String(e);
    aggregateCharts.value = null;
    aggregateRangeLabel.value = null;
  } finally {
    loading.value = false;
  }
}

async function onDateRangeChange(range: "day" | "week" | "month") {
  dateRange.value = range;
  if (range === "day") {
    aggregateCharts.value = null;
    aggregateRangeLabel.value = null;
    await loadRankings();
  } else {
    await loadAggregate();
  }
}

function clearSearch() {
  searchQuery.value = "";
}

function goToday() {
  if (dates.value.length) selectedDate.value = dates.value[0];
  if (dateRange.value === "day") loadRankings();
  else loadAggregate();
}

onMounted(async () => {
  readPlatformFromUrl();
  await loadDates();
  await loadRankings();
});

watch(platform, async () => {
  writePlatformToUrl();
  selectedCategories.value = [];
  await loadDates();
  if (dateRange.value === "day") await loadRankings();
  else await loadAggregate();
});

watch(selectedDate, () => {
  if (dateRange.value === "day") loadRankings();
  else loadAggregate();
});

watch(availableCategories, (avail) => {
  const allowed = new Set(avail);
  const next = selectedCategories.value.filter((c) => allowed.has(c));
  if (next.length !== selectedCategories.value.length) {
    selectedCategories.value = next;
  }
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
        <button
          type="button"
          :class="{ on: platform === 'yyb' }"
          @click="platform = 'yyb'"
        >
          腾讯应用宝
        </button>
      </div>

      <div class="genre-filter-bar">
        <span class="filter-label">分类</span>
        <button
          v-for="cat in availableCategories"
          :key="cat"
          type="button"
          :class="[
            'genre-chip',
            {
              active:
                cat === '全部'
                  ? selectedCategories.length === 0
                  : selectedCategories.includes(cat),
              'genre-chip--blocked': categoryChipBlocked(cat),
            },
          ]"
          :aria-disabled="categoryChipBlocked(cat) ? 'true' : undefined"
          @click="toggleCategory(cat)"
        >
          {{ cat }}
        </button>
      </div>

      <div class="date-search-bar">
        <span class="filter-label">日期范围</span>
        <button
          type="button"
          :class="['range-btn', { active: dateRange === 'day' }]"
          @click="onDateRangeChange('day')"
        >
          日榜
        </button>
        <button
          type="button"
          :class="['range-btn', { active: dateRange === 'week' }]"
          @click="onDateRangeChange('week')"
        >
          周榜
        </button>
        <button
          type="button"
          :class="['range-btn', { active: dateRange === 'month' }]"
          @click="onDateRangeChange('month')"
        >
          月榜
        </button>

        <label v-if="dateRange === 'day'" class="date-inline">
          日期
          <select v-model="selectedDate">
            <option v-for="d in dates" :key="d" :value="d">{{ d }}</option>
          </select>
        </label>
        <label v-else class="date-inline">
          截止
          <select v-model="selectedDate">
            <option v-for="d in dates" :key="d" :value="d">{{ d }}</option>
          </select>
        </label>

        <span class="data-hint">数据每日约 11:00 更新</span>

        <div class="date-bar-end">
          <button type="button" class="ghost ghost--compact" @click="goToday">
            今日
          </button>
          <div class="search-box" :class="{ 'with-clear': searchQuery.trim() }">
          <div class="search-field">
            <input
              v-model="searchQuery"
              type="search"
              class="search-input"
              placeholder="输入游戏名/公司名"
              aria-label="按游戏名或公司名筛选"
            />
            <span class="search-input-icon" aria-hidden="true">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.3-4.3" />
              </svg>
            </span>
          </div>
          <button
            v-if="searchQuery.trim()"
            type="button"
            class="search-clear-btn"
            @click="clearSearch"
          >
            清空
          </button>
        </div>
        </div>
      </div>

      <div class="date-row">
        <span v-if="loading" class="muted">加载中…</span>
        <span v-if="err" class="err">{{ err }}</span>
      </div>
    </header>

    <template
      v-if="
        (dateRange === 'day' && payload && payload.date) ||
          (dateRange !== 'day' && aggregateCharts && aggregateRangeLabel)
      "
    >
      <p v-if="dateRange !== 'day' && aggregateRangeLabel" class="range-meta">
        统计区间：{{ aggregateRangeLabel.start }} ~ {{ aggregateRangeLabel.end }}（均名次升序）
      </p>
      <RankingsSyncedGrid
        :cols="cols"
        :charts="chartDataForGrid"
        :platform="platform"
        :end-date="gridEndDate"
        :layout-mode="useListLayout ? 'list' : 'sync'"
        :show-trend="showTrendInGrid"
        @pick="modalAppid = $event"
      />
      <div
        v-if="dateRange === 'day' && payload && payload.date"
        class="dropped-wrap"
      >
        <p class="dropped-hint">跌出榜（仅当日有跌出记录时显示）</p>
        <div class="grid dropped-grid">
          <RankColumn
            v-for="c in cols"
            :key="c.key"
            :title="c.title"
            :entries="droppedFiltered(payload.charts[c.key]?.entries)"
            :platform="platform"
            :chart="c.chart"
            :end-date="payload.date"
            @pick="modalAppid = $event"
          />
        </div>
      </div>
    </template>
    <p v-else-if="!loading" class="empty">暂无数据。启动后端并完成采集或 POST /api/ingest。</p>

    <GameModal
      :appid="modalAppid"
      :platform="platform"
      @close="modalAppid = null"
    />

    <PageScrollFab />
  </div>
</template>

<style scoped>
.page {
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px 20px 48px;
  background: #ffffff;
}
.top {
  margin-bottom: 20px;
}
h1 {
  margin: 0 0 16px;
  font-size: 1.5rem;
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
.genre-filter-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.filter-label {
  font-size: 13px;
  color: #64748b;
  font-weight: 600;
  margin-right: 4px;
}
.genre-chip {
  padding: 5px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
  color: #475569;
  font-weight: 500;
}
.genre-chip.active,
.genre-chip:not(.genre-chip--blocked):hover {
  border-color: #2563eb;
  color: #1d4ed8;
  background: rgba(37, 99, 235, 0.08);
}
.genre-chip--blocked {
  opacity: 0.45;
  cursor: not-allowed;
  pointer-events: none;
}
.date-search-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f1f5f9;
}
.range-btn {
  padding: 6px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
  color: #475569;
  font-weight: 600;
}
.range-btn.active {
  border-color: #2563eb;
  color: #1d4ed8;
  background: rgba(37, 99, 235, 0.08);
}
.date-inline {
  font-size: 13px;
  color: #475569;
}
.date-inline select {
  margin-left: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
}
.data-hint {
  font-size: 12px;
  color: #94a3b8;
}
.date-bar-end {
  margin-left: auto;
  display: flex;
  align-items: stretch;
  flex-wrap: wrap;
  gap: 8px 10px;
}
.search-box {
  display: flex;
  align-items: stretch;
  flex-wrap: wrap;
  gap: 0;
}
.search-field {
  display: flex;
  align-items: center;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #fff;
  min-width: min(220px, 50vw);
}
.search-box.with-clear .search-field {
  border-radius: 8px 0 0 8px;
  border-right: none;
}
.search-input {
  flex: 1;
  min-width: 0;
  width: min(200px, 42vw);
  padding: 6px 4px 6px 10px;
  border: none;
  font-size: 13px;
  outline: none;
  background: transparent;
}
.search-input::placeholder {
  color: #94a3b8;
}
.search-input:focus {
  outline: none;
}
.search-field:focus-within {
  border-color: #2563eb;
}
.search-input-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  padding: 0 10px 0 4px;
  color: #94a3b8;
}
.search-clear-btn {
  padding: 6px 12px;
  background: #f1f5f9;
  color: #475569;
  border: 1px solid #cbd5e1;
  border-left: none;
  border-radius: 0 8px 8px 0;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}
.search-clear-btn:hover {
  background: #e2e8f0;
}
.range-meta {
  font-size: 12px;
  color: #64748b;
  margin: 0 0 10px;
}
.date-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.ghost {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #2563eb;
  cursor: pointer;
  font-weight: 600;
}
.ghost:hover {
  border-color: #2563eb;
  background: rgba(37, 99, 235, 0.06);
}
.ghost--compact {
  padding: 6px 12px;
  font-size: 13px;
  align-self: center;
}
.muted {
  font-size: 13px;
  color: #64748b;
}
.err {
  font-size: 13px;
  color: #dc2626;
}
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}
.dropped-wrap {
  margin-top: 28px;
}
.dropped-hint {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
}
.dropped-grid {
  align-items: start;
}
@media (max-width: 1024px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
.empty {
  color: #64748b;
  font-size: 14px;
}
</style>
