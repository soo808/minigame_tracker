<script setup lang="ts">
import { ref, nextTick } from "vue";
import { apiUrl } from "../config";

const platform = ref<"wx" | "dy" | "yyb">("wx");
const input = ref("");
const loading = ref(false);

interface Message {
  role: "user" | "assistant";
  content: string;
  sql?: string | null;
  sources?: string[];
  timestamp: string;
}

const messages = ref<Message[]>([]);
const chatBody = ref<HTMLElement | null>(null);

const QUICK_QUESTIONS = [
  "今日新上榜游戏有哪些？",
  "本周排名上升最快的游戏",
  "当前各品类游戏数量分布",
  "角色扮演类游戏有哪些在榜？",
  "排名前10的游戏是哪些？",
  "今日外部热点",
];

function now() {
  return new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

async function scrollToBottom() {
  await nextTick();
  if (chatBody.value) {
    chatBody.value.scrollTop = chatBody.value.scrollHeight;
  }
}

async function ask(question: string) {
  if (!question.trim() || loading.value) return;

  messages.value.push({ role: "user", content: question, timestamp: now() });
  await scrollToBottom();

  loading.value = true;
  try {
    const resp = await fetch(apiUrl("qa"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, platform: platform.value }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    messages.value.push({
      role: "assistant",
      content: data.answer || "未能生成回答",
      sql: data.sql,
      sources: data.sources || [],
      timestamp: now(),
    });
  } catch (e) {
    messages.value.push({
      role: "assistant",
      content: `请求失败：${e instanceof Error ? e.message : String(e)}`,
      timestamp: now(),
    });
  } finally {
    loading.value = false;
    await scrollToBottom();
  }
}

function submit() {
  const q = input.value.trim();
  if (q) {
    ask(q);
    input.value = "";
  }
}

function askQuick(q: string) {
  input.value = "";
  ask(q);
}
</script>

<template>
  <div class="qa-page">
    <!-- Header -->
    <header class="qa-header">
      <h1>AI 问答</h1>
      <div class="qa-tabs">
        <button :class="{ on: platform === 'wx' }" @click="platform = 'wx'">微信小游戏</button>
        <button :class="{ on: platform === 'dy' }" @click="platform = 'dy'">抖音小游戏</button>
        <button :class="{ on: platform === 'yyb' }" @click="platform = 'yyb'">应用宝</button>
      </div>
    </header>

    <!-- Chat Body -->
    <div ref="chatBody" class="qa-chat-body">
      <!-- Welcome -->
      <div v-if="!messages.length" class="qa-welcome">
        <div class="qa-welcome-icon">?</div>
        <p class="qa-welcome-title">小游戏数据分析助手</p>
        <p class="qa-welcome-desc">
          基于本地数据库的排行榜数据，为你解答小游戏市场相关问题。
          支持排名查询、品类分析、趋势洞察等。
        </p>
        <div class="qa-quick-grid">
          <button
            v-for="q in QUICK_QUESTIONS"
            :key="q"
            class="qa-quick-btn"
            @click="askQuick(q)"
          >{{ q }}</button>
        </div>
      </div>

      <!-- Messages -->
      <template v-for="(msg, i) in messages" :key="i">
        <div class="qa-msg" :class="msg.role">
          <div class="qa-msg-avatar">
            {{ msg.role === "user" ? "U" : "AI" }}
          </div>
          <div class="qa-msg-content">
            <div class="qa-msg-bubble" :class="msg.role">
              <div class="qa-msg-text">{{ msg.content }}</div>
              <div v-if="msg.sources && msg.sources.length" class="qa-msg-sources">
                <span
                  v-for="s in msg.sources"
                  :key="s"
                  class="qa-source-tag"
                >{{ s }}</span>
              </div>
            </div>
            <span class="qa-msg-time">{{ msg.timestamp }}</span>
          </div>
        </div>
      </template>

      <!-- Loading -->
      <div v-if="loading" class="qa-msg assistant">
        <div class="qa-msg-avatar">AI</div>
        <div class="qa-msg-content">
          <div class="qa-msg-bubble assistant qa-typing">
            <span class="dot"></span>
            <span class="dot"></span>
            <span class="dot"></span>
          </div>
        </div>
      </div>
    </div>

    <!-- Input Area (fixed at bottom when messages exist) -->
    <div class="qa-input-area">
      <div v-if="messages.length" class="qa-quick-row">
        <button
          v-for="q in QUICK_QUESTIONS"
          :key="q"
          class="qa-quick-chip"
          :disabled="loading"
          @click="askQuick(q)"
        >{{ q }}</button>
      </div>
      <div class="qa-input-row">
        <input
          v-model="input"
          class="qa-input"
          placeholder="输入问题，如：传奇类游戏今天排名情况？"
          :disabled="loading"
          @keydown.enter="submit"
        />
        <button
          class="qa-send"
          :disabled="loading || !input.trim()"
          @click="submit"
        >
          {{ loading ? "思考中…" : "发送" }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.qa-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 50px);
  max-width: 900px;
  margin: 0 auto;
}

.qa-header {
  padding: 16px 20px 12px;
  border-bottom: 1px solid #e2e8f0;
  background: #fff;
  flex-shrink: 0;
}
.qa-header h1 {
  margin: 0 0 10px;
  font-size: 1.3rem;
  font-weight: 800;
  color: #0f172a;
}
.qa-tabs {
  display: flex;
  gap: 6px;
}
.qa-tabs button {
  padding: 5px 12px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #64748b;
  font-weight: 600;
  font-size: 12px;
  cursor: pointer;
}
.qa-tabs button.on {
  border-color: #2563eb;
  color: #1d4ed8;
  background: rgba(37, 99, 235, 0.08);
}

/* Chat Body */
.qa-chat-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: #f8fafc;
}

