<script setup lang="ts">
import * as echarts from "echarts";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { apiUrl } from "../config";
import { resolveIconSrc } from "../iconSrc";
import CreativeModal from "./CreativeModal.vue";

type PeerRow = {
  appid: string;
  name: string;
  icon_url: string | null;
  rank: number;
  chart: string;
};

type GameplayRow = {
  tag_id: number;
  slug: string;
  name: string;
  role: string | null;
  evidence: string | null;
  source: string;
};

type MonetizationRow = {
  monetization_model: string;
  mix_note: string | null;
  confidence: number | null;
  evidence_summary: string | null;
  ad_placement_notes: string | null;
  source?: string;
};

type ViralityRow = {
  id: number;
  channels: string | null;
  hypothesis: string;
  evidence: string | null;
  confidence: number | null;
  source: string;
};

type AdxCreative = {
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
  exposure_num: number | null;
  exposure_per_creative: number | null;
  days_on_chart: number | null;
  rising_speed: number | null;
  accel_3d: number | null;
  material_num: number | null;
  creative_num: number | null;
  media_spread: number | null;
  sustain_rate_7d: number | null;
  freshness: number | null;
  pic_list: string[];
  video_list: string[];
  fetched_at: string | null;
};

const props = defineProps<{
  appid: string | null;
  platform: "wx" | "dy" | "yyb";
  /** 榜单参考日（日榜单日 / 周月榜区间结束日），用于同榜同类 */
  asOfDate?: string | null;
}>();

const emit = defineEmits<{ close: []; pick: [appid: string] }>();

const PEER_CHART_LABELS: Record<"wx" | "dy" | "yyb", Record<string, string>> = {
  wx: { renqi: "人气榜", changxiao: "畅销榜", changwan: "畅玩榜" },
  dy: { renqi: "热门榜", changxiao: "畅销榜", xinyou: "新游榜" },
  yyb: { popular: "热门榜", bestseller: "畅销榜", new_game: "新游榜" },
};

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
const snapshotDate = ref<string | null>(null);
const chartPayload = ref<
  Record<string, { label: string; series: { date: string; rank: number }[] }>
>({});
const sameGenrePeers = ref<Record<string, PeerRow[]>>({});
const gameplayTags = ref<GameplayRow[]>([]);
const monetization = ref<MonetizationRow | null>(null);
const viralityAssumptions = ref<ViralityRow[]>([]);
const adxCreatives = ref<AdxCreative[]>([]);
const selectedAdxCreative = ref<AdxCreative | null>(null);

const insightLoading = ref(false);
const insightNote = ref("");
/** 前 50 并集且三类洞察已齐时后端为 false，50 名外为 true */
const showAiInsightInfer = ref(true);

const insightBlocked = computed(
  () => monetization.value?.source === "manual",
);

const peerSectionKeys = computed(() => Object.keys(PEER_CHART_LABELS[props.platform]));

function peerLabel(key: string): string {
  return PEER_CHART_LABELS[props.platform][key] || key;
}

async function load() {
  if (!props.appid) return;
  showAiInsightInfer.value = true;
  const u = new URL(apiUrl(`game/${props.appid}`));
  u.searchParams.set("platform", props.platform);
  u.searchParams.set("days", "30");
  u.searchParams.set("include", "gameplay,monetization,virality");
  if (props.asOfDate) u.searchParams.set("date", props.asOfDate);
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
  snapshotDate.value = data.snapshot_date ?? null;
  chartPayload.value = data.charts || {};
  sameGenrePeers.value = data.same_genre_peers || {};
  gameplayTags.value = Array.isArray(data.gameplay_tags) ? data.gameplay_tags : [];
  monetization.value = data.monetization ?? null;
  viralityAssumptions.value = Array.isArray(data.virality_assumptions)
    ? data.virality_assumptions
    : [];
  showAiInsightInfer.value =
    typeof data.show_ai_insight_button === "boolean"
      ? data.show_ai_insight_button
      : true;
  renderChart();

  // Load ADX creatives for this game
  try {
    const adxRes = await fetch(apiUrl(`adx/creatives/${props.appid}`));
    if (adxRes.ok) {
      const adxData = await adxRes.json();
      adxCreatives.value = adxData.items || [];
    } else {
      adxCreatives.value = [];
    }
  } catch {
    adxCreatives.value = [];
  }
}

async function runInsightInfer() {
  if (!props.appid) return;
  insightNote.value = "";
  insightLoading.value = true;
  try {
    const res = await fetch(apiUrl("insight/infer-batch"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        appid: props.appid,
        platform: props.platform,
        limit: 1,
        batch_size: 1,
        only_missing: false,
        force: true,
      }),
    });
    let data: Record<string, unknown> = {};
    try {
      data = (await res.json()) as Record<string, unknown>;
    } catch {
      /* ignore */
    }
    if (!res.ok) {
      const detail = data.detail;
      insightNote.value =
        typeof detail === "string" ? detail : `请求失败 HTTP ${res.status}`;
      return;
    }
    const errs = data.errors as string[] | undefined;
    if (errs?.length) {
      insightNote.value = errs.join(" ");
      return;
    }
    insightNote.value =
      `已更新：变现 ${String(data.monetization_updated ?? 0)}，玩法关联 ${String(data.gameplay_links_added ?? 0)}，传播 ${String(data.virality_inserted ?? 0)}`;
    await load();
  } catch (e) {
    insightNote.value = e instanceof Error ? e.message : String(e);
  } finally {
    insightLoading.value = false;
  }
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

