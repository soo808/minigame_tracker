# 微信 & 抖音小游戏榜单追踪系统 — 设计文档 v3.1

**日期：** 2026-03-24（v3.1 移除飞书；采集窗口 11:00–11:20、11:30 截止、缩短榜间间隔、取消 14:00 自动兜底，改手动 ingest）
**状态：** 待实施
**阶段：** 一期 — 微信 + 抖音小游戏六榜（微信：人气 / 畅玩 / 畅销；抖音：人气 / 畅销 / 新游）

**v3.1 变更说明：** 一期不再集成飞书（或钉钉等）即时推送；异常与运维信息通过 **结构化日志** 与 **`GET /api/status`** 可观测。可选 IM 推送列入二期。

---

## 一、背景与目标

构建一个自动化工具，每天无人值守采集微信和抖音小游戏官方六个榜单数据，追踪产品名次变化，提供 Web 可视化看板（参考大鹅盯榜风格）。运维与排障依赖服务日志及各榜采集状态接口，不外呼即时通讯。

**数据来源：** 引力引擎（`rank.gravity-engine.com`）—— 第三方整合平台，汇聚微信和抖音两平台官方榜单数据，每日 11:00 前更新完毕。账号已获得授权访问权限。

**一期范围：**
- 微信小游戏：人气榜 / 畅玩榜 / 畅销榜（各 Top 100）
- 抖音小游戏：人气榜 / 畅销榜 / 新游榜（各 Top 100）
- 公司内网访问，100~200 并发用户，无登录验证

---

## 二、整体架构

```
[引力引擎 API - rank.gravity-engine.com]
  POST /apprank/api/v1/rank/list/
  认证：JWT Bearer + 动态签名（MD5）
  响应：AES 加密密文 → Python 解密
  采集时间：每日 11:00~11:20 内随机触发；全部请求与写入须不晚于 11:30
  每次采集 6 个榜单，各间隔 2~8 秒随机（实现上随距 11:30 剩余时间收紧上限）

         ↓ 内网数据库直写（采集器与后端同容器）

[服务端 - 公司 NAS，Intel N150，x86_64，12GB RAM]

  ┌──────────────────────────────────────────────┐
  │  gateway（共享网关，端口 :80）                 │
  │  nginx:1.26                                  │
  │  ├── /           → google-tracker（现有服务） │
  │  ├── /minigame-tracker/ → wechat-backend:8000 │
  │  └── /douyin/    → （wechat-backend 同服务）  │
  └──────────────────────────────────────────────┘
           │
           ↓
  [wechat-tracker]
  FastAPI + SQLite(WAL)
  + APScheduler（内置采集调度）
  + Vue3 静态文件

  所有容器通过 Docker 网络 tracker-net 互联，
  均不对宿主机暴露端口，只走网关
```

一期不向飞书/钉钉等 Webhook 推送。采集异常、JWT 过期等写入 **ERROR 级别日志**（含榜单、平台、`code`、是否鉴权失败），并通过 **`GET /api/status`** 查看各榜 `snapshots` 状态。

> **待确认：** Google 榜单追踪的容器名，运行 `docker ps --format "table {{.Names}}\t{{.Ports}}"` 查看，填入网关 nginx.conf 的 `proxy_pass` 地址。

**设计原则：**
- 采集器与服务端合并部署在 NAS：无需 Windows PC，不依赖 WeChat 客户端
- 共享网关：所有榜单追踪服务统一由一个 Nginx 管理，新增服务只需加 `location` 块
- 服务端单写（FastAPI 是唯一写入方），SQLite WAL 模式支持 100~200 并发读
- 采集失败不影响服务可用性

---

## 三、数据采集方案

### 3.1 数据源

**引力引擎**（`api-insight.gravity-engine.com`）

