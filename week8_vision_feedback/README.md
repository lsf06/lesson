# Week 8：视觉反馈闭环（Vision Feedback Loop）

> 项目：group01_esp32s3eye | EgoLink DevBench
> 目录：`week8_vision_feedback/`
> 更新：2026-10-29（红线修复后）

---

## 0. 证据等级声明（必读）

**本模块的视觉推理为模拟实现（MOCK-V1），未接入任何真实模型，明确不作为端侧/云端视觉推理能力的证据。**

| 项 | 事实 | 代码位置 |
|----|------|----------|
| 推理开关 | `ENABLE_MOCK_VISION = True`，请求直接走 `_mock_infer()` | `server/app.py:954`、`:1000-1006` |
| 结果来源 | `random.choice(VISION_LABELS)` 随机取标签，约 30% 概率给低分以演示 uncertain | `server/app.py:956-979` |
| 版本标注 | 结果内 `model_version = MOCK-V1`，不伪装真实模型分数 | `server/app.py:979` |
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
return jsonify({
    success: False,
    error: 等待新图超时，当前仅有 N.Ns 前的缓存图,
    source: recent_cache,
    captured_at: 2026-10-29 12:08:26,
    age_seconds: N.N,
    image: ...  # 仍返回图片，但绝不标记为采集成功
})
```

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

复现缓存判定（无 ESP32 时）：

```bash
# 刷新 latest.jpg 的 mtime，使其落入 30s 窗口
# 然后调用取图接口，应得到 success=false + source=recent_cache
curl -X POST http://127.0.0.1:5000/api/capture_image
```

预期输出（字段裁剪）：

```json
{"success": false, "source": "recent_cache", "captured_at": "...", "age_seconds": 0.0}
```

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
