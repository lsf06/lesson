# RUNBOOK · 从零到跑通（最小命令序列）

面向“换了一台电脑 / 想完整复现一遍”的场景。每一步都有**预期输出**，对不上就看后面的故障表。
详细背景见 `README.md`，装机与路径问题见 `MIGRATION-newPC.md`。

## 0. 前置检查

| 项 | 要求 | 检查命令 |
|---|---|---|
| ESP-IDF | **v5.4.4**（旧机实测版本） | `idf.py --version` |
| 终端 | “ESP-IDF 5.4 PowerShell” | 否则 `& 'C:\Espressif\frameworks\esp-idf-v5.4.4\export.ps1'` |
| 工程路径 | ≤115 字符（`C:\esp\lesson\wei\...` = 52 ✔） | `(Resolve-Path .).Path.Length` |
| 板子 | ESP32-S3-EYE 插好、驱动免装 | `[System.IO.Ports.SerialPort]::GetPortNames()` |
| SD 卡 | 工程 A / C 需要（**工程 B 不需要**） | — |

下文的 `COM6` 是旧机口号，**请全部替换成你的实际口号**；退出监视器用 `Ctrl + ]`。

---

## 1. 工程 B：LCD 实时猫狗分类（最先跑这个，不需要 SD 卡）

```powershell
cd C:\esp\lesson\wei\extensions\03_live_catdog_assignment
idf.py build
idf.py -p COM6 flash monitor
```

**通过判据**（逐条对上即成功）：

```text
camera_catdog_live.bin binary size 0x4b4360 bytes. Smallest app partition is 0x6d6000 bytes. 0x221ca0 bytes (31%) free.
Bootloader binary size 0x51c0 bytes. 0x2e40 bytes (36%) free.
Serial port COM6
Chip is ESP32-S3 (QFN56) (revision v0.2)
USB mode: USB-Serial/JTAG
MAC: 94:a9:90:1c:6f:88
Hash of data verified.            ×3
I (2131) camera_catdog_live: Classifier loaded successfully
I (2561) LVGL: Starting LVGL task
I (2681) camera_catdog_live: System ready — camera preview + periodic inference running
I (6451) camera_catdog_live: [1] cat: 0.6926 (推理耗时 3269503 us / 3269.503 ms)
I (40391) camera_catdog_live: [10] cat: 0.7311 (推理耗时 3263743 us / 3263.743 ms)
```

- 屏幕上应能看到摄像头预览；每 0.5 s 触发一次推理（纯推理约 **3.26 s**，所以打印间隔较长，属正常）
- 会一直循环，按 RST 或 `Ctrl + ]` 结束
- 模型是**编进 flash 的**（`main/models/s3/catdog_mobilenet_v2.espdl`，2 372 224 B），插不插卡都能跑

---

## 2. 工程 A：SD 卡静态图推理

前置：卡里已有 `/sdcard/models/s3/catdog_mobilenet_v2.espdl` 与 `/sdcard/images/sample.jpg`（没有就先做第 3 步）。

```powershell
cd C:\esp\lesson\wei\extensions\03_catdog_static_infer
idf.py build
idf.py -p COM6 flash monitor
```

**通过判据**：

```text
catdog_static_infer.bin binary size 0x21ab50 bytes. Smallest app partition is 0x7d0000 bytes. 0x5b54b0 bytes (73%) free.
I (1193) catdog_static_infer: SD card mounted at /sdcard
I (3953) catdog_static_infer: decoded /sdcard/images/sample.jpg: 336 x 499 in 54132 us
I (7193) catdog_static_infer: top1=dog score=0.626124 infer=3240357 us
```

- 打印完就结束（**不是死机**），按 **RST** 可再跑一次
- `infer=3240357 us`（3.24 s）是**纯推理耗时**，`54132 us` 是**软件 JPEG 解码耗时**，两者独立——这就是本案例要观察的重点
- ⚠️ `top1=dog score=0.626124`：被推理的 `sample.jpg` 在仓库里其实是 `valid/cat/cat.1001.jpg`（**猫图**），
  这是一次**模型误判**（仅训 3 epoch，`val_accuracy` ≈ 0.61）。它证明的是“读图→解码→推理→打印”这条流水线正常，
  **不是**准确率验收。对狗图的表现见 `extensions/03_catdog_static_infer/flash_output_dogjpg_demo.txt`（临时实验）。

---

## 3. 播种工具：把模型与两张图写进 SD 卡

```powershell
cd C:\esp\lesson\wei\extensions\_tools\sdcard_seed
idf.py build            # 只用 IDF 自带组件，不联网
idf.py -p COM6 flash monitor
```

**通过判据**：

