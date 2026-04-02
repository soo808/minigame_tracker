<script setup lang="ts">
import { ref } from "vue";

export type AdxCreativeDetail = {
  creative_id: string;
  title: string | null;
  body_text: string | null;
  product_id: string | null;
  product_name: string | null;
  product_icon: string | null;
  platform: string | null;
  material_type: string | null;
  grade: string | null;
  composite_score: number | null;
  days_on_chart: number | null;
  rising_speed: number | null;
  accel_3d: number | null;
  material_num: number | null;
  creative_num: number | null;
  exposure_num: number | null;
  exposure_per_creative: number | null;
  media_spread: number | null;
  sustain_rate_7d: number | null;
  freshness: number | null;
  pic_list: string[];
  video_list: string[];
  fetched_at: string | null;
  mapped_appid: string | null;
};

const props = defineProps<{
  creative: AdxCreativeDetail | null;
}>();

const emit = defineEmits<{ close: []; "pick-game": [appid: string] }>();

const activeVideo = ref<string | null>(null);
const videoErrors = ref<Set<string>>(new Set());

function adxUrl(creativeId: string): string {
  return `https://adxray.dataeye.com/creative/${creativeId}`;
}

function fmt(n: number | null | undefined): string {
  if (n == null) return "--";
  if (n >= 1_0000_0000) return (n / 1_0000_0000).toFixed(1) + "亿";
  if (n >= 1_0000) return (n / 1_0000).toFixed(1) + "万";
  return String(n);
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return "--";
  return (n * 100).toFixed(1) + "%";
}

function fmtFloat(n: number | null | undefined): string {
  if (n == null) return "--";
  return n.toFixed(2);
}

function onOverlay(e: MouseEvent) {
  if (e.target === e.currentTarget) emit("close");
}

function playVideo(url: string) {
  activeVideo.value = activeVideo.value === url ? null : url;
}

function onVideoError(url: string) {
  videoErrors.value.add(url);
}

