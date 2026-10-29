# 审计补充取证：原始输出（未编辑，仅加分段标题）

> 生成时间：2026-10-29 12:4x ｜ 生成方式：把本轮各次实跑的控制台输出文件原样拼接（拼接脚本是一次性的，未入库，避免"证据生成器"本身成为不可核查环节）
> 说明：所有数字均来自下方原始行；不接受口头复述。

---

## A. week7 拍照接口两段用例（T1 非本次采集 / T2 等待超时未替换）

```
[server] pid=39484 up=True

===== T1: 设备通道先上传 1 张新图，1.5s 后浏览器点“拍照” =====
upload_jpeg=capture_20261001_161230.jpg bytes=3974 sha=6d183d4ff36c590f  (latest.jpg 原 sha=804d5dcd9e5f52ef)
BEFORE       {'n_files': 25, 'sha': '804d5dcd9e5f52ef', 'mtime': 1793248286.7247953, 'n_requests': 61, 'n_captured': 14}
UPLOAD       status=200 17ms body={"filename":"capture_20261029_123600.jpg","message":"image saved","success":true}

AFTER-UPLOAD {'n_files': 26, 'sha': '6d183d4ff36c590f', 'mtime': 1793248560.2298975, 'n_requests': 61, 'n_captured': 15}
             CHECK latest_sha_changed=True new_files=1 new_captured_rows=1
BROWSER      status=200 2ms
  success=False source=recent_cache waited_seconds=0.0 age_seconds=1.5 cache_file=latest.jpg
  captured_at=2026-10-29 12:36:00 error=非本次采集：latest.jpg 是 1.5s 前上传的缓存图，本次未等待新图
  returned_bytes=3974 decoded_sha=6d183d4ff36c590f same_as_file=True
AFTER-BROWSER {'n_files': 26, 'sha': '6d183d4ff36c590f', 'mtime': 1793248560.2298975, 'n_requests': 61, 'n_captured': 15}
  CHECK sha_unchanged=True file_count_unchanged=True captured_rows_unchanged=True new_requests=0
  DB captured_images: (15, 'capture_20261029_123600.jpg', 'esp32_camera', '2026-10-29T12:36:00.229897')
  DB captured_images: (14, 'capture_20261029_123445.jpg', 'esp32_camera', '2026-10-29T12:34:45.210590')

===== T2: latest.jpg 置为 200s 前（陈旧缓存），再点一次（服务端等满 30s）=====
BEFORE age=200s sha=6d183d4ff36c590f n_files=26 n_captured=15 n_requests=61
RESP   status=404 elapsed=30.7s body={"error": "no images", "source": "timeout", "success": false, "waited_seconds": 30.0}
AFTER  age=231s sha=6d183d4ff36c590f n_files=26 n_captured=15 n_requests=62
  CHECK sha_unchanged=True mtime_unchanged=True file_count_unchanged=True captured_rows_unchanged=True new_requests=1
  collection_requests columns: ['request_id', 'device_id', 'status', 'created_at', 'completed_at', 'ax', 'ay', 'az', 'device_time', 'action']
  DB newest request: ('20261029_123601_BB01D8', 'PENDING', '2026-10-29 12:36:01', 'capture')
[server] stopped
WROTE C:\Users\user\AppData\Local\Temp\a_test.out
```

---

## D. week13_14_15 补传徽章闭环（注入 → /api/history → /api/source_states → 模板 JS 渲染）