```text
sdcard_seed.bin binary size 0x299ac0 bytes. Smallest app partition is 0x7d0000 bytes. 0x536540 bytes (67%) free.
I (1282) sdcard_seed: SD card mounted at /sdcard
I (9452) sdcard_seed: written+verified: /sdcard/models/s3/catdog_mobilenet_v2.espdl (2372240 bytes)
I (9552) sdcard_seed: written+verified: /sdcard/images/sample.jpg (23099 bytes)
I (9652) sdcard_seed: written+verified: /sdcard/images/dog.jpg (24211 bytes)
```

- 三条 `written+verified` = 写完立刻回读校验通过；写成后把卡插到读卡器上应能直接看到这三个文件
- 卡是空的也没关系（代码里开了 `format_if_mount_failed`，会自动格式化为 FAT32 再写）

---

## 4. 一次把三个工程都编译一遍（不含烧录，安全批量）

```powershell
$root = 'C:\esp\lesson\wei\extensions'
foreach ($p in @('03_live_catdog_assignment','03_catdog_static_infer','_tools\sdcard_seed')) {
    Write-Host "=== build $p ==="
    Set-Location (Join-Path $root $p)
    idf.py build
    if ($LASTEXITCODE -ne 0) { Write-Host "!! $p 构建失败，已停止"; break }
}
```

非交互式烧录（不进入监视器，适合脚本化）：`idf.py -p COM6 flash`（要看日志再单独 `idf.py -p COM6 monitor`）。

| 工程 | 期望固件大小 | 期望 app 分区 |
|---|---|---|
| `03_catdog_static_infer` | `0x21ab50` | `0x7d0000`（剩余 73%） |
| `03_live_catdog_assignment` | `0x4b4360` | `0x6d6000`（剩余 31%） |
| `_tools\sdcard_seed` | `0x299ac0` | `0x7d0000`（剩余 67%） |

> 尺寸若只差几字节（构建时间戳/路径长度会轻微影响），属正常；差很多就先核对
> `idf.py --version` 是否为 **v5.4.4**、以及 `dependencies.lock` 是否被改动。

---

## 5. 故障表（对不上就查这里）

| 现象 | 原因 | 处理 |
|---|---|---|
| `fatal error: opening dependency file ….obj.d: No such file or directory` | 工程路径超过 MAX_PATH 260 | 把 `wei\` 挪到 `C:\esp\…`，或用 `-B C:\esi_build\projB` |
| `espressif/esp_video … not found` / `Failed to install component` | 托管组件安装被长路径截断 | 跑 `powershell -ExecutionPolicy Bypass -File extensions\_tools\fix_esp_video_long_path.ps1`（幂等） |
| 拉组件超时 / `Failed to download` | 首次构建需联网 | 联网重试；或从旧机拷 `managed_components`（`MIGRATION-newPC.md` 第 3 节） |
| `SD card mount failed: ESP_ERR_TIMEOUT` 等 | 卡没插好 / 非 FAT32 / 卡坏 | 重新插卡；空白卡可直接跑播种工具自动格式化 |
| `cat/dog model load failed: /sdcard/models/s3/catdog_mobilenet_v2.espdl` | 卡里缺模型 | 先跑第 3 节播种工具 |
| `cannot open image: /sdcard/images/sample.jpg` | 卡里缺图 | 同上 |
| `JPEG decode failed` | 文件不是合法 JPEG | 重新播种 |
| `idf.py: command not found` | 不在 IDF 环境终端 | 换成“ESP-IDF 5.4 PowerShell” |
| 串口被占用 / `could not open port` | 别的程序占着 COM 口 | 关掉其它 monitor / 串口助手；拔插 USB |
| B 的日志中文花屏 | 旧日志是 GBK 字节 | 正常现象，见 `evidence/README.md` |

---

## 6. 验收清单（逐条打勾即可认为“复现成功”）

- [ ] `idf.py --version` = **ESP-IDF v5.4.4**
- [ ] 三个工程 `idf.py build` 全部 `Project build complete`，固件大小与第 4 节表一致
- [ ] 工程 B：出现 `System ready — camera preview + periodic inference running`，并有 `[n] cat/dog: 0.xxxx`
- [ ] 工程 A：出现 `SD card mounted at /sdcard`、`decoded … in … us`、`top1=… infer=… us`
- [ ] 播种工具：三条 `written+verified`
- [ ] 用读卡器核对卡上三件的 SHA-256 与 `CHECKSUMS.txt` 的 `# ================= SD-CARD-3 =================` 段一致
- [ ] 换电脑前后关键数字一致：A `top1=dog score=0.626124 infer=3240357 us`；固件 `0x21ab50` / `0x4b4360` / `0x299ac0`

---

## 7. 相关文档

| 想看什么 | 去哪 |
|---|---|
| 包内容总览、哈希、裁剪说明 | `README.md` |
| 换电脑、路径、COM 口号、SD 卡要不要重写 | `MIGRATION-newPC.md` |
| 日志与证据的来源与对应关系 | `evidence/README.md` |
| 每个工程的设计与逐行讲解 | `extensions/*/README.md`、`docs/catdog-run-report.md` |