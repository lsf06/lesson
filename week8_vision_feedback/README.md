# Week 8：视觉反馈闭环（Vision Feedback Loop）

> 项目：group01_esp32s3eye | EgoLink DevBench
> 目录：`week8_vision_feedback/`
> 更新：2026-10-29（红线修复后）

---

## 0. 证据等级声明（必读）

**本模块的视觉推理为模拟实现（MOCK-V1），未接入任何真实模型，明确不作为端侧/云端视觉推理能力的证据。**

| 项 | 事实 | 代码位置 |
|----|------|----------|
| 推理开关 | `ENABLE_MOCK_VISION = True`，请求直接走 `_mock_infer()` | `server/app.py:957`、`:1003-1009` |
| 结果来源 | `random.choice(VISION_LABELS)` 随机取标签，约 30% 概率给低分以演示 uncertain | `server/app.py:964-983` |
| 版本标注 | 结果内 `model_version = MOCK-V1`，不伪装真实模型分数 | `server/app.py:982` |
| 模型权重 | 无。仓库内不存在 .onnx / .tflite / .pt 权重文件 | - |
| 端侧部署 | 无。ESP32-S3-EYE 未部署任何推理算子 | - |

> 结论：本目录能证明「拍照 -> 存库 -> 出结果 -> 人工纠正 -> 写回」的闭环与数据结构成立；
> **不能**证明真实视觉模型可用，验收与答辩中不得将其作为视觉推理能力证据提交。

---

## 一、模块能力（真实实现部分）

| 能力 | 路由 | 状态 |
|------|------|------|
| 图像上传（ESP32-CAM 二进制 JPEG） | `POST /api/upload`（Content-Type: image/jpeg） | 已实现 |
| 浏览器取图 | `POST /api/capture_image` | 已实现（缓存图不再冒充实时，见第二节） |
| 图像历史 | `GET /api/image_history` | 已实现 |
| 推理入口 | `POST /api/infer_image` | 已实现，但结果来自 MOCK-V1 |
| 人工纠正 | `POST /api/correct_label` | 已实现，写 `human_corrected_label` + `corrected_at` |
| 纠正历史 | `GET /api/vision_history` | 已实现 |

数据表 `vision_results`（`server/app.py:113` 起）：
`image_path / model_label / model_score / model_version / status / human_corrected_label / corrected_at`。

---

## 二、2026-10-29 红线修复记录

### 修复前（错误行为）

`server/app.py` 在 30s 内命中 `latest.jpg` 时直接返回：

```python
return jsonify({
    success: True,
    image: ... ,
    source: esp32_camera
})
```

前端据此渲染绿色徽章「📷 实时拍摄（ESP32-CAM）」——把上一轮的旧图冒充成本次采集，属虚假证据。

### 修复后

```python
# 本目录：server/app.py（recent_cache 在 :906）；week7 同源实现见 app.py:871-893
if os.path.isfile(latest_path):
    age = time.time() - os.path.getmtime(latest_path)
    if age < 30:            # 走到这里 = 磁盘上有 30s 内文件，本分支不等待任何新图
        ...
        return jsonify({
            'success': False,
            'error': f'非本次采集：latest.jpg 是 {age:.1f}s 前上传的缓存图，本次未等待新图',
            'source': 'recent_cache',
            'captured_at': captured_at,
            'age_seconds': round(age, 1),
            'waited_seconds': 0.0,      # 0 等待，防止再出现「等待超时 + 0.0s」的自相矛盾
            'cache_file': 'latest.jpg',
            'image': ...                # 仍返回图片，但绝不标记为采集成功
        })
```

只有「30s 内没有任何文件」时才会建 PENDING 请求并进入 60×0.5s=30s 轮询（week7 `:913`），
超时返回 `{'success': False, 'source': 'timeout', 'waited_seconds': 30.0}`（`:930-931`）。