```
[server] pid=6660 up=True

===== 1) 用真实 HTTP 注入 3 条补传数据（delay=45s） =====
[POST] /api/upload status=200 original_ts=1793248576 retransmit_ts=1793248621 -> {"server_time": "2026-10-29 12:37:01", "status": "ok"}

[POST] /api/upload status=200 original_ts=1793248575 retransmit_ts=1793248621 -> {"server_time": "2026-10-29 12:37:01", "status": "ok"}

[POST] /api/upload status=200 original_ts=1793248574 retransmit_ts=1793248621 -> {"server_time": "2026-10-29 12:37:01", "status": "ok"}



=== /api/history ���£�������ע���У�===

original_ts | retransmit_ts | delivery_status | data_origin

-----------------------------------------------------------

 1793248576 |    1793248621 |       recovered | simulated

 1793248575 |    1793248621 |       recovered | simulated

 1793248574 |    1793248621 |       recovered | simulated



PASS: 3 �о�Ϊ delivery_status=recovered + data_origin=simulated
fixture_exit=1

===== 2) GET /api/history?count=5 完整有序数组 =====
status=200 n=5  (代码 :522 result.reverse() => 索引 0 最旧，索引 n-1 最新)
  [0] id=8 server_time=2026-10-29 12:17:07 original_ts=1793247381 retransmit_ts=1793247427 delivery=recovered origin=simulated
  [1] id=9 server_time=2026-10-29 12:17:07 original_ts=1793247380 retransmit_ts=1793247427 delivery=recovered origin=simulated
  [2] id=10 server_time=2026-10-29 12:37:01 original_ts=1793248576 retransmit_ts=1793248621 delivery=recovered origin=simulated
  [3] id=11 server_time=2026-10-29 12:37:01 original_ts=1793248575 retransmit_ts=1793248621 delivery=recovered origin=simulated
  [4] id=12 server_time=2026-10-29 12:37:01 original_ts=1793248574 retransmit_ts=1793248621 delivery=recovered origin=simulated
  ASSERT 最后一条 delivery_status == recovered -> True

===== 3) GET /api/source_states 徽章数据源 =====
status=200 success=True n_sources=5
  source=camera           status=not_attempted transmission_status=live      is_delayed=False observation_time=None
  source=device_inference status=stale  transmission_status=live      is_delayed=False observation_time=2026-10-21T19:28:32
  source=gps              status=stale  transmission_status=live      is_delayed=False observation_time=2026-10-21T19:26:50.770838
  source=network          status=success transmission_status=recovered is_delayed=True  observation_time=2026-10-29T12:37:01
  source=sensor           status=stale  transmission_status=recovered is_delayed=True  observation_time=2026-10-29T12:36:14
  ASSERT sensor.transmission_status == recovered -> True

===== 4) 用模板里那段真实 JS 渲染卡片（Node + stub DOM，不是浏览器截图）=====
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
[server] stopped
WROTE C:\Users\user\AppData\Local\Temp\d_test.out
```

---

## D2. backfill_fixture 以 UTF-8 输出重跑（exit=0）

```
[POST] /api/upload status=200 original_ts=1793248609 retransmit_ts=1793248654 -> {"server_time": "2026-10-29 12:37:34", "status": "ok"}

[POST] /api/upload status=200 original_ts=1793248608 retransmit_ts=1793248654 -> {"server_time": "2026-10-29 12:37:34", "status": "ok"}

[POST] /api/upload status=200 original_ts=1793248607 retransmit_ts=1793248654 -> {"server_time": "2026-10-29 12:37:34", "status": "ok"}



=== /api/history 回吐（仅本次注入行）===

original_ts | retransmit_ts | delivery_status | data_origin

-----------------------------------------------------------

 1793248609 |    1793248654 |       recovered | simulated

 1793248608 |    1793248654 |       recovered | simulated

 1793248607 |    1793248654 |       recovered | simulated



PASS: 3 行均为 delivery_status=recovered + data_origin=simulated

注意：这是状态注入结果，前端会显示「🧪 注入样例」标记；实物断网补传仍未验证。


[exit=0]
```

---

## C. week17 心率仿真（含 [COUNT] 计数口径）

