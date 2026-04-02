<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { apiUrl } from "../config";
import CreativeModal from "../components/CreativeModal.vue";
import type { AdxCreativeDetail } from "../components/CreativeModal.vue";
import GameModal from "../components/GameModal.vue";

const platform = ref<string>("wx");
const grade = ref<string>("");
const search = ref<string>("");
const sort = ref<string>("composite_score");
const page = ref(1);
const pageSize = 20;
const items = ref<AdxCreativeDetail[]>([]);
const total = ref(0);
const loading = ref(false);

const selectedCreative = ref<AdxCreativeDetail | null>(null);
const gameModalAppid = ref<string | null>(null);

function fmt(n: number | null | undefined): string {
  if (n == null) return "--";
  if (n >= 1_0000_0000) return (n / 1_0000_0000).toFixed(1) + "亿";
  if (n >= 1_0000) return (n / 1_0000).toFixed(1) + "万";
  return String(n);
}

function materialTypeLabel(t: string | number | null): string {
  if (t == null) return "";
  const map: Record<string, string> = {
    "1": "横版视频",
    "2": "竖版视频",
    "3": "图片",
  };
  return map[String(t)] || String(t);
}

async function load() {
  loading.value = true;
  const u = new URL(apiUrl("adx/creatives"));
  if (platform.value) u.searchParams.set("platform", platform.value);
  if (grade.value) u.searchParams.set("grade", grade.value);
  if (search.value.trim()) u.searchParams.set("search", search.value.trim());
  u.searchParams.set("sort", sort.value);
  u.searchParams.set("limit", String(pageSize));
  u.searchParams.set("offset", String((page.value - 1) * pageSize));
  try {
    const res = await fetch(u.href);
    if (!res.ok) return;
    const data = await res.json();
    items.value = data.items || [];
    total.value = data.total || 0;
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  page.value = 1;
  load();
}

const totalPages = () => Math.ceil(total.value / pageSize) || 1;

function goPage(p: number) {
  if (p < 1 || p > totalPages()) return;
  page.value = p;
  load();
}

function openCreative(c: AdxCreativeDetail) {
  selectedCreative.value = c;
}

function onPickGame(appid: string) {
  selectedCreative.value = null;
  gameModalAppid.value = appid;
}

function onGameModalClose() {
  gameModalAppid.value = null;
}

watch([platform, grade, sort], () => {
  page.value = 1;
  load();
});

onMounted(load);
</script>

<template>
  <div class="page">
    <header class="top">
      <h1>ADX 素材库</h1>
      <div class="filters">
        <div class="tabs">
          <button :class="{ on: platform === 'wx' }" @click="platform = 'wx'">
            微信小游戏
          </button>
          <button :class="{ on: platform === 'dy' }" @click="platform = 'dy'">
            抖音小游戏
          </button>
          <button :class="{ on: platform === '' }" @click="platform = ''">
            全部平台
          </button>
        </div>
        <div class="tabs">
          <button :class="{ on: grade === '' }" @click="grade = ''">
            全部评级
          </button>
          <button :class="{ on: grade === 'S' }" @click="grade = 'S'">S</button>
          <button :class="{ on: grade === 'A' }" @click="grade = 'A'">A</button>
          <button :class="{ on: grade === 'B' }" @click="grade = 'B'">B</button>
        </div>
        <div class="sort-row">
          <label>
            排序
            <select v-model="sort">
              <option value="composite_score">综合分</option>
              <option value="exposure_num">曝光量</option>
              <option value="freshness">新鲜度</option>
              <option value="days_on_chart">在榜天数</option>
            </select>
          </label>
          <div class="search-box">
            <input
              v-model="search"
              placeholder="搜索标题或游戏名..."
              @keyup.enter="onSearch"
            />
            <button type="button" @click="onSearch">搜索</button>
          </div>
        </div>
      </div>
      <p class="total-hint">
        共 {{ total }} 条素材
        <span v-if="loading" class="muted">加载中…</span>
      </p>
    </header>

    <!-- Creative List -->
    <div class="creative-list">
      <div
        v-for="c in items"
        :key="c.creative_id"
        class="card"
        @click="openCreative(c)"
      >
        <img
          v-if="c.pic_list && c.pic_list.length"
          class="card-thumb"
          :src="c.pic_list[0]"
          alt=""
        />
        <div v-else class="card-thumb card-ph" />
        <div class="card-body">
          <div class="card-row1">
            <p class="card-title">{{ c.title || "无标题" }}</p>
            <span
              v-if="c.grade"
              class="card-grade"
              :class="'g-' + c.grade"
            >{{ c.grade }}</span>
          </div>
          <p v-if="c.body_text" class="card-text">{{ c.body_text }}</p>
          <div class="card-product">
            <img
              v-if="c.product_icon"
              class="card-picon"
              :src="c.product_icon"
              alt=""
            />
            <button
              v-if="c.mapped_appid"
              type="button"
              class="card-pname"
              @click.stop="onPickGame(c.mapped_appid)"
            >{{ c.product_name || "未知游戏" }}</button>
            <span v-else class="card-pname-text">{{ c.product_name || "" }}</span>
            <span v-if="c.material_type" class="card-type">{{ materialTypeLabel(c.material_type) }}</span>
            <span v-if="c.video_list && c.video_list.length" class="card-video-tag">含视频</span>
          </div>
          <div class="card-metrics">
            <span>曝光 {{ fmt(c.exposure_num) }}</span>
            <span>单创意 {{ fmt(c.exposure_per_creative) }}</span>
            <span>素材 {{ c.material_num ?? "--" }}</span>
            <span>创意 {{ c.creative_num ?? "--" }}</span>
          </div>
          <div class="card-metrics2">
            <span v-if="c.composite_score != null">综合分 {{ c.composite_score.toFixed(1) }}</span>
            <span v-if="c.rising_speed != null">上升 {{ c.rising_speed.toFixed(2) }}</span>
            <span v-if="c.days_on_chart != null">在榜 {{ c.days_on_chart }}天</span>
            <span v-if="c.freshness != null">新鲜度 {{ c.freshness.toFixed(1) }}</span>
          </div>
        </div>
      </div>
    </div>

    <p v-if="!loading && !items.length" class="empty">暂无素材数据。请先同步 ADX 素材。</p>

    <!-- Pagination -->
    <div v-if="total > pageSize" class="pager">
      <button :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
      <span>{{ page }} / {{ totalPages() }}</span>
      <button :disabled="page >= totalPages()" @click="goPage(page + 1)">下一页</button>
    </div>

    <!-- Creative detail modal -->
    <CreativeModal
      :creative="selectedCreative"
      @close="selectedCreative = null"
      @pick-game="onPickGame"
    />

    <!-- Game modal (for viewing game from creative) -->
    <GameModal
      :appid="gameModalAppid"
      :platform="(platform || 'wx') as 'wx' | 'dy' | 'yyb'"
      @close="onGameModalClose"
      @pick="(id: string) => { gameModalAppid = id; }"
    />
  </div>
</template>

<style scoped>
.page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px 24px 64px;
}
.top { margin-bottom: 20px; }
h1 {
  margin: 0 0 16px;
  font-size: 1.6rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: #0f172a;
}
.filters { display: flex; flex-direction: column; gap: 12px; }
.tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.tabs button {
  padding: 7px 14px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #64748b;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
}
.tabs button.on {
  border-color: #2563eb;
  color: #1d4ed8;
  background: rgba(37, 99, 235, 0.08);
}
.sort-row {
  display: flex;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
}
.sort-row label {
  font-size: 13px;
  color: #475569;
  font-weight: 500;
}
.sort-row select {
  margin-left: 6px;
  padding: 5px 8px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #0f172a;
  font-size: 13px;
}
.search-box {
  display: flex;
  gap: 6px;
}
.search-box input {
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
  font-size: 13px;
  width: 200px;
}
.search-box button {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid #2563eb;
  background: #2563eb;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.search-box button:hover { background: #1d4ed8; }
.total-hint {
  margin: 12px 0 0;
  font-size: 13px;
  color: #64748b;
}
.muted { color: #94a3b8; }

/* Creative List */
.creative-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.card {
  display: flex;
  gap: 14px;
  padding: 14px;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  background: #fff;
  cursor: pointer;
  transition: box-shadow 0.15s;
}
.card:hover {
  box-shadow: 0 2px 12px rgba(15, 23, 42, 0.08);
  border-color: #cbd5e1;
}
.card-thumb {
  width: 80px;
  height: 80px;
  border-radius: 8px;
  object-fit: cover;
  flex-shrink: 0;
  border: 1px solid #e2e8f0;
}
.card-ph { background: #f1f5f9; }
.card-body {
  flex: 1;
  min-width: 0;
}
.card-row1 {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}
.card-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.4;
}
.card-grade {
  font-size: 12px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  flex-shrink: 0;
}
.card-grade.g-S { color: #b45309; background: #fef3c7; }
.card-grade.g-A { color: #1d4ed8; background: #dbeafe; }
.card-grade.g-B { color: #475569; background: #f1f5f9; }
.card-grade.g-C { color: #94a3b8; background: #f8fafc; }
.card-text {
  margin: 4px 0 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-product {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.card-picon {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  object-fit: cover;
}
.card-pname {
  border: none;
  background: none;
  color: #2563eb;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.card-pname:hover { color: #1d4ed8; }
.card-pname-text {
  font-size: 12px;
  color: #475569;
  font-weight: 500;
}
.card-type {
  font-size: 11px;
  color: #64748b;
  padding: 1px 6px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
}
.card-video-tag {
  font-size: 10px;
  color: #dc2626;
  padding: 1px 5px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 4px;
  font-weight: 600;
}
.card-metrics, .card-metrics2 {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 6px;
  font-size: 12px;
  color: #475569;
}
.card-metrics2 {
  color: #94a3b8;
  font-size: 11px;
}
.empty {
  color: #64748b;
  font-size: 14px;
  padding: 40px 0;
  text-align: center;
}

/* Pagination */
.pager {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 16px;
  margin-top: 24px;
}
.pager button {
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #475569;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
}
.pager button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.pager button:not(:disabled):hover {
  border-color: #2563eb;
  color: #1d4ed8;
}
.pager span {
  font-size: 13px;
  color: #64748b;
}

@media (max-width: 768px) {
  .card { flex-direction: column; }
  .card-thumb { width: 100%; height: 160px; }
}
</style>
