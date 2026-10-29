# 证据造假 / 夸大 审计与修复报告

> 审计对象：`d:\lesson\xiaolin\lesson-main (1)\lesson-main`
> 执行日期：2026-10-29
> 判定口径：只看三类证据 —— **代码、接口实测输出、数据库原始字段**。口头描述、设计文档、单张截图不算证据。
> 本报告只写两件事：(1) 已在代码或接口上验证过的；(2) 明确标注「补不上」的。

---

## 摘要

| # | 问题（修前状态） | 定性 | 处置 | 结论 |
|---|---|---|---|---|
| 1 | 30s 内的旧图被当作「本次实时拍摄」，前端打绿色「📷 实时拍摄（ESP32-CAM）」 | **造假** | 后端改为 `success:false / source:recent_cache / captured_at / age_seconds`，前端加红条 + 橙徽章；8 个同源拷贝全部修 | 已修复 + 已实测 |
| 2 | week8 无 README；视觉推理 `MOCK-V1` 未在任何交付文档里声明 | **夸大（未声明）** | 新建 `week8_vision_feedback/README.md` 证据等级表；`README_SUBMIT.md` 顶部加声明 | 已补证 |
| 3 | 补传徽章上游字段缺失：`/api/history`、`/api/sensor_history` 都不返回 `delivery_status` | **链路断（无法举证）** | 两接口补齐 4 个字段；新增 `data_origin` 迁移；前端加「来源」列 | 已修复 + 已实测 |
| 4 | week17 声称「已迁移至心率场景」，目录内无任何实现代码 | **夸大** | README 重写为「设计级 + 未接 MAX30102」；新增可运行仿真脚本并附实跑输出 | 已补证（仿真，非实物） |
| 5 | week18 称「全系统未部署 VPS」「无 git tag」，与 week1 实测 201 自相矛盾 | **过时 / 自相矛盾** | 改为「数据面已通、Web 仍本机」；补打本地 tag | 已修复 |
| 6 | 真实模型推理、GNSS、板载麦克风、第16周 n=2 录屏、真实断网补传 | **外部条件缺失** | 不补，逐条写清边界 | 补不上 |

---

## 一、Week7：缓存图冒充实时拍摄（最严重）

### 1.1 改前（假证据）

`week7_image_capture/server/app.py:871-882`：

```python
if os.path.isfile(latest_path):
    age = time.time() - os.path.getmtime(latest_path)
    if age < 30:
        ...
        log.info(''Capture: returning recent ESP32 image (age=%.1fs)', age)
        return jsonify({
            ''success': True,
            ''image': ...,
            ''source': ''esp32_camera''
        })
```

前端 `templates/index.html:706-707`（改前）：`isEsp32` 为真就打绿色徽章「✅ 摄像头实时拍摄」。

**为什么算造假**：图片是磁盘上最多 30 秒前的旧文件，接口却回报 `source=esp32_camera`，前端据此宣称「实时拍摄」，且不显示拍摄时间 —— 用户无法分辨这是本次采集还是上一轮遗留。

### 1.2 改后（week7 `app.py:871-893`）

```python
if os.path.isfile(latest_path):
    age = time.time() - os.path.getmtime(latest_path)
    if age < 30:                      # 有 30s 内文件：直接返回，不等待任何新图
        ...
        log.warning('Capture: recent cached image (age=%.1fs), NOT live', age)
        return jsonify({
            'success': False,
            'error': f'非本次采集：latest.jpg 是 {age:.1f}s 前上传的缓存图，本次未等待新图',
            'source': 'recent_cache',
            'captured_at': captured_at,
            'age_seconds': round(age, 1),
            'waited_seconds': 0.0,        # 本分支 0 等待
            'cache_file': 'latest.jpg',
            'image': ...
        })
# 只有「30s 内没有任何文件」才建 PENDING 并进入 60×0.5s 轮询（:913），超时返回
# {'success': False, 'source': 'timeout', 'waited_seconds': 30.0}（:930-931）
```

前端 `templates/index.html:690` 起新增 `recent_cache` 分支：叠加红条「⚠️ 非本次采集：这是 <拍摄时间> 的缓存图片（Ns 前）」，徽章降级为橙色「⚠️ 历史缓存」；样式 `:133`。

### 1.3 为什么「0.0s 前的图」也不是本次采集（回答 A 的自相矛盾）

判断逻辑只有两条互斥分支：

| 分支 | 触发条件 | 是否等待 | 返回 |
|---|---|---|---|
| 2a 缓存直返 | `latest.jpg` 存在且 `age < 30s` | **不等待**（`:871-893`） | `success:false / source:recent_cache / waited_seconds:0.0` |
| 2b+2c 请求新图 | 无 `latest.jpg` 或 `age ≥ 30s` | 建 PENDING 后 60×0.5s 轮询（`:913`） | 有新图 → `success:true / source:esp32_camera`；超时 → `404 / source:timeout / waited_seconds:30.0`（`:930-931`） |

所以 `age_seconds` 的含义是「**磁盘上那张 latest.jpg 距现在多久**」，不是「本次等了多久」；
本次等待时长由 `waited_seconds` 单独给出。旧文案把两者揉成一句「等待新图超时，当前仅有 0.0s 前的缓存图」，
而 2a 分支根本没等待 —— 这句描述本身是错的，已删除并用 `waited_seconds` 显式区分。

**上一版 `age_seconds: 0.0` 的来源必须交代**：那是我用 `os.utime` 把 `latest.jpg` 的 mtime 刷成「刚刚」，
人为造出的 0.0s。这个取证手法不规范（改动了被测对象），已作废，改用下面两段可重复用例重取。