| 属性 | 值 |
|------|----|
| 接口 | `POST /apprank/api/v1/rank/list/` |
| 认证 | JWT Bearer Token（7 天有效期）+ 动态请求签名 |
| 榜单覆盖 | 微信小游戏 × 3 + 抖音小游戏 × 3，各 Top 100 |
| 数据更新时间 | 每日约 10:00 平台出数，引力引擎约 11:00 完成处理 |
| 采集窗口 | 11:00 ~ 11:20 随机触发（Asia/Shanghai）；**11:30 硬截止**（未完成榜记 `failed`，`note=deadline_1130`） |

### 3.2 请求结构

```python
# 请求体
{
  "page": 1,
  "page_size": 100,
  "extra_fields": {"change_label": True, "app_genre_ranking": True},
  "filters": [
    {"field": "rank_type",     "operator": 1, "values": ["popularity"]},  # popularity|revenue|playtime
    {"field": "rank_genre",    "operator": 1, "values": ["wx_minigame"]}, # wx_minigame|dy_minigame（待验证）
    {"field": "stat_datetime", "operator": 1, "values": ["2026-03-24"]},
  ]
}
```

**六个榜单组合（待验证 rank_type 和 rank_genre 的实际枚举值）：**

| platform | rank_genre | rank_type | 说明 |
|----------|-----------|-----------|------|
| 微信 | `wx_minigame` | `popularity` | 微信人气榜 |
| 微信 | `wx_minigame` | `bestseller` | 微信畅销榜 |
| 微信 | `wx_minigame` | `most_played` | 微信畅玩榜 |
| 抖音 | `dy_minigame` | `popularity` | 抖音人气榜 |
| 抖音 | `dy_minigame` | `bestseller` | 抖音畅销榜 |
| 抖音 | `dy_minigame` | `fresh_game` | 抖音新游榜 |

> **注：** 所有枚举值已于 2026-03-24 实测确认，六榜均返回 `code=0`。微信有畅玩榜（`most_played`），抖音无畅玩榜，对应为新游榜（`fresh_game`）。其他可用 rank_type：`free`（免费榜），本期不采集。

### 3.3 认证与签名算法

**JWT Token**（Authorization 头）
- 有效期 7 天，需每 7 天手动从浏览器 DevTools 更新
- 到期后 API 返回非 200 状态；采集器检测到时 **打 ERROR 日志**（明确提示更新 JWT）并写入失败 `snapshots`

**动态签名**（已通过 JS bundle 逆向确认）：
```python
import hashlib, base64, random, string, time, json

def make_session() -> str:
    """生成 gravity-session: base64(etg + 5位随机字母数字)"""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
    return base64.b64encode(("etg" + suffix).encode()).decode()

def make_signature(timestamp_ms: int, session_b64: str, body: dict) -> str:
    """MD5(timestamp[3:8] + '11' + session_b64 + JSON.stringify(body))"""
    ts_slice = str(timestamp_ms)[3:8]
    body_json = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    raw = ts_slice + "11" + session_b64 + body_json
    return hashlib.md5(raw.encode("utf-8")).hexdigest()
```

必需请求头（每次请求重新生成 timestamp/session/signature）：
```python
{
    "Authorization": f"Bearer {JWT_TOKEN}",
    "Gravity_Id": GRAVITY_ID,
    "gravity_Cid": GRAVITY_CID,
    "gravity_Super": "true",
    "gravity_Email": GRAVITY_EMAIL,
    "gravity-timestamp": str(timestamp_ms),
    "gravity-session": session_b64,
    "gravity-signature": signature,
}
```

### 3.4 响应解密

API 响应结构：
```json
{"data": {"text": "<AES加密后的Base64密文>"}, "code": 0, "msg": "成功"}
```

`data.text` 为 AES 加密密文，解密密钥位于前端 JS bundle（`Home-DQoFfVR_js.js`）。

