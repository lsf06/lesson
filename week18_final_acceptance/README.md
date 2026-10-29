# 第18周：系统成果归档与真实复盘报告

> 归档日期：2026-10-23 ｜ 最终版本：v1.0-final（代码目录 `week13_14_15_edge_inference`；**2026-10-29 已补打本地 tag `v1.0-final`**，未 push 远端）
> 归档原则：**以代码、日志、数据库原始记录为准。凡拿不出证据的能力，一律不计入"已完成"。**

---

## 1. 原型运行环境与接口索引

| 项目 | 实际情况 |
| :--- | :--- |
| **硬件** | ESP32-S3-EYE（OV2640 摄像头 + QMA6100P 加速度计 + GPIO0 按键 + 板载 LCD） |
| **运行位置** | 局域网内 PC 上的 Flask（`0.0.0.0:5000`，实测地址 `10.1.41.43:5000`），板子经 Wi-Fi（SSID `431`）直连 |
| **数据存储** | SQLite `server/sensor_data.db`，7 张表：`accelerometer` / `collection_requests` / `trigger_events` / `captured_images` / `vision_results` / `source_states` / `user_preferences` |
| **启动方式** | `python server/app.py`（启动时自动 `init_db()` 建表） |
| **注意** | **数据面已上 VPS**：`https://123.58.43.162:8443`，2026-10-29 实测 `POST /api/data` 返回 `201`（`id=10`）、`GET /api/data` 代理后 `count=4`（见 `week1_vps_upload/README_SUBMIT.md` 0.7 节）；今日只读探活返回 `401`（26ms，服务在线）。**Web 控制台仍只跑在本机局域网** `10.1.41.43:5000`，无自有域名、无生产级 TLS 终止、无 gunicorn/nginx/systemd，见第 5 节 |

### 核心复用接口

| 能力 | 真实位置 | 说明 |
| :--- | :--- | :--- |
| 端侧容错 | `main.c` 的 `cache_enqueue()` | 定长环形队列 `CACHE_QUEUE_SIZE = 20`，满队列丢弃最旧并打印 `QUEUE FULL, dropped oldest record` |
| 并发幂等 | `app.py` 的 `/api/upload` | `BEGIN IMMEDIATE` 显式事务，对同一 `request_id` 串行化校验后再写入 |
| 交互状态机 | 前端 `checkOfflineStatus()` + `source-card-delay` | 每 15s 轮询 `/api/offline_status` 的 `offline_mode` / `banner_text`；补传标记按服务端 `delivery_status` 渲染 |
| **命名更正** | — | 仓库中**不存在** `is_device_offline` / `recent_retransmit_count` 这两个变量，实际实现即上述两处 |

---

## 2. 可运行原型（真实成立、可当场复现）

| # | 能力 | 证据（可核验） |
| :--- | :--- | :--- |
| 1 | 周期性采集与上传（第1周） | QMA6100P I2C 读取，5Hz HTTP POST；`flask.log` 中来自板子 IP `10.1.41.149` 的请求累计 3.6 万（周3）→ 17.9 万条（周13） |
| 2 | 按键触发 + 本地反馈 + 远端 ACK（第3周） | `trigger_events` **203 条**真实记录（周10 起 230 条），`acknowledged_at` / `cancelled_at` 均有值 |
| 3 | 请求下发 / 回执 / 状态机（第2周） | 板子对 `/api/pending_request` 轮询 **47,207 次**；`collection_requests` 中 PENDING / RECEIVED / COMPLETED / CANCELLED / EXPIRED 五种状态均有真实记录 |
| 4 | 按需拍照并落盘（第7周） | `server/static/captured/` 共 **59 张 jpg**，单张 3–8KB 且大小互不相同，人工查看确认为真实场景（室内天花板/货架），非占位图 |
| 5 | 多源状态与"观测时间 vs 接收时间"分离（第10周） | `source_states` 4 行：sensor / network / camera 为真实源；GPS 明确标注 `回放数据-仅供演示（无真实GNSS硬件）` |
| 6 | 用户偏好记录与回退（第12周） | `user_preferences` 3–9 行，含 `config_version` 递增与 `_RESET_` 记录 |
| 7 | 重复 / 过期任务拦截（第15周） | `flask.log`：**229 条** `Duplicate upload ignored`、**3 条** `Task expired receipt recorded`（含 `W15_EXPIRED_TEST`）；DB 中对应 `EXPIRED` / `CANCELLED` 记录 |
| 8 | 断网缓存与恢复补传（第14周） | 见第 3 节，**19 条带双时间戳的真实补传记录** |
| 9 | 点击采集 3 秒倒计时（第17周） | `templates/index.html` 第 578–611 行 `REQ_COUNTDOWN_S=3` / `startReqCountdown()` / `stopReqCountdown()` |

---

## 3. 第14周"断网补传"证据（本次归档新增）