### 1.4 实测重取（2026-10-29 12:36，week7，5000 端口）

T1：设备先上传一张 3974B 新图 → 1.5s 后浏览器点「拍照」

```
upload_jpeg=capture_20261001_161230.jpg bytes=3974 sha=6d183d4ff36c590f
UPLOAD       status=200 17ms {"filename":"capture_20261029_123600.jpg","message":"image saved","success":true}
AFTER-UPLOAD n_files=26 sha=6d183d4ff36c590f n_captured=15 n_requests=61
BROWSER      status=200 2ms
  success=False source=recent_cache waited_seconds=0.0 age_seconds=1.5 cache_file=latest.jpg
  captured_at=2026-10-29 12:36:00
  error=非本次采集：latest.jpg 是 1.5s 前上传的缓存图，本次未等待新图
  returned_bytes=3974 decoded_sha=6d183d4ff36c590f same_as_file=True
AFTER-BROWSER n_files=26 sha=6d183d4ff36c590f n_captured=15 n_requests=61
  CHECK sha_unchanged=True file_count_unchanged=True captured_rows_unchanged=True new_requests=0
```

T2：`latest.jpg` 置为 200s 前（构造陈旧缓存）→ 点「拍照」

```
BEFORE age=200s sha=6d183d4ff36c590f n_files=26 n_captured=15 n_requests=61
RESP   status=404 elapsed=30.7s {"error":"no images","source":"timeout","success":false,"waited_seconds":30.0}
AFTER  age=231s sha=6d183d4ff36c590f n_files=26 n_captured=15 n_requests=62
  CHECK sha_unchanged=True mtime_unchanged=True file_count_unchanged=True captured_rows_unchanged=True new_requests=1
  DB newest request: ('20261029_123601_BB01D8', 'PENDING', '2026-10-29 12:36:01', 'capture')
```

- T1 结论：返回图解码后与被上传的 3974B 文件 sha 相同，且本次**没有**新增文件 / `captured_images` 行 / 采集请求 ⇒ 这张图属于上一个请求，不是本次采集。
- T2 结论：等满 30s 超时（`waited_seconds=30.0`），`latest.jpg` 的 sha、mtime、文件数、`captured_images` 行数**全部未变**，只多一条 `PENDING` 请求 ⇒ 「等待超时后 latest.jpg 未被替换」可稳定复现。

### 1.5 同一段代码的 8 份拷贝

| 周目录 | 后端 app.py | 前端 index.html |
|---|---|---|
| week1_vps_upload | 已修 | 已修 |
| week7_image_capture | 已修 | 已修 |
| week8_vision_feedback | 已修 | 已修 |
| week9_proactive_inquiry | 已修 | 已修 |
| week10_multi_source_state | 已修 | 已修 |
| week11_context_engine | 已修 | 已修 |
| week12_feedback_preferences | 已修 | 已修 |
| week13_14_15_edge_inference | 已修 | 已修 |

前端 8 个模板合计 `+171 -2`，后端 8 个文件合计 `+143 -52`（其中 week7 `+17 -6`、week13 `+41 -15`），均无整文件重写（`git diff --shortstat HEAD~1 -- ...` 即可核对）。

### 1.6 没有动的部分

`git diff -- '*.c'` → `diff_chars=0`。固件一行未改，拍照链路本身未被破坏。

---

## 二、Week8 / Week13_14_15：视觉推理是 Mock，却没有一句声明

### 2.1 改前

- `week8_vision_feedback/` **没有 README.md**（整个目录只有 server / firmware / 素材）。
- `week13_14_15_edge_inference/README_SUBMIT.md` 把 `/api/infer_image` 当普通能力列在「新增 API 路由」表里，全文没有 mock 字样；
  而 week8 `server/app.py:957` / week13 `server/app.py:1238` 写死 `ENABLE_MOCK_VISION = True`，
  `_mock_infer()`（week8 `:964` / week13 `:1245`）用 `random.choice()` 造标签，`model_version` 硬编码 `MOCK-V1`（week8 `:982` / week13 `:1263`）。
- `README_SUBMIT.md:180` 称「main.c / esp32_firmware — 零改动」（改前为 `:175`），实际 `week13_14_15_edge_inference/esp32_firmware/main/main.c:407` 有新增的 `device_infer_accel()`（调用点 `:419`、`:1199`）。
- `README_SUBMIT.md:191` 启动路径写成 `...\week13_edge_inference\server`（改前为 `:184`，目录不存在）。

### 2.2 改后

- 新建 `week8_vision_feedback/README.md`（122 行），第 0 节即「证据等级声明」表格：

| 项 | 事实 | 位置（改后 `git grep -n` 实测） |
|---|---|---|
| 推理开关 | `ENABLE_MOCK_VISION = True` | `server/app.py:957` |
| 结果来源 | `random.choice(VISION_LABELS)`，30% 低分演示 uncertain | `:964-983` |
| 版本标注 | `model_version = MOCK-V1` | `:982` |
| 调用点 | `if ENABLE_MOCK_VISION: result = _mock_infer()` | `:1003-1009` |
| 模型权重 | 无（仓库无 .onnx/.tflite/.pt） | — |
| 端侧部署 | 无 | — |