**解密实现步骤（实施前执行）：**
1. DevTools → Sources → `Home-DQoFfVR_js.js` → 格式化 → 搜索 `decrypt`
2. 找到 AES key 和 iv，在 `collector/config.py` 的 `GRAVITY_AES_KEY` / `GRAVITY_AES_IV` 填入
3. 解密代码：
   ```python
   from Crypto.Cipher import AES
   import base64

   def decrypt_response(text: str) -> list:
       cipher = AES.new(GRAVITY_AES_KEY.encode(), AES.MODE_CBC,
                        iv=GRAVITY_AES_IV.encode())
       plain = cipher.decrypt(base64.b64decode(text))
       # 去除 PKCS7 padding
       pad = plain[-1]
       return json.loads(plain[:-pad].decode("utf-8"))
   ```

**备用方案（若无法获取解密密钥）：** 使用 Playwright 无头浏览器渲染页面，抓取已解密的 DOM 表格，浏览器自动完成解密。

### 3.5 采集流程（每日随机窗口自动执行）

```
APScheduler 每日启动时注册当日任务（11:00~11:20 内随机触发；早于 11:00 则落在窗口内随机时刻）
  └── collect_all_charts()
        ├── 依次采集 6 个榜单（随机顺序；榜间 2~8s 随机，且随距 11:30 剩余时间缩短上限）
        ├── 每榜：POST → 解密 → 解析排名列表 → 写入 DB（rankings + snapshots）
        ├── 若当前时刻 ≥ 当日 11:30：未执行榜不再请求，写入 snapshots(status=failed, note=deadline_1130)
        ├── 全部六榜到齐且均为 ok/partial 时：run_analysis(today)（批次门控，见 §五）
        └── 任意榜单失败：记录 ERROR 日志；**无**定时自动部分分析，缺数由运维手动 POST /api/ingest 补写
```

**总目标：** 在 **11:30 前** 跑完六榜（含间隔）；实际耗时常约 1 分钟内，视网络与解密耗时而定。

### 3.6 采集字段

| 字段 | 来源 | 是否必需 | 备注 |
|------|------|---------|------|
| 游戏名（name） | 解密后 JSON | **必需** | 缺失则丢弃该条目 |
| AppID / 游戏标识符 | 解密后 JSON | **必需** | 缺失则丢弃 |
| 排名（rank） | 按列表顺序（1-based） | **必需** | 若 JSON 含显式排名字段则优先使用 |
| 图标 URL（icon_url） | 解密后 JSON | 可选 | 缺失时 UI 显示占位图 |
| 平台（platform） | 请求参数推断 | **必需** | `wx` 或 `dy` |
| 开发商（developer） | 解密后 JSON | 可选 | 缺失时详情弹窗隐藏开发商行 |
| 标签（tags） | 解密后 JSON | 可选 | 缺失时不显示标签 |

> **注：** 实际字段结构需在成功采集后对照 `data.text` 解密结果确认，上表为预期结构。

### 3.7 兜底机制

| 触发条件 | 处理方式 |
|---------|---------|
| JWT 过期（401/403） | ERROR 日志（说明 Token 过期与更新步骤）；对应榜 `snapshots.status=failed` |
| 单个榜单采集失败 | ERROR 日志（平台、榜单、异常）；其余榜单照常 |
| 当日全部榜单失败 | ERROR 日志汇总；服务继续展示历史数据 |
| 超过 11:30 仍未执行的榜 | 不再请求接口；写入 `failed` + `note=deadline_1130` |
| 当日未凑齐六榜或需改数 | **无** 14:00 自动任务；由运维通过 **`POST /api/ingest`** 手工补写/更正，并在 `snapshots.note` 标明来源（如 `manual_fix`） |

> 若后续需要 IM 提醒，可在二期接入飞书/钉钉 Webhook，**不在一期范围**。

### 3.8 JWT 更新流程（每 7 天）

1. 登录 `rank.gravity-engine.com`
2. 切换任意榜单，触发 API 请求
3. F12 → Network → 找到 `rank/list/` 请求 → Headers 复制 `Authorization` 值
4. 更新 `collector/config.py` 中的 `GRAVITY_JWT`
5. 重启服务（`docker compose restart wechat-backend`）

