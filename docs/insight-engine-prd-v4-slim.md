# 分析引擎扩展 PRD — 精简版（v4.0 · 实现对照）

---

| 字段 | 内容 |
|------|------|
| **版本** | v4.0 slim |
| **日期** | 2026-03-30 |
| **用途** | 本仓库开发对照：表结构、API、验收、与现有表关系 |
| **完整版** |  sister 文档仓：`minigame-tracker-fortencent-yyb/docs/superpowers/specs/2026-03-30-insight-engine-prd-v4.md` |

---

## 1. 范围

在现有 **九榜采集 + `games` / `rankings` / `snapshots` / `yyb_tag_stats` + `genre_major|minor`** 之上，增量四类能力：

1. **玩法追踪** — `gameplay_tags` 与 `genre_*` **并行**  
2. **买量追踪** — ADX 素材入库（合规允许时自动化，否则导入）  
3. **变现分析** — 结构化落库 + 规则 + LLM  
4. **裂变假设** — 不外爬，AI checklist + 审计字段  

**已确认**：无登录；表预留 `updated_by`、`source`（及等价审计列）。

---

## 2. 与现有库表关系

```text
games (已有: appid, tags, genre_major, genre_minor, description, ...)
  ├── game_gameplay_tags ──► gameplay_tags
  ├── game_monetization    (或 games 上扩展列，二选一由实现定)
  └── virality_assumptions (或 games.virality_json，二选一)

rankings (不变)
ad_creatives (+ 可选 ad_creative_snapshots)
```

---

## 3. 建议表结构（SQLite）

### 3.1 `gameplay_tags`

| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | |
| slug | TEXT UNIQUE | 英文键，如 `loot_box` |
| name | TEXT | 展示名 |
| parent_id | INTEGER NULL | 可选层级 |
| description | TEXT NULL | |
| created_at | TEXT | ISO |

### 3.2 `game_gameplay_tags`

| 列 | 类型 | 说明 |
|----|------|------|
| appid | TEXT FK → games.appid | |
| tag_id | INTEGER FK | |
| role | TEXT NULL | `primary` / `secondary` 等 |
| evidence | TEXT NULL | 短文本或 JSON |
| source | TEXT | `rule` \| `ai` \| `manual` |
| updated_by | TEXT NULL | 人工标识，无账号时为工号/昵称 |
| updated_at | TEXT | |

`UNIQUE(appid, tag_id)` 建议。

### 3.3 `game_monetization`（独立表推荐，便于历史版本时可再拆）

| 列 | 类型 | 说明 |
|----|------|------|
| appid | TEXT PK FK | 或与 `effective_at` 组成复合主键若需历史 |
| monetization_model | TEXT | `iaa` \| `iap` \| `hybrid` \| `unknown` |
| mix_note | TEXT NULL | |
| confidence | REAL NULL | 0–1 或改 TEXT `low/med/high` |
| evidence_summary | TEXT NULL | JSON 数组字符串 |
| ad_placement_notes | TEXT NULL | 可选 |
| source | TEXT | `ai` \| `manual` |
| updated_by | TEXT NULL | |
| updated_at | TEXT | |

### 3.4 `virality_assumptions`

| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | |
| appid | TEXT FK | |
| channels | TEXT NULL | JSON 数组，如 `["wechat_share","douyin_mount"]` |
| hypothesis | TEXT | |
| evidence | TEXT NULL | 引用 description/tags/内部纪要 |
| confidence | REAL NULL | |
| source | TEXT | `ai` \| `manual` |
| updated_by | TEXT NULL | |
| updated_at | TEXT | |

### 3.5 `ad_creatives`

| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | |
| external_id | TEXT NULL | ADX 侧 ID |
| vendor | TEXT NULL | 如 `adx` |
| game_name_raw | TEXT NULL | |
| matched_appid | TEXT NULL FK | 人工确认后填入 |
| title | TEXT NULL | |
| metrics_json | TEXT NULL | 曝光等原始可解析字段 |
| page_url | TEXT NULL | |
| video_sha256 | TEXT NULL | 与 `media_cache` 对齐可复用 |
| video_path | TEXT NULL | 相对工程的路径或留空仅 URL |
| thumb_sha256 | TEXT NULL | |
| first_seen_at | TEXT | |
| last_seen_at | TEXT | |
| source | TEXT | `import` \| `adx_rpa` 等 |
| imported_by | TEXT NULL | |

可选：`ad_creative_snapshots(ad_creative_id, date, metrics_json)`。

---

## 4. API 清单（建议）

实现时与 FastAPI 路由风格保持一致；以下为逻辑分组。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/game/{appid}` | 已扩展：`date`、`include=gameplay,monetization,virality`；含 `same_genre_peers`、`snapshot_date` |
| GET | `/api/gameplay/tags` | 词表 |
| POST | `/api/gameplay/assign` | 绑定 appid ↔ tag（body：`GameplayAssignBody`） |
| POST | `/api/monetization/upsert` | 单行写入/更新 |
| POST | `/api/monetization/run` | 占位：批量 LLM 未实现 |
| POST | `/api/virality/upsert` | 新增一条假设 |
| POST | `/api/virality/generate` | 占位：AI 未实现 |
| GET | `/api/gameplay/games?date=&platform=` | （可选）带标签的榜内游戏 |
| GET | `/api/ad_creatives` | 分页筛选（买量模块） |
| POST | `/api/ad_creatives/import` | 上传 CSV/JSON |
| GET | `/api/ad_creatives/{id}/file` | 授权下载视频 |

详情弹窗统一用 `GET /api/game/{appid}?include=gameplay,monetization,virality`。

---

## 5. 验收标准（P0）

- [x] 玩法：表 + `assign` + 详情 `include=gameplay`；生产用 `POST /api/insight/infer-batch`（或 `monetization/run`、`virality/generate`）+ 手动 upsert；`seed_insight_demo` 仅 dev（需 `MINIGAME_ALLOW_DEMO_SEED=1`），误灌用 `scripts/cleanup_seed_insight_demo.py`  
- [x] 变现：`upsert` + 详情 `include=monetization`；批量 LLM 仍为占位 `/api/monetization/run`  
- [x] 裂变：`upsert` + 详情 `include=virality`；`/api/virality/generate` 占位  
- [x] 同榜同类：`GET /api/game/{appid}?date=` + `same_genre_peers`；[`GameModal`](frontend/src/components/GameModal.vue) 展示并可点选切换游戏  
- [ ] 买量：**若未获批 RPA**：CSV/JSON 导入可写入 `ad_creatives` 并在列表页展示；获批后单独里程碑验收自动化。  
- [x] 写入路径支持 `source` / `updated_by`（assign/upsert body）  

---

## 6. 实现度对照（维护用）

| 项 | 状态 | 备注 |
|----|------|------|
| 九榜采集 | 已有 | |
| genre 分类 | 已有 | `backend/analyzer/classify.py` |
| 玩法并行标签 | **已做（详情入口）** | `gameplay_tags` / `game_gameplay_tags`，`GameModal` |
| 变现结构化 | **已做（详情入口）** | `game_monetization`，`POST /api/monetization/upsert` |
| 裂变假设 | **已做（详情入口）** | `virality_assumptions`，`POST /api/virality/upsert` |
| 同榜同类 | **已做** | `same_genre_peers` |
| ADX 素材 | 待做 | 合规后分导入 / RPA |

---

## 7. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-03-30 | 初版：与 v4 完整版及需求确认一致 |
| 2026-03-30 | 详情富化衔接：表结构、game API include、GameModal、seed_insight_demo |