- `README_SUBMIT.md` 顶部加 5 行声明（含「云端 DeepSeek 未配置 Key，云路径实际未跑通」+ 本目录/week8 的精确行号）。
- `:180-182` 改为：main.c **并非零改动**，`device_infer_accel()` 是 if/else 阈值判定、**不含模型推理**；本次修复对 main.c 改动 0 字节。
- `:191` 路径更正为 `week13_14_15_edge_inference\server`。

**B：行号为什么会「对不上」** —— 三个原因，逐条给实测：

1. `954 / 961 / 979` 是 **week8** 的行号（当时 `git grep` 实测），不是 week13 的；
2. 本轮我又在 2a 分支插了 2 行、超时分支插了 1 行，week8 整体 +3 → 现在是 `957 / 964 / 982`；
3. 施工单里的 `week13_14_15/server/app.py:1212 / 1219 / 1237`，在当前 HEAD 上分别是「capture 轮询里的 `age` 计算」「轮询命中后的 `success: True`」「`VISION_LABELS` 第一行」，**都不是 mock 本体** —— 行号随代码演进漂移了。week13 的 mock 本体是 `:1238 / :1245 / :1263`。

当前 HEAD 实测（`git grep -n`，原样粘贴）：

```
week13_14_15_edge_inference/server/app.py:1238:ENABLE_MOCK_VISION = True
week13_14_15_edge_inference/server/app.py:1245:def _mock_infer():
week13_14_15_edge_inference/server/app.py:1263:        "model_version": "MOCK-V1"
week13_14_15_edge_inference/server/app.py:1284:    if ENABLE_MOCK_VISION:
week8_vision_feedback/server/app.py:957:ENABLE_MOCK_VISION = True
week8_vision_feedback/server/app.py:964:def _mock_infer():
week8_vision_feedback/server/app.py:982:        "model_version": "MOCK-V1"
week8_vision_feedback/server/app.py:1003:    if ENABLE_MOCK_VISION:
```

`README_SUBMIT.md` 两处修正的当前行号（`git diff -U0` + 带行首编号）：

```
@@ -8,0 +9,2 @@
+> 本目录代码位置（2026-10-29 `git grep -n` 实测）：`server/app.py:1238` 开关、`:1245` `_mock_infer()`、`:1263` `model_version`、`:1284-1290` 调用点；
+> week8 同源代码位于 `week8_vision_feedback/server/app.py:957 / :964 / :982`（`:1003-1009` 为调用点）。
  180| ### 本次红线修复未修改的文件
  182| - ⚠️ main.c — **第 13 周功能改动里已包含设备端阈值规则** `device_infer_accel()`（`esp32_firmware/main/main.c:407`，调用点 `:419`、`:1199`），属于 if/else 阈值判定、**不含任何模型推理**；2026-10-29 红线修复对 main.c 的改动为 **0 字节**（`git diff -- *.c` 输出 0 字符）
  191| cd "d:\lesson\xiaolin\lesson-main (1)\lesson-main\week13_14_15_edge_inference\server"
```

---

## 三、Week14：补传徽章「看得见但举不了证」

### 3.1 根因链（改前）

1. 徽章只读 `GET /api/source_states` 的 `transmission_status`；
2. 该字段只在 `POST /api/upload` 的瞬间由 `update_source_state(...)` 写入（`app.py:445-456`）；
3. 而 `GET /api/history`（`:495-500`）与 `GET /api/sensor_history`（`:1034-1039`）**都不返回 `delivery_status`**。

→ 结果：只要错过上传那一秒，页面上再也看不到「📦 补传」，任何事后复核都无从举证。

### 3.2 改后（字段 + 迁移 + 前端列）

| 位置 | 改动 |
|---|---|
| `app.py:113-116` | 迁移列表加 `('data_origin', TEXT DEFAULT 'device')` |
| `app.py:414-416` | 上传时判定来源：`data_origin in (device, simulated)`，兼容 `simulated:true` |
| `app.py:421` | INSERT 增加 `data_origin` 列（旧库缺列时仍走原 fallback） |
| `app.py:502-503` | `/api/history` SELECT 增加 `id` 与 `original_ts, retransmit_ts, delivery_status, data_origin` |
| `app.py:511` / `:520` | 同上，dict 回吐（`id` / 四个字段） |
| `app.py:1047` / `:1066` | `/api/sensor_history` 同上 |
| `index.html:491` | 表头加「来源」列 |
| `index.html:1052-1054` | 行内渲染 🧪 注入样例 / 📡 真实设备 / 📦 补传 |

### 3.3 状态注入工具（新增）

`week13_14_15_edge_inference/tools/backfill_fixture.py`：走**真实** `POST /api/upload`，把 `original_ts` 设为 45s 前、
`retransmit_ts` 设为当前，让服务端按 `app.py:356-367` 自行判 `recovered`；再 `GET /api/history` 回读断言。
文件头已写明：**这是状态注入，不是实物断网**。

### 3.4 实测闭环（2026-10-29 12:37，week13_14_15，5000 端口）

**① 注入 3 条补传（真实 `POST /api/upload`，`data_origin=simulated`）**

```
[POST] /api/upload status=200 original_ts=1793248609 retransmit_ts=1793248654 -> {"server_time": "2026-10-29 12:37:34", "status": "ok"}
[POST] /api/upload status=200 original_ts=1793248608 retransmit_ts=1793248654 -> {"server_time": "2026-10-29 12:37:34", "status": "ok"}
[POST] /api/upload status=200 original_ts=1793248607 retransmit_ts=1793248654 -> {"server_time": "2026-10-29 12:37:34", "status": "ok"}
=== /api/history 回吐（仅本次注入行）===
original_ts | retransmit_ts | delivery_status | data_origin
 1793248609 |    1793248654 |       recovered | simulated
 1793248608 |    1793248654 |       recovered | simulated
 1793248607 |    1793248654 |       recovered | simulated
PASS: 3 行均为 delivery_status=recovered + data_origin=simulated
注意：这是状态注入结果，前端会显示「🧪 注入样例」标记；实物断网补传仍未验证。
[exit=0]
```