**自动化 Token 刷新（二期可选）：** 使用 Playwright 模拟登录引力引擎获取新 JWT，无需人工介入。

---

## 四、数据库设计（SQLite，WAL 模式）

### 4.1 games — 游戏主表

```sql
CREATE TABLE games (
  appid         TEXT PRIMARY KEY,   -- 游戏唯一标识（AppID 或平台内部 ID）
  platform      TEXT NOT NULL,      -- 'wx' | 'dy'
  name          TEXT NOT NULL,
  description   TEXT,
  icon_url      TEXT,
  tags          TEXT,               -- JSON 数组
  developer     TEXT,
  first_seen    DATE,
  updated_at    DATETIME
);
```

**games upsert 策略：**
```sql
INSERT INTO games (appid, platform, name, icon_url, tags, developer, first_seen, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(appid) DO UPDATE SET
  name        = excluded.name,
  icon_url    = COALESCE(excluded.icon_url, icon_url),
  tags        = COALESCE(excluded.tags, tags),
  developer   = COALESCE(excluded.developer, developer),
  updated_at  = excluded.updated_at;
```

### 4.2 rankings — 每日排名记录

```sql
CREATE TABLE rankings (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  date          DATE NOT NULL,
  platform      TEXT NOT NULL,      -- 'wx' | 'dy'
  chart         TEXT NOT NULL,      -- 微信: 'popularity'|'bestseller'|'most_played'  抖音: 'popularity'|'bestseller'|'fresh_game'
  rank          INTEGER NOT NULL,
  appid         TEXT NOT NULL REFERENCES games(appid),
  UNIQUE(date, platform, chart, appid)
);
CREATE INDEX idx_rankings_date ON rankings(date, platform, chart);
CREATE INDEX idx_rankings_appid ON rankings(appid);
```

**重复写入策略（upsert）：**
```sql
INSERT INTO rankings (date, platform, chart, rank, appid)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(date, platform, chart, appid) DO UPDATE SET rank = excluded.rank;
```

### 4.3 daily_status — 每日新进/跌出标记

```sql
CREATE TABLE daily_status (
  date          DATE    NOT NULL,
  platform      TEXT    NOT NULL,
  chart         TEXT    NOT NULL,
  appid         TEXT    NOT NULL REFERENCES games(appid),
  is_new        INTEGER NOT NULL DEFAULT 0,
  is_dropped    INTEGER NOT NULL DEFAULT 0,
  rank_delta    INTEGER,            -- 负=上升，正=下滑，NULL=新进
  PRIMARY KEY (date, platform, chart, appid)
);
```

**跌出榜行写入机制：** 由 analyzer.py 在六榜全部到齐后，查询昨日在榜、今日缺席的 appid，插入 `is_dropped=1` 行。

### 4.4 snapshots — 原始快照记录

```sql
CREATE TABLE snapshots (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  date          DATE NOT NULL,
  platform      TEXT NOT NULL,
  chart         TEXT NOT NULL,
  fetched_at    DATETIME NOT NULL,
  status        TEXT NOT NULL,      -- 'ok' | 'failed' | 'partial'
  game_count    INTEGER,
  note          TEXT,
  UNIQUE(date, platform, chart)
);
```

---

## 五、分析层

**触发时机：** 六个榜单全部到齐后触发（批次门控）。

**批次门控机制：**
```python
REQUIRED_CHARTS = {
    ("wx", "popularity"), ("wx", "bestseller"), ("wx", "most_played"),
    ("dy", "popularity"), ("dy", "bestseller"), ("dy", "fresh_game"),
}

received = set(
    (row.platform, row.chart)
    for row in db.execute(
        "SELECT platform, chart FROM snapshots WHERE date=? AND status IN ('ok','partial')",
        [today]
    )
)
if received == REQUIRED_CHARTS:
    run_analysis(today)
```

