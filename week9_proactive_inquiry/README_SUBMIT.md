# 第9周：视觉事件触发主动询问 (Proactive Inquiry)

> **提交日期**: 2026-10-08
> **对应目录**: `week9_proactive_inquiry/`

---

## 1. 新增功能

| 功能 | 说明 |
|------|------|
| **uncertain 事件触发** | 推理返回 `status=="uncertain"` 时，前端主动弹出询问模态框 |
| **📷 重拍** | 清空当前结果，重新触发拍照流程，记录 `user_action='retake'` |
| **❌ 忽略 + 冷却** | 关闭弹窗，启用 60 秒冷却，期间再次推理若仍 uncertain 不再弹出；用 localStorage 持久化 |
| **冷却状态持久化** | `localStorage.proactiveCooldownUntil` 保存时间戳，刷新页面不丢失 |
| **运行位置标注** | 面板下方明确标注模型/设备/服务实际运行位置 |
| **冷却倒计时** | 冷却期间显示"已忽略本次询问，冷却中（剩余 XX 秒）" |

---

## 2. API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/record_user_action` | 记录用户对 uncertain 推理的响应（retake/ignore），写入 vision_results |

---

## 3. 数据库新增字段

```sql
ALTER TABLE vision_results ADD COLUMN user_action TEXT;    -- 'retake' | 'ignore'
ALTER TABLE vision_results ADD COLUMN action_at TEXT;      -- 操作时间 ISO datetime
```

兼容策略：`init_vision_db()` 在 CREATE TABLE 后用 try/except ALTER TABLE，列已存在则跳过。

---

## 4. 测试记录

### 测试环境

- Flask 服务器：`10.1.41.43:5000`
- 浏览器：Chrome
- ESP32：COM4（在线采集或降级模式均可）

### 完整测试流程

| 步骤 | 操作 | 预期 | 结果 |
|------|------|------|------|
| ① 拍照 | 点击「📷 拍照」 | 图像区域显示图片 | ✅ |
| ② 推理触发 uncertain | 点击「🔍 推理」 | 多次推理中约 30% 概率触发低分 | ✅ |
| ③ 模态框弹出 | uncertain 发生时 | 弹出半透明遮罩 + 橙色边框模态框，文案："⚠️ 画面不可用/无法确定" | ✅ |
| ④ 点击🔄重拍 | 点击「🔄 重拍」 | 模态框关闭 → 图片区域清空 → 重新拍照 → DB 记录 user_action='retake' | ✅ |
| ⑤ 再次触发 uncertain → 点击❌忽略 | 推理→低分→点「❌ 忽略」 | 模态框关闭 → DB 记录 user_action='ignore' → 面板显示"冷却中（剩余 60 秒）" | ✅ |
| ⑥ 冷却期间再次推理 | 冷却中再次点击推理 | 即使返回 uncertain，也**不弹出**询问框，仅更新冷却倒计时 | ✅ |
| ⑦ 冷却结束后推理 | 等待 60 秒后再次推理 → uncertain | 冷却提示消失，询问框**正常弹出** | ✅ |
| ⑧ 刷新页面冷却不丢 | 忽略后立即刷新页面 | localStorage 恢复冷却状态，倒计时继续 | ✅ |
| ⑨ 人工纠正保留 | 推理后点击「✏️ 人工纠正」 | 弹窗输入 → 显示"模型说 XX / 人工纠正为 YY"对比 | ✅ |
| ⑩ 重拍清除冷却 | 在有冷却时手动点击「📷 重新采集」 | 冷却提示消失，冷却状态清除 | ✅ |

---

## 5. 问题归因与修复清单

| # | 现象 | 归因 | 修复 |
|---|------|------|------|
| 1 | 旧数据库没有 user_action 列 | 第8周 CREATE TABLE 不含这两个字段 | init_vision_db() 中 ALTER TABLE try/except 兼容 |
| 2 | 冷却状态刷新后丢失 | 未持久化，仅存于 JS 内存变量 | 添加 localStorage.setItem/getItem 持久化 proactiveCooldownUntil |
| 3 | 冷却期间不确定是否生效 | 无可见提示 | 在面板中添加 .cooldown-hint 显示倒计时 |
| 4 | 重拍后冷却未清除 | recapture() 函数无冷却重置逻辑 | monkey-patch recapture() 追加 proactiveCooldownUntil=0 |
| 5 | 两次连续 uncertain 可能弹出两个模态框 | showProactiveInquiry 无去重 | 添加 if (document.getElementById('proactive-overlay')) return |
| 6 | 老师要求标注实际运行位置 | 第8周未标注 | 添加 .location-note 显示模型/设备/服务位置 |
| 7 | 拍照卡死——ESP32 未响应 capture 命令 | COM4 被占用且板子跑的 lesson10_real 旧固件（无 poll_service） | 杀进程释放 COM4，重新烧录 week7 固件恢复 poll_service + capture_and_upload |
| 8 | 烧录 week7 固件后摄像头仍不工作 | 草率复制依赖（robocopy 单独拷贝不保证完整） | 重新执行 idf.py fullclean && idf.py build && idf.py -p COM4 flash 编译完整项目 |
| 9 | ipconfig 双 IP（以太 10.1.41.43 + WLAN 10.1.41.199） | 双网卡同子网，路由歧义 | 未阻断通信；Flask 绑定 0.0.0.0:5000 两边可访问 |

## 6. 启动命令## 6. 启动命令

```powershell
cd "D:\lesson\xiaolin\lesson-main (1)\lesson-main\week9_proactive_inquiry\server"
python app.py
```

浏览器访问：`http://10.1.41.43:5000`

---

## 7. 架构图

```
用户点击推理
    │
    v
POST /api/infer_image
    │
    ├── status='success' ──► 正常展示标签/置信度
    │
    └── status='uncertain' ──► 前端检查冷却
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
              冷却中？       无冷却         重复弹窗？
                    │              │              │
              更新倒计时   弹出询问框      return
              不弹出        ┌────┴────┐
                          🔄 重拍   ❌ 忽略
                          │              │
                     recapture()   POST /api/record_user_action
                          │         action='ignore'
                          │         localStorage 存冷却
                          │         启动倒计时
                          │
                     POST /api/record_user_action
                     action='retake'
```