（上一版这里出现 `fixture_exit=1`：原因是我用 cp936 管道捕获子进程 stdout，脚本打印 🧪 时触发 `UnicodeEncodeError` 退出码 1；
加 `PYTHONIOENCODING=utf-8` 后 `exit=0`，断言本身一直是 PASS。已改正重现方式。）

**② `GET /api/history?count=5` 完整有序数组（含 `id`，不截断）**

```
status=200 n=5
[0] id=8  server_time=2026-10-29 12:17:07 original_ts=1793247381 retransmit_ts=1793247427 delivery=recovered origin=simulated
[1] id=9  server_time=2026-10-29 12:17:07 original_ts=1793247380 retransmit_ts=1793247427 delivery=recovered origin=simulated
[2] id=10 server_time=2026-10-29 12:37:01 original_ts=1793248576 retransmit_ts=1793248621 delivery=recovered origin=simulated
[3] id=11 server_time=2026-10-29 12:37:01 original_ts=1793248575 retransmit_ts=1793248621 delivery=recovered origin=simulated
[4] id=12 server_time=2026-10-29 12:37:01 original_ts=1793248574 retransmit_ts=1793248621 delivery=recovered origin=simulated
ASSERT 最后一条 delivery_status == recovered -> True
```

**排序口径（也就是我上一版贴错的地方）**：`app.py:504` 是 `ORDER BY id DESC`，紧接着 `:523 result.reverse() # oldest first`，
所以数组是**最旧 → 最新**，`records[-1]` 才是最新一条。上一版我贴的「recovered 在前、live 在后」两行是按我自己的挑选顺序排的，
不是接口顺序 —— 取证不规范，作废；以上是按 `records[0..4]` 原样打印。

**③ `GET /api/source_states`（徽章真正读的那个接口，`app.py:1424`）**

```
status=200 success=True n_sources=5
  source=camera           status=not_attempted transmission_status=live      is_delayed=False observation_time=None
  source=device_inference status=stale  transmission_status=live      is_delayed=False observation_time=2026-10-21T19:28:32
  source=gps              status=stale  transmission_status=live      is_delayed=False observation_time=2026-10-21T19:26:50.770838
  source=network          status=success transmission_status=recovered is_delayed=True  observation_time=2026-10-29T12:37:01
  source=sensor           status=stale  transmission_status=recovered is_delayed=True  observation_time=2026-10-29T12:36:14
ASSERT sensor.transmission_status == recovered -> True
```

> sensor 同时是 `status=stale`：`stale` 由 `SOURCE_STALE_THRESHOLDS`（按 `observation_time` 算年龄，`app.py:1460-1463`）决定，
> 与补传标记无关；徽章只看 `transmission_status`。两者并存不矛盾，但必须写清楚，否则容易被误读成「又实时又补传」。

**④ 页面徽章断言：拿模板里那段真实 JS + 上面的真实 JSON 求值（不是 `has_字样`）**

```
template line of marker = 1578
extracted lines 1579-1585:
    1579|                 var delayHtml = '';
    1580|                 if (src.transmission_status === 'recovered') {
    1581|                     delayHtml = '<div class="source-card-delay">📦 已接收（补传）'
    1582|                         + ' 原始时间：' + (src.observation_time || '--') + '</div>';
    1583|                 } else if (src.transmission_status === 'live' && src.status === 'success') {
    1584|                     delayHtml = '<div style="color:var(--green);font-size:13px;margin-top:4px;">✅ 已接收（实时）</div>';
    1585|                 }
node exit=0
rendered HTML: <div class="source-card-delay">📦 已接收（补传） 原始时间：2026-10-29T12:36:14</div>
ASSERT 含「📦 已接收（补传）」 -> True
ASSERT 含 source-card-delay 类（CSS 定义在模板 :244） -> True
ASSERT 不再出现「✅ 已接收（实时）」 -> True
```

> 这一步的两条边界必须写明：
> 1. 它是「真实模板代码 + 真实接口 JSON + Node 求值」，**不是浏览器截图**。本机 `playwright/selenium/jsdom` 三者都没有（实测 `missing`），
>    无法做 DOM 断言，也就没有伪造「页面已显示」的截图。
> 2. 注入数据是 `data_origin=simulated`，证明的是「服务端判定 → 落库 → 回吐 → 徽章渲染」整链通；
>    **不证明**设备在真实断网时缓存并补传。

---

## 四、Week17：声称「已迁移」，实际零实现

### 4.1 改前

`week17_migration_and_fix/README.md:11-14` 用将来时写迁移（「将替换为 MAX30102」），但目录中**没有任何 .py**，
也没有心率相关代码；`heart_rate_simulator.py` 在被审计时根本不存在。等于用一段设计文字冒充「迁移完成」。

### 4.2 改后

1. README 重写（114 行），开头即「本目录不是一个已完成迁移的心率系统」，第 0 节证据表把四件事分别定性：
   UI 改进=已落地代码；迁移=设计+仿真；MAX30102 驱动=不存在；真实断网补传=未验证。