function onPickPeer(peerAppid: string) {
  emit("pick", peerAppid);
}

function monetizationLabel(m: string): string {
  const map: Record<string, string> = {
    iaa: "IAA",
    iap: "IAP",
    hybrid: "混变",
    unknown: "未标注",
  };
  return map[m] || m;
}

function formatNum(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_0000_0000) return (n / 1_0000_0000).toFixed(1) + "亿";
  if (n >= 1_0000) return (n / 1_0000).toFixed(1) + "万";
  return String(n);
}

onMounted(load);
watch(
  () => [props.appid, props.platform, props.asOfDate],
  () => {
    insightNote.value = "";
    load();
  },
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
          <p v-if="snapshotDate" class="snap-date">参考榜单日：{{ snapshotDate }}</p>
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

      <div
        v-if="insightBlocked || showAiInsightInfer || insightLoading || insightNote"
        class="insight-actions"
      >
        <button
          v-if="insightBlocked || showAiInsightInfer"
          type="button"
          class="btn-insight"
          :disabled="insightBlocked || insightLoading"
          :title="
            insightBlocked
              ? '人工标注变现的游戏不进行 AI 推断'
              : '为本游戏推断玩法、变现与传播（需配置 DeepSeek/OpenAI）'
          "
          @click="runInsightInfer"
        >
          {{ insightLoading ? "推断中…" : "AI 补全本游戏洞察" }}
        </button>
        <p v-if="insightNote" class="insight-note">{{ insightNote }}</p>
      </div>

      <section class="insight-block">
        <p class="section-title">玩法标签</p>
        <div v-if="gameplayTags.length" class="chip-row">
          <span v-for="gt in gameplayTags" :key="gt.tag_id" class="insight-chip">
            {{ gt.name }}
            <span v-if="gt.role" class="chip-role">（{{ gt.role }}）</span>
          </span>
        </div>
        <p v-else class="muted">暂无玩法标签数据。</p>
      </section>

      <section class="insight-block">
        <p class="section-title">变现</p>
        <template v-if="monetization">
          <p class="mono-line">
            <strong>{{ monetizationLabel(monetization.monetization_model) }}</strong>
            <span v-if="monetization.mix_note" class="mix"> — {{ monetization.mix_note }}</span>
          </p>
          <p v-if="monetization.evidence_summary" class="evidence">
            {{ monetization.evidence_summary }}
          </p>
        </template>
        <p v-else class="muted">暂无变现方式说明。</p>
      </section>

      <section class="insight-block">
        <p class="section-title">裂变与传播（假设）</p>
        <ul v-if="viralityAssumptions.length" class="virality-list">
          <li v-for="v in viralityAssumptions" :key="v.id">
            <span class="vh">{{ v.hypothesis }}</span>
            <span v-if="v.channels" class="vc">{{ v.channels }}</span>
          </li>
        </ul>
        <p v-else class="muted">暂无传播假设记录。</p>
      </section>

      <section v-if="adxCreatives.length" class="insight-block">
        <p class="section-title">
          ADX 素材
          <span class="adx-badge">{{ adxCreatives.length }}</span>
        </p>
        <div class="adx-grid">
          <div
            v-for="c in adxCreatives"
            :key="c.creative_id"
            class="adx-card adx-clickable"
            @click="selectedAdxCreative = c"
          >
            <img
              v-if="c.pic_list && c.pic_list.length"
              :src="c.pic_list[0]"
              class="adx-thumb"
              alt=""
            />
            <div v-else class="adx-thumb adx-ph" />
            <div class="adx-info">
              <p class="adx-title">{{ c.title || "无标题" }}</p>
              <p v-if="c.body_text" class="adx-body">{{ c.body_text }}</p>
              <p class="adx-meta">
                <span v-if="c.grade" class="adx-grade" :class="'g-' + c.grade">{{ c.grade }}</span>
                <span v-if="c.exposure_num != null">曝光 {{ formatNum(c.exposure_num) }}</span>
                <span v-if="c.material_type">{{ c.material_type }}</span>
                <span v-if="c.video_list && c.video_list.length" class="adx-video-flag">含视频</span>
              </p>
              <p class="adx-metrics-row">
                <span v-if="c.composite_score != null">综合分 {{ c.composite_score.toFixed(1) }}</span>
                <span v-if="c.material_num != null">素材 {{ c.material_num }}</span>
                <span v-if="c.creative_num != null">创意 {{ c.creative_num }}</span>
                <span v-if="c.days_on_chart != null">在榜 {{ c.days_on_chart }}天</span>
              </p>
            </div>
          </div>
        </div>
      </section>

      <section class="insight-block">
        <p class="section-title">同榜同类（{{ snapshotDate || "—" }}）</p>
        <p v-if="!genreMajor" class="muted">当前游戏未标注大类，无法匹配同榜同类。</p>
        <template v-else>
          <div
            v-for="key in peerSectionKeys"
            :key="key"
            class="peer-row"
          >
            <span class="peer-lab">{{ peerLabel(key) }}</span>
            <div v-if="(sameGenrePeers[key] || []).length" class="peer-icons">
              <button
                v-for="p in sameGenrePeers[key] || []"
                :key="p.appid"
                type="button"
                class="peer-btn"
                :title="`${p.name} #${p.rank}`"
                @click="onPickPeer(p.appid)"
              >
                <img
                  v-if="p.icon_url"
                  class="peer-img"
                  :src="resolveIconSrc(p.icon_url)"
                  alt=""
                />
                <span v-else class="peer-ph" />
                <span class="peer-rank">#{{ p.rank }}</span>
              </button>
            </div>
            <span v-else class="muted inline">无其他同类在榜</span>
          </div>
        </template>
      </section>

      <p class="section-title">近 30 日排名走势</p>
      <div ref="chartEl" class="chart" />
    </div>

    <!-- ADX Creative detail modal (nested) -->
    <CreativeModal
      :creative="selectedAdxCreative"
      @close="selectedAdxCreative = null"
      @pick-game="(id: string) => { selectedAdxCreative = null; emit('pick', id); }"
    />
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
.snap-date {
  margin: 4px 0 0;
  font-size: 12px;
  color: #94a3b8;
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
.insight-actions {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}
.btn-insight {
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid #2563eb;
  background: rgba(37, 99, 235, 0.08);
  color: #1d4ed8;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.btn-insight:hover:not(:disabled) {
  background: rgba(37, 99, 235, 0.14);
}
.btn-insight:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.insight-note {
  margin: 0;
  font-size: 12px;
  color: #0f766e;
  line-height: 1.45;
  max-width: 42rem;
}
.insight-block {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid #f1f5f9;
}
.section-title {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
}
.muted {
  margin: 0;
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.45;
}
.muted.inline {
  display: inline;
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.insight-chip {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  border: 1px solid #bfdbfe;
}
.chip-role {
  font-weight: 400;
  color: #64748b;
}
.mono-line {
  margin: 0;
  font-size: 13px;
  color: #334155;
}
.mix {
  font-weight: 400;
  color: #64748b;
}
.evidence {
  margin: 6px 0 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.4;
}
.virality-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: #334155;
}
.virality-list li {
  margin-bottom: 6px;
}
.vh {
  display: block;
}
.vc {
  display: block;
  font-size: 11px;
  color: #94a3b8;
  margin-top: 2px;
}
.peer-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.peer-lab {
  flex: 0 0 72px;
  font-size: 12px;
  color: #64748b;
  font-weight: 600;
}
.peer-icons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  flex: 1;
}
.peer-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 4px;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 8px;
}
.peer-btn:hover {
  background: #f8fafc;
}
.peer-img,
.peer-ph {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  object-fit: cover;
  border: 1px solid #e2e8f0;
}
.peer-ph {
  background: #f1f5f9;
}
.peer-rank {
  font-size: 10px;
  color: #94a3b8;
}
.chart {
  width: 100%;
  height: 320px;
}