前端 `templates/index.html` 新增 `recent_cache` 分支：渲染图片的同时叠加红条
「⚠️ 非本次采集：这是 <拍摄时间> 的缓存图片（Ns 前）」，徽章降级为橙色「⚠️ 历史缓存」，状态栏走 `error` 样式。

### 影响范围

同一段复制代码存在于 8 个周目录，已全部修复（后端 + 前端各 8 处）：
`week1_vps_upload` / `week7_image_capture` / `week8_vision_feedback` / `week9_proactive_inquiry` /
`week10_multi_source_state` / `week11_context_engine` / `week12_feedback_preferences` / `week13_14_15_edge_inference`。

---

## 三、运行与复现

```bash
cd week8_vision_feedback/server
python app.py
# 浏览器打开 http://127.0.0.1:5000
```

复现（两段，均可稳定重复；下面是 2026-10-29 12:36 在 week7 同源代码上的实跑输出）：

**T1：为什么 1.5s 前的图不是「本次采集」**

```bash
# 1) 设备通道先上传一张 jpg（模拟板子上一次上报）
curl -X POST -H "Content-Type: image/jpeg" --data-binary @capture_20261001_161230.jpg \
     http://127.0.0.1:5000/api/capture_image
# 2) 1.5s 后浏览器点「拍照」
curl -X POST http://127.0.0.1:5000/api/capture_image
```

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

→ 浏览器拿到的 3974 字节解码后与本机 `latest.jpg` 的 sha 完全相同，且本次调用**没有**新增文件、
没有新增 `captured_images` 行、没有创建 `collection_requests` ⇒ 这张图属于**上一个请求**，
不属于「本次采集」。`age_seconds` 只表示「设备上一次上传距今多久」，与本次点击无关。

**T2：等待超时后 `latest.jpg` 未被替换**

```bash
# 把 latest.jpg 置为 200s 前，模拟「板子很久没上传」
python -c "import os,time; p='static/captured/latest.jpg'; os.utime(p,(time.time()-200,)*2)"
curl -X POST http://127.0.0.1:5000/api/capture_image
```

```
BEFORE age=200s sha=6d183d4ff36c590f n_files=26 n_captured=15 n_requests=61
RESP   status=404 elapsed=30.7s {"error":"no images","source":"timeout","success":false,"waited_seconds":30.0}
AFTER  age=231s sha=6d183d4ff36c590f n_files=26 n_captured=15 n_requests=62
  CHECK sha_unchanged=True mtime_unchanged=True file_count_unchanged=True captured_rows_unchanged=True new_requests=1
  DB newest request: ('20261029_123601_BB01D8', 'PENDING', '2026-10-29 12:36:01', 'capture')
```

→ 等满 30s → 404，`latest.jpg` 的 sha / mtime、文件数、`captured_images` 行数全部不变；
只多出一条 `PENDING` 采集请求（请求发出去了，设备没回图）。这就是「等待超时但 latest.jpg 未被替换」。

> T2 用 `os.utime` 只是构造「陈旧缓存」这个前置条件；被检验的是**响应 + 文件/DB 不变量**，
> 不依赖改 mtime 这一手法本身。上一版 README 只写「刷新 mtime 再调接口」并附 `age_seconds: 0.0`，
> 属于取证不规范（0.0s 是人为改表造成的），已作废。

---

## 四、未通过 / 未覆盖

- 真实视觉模型推理（无权重、无 NPU 部署）——**未通过**
- 端侧连续多帧推理与实时性指标——**未覆盖**
- 板载摄像头帧率、丢帧率——**未测**
- 人工纠正样本量与误判率统计——**未覆盖**（仅有接口与数据表）

---

## 五、目录说明

- `server/`、`esp32_firmware/`、`precaptured_images/`、`tools/` —— 主交付物与素材
- `fix_html.py` / `fix_html_structure.py` / `fix_prep.py` / `verify_fix.py` —— 历史一次性修补脚本，**非交付物**，可清理

---

最后更新：2026-10-29