2. 新增 `heart_rate_simulator.py`（纯标准库），复刻：
   - `main.c:92` `CACHE_QUEUE_SIZE=20`、`:377-388` `cache_enqueue()` 丢最旧 + `QUEUE FULL, dropped oldest record`；
   - `app.py:356-367` 的 `delay>30s → recovered` 判定。
3. 实跑结果（`python week17_migration_and_fix/heart_rate_simulator.py`，纯标准库、不联网）：

```
  6 |     72 |    09:00:06 |      09:00:44 |    38.0 | recovered
  7 |     75 |    09:00:07 |      09:00:44 |    37.0 | recovered
  8 |     78 |    09:00:08 |      09:00:44 |    36.0 | recovered
[WARN] QUEUE FULL, dropped oldest record: seq=13 hr=64
[INFO] flush -> 20 条补传记录，丢弃 5 条最旧记录

=== 计数口径（逐项可核对，不是自证）===
[COUNT] 样本总数 seq=33 = 阶段1 5(live) + 阶段2 3(进队列) + 阶段4 灌入 25
[COUNT] recovered=23 = 阶段3 补传 3 + 阶段4 补传 20
[COUNT] 阶段4：灌入 25 = 入队 20 + 丢弃最旧 5
[COUNT] live=5（阶段1 直传，retransmit_ts=0）

ALL ASSERTIONS PASSED (live=5, recovered=23, dropped=5)
```

**C：`flush -> 20` 与 `recovered=23` 为什么不矛盾**

`recovered` 是**全局累加**，`flush -> 20` 只是**阶段4 那一次** flush 的条数：

| 阶段 | 输入 | 结果 |
|---|---|---|
| 1 网络正常 | 5 拍 1Hz 直传 | `live = 5`（`retransmit_ts=0`） |
| 2 断网 | 3 拍进 20 槽环形队列 | 队列 3/20，未发送 |
| 3 网络恢复 | flush 3 拍，delay 36–38s > 30s | `recovered += 3` |
| 4 长时间断网 | 25 拍灌入 20 槽，丢最旧 5 条 | `dropped = 5`；flush 20 条 → `recovered += 20` |

合计：样本 `5 + 3 + 25 = 33`（断言 `seq == 33`）；`recovered = 3 + 20 = 23`；`dropped = 5`（只发生在阶段4）；`live = 5`。

`recovered` 不是自证：每条状态由 `RingCache.flush()` 按**与服务端同一条件**
（`retransmit_ts > 0 and (original_ts <= 0 or delay > 30)`，对齐 `app.py:363`）计算，
断言再独立检查 `retransmit_ts > original_ts`、`delay_s > 30`、`dropped == 5`、`len(recovered2) == QUEUE_SIZE`、`seq == 33`；
而这条规则本体已在 week14 服务端由 `tools/backfill_fixture.py` 实测通过（3.4 ②③）。

> 边界：仿真通过的只是队列容量、丢最旧策略、双时间戳与状态判定；**心率数值是构造的**，与真实脉搏无关。

---

## 五、Week18：把「已做到的」写成「没做到」，把「没做的」写成「已做」

### 5.1 改前

| 行 | 原文 | 问题 |
|---|---|---|
| `:16` | 全系统**未部署到 VPS**，无公网域名、无 TLS | 与 `week1_vps_upload/README_SUBMIT.md` 0.7 节矛盾（该节记录 `POST /api/data` 返回 201、`id=10`） |
| `:76` | 第1周 **未部署 VPS**，只有局域网地址 | 同上 |
| `:89` | **VPS 未部署** … 只能在局域网内联调 | 同上 |
| `:79` / `:103` | 无 git tag、`git tag` 为空 | 修复后已打 tag，需同步 |
| `:101` | 补传 UI 标签未验证 | 已有注入验证手段，应写清「注入过、实物未过」 |

### 5.2 本次取证

```
GET /api/vps_history -> HTTP 401 in 0.026317s
{"error": "缺少或无效的 Authorization: Bearer <token>"}
```

→ VPS `https://123.58.43.162:8443` **在线且要求鉴权**（26ms 响应）。
仓库内**没有 `.env`**，本次无法登录复验，因此不声称「我又跑通了一次」；
鉴权后的 `201 / id=10 / count=4` **全部引用** `week1_vps_upload/README_SUBMIT.md` 0.7 节的原记录（该记录标注为 2026-10-29 早前一轮联调，不是本次审计）。
`week18_final_acceptance/README.md:16` 已按你要求写成：

> 其中 `POST /api/data → 201 (id=10)`、`GET /api/data → count=4` 为**引用** `week1_vps_upload/README_SUBMIT.md` 0.7 节的既有记录，**本次审计未复验**（仓库内无 `.env`，无法登录）；本次只做了**未鉴权只读探活**：`GET /api/vps_history → 401`（26ms，说明服务在线且要求 Bearer）。

### 5.3 改后

- `:16` → 「其中 `POST /api/data → 201 (id=10)`、`GET /api/data → count=4` 为**引用** week1 0.7 节的既有记录，**本次审计未复验**（仓库内无 `.env`）；本次只做**未鉴权只读探活**：`GET /api/vps_history → 401`（26ms，说明服务在线且要求 Bearer）；**Web 控制台仍只跑本机局域网**，无域名/无生产级 TLS/无 gunicorn+nginx+systemd」。
- `:76` → 第1周「数据面已通，Web 未上公网」。
- `:89` → 「**VPS 仅覆盖数据面**」，仍不能宣称 Web 公网可用。
- `:79` / `:103` → 已补打本地 tag `v1.0-final`（不 push），此项销账。
- `:101` → 改为「注入验证已过、实物复测仍缺」。