function onPickGame() {
  const appid = props.creative?.mapped_appid;
  if (appid) emit("pick-game", appid);
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
</script>

<template>
  <div v-if="creative" class="cm-overlay" @click="onOverlay">
    <div class="cm-panel" @click.stop>
      <button type="button" class="cm-close" aria-label="关闭" @click="emit('close')">
        &times;
      </button>

      <!-- Header -->
      <div class="cm-head">
        <img
          v-if="creative.product_icon"
          class="cm-icon"
          :src="creative.product_icon"
          alt=""
        />
        <div v-else class="cm-icon cm-icon-ph" />
        <div class="cm-head-info">
          <h2 class="cm-product">
            <button
              v-if="creative.mapped_appid"
              type="button"
              class="cm-game-link"
              @click="onPickGame"
            >
              {{ creative.product_name || "未知游戏" }}
            </button>
            <span v-else>{{ creative.product_name || "未知游戏" }}</span>
          </h2>
          <div class="cm-head-tags">
            <span
              v-if="creative.grade"
              class="cm-grade"
              :class="'g-' + creative.grade"
            >{{ creative.grade }}</span>
            <span v-if="creative.composite_score != null" class="cm-score-tag">
              综合分 {{ creative.composite_score.toFixed(1) }}
            </span>
            <span v-if="creative.platform" class="cm-plat-tag">
              {{ creative.platform }}
            </span>
            <span v-if="creative.material_type" class="cm-type-tag">
              {{ materialTypeLabel(creative.material_type) }}
            </span>
            <a
              class="cm-adx-link"
              :href="adxUrl(creative.creative_id)"
              target="_blank"
              rel="noopener noreferrer"
            >ADX 原始页面</a>
          </div>
        </div>
      </div>

      <!-- Title & Body -->
      <div v-if="creative.title || creative.body_text" class="cm-text-block">
        <p v-if="creative.title" class="cm-title">{{ creative.title }}</p>
        <p v-if="creative.body_text" class="cm-body">{{ creative.body_text }}</p>
      </div>

      <!-- Media Gallery -->
      <div v-if="creative.pic_list.length || creative.video_list.length" class="cm-media">
        <p class="cm-section-label">素材媒体</p>
        <div class="cm-media-grid">
          <img
            v-for="(pic, i) in creative.pic_list"
            :key="'p' + i"
            class="cm-media-img"
            :src="pic"
            alt=""
          />
        </div>
        <div v-if="creative.video_list.length" class="cm-videos">
          <div v-for="(vid, i) in creative.video_list" :key="'v' + i" class="cm-video-item">
            <button
              type="button"
              class="cm-video-btn"
              @click="playVideo(vid)"
            >
              {{ activeVideo === vid ? "收起视频" : `播放视频 ${i + 1}` }}
            </button>
            <a class="cm-video-link" :href="vid" target="_blank" rel="noopener noreferrer">
              新窗口打开
            </a>
            <template v-if="activeVideo === vid">
              <p v-if="videoErrors.has(vid)" class="cm-video-expired">
                视频链接已过期，请重新同步 ADX 素材以获取新链接，或点击上方链接尝试打开。
              </p>
              <video
                v-else
                :src="vid"
                controls
                class="cm-video-player"
                @error="onVideoError(vid)"
              />
            </template>
          </div>
        </div>
      </div>

      <!-- Metrics Grid -->
      <div class="cm-metrics">
        <p class="cm-section-label">核心指标</p>
        <div class="cm-metrics-grid">
          <div class="cm-metric">
            <span class="cm-metric-val">{{ fmt(creative.exposure_num) }}</span>
            <span class="cm-metric-lbl">总曝光</span>
          </div>
          <div class="cm-metric">
            <span class="cm-metric-val">{{ fmt(creative.exposure_per_creative) }}</span>
            <span class="cm-metric-lbl">单创意曝光</span>
          </div>
          <div class="cm-metric">
            <span class="cm-metric-val">{{ creative.material_num ?? "--" }}</span>
            <span class="cm-metric-lbl">素材数</span>
          </div>
          <div class="cm-metric">
            <span class="cm-metric-val">{{ creative.creative_num ?? "--" }}</span>
            <span class="cm-metric-lbl">创意数</span>
          </div>
          <div class="cm-metric">
            <span class="cm-metric-val">{{ creative.days_on_chart ?? "--" }}天</span>
            <span class="cm-metric-lbl">在榜天数</span>
          </div>
          <div class="cm-metric">
            <span class="cm-metric-val">{{ fmtFloat(creative.rising_speed) }}</span>
            <span class="cm-metric-lbl">上升速度</span>
          </div>
          <div class="cm-metric">
            <span class="cm-metric-val">{{ fmtFloat(creative.accel_3d) }}</span>
            <span class="cm-metric-lbl">3日加速度</span>
          </div>
          <div class="cm-metric">
            <span class="cm-metric-val">{{ fmtFloat(creative.media_spread) }}</span>
            <span class="cm-metric-lbl">媒体扩散度</span>
          </div>
          <div class="cm-metric">
            <span class="cm-metric-val">{{ fmtPct(creative.sustain_rate_7d) }}</span>
            <span class="cm-metric-lbl">7日留存率</span>
          </div>
          <div class="cm-metric">
            <span class="cm-metric-val">{{ fmtFloat(creative.freshness) }}</span>
            <span class="cm-metric-lbl">新鲜度</span>
          </div>
        </div>
      </div>

      <p v-if="creative.fetched_at" class="cm-fetched">
        数据更新：{{ creative.fetched_at }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.cm-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1100;
  padding: 24px;
  backdrop-filter: blur(4px);
}
.cm-panel {
  position: relative;
  width: min(780px, 100%);
  max-height: 90vh;
  overflow-y: auto;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 24px 24px 20px;
  box-shadow: 0 25px 50px -12px rgba(15, 23, 42, 0.2);
}
.cm-close {
  position: absolute;
  top: 12px;
  right: 14px;
  border: none;
  background: transparent;
  color: #64748b;
  font-size: 26px;
  cursor: pointer;
}
.cm-close:hover { color: #0f172a; }

/* Head */
.cm-head {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  margin-bottom: 16px;
}
.cm-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  object-fit: cover;
  border: 1px solid #e2e8f0;
  flex-shrink: 0;
}
.cm-icon-ph { background: #f1f5f9; }
.cm-head-info { min-width: 0; }
.cm-product {
  margin: 0 0 6px;
  font-size: 1.15rem;
  font-weight: 700;
  color: #0f172a;
}
.cm-game-link {
  border: none;
  background: none;
  color: #2563eb;
  font-size: inherit;
  font-weight: inherit;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.cm-game-link:hover { color: #1d4ed8; }
.cm-head-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.cm-grade {
  font-size: 12px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
}
.cm-grade.g-S { color: #b45309; background: #fef3c7; }
.cm-grade.g-A { color: #1d4ed8; background: #dbeafe; }
.cm-grade.g-B { color: #475569; background: #f1f5f9; }
.cm-grade.g-C { color: #94a3b8; background: #f8fafc; }
.cm-score-tag {
  font-size: 12px;
  color: #059669;
  font-weight: 600;
}
.cm-plat-tag, .cm-type-tag {
  font-size: 11px;
  color: #64748b;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}
.cm-adx-link {
  font-size: 11px;
  color: #2563eb;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.cm-adx-link:hover { color: #1d4ed8; }

/* Text */
.cm-text-block {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f1f5f9;
}
.cm-title {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.5;
}
.cm-body {
  margin: 0;
  font-size: 13px;
  color: #475569;
  line-height: 1.5;
}

/* Section label */
.cm-section-label {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
}

/* Media */
.cm-media {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f1f5f9;
}
.cm-media-grid {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.cm-media-img {
  width: 140px;
  height: 140px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  flex-shrink: 0;
}
.cm-videos { margin-top: 10px; }
.cm-video-item { margin-bottom: 8px; }
.cm-video-btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid #2563eb;
  background: rgba(37, 99, 235, 0.08);
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.cm-video-btn:hover { background: rgba(37, 99, 235, 0.14); }
.cm-video-link {
  font-size: 12px;
  color: #64748b;
  margin-left: 8px;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.cm-video-link:hover { color: #2563eb; }
.cm-video-expired {
  margin: 8px 0 0;
  padding: 10px 14px;
  border-radius: 6px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #dc2626;
  font-size: 12px;
  line-height: 1.5;
}
.cm-video-player {
  display: block;
  margin-top: 8px;
  width: 100%;
  max-width: 480px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

/* Metrics */
.cm-metrics { margin-bottom: 12px; }
.cm-metrics-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
}
.cm-metric {
  text-align: center;
  padding: 10px 6px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #f1f5f9;
}
.cm-metric-val {
  display: block;
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}
.cm-metric-lbl {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: #94a3b8;
}

.cm-fetched {
  margin: 12px 0 0;
  font-size: 11px;
  color: #cbd5e1;
}

@media (max-width: 768px) {
  .cm-metrics-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
@media (max-width: 480px) {
  .cm-metrics-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