```
=== 阶段1：网络正常，心率 1Hz 直传（delivery_status=live）===
[INFO] POST /api/upload hr=70 original_ts=09:00:00 -> live
[INFO] POST /api/upload hr=71 original_ts=09:00:01 -> live
[INFO] POST /api/upload hr=72 original_ts=09:00:02 -> live
[INFO] POST /api/upload hr=73 original_ts=09:00:03 -> live
[INFO] POST /api/upload hr=74 original_ts=09:00:04 -> live

=== 阶段2：断网 3 拍，写入环形队列（不发送）===
[INFO] Cached locally (queue=1/20) hr=72 bpm
[INFO] Cached locally (queue=2/20) hr=75 bpm
[INFO] Cached locally (queue=3/20) hr=78 bpm

=== 阶段3：网络恢复，补传（delay>30s 判 recovered）===
[INFO] POST /api/upload hr=72 original_ts=09:00:06 retransmit_ts=09:00:44 delay=38.0s -> recovered
[INFO] POST /api/upload hr=75 original_ts=09:00:07 retransmit_ts=09:00:44 delay=37.0s -> recovered
[INFO] POST /api/upload hr=78 original_ts=09:00:08 retransmit_ts=09:00:44 delay=36.0s -> recovered

=== 阶段4：长时间断网，25 拍灌入 20 槽队列（验证丢最旧）===
[INFO] Cached locally (queue=1/20) hr=60 bpm
[INFO] Cached locally (queue=2/20) hr=61 bpm
[INFO] Cached locally (queue=3/20) hr=62 bpm
[INFO] Cached locally (queue=4/20) hr=63 bpm
[INFO] Cached locally (queue=5/20) hr=64 bpm
[INFO] Cached locally (queue=6/20) hr=65 bpm
[INFO] Cached locally (queue=7/20) hr=66 bpm
[INFO] Cached locally (queue=8/20) hr=67 bpm
[INFO] Cached locally (queue=9/20) hr=68 bpm
[INFO] Cached locally (queue=10/20) hr=69 bpm
[INFO] Cached locally (queue=11/20) hr=70 bpm
[INFO] Cached locally (queue=12/20) hr=71 bpm
[INFO] Cached locally (queue=13/20) hr=72 bpm
[INFO] Cached locally (queue=14/20) hr=73 bpm
[INFO] Cached locally (queue=15/20) hr=74 bpm
[INFO] Cached locally (queue=16/20) hr=75 bpm
[INFO] Cached locally (queue=17/20) hr=76 bpm
[INFO] Cached locally (queue=18/20) hr=77 bpm
[INFO] Cached locally (queue=19/20) hr=78 bpm
[INFO] Cached locally (queue=20/20) hr=79 bpm
[WARN] QUEUE FULL, dropped oldest record: seq=9 hr=60
[INFO] Cached locally (queue=20/20) hr=80 bpm
[WARN] QUEUE FULL, dropped oldest record: seq=10 hr=61
[INFO] Cached locally (queue=20/20) hr=81 bpm
[WARN] QUEUE FULL, dropped oldest record: seq=11 hr=62
[INFO] Cached locally (queue=20/20) hr=82 bpm
[WARN] QUEUE FULL, dropped oldest record: seq=12 hr=63
[INFO] Cached locally (queue=20/20) hr=83 bpm
[WARN] QUEUE FULL, dropped oldest record: seq=13 hr=64
[INFO] Cached locally (queue=20/20) hr=84 bpm
[INFO] flush -> 20 条补传记录，丢弃 5 条最旧记录

=== 计数口径（逐项可核对，不是自证）===
[COUNT] 样本总数 seq=33 = 阶段1 5(live) + 阶段2 3(进队列) + 阶段4 灌入 25
[COUNT] recovered=23 = 阶段3 补传 3 + 阶段4 补传 20
[COUNT] 阶段4：灌入 25 = 入队 20 + 丢弃最旧 5
[COUNT] live=5（阶段1 直传，retransmit_ts=0）

=== 结果表 ===
seq | hr_bpm | original_ts | retransmit_ts | delay_s | delivery_status
----------------------------------------------------------------------
  1 |     70 |    09:00:00 |             - |     0.0 | live
  2 |     71 |    09:00:01 |             - |     0.0 | live
  3 |     72 |    09:00:02 |             - |     0.0 | live
  4 |     73 |    09:00:03 |             - |     0.0 | live
  5 |     74 |    09:00:04 |             - |     0.0 | live
  6 |     72 |    09:00:06 |      09:00:44 |    38.0 | recovered
  7 |     75 |    09:00:07 |      09:00:44 |    37.0 | recovered
  8 |     78 |    09:00:08 |      09:00:44 |    36.0 | recovered
 14 |     65 |    09:00:50 |      09:04:04 |   194.0 | recovered
 15 |     66 |    09:00:51 |      09:04:04 |   193.0 | recovered
 16 |     67 |    09:00:52 |      09:04:04 |   192.0 | recovered
 17 |     68 |    09:00:53 |      09:04:04 |   191.0 | recovered
 18 |     69 |    09:00:54 |      09:04:04 |   190.0 | recovered
 19 |     70 |    09:00:55 |      09:04:04 |   189.0 | recovered
 20 |     71 |    09:00:56 |      09:04:04 |   188.0 | recovered
 21 |     72 |    09:00:57 |      09:04:04 |   187.0 | recovered
 22 |     73 |    09:00:58 |      09:04:04 |   186.0 | recovered
 23 |     74 |    09:00:59 |      09:04:04 |   185.0 | recovered
 24 |     75 |    09:01:00 |      09:04:04 |   184.0 | recovered
 25 |     76 |    09:01:01 |      09:04:04 |   183.0 | recovered
 26 |     77 |    09:01:02 |      09:04:04 |   182.0 | recovered
 27 |     78 |    09:01:03 |      09:04:04 |   181.0 | recovered
 28 |     79 |    09:01:04 |      09:04:04 |   180.0 | recovered
 29 |     80 |    09:01:05 |      09:04:04 |   179.0 | recovered
 30 |     81 |    09:01:06 |      09:04:04 |   178.0 | recovered
 31 |     82 |    09:01:07 |      09:04:04 |   177.0 | recovered
 32 |     83 |    09:01:08 |      09:04:04 |   176.0 | recovered
 33 |     84 |    09:01:09 |      09:04:04 |   175.0 | recovered

=== 断言 ===
ALL ASSERTIONS PASSED (live=5, recovered=23, dropped=5)

说明：本输出是仿真结果，仅证明队列/时间戳/状态机逻辑成立；
      不代表已连接 MAX30102 实物，也不代表设备端真实断网补传已通过。
```