---

## 六、补不上的（外部条件，不粉饰）

| 事项 | 为什么补不上 | 现在的诚实写法 |
|---|---|---|
| 真实视觉模型推理 | 无权重、无 NPU 部署、教师基线未接入 | 全链路标注 `MOCK-V1`，见 week8 README 第 0 节 |
| 真实云端语言模型 | `DEEPSEEK_API_KEY` 为空，一次都没跑 | `README_SUBMIT.md` 顶部声明「云路径未跑通」 |
| 端侧模型推理 | `device_infer_accel()` 只是 if/else 阈值 | 明确写「非模型」，不写「端侧 AI 推理」 |
| GNSS 定位 | 无硬件 | 沿用「回放数据-仅供演示（无真实GNSS硬件）」标注 |
| 板载麦克风 | 音频链路未打通 | 只写浏览器 Web Speech API |
| 第16周 n=2 录屏 / 埋点 | 当时未录，事后无法补拍 | week17 README 写「n=2 只能定位问题，不构成统计显著」 |
| 真实设备断网补传 | 需实物拔网 + 串口日志，本机无设备 | 只提供 `recovered` **状态注入**证据，并标注「非实物」 |
| 真实拍照（ESP32-CAM） | 板子不在手边 | 缓存分支已改为 `recent_cache`，不再冒充实时 |

---

## 七、验证清单（可逐条复跑）

| 检查 | 命令 | 结果 |
|---|---|---|
| Python 语法（8 个后端 + 2 个新脚本） | `python -m py_compile ...` | `py_compile=0` |
| 前端 JS 语法（8 个模板） | `node --check` 提取的 script 块 | `node_check_failures=0` |
| 缓存图不再冒充实时（T1） | 设备上传 3974B → 1.5s 后 `POST /api/capture_image` | `success=false, source=recent_cache, waited_seconds=0.0, age_seconds=1.5`，返回图与上传文件 sha 相同，`new_files=0 / new_captured_rows=0 / new_requests=0` |
| 等待超时后 latest.jpg 未被替换（T2） | `latest.jpg` 置 200s 前 → `POST /api/capture_image` | `404, source=timeout, waited_seconds=30.0, elapsed=30.7s`，sha/mtime/文件数/`captured_images` 行数全未变，仅新增 1 条 `PENDING` |
| 补传闭环（服务端） | `PYTHONIOENCODING=utf-8 python tools/backfill_fixture.py --count 3 --delay 45` | `PASS: 3 行均为 delivery_status=recovered + data_origin=simulated`，`exit=0` |
| `/api/history` 有序数组 | `GET /api/history?count=5` | `records[0..4]` 全为 `recovered/simulated`，`records[-1].delivery_status == recovered`（`:523 reverse()` ⇒ 最旧在前） |
| 徽章数据源 | `GET /api/source_states` | `sensor.transmission_status=recovered, is_delayed=True`；`network` 同为 `recovered` |
| 徽章渲染（模板真代码 + 真 JSON） | 切出 `index.html:1579-1585` 交 Node 求值 | `<div class="source-card-delay">📦 已接收（补传）…</div>`，`node exit=0` |
| 心率仿真计数口径 | `python week17_migration_and_fix/heart_rate_simulator.py` | `[COUNT] seq=33 / recovered=23=3+20 / dropped=5 / live=5` + `ALL ASSERTIONS PASSED (live=5, recovered=23, dropped=5)` |
| 固件零改动 | `git diff -- '*.c'` | `diff_chars=0` |

> 未做：浏览器 DOM 断言 / 截图（本机无 `playwright`/`selenium`/`jsdom`，实测均 missing）；不拿「页面 has_字样」冒充「页面已渲染」。

---

## 八、本次变更文件

**代码（16 个）**

- 8 × `*/server/app.py`：缓存图不再冒充实时；本轮二次修正把 `'error'` 文案改成「非本次采集…本次未等待新图」，并新增 `waited_seconds`（缓存分支 0.0 / 超时分支 30.0）与 `cache_file`
- 8 × `*/server/templates/index.html`：新增 `recent_cache` 红条分支 + `.cache-warning` 样式
- `week13_14_15_edge_inference/server/app.py`：`data_origin` 迁移 + 两接口 4 字段 + 上传来源标记 + `/api/history` 回吐 `id`（便于逐条核对）
- `week13_14_15_edge_inference/server/templates/index.html`：历史表「来源」列 + 三种徽章样式

**新增（4 个）**

- `week8_vision_feedback/README.md`
- `week17_migration_and_fix/heart_rate_simulator.py`（本轮加 `[COUNT]` 计数口径段）
- `week13_14_15_edge_inference/tools/backfill_fixture.py`
- `Audit_Evidence_Raw.md`（A/D/C/自检 的原始控制台输出，未编辑）
- `Audit_Fix_Report.md`（本文件）

**文档修订（4 个）**

- `week13_14_15_edge_inference/README_SUBMIT.md`（证据声明 + 精确行号 + main.c 表述 + 启动路径）
- `week8_vision_feedback/README.md`（T1/T2 两段可重复取证替换原「改 mtime」写法）
- `week17_migration_and_fix/README.md`（全文重写 + 计数口径说明）
- `week18_final_acceptance/README.md`（VPS / tag / 补传标签；`:16` 改为「引用 week1 0.7 记录、本次未复验、仅 401 探活」）