**数据来源**：`D:\esp\lesson-main\week13_14_edge_inference\server\sensor_data.db`（当时的实测环境，非当前仓库内被测试脚本重写过的空库）。
**导出文件**：`week18_final_acceptance/evidence/week14_retransmit_records_20261021.csv`（全部 32 行，含 `delay_s` 与 `is_backfill` 列）。

| 观测项 | 实测值 |
| :--- | :--- |
| 记录总数 | 32 行（`device_id = group01_esp32s3eye`，真实板子 ID） |
| 带 `retransmit_ts` 的补传记录 | **19 条** |
| 补传延迟 `retransmit_ts - original_ts` | 最小 **4 s**、中位 **29 s**、最大 **62 s**（其中 >30 s 共 9 条） |
| 补传到达形态 | 19 条集中落在 `19:38:44 – 19:38:51` 之间一次性涌入（另有 2 条长延迟分别落在 19:42:10、19:53:31） |
| 原采样间隔 | `original_ts` 逐条相差 **4 s / 5 s**，说明是离线期间按原采样节奏排队，恢复后**按原顺序补传**，未被打乱或合并 |
| 恢复后的实时数据 | 13 条 `retransmit_ts = 0` 的记录，从 `19:38:55` 起恢复，采样值为真实重力分量（≈ -0.73 / 0.41 / -1.06） |

**结论**：设备在断网期间确实把观测写入本地环形队列，恢复后携带 `original_ts` 补传，服务端按原观测时间入库 —— 大纲"恢复后旧数据不冒充实时"的要求在**数据层面成立**。

**必须同时说明的局限（不隐瞒）**：该次实测所用构建早于 `delivery_status` 判定逻辑，因此这 19 条的 `delivery_status` 字段全部为 `live`（并非 `recovered`）。也就是说，**补传行为本身有数据铁证，但前端"📦 已接收（补传）"橙色标签的呈现未在这次数据中留痕**，属于"能力已实现、UI 标记待补验一次"。

---

## 4. 遗留问题清单（未达成能力，绝不隐瞒）

| 周次 | 大纲要求 | 实际情况 | 证据 |
| :--- | :--- | :--- | :--- |
| 4-6 | 真实语音输入 → 文本任务 → 语音输出 | 语音入口是**浏览器 Web Speech API**（`SpeechRecognition` + `speechSynthesis`），不是板载麦克风，也没有自建 ASR/TTS 服务；无音频文件留存 | `week5/api` 目录无 audio/ASR 接口；`index.html:391-440` |
| 4 / 13 | 接入授权语言服务、真实云端增强 | **一次都没真跑**。所有周日志均为 `DEEPSEEK_API_KEY is empty, using local rule engine`，无一条 `OpenAI client initialized` | 各周 `flask.log` |
| 8-9 | 接入真实模型推理 | `/api/infer_image` 实际调用 `_mock_infer()`，`model_version` 硬编码 `MOCK-V1`，分数为合成值 | `app.py:1212` `ENABLE_MOCK_VISION=True`；DB 中 4 条 `vision_results` 全为 `MOCK-V1` |
| 13 | 目标端真实推理 | 端侧只有 C 语言阈值规则 `device_infer_accel()`（加速度模长判 static/moving），**不是模型**；仓库无任何 `.tflite` / `.espdl` | `main.c:406-411` |
| 9 | 主动询问需含"冷却时间" | `retake` / `ignore` 已实现，**冷却机制未实现**（全文搜不到 cooldown / 冷却） | `app.py` 全文检索 |
| 6 | 测量"输入结束到首次反馈"时延 | 状态机与取消隔离已实现，**未做任何时延测量**，无数据 | 无记录 |
| 8 | 模型分数校准 | 未做校准；仅做到"不把未校准分数写成正确率" | — |
| 1 | 提交"部署入口"（VPS） | **数据面已通**（VPS `123.58.43.162:8443` 实测 201/`id=10`）；**Web 控制台未上公网**，仍是局域网地址，无域名/TLS 反代 | `week1_vps_upload/README_SUBMIT.md` 0.7 节；`GET /api/vps_status` |
| 10 | 真实定位源 | 无 GNSS 硬件，只有回放数据（已在系统内如实标注） | `source_states` 第 4 行 |
| 16 | 两轮可比较的原始记录 | 仅 2 人同伴测试，无录屏、无埋点；报告中所称"串口日志记录了 `Cached locally` / `RETRANSMIT`"——**该串口日志未归档，仓库内无法核验** | `week16_usability_test/README.md` |
| 18 | 源码与版本说明 | **已补打本地 tag `v1.0-final`**（2026-10-29，未 push）；仍无 VERSION 文件 | `git tag -l` |

---

## 5. 外部条件限制 vs 未完成能力（两者必须分开认定）

### 5.1 外部条件限制（受环境/资源约束，非主观放弃）