---

## V. 最终自检（语法 + 行号锚点 + 8 份拷贝一致性）

```
[OK ] scan-others-no-capture | other dirs with capture endpoint=[]
[OK ] backend-week1_vps_upload | ok
[OK ] frontend-week1_vps_upload | ok
[OK ] backend-week7_image_capture | ok
[OK ] frontend-week7_image_capture | ok
[OK ] backend-week8_vision_feedback | ok
[OK ] frontend-week8_vision_feedback | ok
[OK ] backend-week9_proactive_inquiry | ok
[OK ] frontend-week9_proactive_inquiry | ok
[OK ] backend-week10_multi_source_state | ok
[OK ] frontend-week10_multi_source_state | ok
[OK ] backend-week11_context_engine | ok
[OK ] frontend-week11_context_engine | ok
[OK ] backend-week12_feedback_preferences | ok
[OK ] frontend-week12_feedback_preferences | ok
[OK ] backend-week13_14_15_edge_inference | ok
[OK ] frontend-week13_14_15_edge_inference | ok
[OK ] w7-871 | if os.path.isfile(latest_path):
[OK ] w7-885 | 'error': f'非本次采集：latest.jpg 是 {age:.1f}s 前上传的缓存图，本次未等待新图',
[OK ] w7-886 | 'waited_seconds': 0.0,
[OK ] w7-888 | 'source': 'recent_cache',
[OK ] w7-913 | for attempt in range(60):
[OK ] w7-931 | 'waited_seconds': 30.0}), 404
[OK ] week13_14_15_edge_inference:1238 | ENABLE_MOCK_VISION = True
[OK ] week13_14_15_edge_inference:1245 | def _mock_infer():
[OK ] week13_14_15_edge_inference:1263 | "model_version": "MOCK-V1"
[OK ] week13_14_15_edge_inference:1284 | if ENABLE_MOCK_VISION:
[OK ] week8_vision_feedback:957 | ENABLE_MOCK_VISION = True
[OK ] week8_vision_feedback:964 | def _mock_infer():
[OK ] week8_vision_feedback:982 | "model_version": "MOCK-V1"
[OK ] week8_vision_feedback:1003 | if ENABLE_MOCK_VISION:
[OK ] week13_14_15_edge_inference:504 | 'FROM accelerometer ORDER BY id DESC LIMIT ?',
[OK ] week13_14_15_edge_inference:523 | result.reverse()  # oldest first
[OK ] week13_14_15_edge_inference:1424 | def api_source_states():
[OK ] week13_14_15_edge_inference:1440 | transmission_status = row['transmission_status'] or 'live'
[OK ] tpl-244 | 
[OK ] tpl-1579 | 
[OK ] tpl-1581 | 
[OK ] rs-180 | 
[OK ] rs-191 | 
[OK ] w18-16 | 
[OK ] py_compile | exit=0
[OK ] node_check_8_templates | failures=[]
[OK ] firmware_diff_chars | empty diff

ALL_CHECKS_PASSED=True
```