**版本**：本地 tag `v1.0-final`（**未 push**）。本轮为审计后的补充取证，改动量：`git diff --stat HEAD` = 8 个后端 +44 -19，无前端改动。

---

## 九、补证索引（对应复核意见 A–E）

| 复核项 | 结论 | 本报告位置 | 原始输出 |
|---|---|---|---|
| **A** `age_seconds:0.0` 却说「等待超时」 | 文案本身是错的：`age<30` 分支**不等待**；已改文案并新增 `waited_seconds`（0.0 / 30.0）。上一版 0.0s 是我 `os.utime` 刷 mtime 造出来的，作废 | §1.3、§1.4 | `Audit_Evidence_Raw.md` 第 A 段（T1/T2） |
| **B** 行号对不上 | `954/961/979` 是 **week8** 改前行号，改后为 `957/964/982`；施工单的 week13 `1212/1219/1237` 在当前 HEAD 是 capture 轮询与 `VISION_LABELS`，mock 本体在 `1238/1245/1263` | §2.2 | 同上，`git grep -n` 原样粘贴 |
| **C** `flush -> 20` vs `recovered=23` | 不矛盾：`recovered` 全局累加 = 阶段3 的 3 + 阶段4 的 20；样本 33 = 5 + 3 + 25（20 入队 + 5 丢弃） | §4.3 | 第 C 段（含 `[COUNT]` 四行） |
| **D** 缺 `/api/source_states` 与徽章断言 | 已补：`/api/history?count=5` 完整有序数组（`records[-1]=recovered`）、`/api/source_states` 的 `transmission_status=recovered`、模板 `:1579-1585` 真实 JS 求值出「📦 已接收（补传）」；并声明不是浏览器截图 | §3.4 | 第 D/ D2 段 |
| **E** VPS 表述 | `week18_final_acceptance/README.md:16` 已写明「201/id=10/count=4 引用 week1 0.7 节记录，本次仅 401 探活、未复验鉴权后接口」 | §5.2、§5.3 | 第 V 段 `w18-16` 检查 |

**仍未关闭的**：tag/commit **只在本地，未 push**（按要求保持）。

---

## 十、一句话结论

原系统里「缓存图冒充实时拍摄」是真造假，已从代码层根除（8 份拷贝）；
「视觉推理」「心率迁移」是夸大，现已降级为可核验的 Mock / 仿真并写明边界；
「VPS 未部署」是自我贬低的过时表述，已按实测改为「数据面通、Web 未上公网」。
剩下的做不到的部分没有一条被伪造成做得到。

---

## 十一、批1（2026-10-29 13:50–14:35）：课程周次缺口修复（量纲 / no_fix / observed_at / 端口）

> 范围：`week1_vps_upload`、`week10_multi_source_state`、`week11_context_engine`、`week12_feedback_preferences`、`week13_14_15_edge_inference` 五份后端 + 五份 `templates/index.html` + 根 `README.md`。
> 铁律：验证**只用 5001**，5000 全程未起（`netstat -ano | findstr :5000` 无 `LISTENING`，收尾复核同上）。

### 11.1 四条改动与根因

| # | 缺陷（修前） | 根因 | 处置 | 落地位置 |
|---|---|---|---|---|
| 0 | 起第二实例验证必与现场 5000 抢端口 | 端口硬编码 | `_port = int(os.environ.get('PORT','5000'))`，默认不变 | week10 `:1332`、week11 `:1494`、week13 `:2019`（week12/week1 **按约定未改**） |
| 1 | `/api/local_infer` 恒判「可能在移动」 | 设备上报单位是 **g**（静止实测模长 1.31–1.34），代码拿 `9.81` 当基准 | `mag_g = mag if mag <= 4.0 else mag / 9.80665`；判据 `abs(mag_g - 1.0) > 0.5`；`detail` 输出 g | week13 `api_local_infer`、**week1 同源拷贝**（原以为只有 week13，实物发现 week1 也有，一并修） |
| 1b | `/api/context.derived_states.is_moving` 恒判移动 | 同上（另一处拷贝） | 同上换算，`accel_magnitude` 一并输出 g | week1/11/12/13 各 1 处 |
| 2 | GNSS 无解被写成 `failed`（把「没解」污名成「坏了」） | 状态机只有 success/failed | `simulate_no_fix` 写 `status='no_fix'`；**保旧值条件**扩为 `status in ('failed','no_fix')`（兼容库内历史 failed 行）；上下文 `gps.get('status') in ('failed','no_fix')` | 5 份后端 + 5 份前端 `statusText` 加 `no_fix:'🔵 无有效解（非故障）'` + `README.md:715` |
| 3 | `known_facts[].observed_at` 用「生成时刻」冒充「观测时刻」 | 直接 `t_fmt(now)` | `raw[name]` 增 `observation_time`（源的真实 `last_observation_time`）→ `src_time(src)` 解析，**失败返回空串，绝不回退 now**；5 处事实全部改源时间 | week11 先行；随后 week1 `:1863/1895/1915/1921/1932/1941/1956`、week12 `:1426/1458/1478/1484/1495/1504/1519`、week13 `:1566/1598/1618/1624/1635/1644/1659` |

> 改动3 的动机：`observed_at == 生成时刻` 时，「事实」与「何时观测到的」被绑死，等于没有时间证据。week1 是第 18 周现场版，只修 week11 等于现场演示仍是假时间。

### 11.2 实测矩阵（全部在 2026-10-29 本机复跑）