**说明（一期）：** 不在固定时刻做「部分榜单」自动分析。若当日仅部分榜成功、或截止后人工补 ingest，**仅当** `received == REQUIRED_CHARTS`（六键齐全且状态为 `ok`/`partial`）时触发 `run_analysis`；否则依赖人工补全数据后再由下一次写入触发门控。

**`run_analysis` 函数签名：** `def run_analysis(date: str, charts: set = None) -> None`（`charts` 参数保留供实现或测试使用，**一期调度路径不调用部分分析**。）

**rank_delta 符号约定：**
- 负数 = 名次上升（如 10→5，delta = -5）
- 正数 = 名次下滑
- NULL = 当日新进榜

**新进/跌出判定：**
- `is_new = 1`：过去 7 天在该平台+榜单无记录
- `is_dropped = 1`：昨日有记录，今日无记录

```
analyzer/
├── status.py      # 计算新进/跌出/rank_delta，写入 daily_status
└── trends.py      # 按需计算 7日/30日趋势（供 API 查询时调用）
```

---

## 六、Web Dashboard

### 6.1 主榜单页

**平台切换 Tab + 三列榜单布局**（每次显示一个平台的三个榜单）：

```
┌─────────────────────────────────────────────────────────┐
│  [微信小游戏] [抖音小游戏]    [← 2026-03-24 →]  [今日]  │
├────────────────┬────────────────┬────────────────────────┤
│  微信：人气榜   │  微信：畅销榜   │  微信：畅玩榜           │
│  抖音：人气榜   │  抖音：畅销榜   │  抖音：新游榜           │
├────────────────┼────────────────┼────────────────────────┤
│ 1  [图]游戏名 🆕 [小折线图标]   │ 1  [图]游戏名  ...     │
│    一句话描述                    │                        │
│    [标签] [标签]  ▲3             │                        │
│ 2  [图]游戏名 出 [小折线图标]   │ 2  ...                  │
│ ...                              │                        │
└────────────────┴────────────────┴────────────────────────┘
```

**交互说明：**

| 元素 | 交互 |
|------|------|
| 平台 Tab（微信/抖音） | 切换展示平台，URL 参数 `?platform=wx|dy` |
| 右上角日期选择器 | 切换查看任意历史日期快照 |
| 「今日」按钮 | 跳转到最新一天 |
| 绿色「新」标签 | 今日新进榜 |
| 灰色「出」标签 | 今日跌出（显示在列表最底部，置灰） |
| ▲3 / ▼2 | 与昨日名次变化 |
| 鼠标 hover 折线图标 | 弹出 tooltip，显示该游戏近 7 日在该榜的名次曲线 |
| 点击游戏卡片 | 弹出游戏详情弹窗 |

**当日数据与采集截止：** 看板只展示库中已有数据。自动采集须在 **11:30** 前完成各榜写入；未成功或未执行的榜见 **`GET /api/status`**（如 `failed`、`note=deadline_1130`）。**六榜未齐时** 批次门控不会跑满量 `run_analysis`，新进/跌出等依赖分析的展示仅对**已分析过的日期**生效；补数后由运维 **`POST /api/ingest`** 写入，待六榜齐后自动分析。

### 6.2 游戏详情弹窗

```
┌────────────────────────────────────────────┐
│ [图标]  游戏名称                    [×]    │
│          开发商名称                         │
│          [平台标签] [标签] [标签]           │
├────────────────────────────────────────────┤
│  近 30 日排名走势（所在平台三榜）           │
│  ─── 人气榜  ─── 畅玩榜  ─── 畅销榜        │
│  [折线图，Y 轴反转，hover 显示日期和名次]  │
├────────────────────────────────────────────┤
│  一句话描述                                 │
└────────────────────────────────────────────┘
```

### 6.3 API 端点

以下路径为 FastAPI 内部路由；浏览器访问为 `/minigame-tracker/api/...`，网关剥离 `/minigame-tracker/` 后转发到后端 `/api/...`（后端亦可直连并靠中间件识别 `/minigame-tracker/api`）。