/* Welcome */
.qa-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
}
.qa-welcome-icon {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  color: #fff;
  font-size: 28px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
}
.qa-welcome-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}
.qa-welcome-desc {
  margin: 0 0 24px;
  font-size: 13px;
  color: #64748b;
  text-align: center;
  max-width: 400px;
  line-height: 1.6;
}
.qa-quick-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  max-width: 500px;
  width: 100%;
}
.qa-quick-btn {
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #334155;
  font-size: 13px;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
  line-height: 1.4;
}
.qa-quick-btn:hover {
  border-color: #2563eb;
  color: #1d4ed8;
  background: rgba(37, 99, 235, 0.04);
}

/* Messages */
.qa-msg {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.qa-msg.user {
  flex-direction: row-reverse;
}
.qa-msg-avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}
.qa-msg.user .qa-msg-avatar {
  background: #2563eb;
  color: #fff;
}
.qa-msg.assistant .qa-msg-avatar {
  background: #f1f5f9;
  color: #475569;
  border: 1px solid #e2e8f0;
}
.qa-msg-content {
  max-width: 75%;
  min-width: 0;
}
.qa-msg.user .qa-msg-content {
  align-items: flex-end;
  display: flex;
  flex-direction: column;
}
.qa-msg-bubble {
  padding: 10px 14px;
  border-radius: 12px;
  line-height: 1.6;
}
.qa-msg-bubble.user {
  background: #2563eb;
  color: #fff;
  border-bottom-right-radius: 4px;
}
.qa-msg-bubble.assistant {
  background: #fff;
  color: #0f172a;
  border: 1px solid #e2e8f0;
  border-bottom-left-radius: 4px;
}
.qa-msg-text {
  font-size: 14px;
  white-space: pre-wrap;
  word-break: break-word;
}
.qa-msg-sql {
  margin-top: 8px;
  padding: 8px 10px;
  background: #f1f5f9;
  border-radius: 6px;
  font-size: 11px;
  overflow-x: auto;
}
.qa-sql-label {
  font-weight: 700;
  color: #475569;
  margin-right: 6px;
}
.qa-msg-sql code {
  color: #334155;
  font-family: "Consolas", "Monaco", monospace;
  font-size: 11px;
}
.qa-msg-sources {
  margin-top: 6px;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.qa-source-tag {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f0f9ff;
  color: #0369a1;
  border: 1px solid #bae6fd;
}
.qa-msg-time {
  font-size: 10px;
  color: #94a3b8;
  margin-top: 4px;
}

/* Typing animation */
.qa-typing {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 18px;
}
.qa-typing .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #94a3b8;
  animation: typing 1.2s ease-in-out infinite;
}
.qa-typing .dot:nth-child(2) { animation-delay: 0.2s; }
.qa-typing .dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing {
  0%, 100% { opacity: 0.3; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1); }
}

/* Input Area */
.qa-input-area {
  flex-shrink: 0;
  padding: 12px 20px 16px;
  border-top: 1px solid #e2e8f0;
  background: #fff;
}
.qa-quick-row {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 10px;
  margin-bottom: 2px;
}
.qa-quick-chip {
  padding: 5px 10px;
  border-radius: 14px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #475569;
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}
.qa-quick-chip:hover:not(:disabled) {
  border-color: #2563eb;
  color: #1d4ed8;
}
.qa-quick-chip:disabled { opacity: 0.5; cursor: not-allowed; }
.qa-input-row {
  display: flex;
  gap: 8px;
}
.qa-input {
  flex: 1;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid #cbd5e1;
  font-size: 14px;
  color: #0f172a;
  outline: none;
  background: #f8fafc;
}
.qa-input:focus {
  border-color: #2563eb;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}
.qa-send {
  padding: 10px 20px;
  border-radius: 10px;
  border: none;
  background: #2563eb;
  color: #fff;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
}
.qa-send:disabled { opacity: 0.5; cursor: not-allowed; }
.qa-send:not(:disabled):hover { background: #1d4ed8; }

@media (max-width: 640px) {
  .qa-quick-grid { grid-template-columns: 1fr; }
  .qa-msg-content { max-width: 85%; }
}
</style>