| 检查 | 手段 | 结果 |
|---|---|---|
| A1 端口参数化生效 | `PORT=5001` 起 week13，`GET /` + `POST /api/local_infer` | 日志 `Starting sensor dashboard on http://0.0.0.0:5001`，`local_infer HTTP 200`；无板时返回「画面不可用」（**正确语义**，不是推理结果） |
| A2 量纲分支 | scratch DB + `test_client`（不碰真实库、不监听端口） | `|a|=1.305` → `环境正常`(0.85)；`|a|=1.658` → `可能在移动`(0.5611)；`detail=加速度模长=1.66g（静止基准 1.0g）` |
| B no_fix 语义（live） | week10、week13 各起 5001 → `POST /api/simulate_no_fix` → 前后读 `source_states` | 两份均 `status=no_fix`，`previous_value` 仍保留 `lat 31.2304 / lng 121.4737`（旧坐标没丢） |
| C observed_at（fixture） | 四份 `test_client` + 两条 GPS 分支（新 8s / 过期 400s） | 见 11.3，`ALL PASS`；`observed_at` 分别等于源真实时间 14:32:02/03/04/00（B 场景 GPS 为 14:25:32），**均 ≠ now(14:32:12)** |
| D 静态 | `python -c "ast.parse(...)"` × 5；`git grep -n 't_fmt(now)' -- week12 week13 week1` | `AST OK: 5`；grep **0 命中**（exit=1） |
| E 量纲回归 | 同上 fixture | 四份 `accel_magnitude=1.383`、`is_moving=静止`、`uncertain=["GPS 无有效解，非故障"]` |
| F 端口收尾 | `netstat -ano` | 5001/5000 均无 `LISTENING`；只关了自己起的 PID，`msedge 21400` 未动 |

### 11.3 原始输出（节选，完整见 `evidence_batch1.zip`）

```
--- week1 A 新鲜 GPS(8s) -> 当前位置分支
  OK   当前可能静止 | source= 规则推断 | observed_at= 14:32:02
  OK   网络连接正常 | source= 网络连接 | observed_at= 14:32:03
  OK   当前位置 lat=31.2304 lng=121.4737 | source= 位置GPS | observed_at= 14:32:04
  OK   摄像头可用，最后采集 fixture_still.jpg | source= 摄像头 | observed_at= 14:32:00
  OK   observed_at 全都不等于 now(14:32:12)
--- week1 B 过期 GPS(400s) -> 上次报告位置分支
  OK   上次报告位置是 lat=31.2304 lng=121.4737 | observed_at= 14:25:32
  OK   no_fix 回归 -> ["GPS 无有效解，非故障"] | derived -> {"accel_magnitude": 1.383, "is_moving": "静止", ...}
RESULT week1 PASS
... week12 PASS / week13 PASS / week11 PASS
SUMMARY [('week1', True), ('week12', True), ('week13', True), ('week11', True)]
ALL PASS
```

week13 服务端日志（`evidence/batch1/week13_flask_tail200_batch1_20261029.log`，仅 `-Tail 200`）：

```
[2026-10-29 14:01:28] INFO >>> POST /api/local_infer ?   from 127.0.0.1
[2026-10-29 14:01:28] INFO 127.0.0.1 - - [29/Oct/2026 14:01:28] "POST /api/local_infer HTTP/1.1" 200 -
[2026-10-29 14:06:34] INFO Starting sensor dashboard on http://0.0.0.0:5001
[2026-10-29 14:06:36] INFO >>> POST /api/simulate_no_fix ?   from 127.0.0.1
[2026-10-29 14:06:36] INFO 127.0.0.1 - - [29/Oct/2026 14:06:36] "POST /api/simulate_no_fix HTTP/1.1" 200 -
```

week11 服务端日志（`evidence/batch1/week11_flask_tail200_batch1_20261029.log`）：

```
[2026-10-29 14:07:03] INFO Starting sensor dashboard on http://0.0.0.0:5001
[2026-10-29 14:07:04] INFO >>> GET /api/context ?   from 127.0.0.1
[2026-10-29 14:07:04] INFO 127.0.0.1 - - [29/Oct/2026 14:07:04] "GET /api/context HTTP/1.1" 200 -
```

### 11.4 缺口：week13「近端边缘」只能写到「接口通」

A1 在**无摄像头图**的条件下返回 `画面不可用`，这是正确语义，但**不能**据此写「端侧真实推理完成」。本批对此的口径固定为：

- 可写：`/api/local_infer` 接口通（HTTP 200）、量纲分支经 fixture 验证、无图时明确拒绝出结论；
- 不可写：真实图像推理、模型精度、端侧加速比；
- 待补条件：`week7` 相机出图（需烧录，本机无 ESP 板 / 无 COM 口）→ 拿真实 `latest.jpg` 再跑一次本接口并归档响应原文。

### 11.5 本批未做（写明，不粉饰）

| 项 | 原因 | 归属 |
|---|---|---|
| week12 端口参数化 | 约定本批只动 week10/11/13 | 批2 |
| week1 端口参数化 | 第 18 周现场版，保持 5000 硬编码，避免现场行为变化 | 不改 |
| W7 相机烧录 / 串口日志 | 无 ESP 板、无 COM 口（枚举仅 ACPI/蓝牙） | 需人工插板；`env_setup.ps1` 已备好 `Invoke-IdfPy` |
| DeepSeek key、视觉权重、MAX30102、真人被试 | 外部依赖未到 | 不阻塞批1 |
| `idf.py` 版本 | `ESP-IDF v5.4.4-dirty`（工作区有本地改动） | 仅记录 |
