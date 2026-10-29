# 第17周：改进落地与个人项目迁移（心率场景）

> 更新：2026-10-29
> 一句话结论：本目录**不是一个已完成迁移的心率系统**。第 1 节的 UI 改进是真实代码改动；
> 第 2 节是**设计级迁移 + 可运行的软件仿真**，未接入 MAX30102 实物。

---

## 0. 证据等级（先看这张表）

| 项 | 状态 | 证据 / 说明 |
|----|------|-------------|
| 第16周同伴反馈驱动的 UI 改进 | **已落地（代码）** | `week13_14_15_edge_inference/server/templates/index.html` 的 `requestCollection()` 倒计时与离线横幅 |
| 心率场景迁移 | **设计 + 仿真，未接实物** | `week17_migration_and_fix/heart_rate_simulator.py` |
| MAX30102 驱动 / 采样 | **不存在** | 仓库内无该器件驱动，无实物接线记录 |
| 设备端真实断网补传 | **未验证** | 需要拔网实物复测，见第 4 节 |

---

## 1. 基于证据的代码改进（真实修改）

* **修改依据**：第16周同伴测试记录（n=2：1 人因等待焦虑连点，1 人误判降级横幅为报错）。
  说明：n=2 只能定位问题，**不构成统计显著**，不能据此宣称可用性提升幅度。
* **前端修改**：
  - `requestCollection()` 增加 3 秒倒计时视觉反馈，降低等待焦虑导致的误触；
  - 黄色降级横幅文案改为「网络离线，已切换至本地安全推理」。
* **回归记录**：重启 Flask 后 `GET /` 返回 200，新文案生效；Node 桩环境模拟「网络卡顿 / 正常返回 / 禁用期连点」三条路径，
  倒计时 3s→2s→1s 与提前恢复均符合预期；原有 `request_id` 状态机（`PENDING → RECEIVED → COMPLETED`）未被改动。

---

## 2. 个人项目迁移方案（边缘 AI 健康监护）

### 2.1 迁移的是哪两个模块

1. **环形缓存队列**：固件 `week13_14_15_edge_inference/esp32_firmware/main/main.c`
   `:92` `#define CACHE_QUEUE_SIZE 20`、`:102` `g_cache[]`、`:377-388` `cache_enqueue()`。
2. **双时间戳比对**：`original_ts` / `retransmit_ts` 与服务端判定
   `week13_14_15_edge_inference/server/app.py:356-367`（`delay>30s` 判 `recovered`）。

### 2.2 输入替换

原系统采集三轴加速度 `(ax, ay, az)`；个人项目替换为 `MAX30102` 的 **心率 heart_rate**。
**注意：这里只完成了字段与流程映射，器件驱动尚未编写。**

### 2.3 业务价值

心率是强时间相关数据。设备户外断网时心率写入环形队列；恢复网络补传时因为带 `original_ts`，
前端会明确标注「📦 已接收（补传）」，不会被误读为「当前实时心率」，避免医疗健康场景的严重误导。

### 2.4 失败处理

断网过久导致队列满（20 条）时，自动丢弃最旧记录（`g_cache_head` 前移），
并打印 `QUEUE FULL, dropped oldest record`（与固件现有日志同义）。

### 2.5 前端表现

数据卡片的 `transmission_status` 为 `recovered` 时显示「📦 已接收（补传）」并附 `observation_time`（见 `index.html` 中 `source-card-delay` 逻辑）。

---

## 3. 仿真验证（可复现）

```bash
cd week17_migration_and_fix
python heart_rate_simulator.py
```

脚本做了什么：

| 阶段 | 内容 | 预期 |
|------|------|------|
| 1 | 网络正常，心率 1Hz 直传 5 拍 | 全部 `live` |
| 2 | 断网，3 拍进队列 | 队列 3/20 |
| 3 | 网络恢复补传（delay≈36-38s） | 全部 `recovered` |
| 4 | 25 拍灌入 20 槽 | 丢弃 5 条最旧，补传 20 条 |

2026-10-29 实跑结果（节选）：

```
  6 |     72 |    09:00:06 |      09:00:44 |    38.0 | recovered
  7 |     75 |    09:00:07 |      09:00:44 |    37.0 | recovered
  8 |     78 |    09:00:08 |      09:00:44 |    36.0 | recovered
[INFO] flush -> 20 条补传记录，丢弃 5 条最旧记录
ALL ASSERTIONS PASSED (live=5, recovered=23, dropped=5)
```

断言覆盖：补传记录必须 `recovered` 且 `retransmit_ts > original_ts`；实时记录不得被标成补传；
补传延迟必须超过 30s 阈值；队列容量上限与丢最旧计数正确。

> 该输出只证明「队列 + 时间戳 + 状态判定」逻辑成立。

---

## 4. 未通过 / 待补（不要当成已完成）

- MAX30102 实物接入、采样精度、运动伪影处理 —— **未做**
- 真实断网（拔网线 / 关热点）下的设备端补传 —— **未做**，需实物复测并录串口日志
- 心率异常告警阈值与误报率 —— **未设计**
- 队列在掉电场景下的持久化（当前仅 RAM） —— **未实现**

---

## 5. 复用到个人项目的落地清单

1. 写 MAX30102 I2C 驱动，1Hz 采样输出 `heart_rate`；
2. 把固件 `cached_record_t` 的 `ax/ay/az` 换成 `heart_rate`，复用 `cache_enqueue()`；
3. 服务端 `accelerometer` 表新增 `heart_rate` 列（或新表），复用 `original_ts/retransmit_ts/delivery_status` 判定；
4. 前端卡片沿用 `transmission_status === recovered` 的补传徽章文案；
5. 用本目录脚本的输出作为「逻辑验证」材料，实物数据另行补测。

---

最后更新：2026-10-29