/* ── ADX Creatives ── */
.adx-badge {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 10px;
  background: #fef3c7;
  color: #92400e;
  font-weight: 700;
  margin-left: 4px;
}
.adx-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}
.adx-card {
  display: flex;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #fafafa;
}
.adx-clickable {
  cursor: pointer;
  transition: box-shadow 0.15s, border-color 0.15s;
}
.adx-clickable:hover {
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.08);
  border-color: #cbd5e1;
}
.adx-thumb {
  width: 72px;
  height: 72px;
  border-radius: 6px;
  object-fit: cover;
  flex-shrink: 0;
}
.adx-ph {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
}
.adx-info {
  min-width: 0;
  flex: 1;
}
.adx-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.4;
}
.adx-body {
  margin: 3px 0 0;
  font-size: 11px;
  color: #64748b;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.adx-meta {
  margin: 4px 0 0;
  font-size: 11px;
  color: #64748b;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.adx-grade {
  font-weight: 700;
  padding: 0 4px;
  border-radius: 3px;
}
.adx-grade.g-S {
  color: #b45309;
  background: #fef3c7;
}
.adx-grade.g-A {
  color: #1d4ed8;
  background: #dbeafe;
}
.adx-grade.g-B {
  color: #475569;
  background: #f1f5f9;
}
.adx-video-flag {
  font-size: 10px;
  color: #dc2626;
  padding: 1px 5px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 4px;
  font-weight: 600;
}
.adx-metrics-row {
  margin: 3px 0 0;
  font-size: 11px;
  color: #94a3b8;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.adx-score {
  margin: 2px 0 0;
  font-size: 10px;
  color: #94a3b8;
}
</style>