| 端点 | 方法 | 参数 | 返回 |
|------|------|------|------|
| `/api/rankings` | GET | `date?`, `platform`（wx\|dy，默认 wx） | 指定平台三榜当日排名列表 |
| `/api/game/{appid}` | GET | `days=30` | 游戏基本信息 + 近 N 日各榜名次历史 |
| `/api/game/{appid}/sparkline` | GET | `chart`, `days=7` | 近 7 日名次数组 |
| `/api/dates` | GET | `platform?` | 有数据的日期列表 |
| `/api/ingest` | POST | JSON body | 数据写入入口（采集器内部调用） |
| `/api/status` | GET | — | 各榜采集状态 |

**`/api/rankings` 返回结构：**
```json
{
  "date": "2026-03-24",
  "platform": "wx",
  "charts": {
    "renqi":   {"entries": [{"rank": 1, "appid": "wx...", "name": "...", "is_new": false, "is_dropped": false, "rank_delta": -3, ...}]},
    "changwan": {"entries": [...]},
    "changxiao": {"entries": [...]}
  }
}
```

**`/api/ingest` 请求体 schema：**
```json
{
  "date": "2026-03-24",
  "platform": "wx",
  "chart": "renqi",
  "games": [
    {"rank": 1, "appid": "wx1234", "name": "...", "icon_url": "...", "tags": [], "developer": null}
  ]
}
```

**`rank_delta` 前端显示约定：**
- `rank_delta < 0` → `▲{abs(rank_delta)}`（绿色）
- `rank_delta > 0` → `▼{rank_delta}`（红色）
- `rank_delta === 0` → 不显示
- `rank_delta === null` → 「新」标签（is_new）或不显示（is_dropped）

**Vue3 构建配置：** `vite.config` 设置 `base: '/minigame-tracker/'`；`src/config.js` 中 `apiUrl()` 使用 `import.meta.env.BASE_URL` 拼接 API 路径。

---

## 七、通知与可观测性（一期）

- **无 Webhook：** 不向飞书、钉钉等外部系统推送消息。
- **日志：** 采集与鉴权失败使用 ERROR，成功批次可用 INFO；字段建议包含 `platform`、`chart`、`date`、HTTP 状态或业务 `code`。
- **接口：** `GET /api/status` 返回各榜 `snapshots`（`date`、`platform`、`chart`、`status`、`fetched_at`、`game_count`），供看板或运维脚本轮询。
- **看板：** 新进/跌出/名次变化均在 Web UI 展示（`daily_status` + `rankings`），不依赖推送。

---

## 八、部署方案

### 8.1 硬件环境

| 机器 | 用途 | 系统 | 规格 |
|------|------|------|------|
| 公司 NAS | 服务端 + 采集端（全部合并） | Linux（NAS 原生 OS） | Intel N150，x86_64，12GB RAM |

> **说明：** 采集器不再需要 Windows PC。引力引擎 API 为标准 HTTPS 接口，直接在 NAS Docker 容器内运行 Python 采集脚本，无需 WeChat 客户端或 mitmproxy。

---

### 8.2 NAS 目录结构（服务端）

```
/nas/docker/
├── gateway/                  # 共享网关（唯一监听 :80 的容器）
│   ├── docker-compose.yml
│   └── nginx.conf
├── google-tracker/           # 现有 Google 榜单服务（迁移后）
│   └── docker-compose.yml
└── wechat-tracker/           # 本项目
    ├── docker-compose.yml
    ├── backend/
    ├── frontend/dist/
    └── data/
```

---

### 8.3 共享 Docker 网络

```bash
# 首次部署时执行一次（幂等）
docker network create tracker-net
```

---

### 8.4 共享网关（gateway/）

```yaml
# gateway/docker-compose.yml
version: "3.9"

services:
  nginx:
    image: nginx:1.26
    container_name: tracker-gateway
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    networks:
      - tracker-net
    restart: unless-stopped

networks:
  tracker-net:
    external: true
```