| 事项 | 具体约束 | 影响 |
| :--- | :--- | :--- |
| **VPS 仅覆盖数据面** | VPS 已部署且可上行（实测 `POST /api/data` 201），但课程环境未提供域名与证书托管，Web 控制台无法以可信 TLS 暴露公网 | 第1周可宣称"云端数据面已通"；**不能宣称 Web 公网可用**，页面访问仍是同网段 `10.1.41.43:5000` |
| **云端视觉/语言模型未接通** | 未配置云端 VLM 授权，使用 Mock 接口替代；DeepSeek 提供的 `deepseek-chat` 本身不是视觉模型，无法承担图像理解 | 第8-9周只能走 `MOCK-V1` 模拟基线；第4/13周只能走本地规则引擎 |
| **无 GNSS 硬件** | 设备无定位模块 | 第10周定位源只能用带来源标注的回放数据 |
| **板载麦克风驱动未打通** | ESP32-S3-EYE 音频链路未调通 | 第4-6周只能用浏览器麦克风（Web Speech API）替代，未做设备端拾音 |
| **共享设备 + 人力有限** | 设备为小组共用，测试只能约到 2 名同伴 | 第16周样本 n=2，结论不外推 |

### 5.2 未完成能力（条件具备但仍未做到，需在成绩认定中扣减）

| 事项 | 为何不能算"条件限制" |
| :--- | :--- |
| 真实模型推理零次执行 | 大纲允许"先调用教师真实基线"，即使没有自建模型也应接入基线；实际连基线都未接 |
| 端侧无轻量模型 | 第13周允许使用教师保底目标端模型，未申请/未接入，最终以阈值规则替代 |
| 补传 UI 标签未验证 | 已用 `week13_14_15_edge_inference/tools/backfill_fixture.py` 做**状态注入**验证（`recovered` 徽章链路走通，见该脚本输出），但**仍缺一次真实设备断网复测**；注入结果不能替代实物证据 |
| 无截图、无串口日志归档 | 属于留证工作，与外部条件无关 |
| 无版本 tag / 版本说明 | 已于 2026-10-29 补打本地 tag `v1.0-final`（不 push），此项可销 |
| 第9周冷却时间、第6周时延测量 | 纯代码与测量工作，不受硬件限制 |

---

## 6. 个人贡献自证

* 独立完成 ESP32-S3-EYE 固件：QMA6100P 采集、OV2640 拍照、GPIO0 按键中断、LCD 状态绘制、HTTP 上传与命令轮询。
* 独立完成端侧容错：20 条环形队列 `cache_enqueue()`、断网缓存、恢复后按原顺序补传、双时间戳（`original_ts` / `retransmit_ts`）、看门狗喂狗。
* 独立完成服务端：Flask + SQLite 七张表、`BEGIN IMMEDIATE` 事务锁、`request_id` 幂等、`expire_at` 过期拦截、多源状态与偏好配置。
* 独立完成前端：采集倒计时（第17周）、离线横幅、补传标记、视觉结果与人工纠错界面。
* 独立完成验证：229 次重复上传被幂等丢弃、3 次过期回执被拦截、19 条断网补传记录（见第 3 节 CSV）。

---

## 7. 下学期迭代建议

1. 用教师保底 VLM 基线替换 `_mock_infer()`，至少打通"真实模型 → 结构化结果 → 反馈"一条链，并保留失败样本。
2. 将端侧阈值规则替换为轻量 TFLite / esp-dl 模型，补齐模型文件与实测资源占用。
3. 打通板载麦克风，接入真实 ASR/TTS，替换浏览器 Web Speech API。
4. 补一次带 `delivery_status='recovered'` 的断网复测，让"📦 已接收（补传）"标签进入证据链。
5. 申请 VPS 并落地部署（gunicorn + nginx + 域名 + TLS），补齐第1周的"部署入口"。
6. 建立留证规范：每次验收固化"串口日志 + 页面截图 + 数据库导出"三件套，并打 git tag。

---

## 8. 证据索引

| 结论 | 去哪看 |
| :--- | :--- |
| 板子真实在线 | `week13_14_15_edge_inference/server/flask.log` 中来源 `10.1.41.149` 的请求 |
| 命令通道真实 | 同上，`/api/pending_request` 共 47,207 次来自板子 IP |
| 幂等 / 过期拦截 | 同上，`Duplicate upload ignored`（229 条）、`Task expired receipt recorded`（3 条） |
| 断网补传 | `week18_final_acceptance/evidence/week14_retransmit_records_20261021.csv`（原始库：`D:\esp\lesson-main\week13_14_edge_inference\server\sensor_data.db`） |
| 真实拍照 | `week13_14_15_edge_inference/server/static/captured/*.jpg`（59 张） |
| 视觉为模拟 | `app.py` `ENABLE_MOCK_VISION=True` / `_mock_infer()`；DB `vision_results.model_version='MOCK-V1'` |
| 无真实云端 | 各周 `flask.log` 的 `DEEPSEEK_API_KEY is empty` |
| 端侧非模型 | `main.c:406` `device_infer_accel()` |
| 第17周改进 | `templates/index.html:578-611` |
