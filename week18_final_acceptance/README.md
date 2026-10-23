# 第18周：系统成果归档与真实复盘报告

## 1. 原型运行环境与接口索引

* **最终版本**：v1.0-final（运行于 `week13_14_15_edge_inference`）。
* **硬件**：ESP32-S3-EYE (OV2640 + QMA6100P)。
* **核心复用接口**：
* 端侧容错：`main.c` 中的 `cache_enqueue`（20条环形队列，定长 `CACHE_QUEUE_SIZE=20`，满队列丢弃最旧并打印 `QUEUE FULL, dropped oldest record`）。
* 并发幂等：`app.py` 中的 `BEGIN IMMEDIATE` 事务锁（`/api/upload` 对同一 `request_id` 串行化校验）。
* 交互状态机：前端 `checkOfflineStatus()`（每 15s 轮询 `/api/offline_status`，按 `offline_mode` / `banner_text` 控制黄条）与 `source-card-delay` 补传标记（按服务端 `delivery_status='recovered'` 渲染“📦 已接收（补传）”）。
  * 说明：仓库中**不存在** `is_device_offline` / `recent_retransmit_count` 这两个变量名，实际实现即上述两处（离线判定与补传判定）。

## 2. 真实遗留问题与未达成能力（严格遵守大纲要求，绝不隐瞒）

* **视觉大模型（第8-9周）**：未接入真实云端 VLM 模型，仅用本地规则和模拟基线完成了前端界面闭环（前端拍完照后弹窗）。`/api/infer_image` 实际调用的是 `_mock_infer()`，返回的 `model_version` 硬编码为 `MOCK-V1`，不产生真实模型分数。
* **语音链路（第4-6周）**：受限于硬件麦克风驱动未打通，采用文字输入替代语音输入，完成了 NLU 本地意图解析。可核实证据：`week6_voice_interaction/server/app.py` 中不存在任何 audio/ASR/录音相关接口（关键词计数为 0）。
* **样本局限（第16周）**：同伴测试样本量仅为 2 人（n=2），数据存在主观性，结论未外推。

## 3. 个人贡献自证

* 独立完成了从底层 ESP32 固件缓存机制、后端事务锁、到前端降级与补传 UI 的全链路开发。
* 独立完成了真实的并发注入测试与过期拦截验证：服务端 `flask.log` 中可检索到 `Task expired receipt recorded: request_id=W15_EXPIRED_TEST`（2026-10-21）与 229 条 `Duplicate upload ignored` 记录；设备侧对应输出语句为 `main.c` 中的 `Task expired, skipped`（原始串口日志未随仓库归档，仅保留打印语句与 Flask 侧日志）。

## 4. 下学期迭代建议

* 将本地规则引擎替换为端侧轻量级 TFLite 模型。
* 完善硬件音频采集链路，接入真实的 ASR/TTS。