```nginx
# gateway/nginx.conf
server {
    listen 80;

    # Google 榜单（现有服务）
    # 待确认：替换 <google-tracker-container-name>
    location / {
        proxy_pass http://<google-tracker-container-name>:<port>/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # 微信 & 抖音小游戏榜单（本项目）
    location /minigame-tracker/ {
        proxy_pass http://wechat-backend:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

### 8.5 微信榜单服务（wechat-tracker/）

```yaml
# wechat-tracker/docker-compose.yml
version: "3.9"

services:
  wechat-backend:
    image: python:3.12-slim
    container_name: wechat-backend
    working_dir: /app
    volumes:
      - ./backend:/app
      - ./data:/data
    command: >
      sh -c "pip install -r requirements.txt -q &&
             uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1"
    environment:
      - DB_PATH=/data/tracker.db
    networks:
      - tracker-net
    restart: unless-stopped

networks:
  tracker-net:
    external: true
```

---

### 8.6 现有 Google 榜单服务迁移步骤

```bash
# 步骤 1：创建共享网络（已存在则跳过）
docker network create tracker-net

# 步骤 2：将现有 Google 榜单容器热接入 tracker-net
docker network connect tracker-net <google-tracker-container-name>

# 步骤 3：启动共享网关
cd /nas/docker/gateway
docker compose up -d

# 步骤 4：验证通过网关访问 Google 榜单
curl http://10.9.2.20/

# 步骤 5：部署微信/抖音榜单服务
cd /nas/docker/wechat-tracker
docker compose up -d
```

---

### 8.7 访问地址汇总

| 服务 | 内网地址 | 备注 |
|------|----------|------|
| Google 榜单 | `http://10.9.2.20/` | 迁移后通过网关访问 |
| 微信小游戏榜单 | `http://10.9.2.20/minigame-tracker/?platform=wx` | 本项目 |
| 抖音小游戏榜单 | `http://10.9.2.20/minigame-tracker/?platform=dy` | 本项目（同服务，Tab 切换） |

---

## 九、项目目录结构

```
wechat-minigame-tracker/
├── collector/                   # 采集模块（运行在 NAS Docker，嵌入 backend）
│   ├── gravity.py               # 引力引擎 API 采集器（签名+解密+解析）
│   ├── scheduler.py             # APScheduler：11:00~11:20 随机触发，11:30 截止
│   └── config.py                # 引力引擎认证信息（JWT、用户 ID 等）
│
├── backend/                     # FastAPI 服务端（运行在 NAS Docker）
│   ├── main.py                  # FastAPI 入口 + 路由 + StaticFiles 挂载
│   ├── db.py                    # 数据库初始化 + 连接
│   ├── models.py                # Pydantic 数据模型
│   ├── analyzer/
│   │   ├── status.py            # 计算新进/跌出/rank_delta，写入 daily_status
│   │   └── trends.py            # 7日/30日趋势计算
│   └── requirements.txt
│
├── frontend/                    # Vue3 前端
│   ├── src/
│   │   ├── App.vue
│   │   ├── config.ts            # API_BASE 配置
│   │   ├── views/
│   │   │   └── Rankings.vue     # 主榜单页（含平台 Tab）
│   │   └── components/
│   │       ├── RankColumn.vue   # 单列榜单
│   │       ├── GameCard.vue     # 游戏行卡片
│   │       ├── Sparkline.vue    # 7日迷你折线 tooltip
│   │       └── GameModal.vue    # 游戏详情弹窗
│   ├── vite.config.js           # base: '/minigame-tracker/'
│   └── dist/                    # 构建产物
│
├── data/                        # SQLite 数据库（NAS 持久化卷）
│   └── tracker.db
│
├── nas/                         # NAS 服务端部署配置
│   ├── gateway/
│   │   ├── docker-compose.yml
│   │   └── nginx.conf
│   └── wechat-tracker/
│       └── docker-compose.yml
│
└── docs/
    └── superpowers/specs/
        └── minigame-tracker-wechat-douyin.md
```

**collector/config.py 关键字段模板：**
```python
# 引力引擎认证（JWT 每 7 天更新一次）
GRAVITY_JWT       = "eyJhbGciOiJIUzI1NiIs..."
GRAVITY_ID        = "275008"
GRAVITY_CID       = "269604"
GRAVITY_EMAIL     = "5b9b1f62bb85e17929c74ab6dbf61d09"  # MD5(邮箱)

# 响应解密（从 JS bundle 提取，首次部署前填入）
GRAVITY_AES_KEY   = ""   # 待填入
GRAVITY_AES_IV    = ""   # 待填入

# 榜单枚举（首次采集后验证并修正）
RANK_GENRES = {
    "wx": "wx_minigame",   # 待验证
    "dy": "dy_minigame",   # 已确认
}
RANK_TYPES = {
    # 微信
    "wx_renqi":    ("wx_minigame", "popularity"),   # ✅ 已验证
    "wx_changxiao":("wx_minigame", "bestseller"),   # ✅ 已验证
    "wx_changwan": ("wx_minigame", "most_played"),  # ✅ 已验证
    # 抖音（无畅玩榜，第三榜为新游榜）
    "dy_renqi":    ("dy_minigame", "popularity"),   # ✅ 已验证
    "dy_changxiao":("dy_minigame", "bestseller"),   # ✅ 已验证
    "dy_xinyou":   ("dy_minigame", "fresh_game"),   # ✅ 已验证
}
```

---

## 十、技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| HTTP 采集 | httpx | 最新稳定版 |
| 签名计算 | hashlib（MD5） | Python 内置 |
| 响应解密 | pycryptodome（AES-CBC） | 最新稳定版 |
| 定时调度 | APScheduler（BackgroundScheduler） | 3.x |
| 后端 | FastAPI + Uvicorn | Python 3.12 |
| 数据库 | SQLite（WAL 模式） | 内置 |
| 前端框架 | Vue 3 + Vite | Vue 3.4+ |
| 图表 | ECharts | 5.x |
| 部署 | Docker Compose + Nginx | nginx:1.26 |

---

## 十一、一期不做（范围外）

- 登录验证和用户权限系统
- 自动刷新引力引擎 JWT（手动更新，约每 7 天一次）
- Google Play / App Store 榜单
- 代理/IP 轮换（每天 6 次请求，无需）
- 自动模糊匹配游戏实体（同名不同平台游戏手动处理）
- 微信/抖音游戏大类榜单（手游等）
- 飞书/钉钉等即时消息推送（日报、掉榜、Token 告警）— 若需要列入二期

---

## 十二、后续规划

| 阶段 | 内容 |
|------|------|
| **一期（当前）** | 微信 + 抖音小游戏六榜（引力引擎）；NAS 部署；内网看板；日志 + `/api/status` |
| **二期** | 自动刷新 JWT；按标签/开发商分类筛选；黑马检测；**可选** 飞书/钉钉 Webhook |
| **三期** | Google Play 榜单合并（复用现有 NAS 服务）；App Store |

---

## 十三、首次部署前置步骤

> 在写采集代码之前，需完成以下两项。

### 步骤 1：提取 AES 解密密钥（唯一剩余前置项）

所有 rank_genre 和 rank_type 枚举值已于 2026-03-24 实测确认，六榜均返回 `code=0`。

剩余工作：获取 `data.text` 的解密密钥：
1. DevTools → Sources → `Home-DQoFfVR_js.js` → `{}` 格式化
2. 搜索 `decrypt` 或 `AES`，找到 key 和 iv
3. 填入 `collector/config.py` 的 `GRAVITY_AES_KEY` 和 `GRAVITY_AES_IV`

若无法提取（代码混淆严重），改用 Playwright 无头浏览器方案（在 `collector/gravity.py` 中实现备用采集路径）。
