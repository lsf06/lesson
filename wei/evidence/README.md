# 原始证据索引（`wei/evidence/`）

这里的日志是从采集目录 `%TEMP%\catdog_run\` **原样（按字节）拷来**的，没有再做任何加工，
用于支撑 `docs/catdog-run-report.md` 与 `docs/build-verification.md` 里的结论。
行尾为 CRLF，包含 PowerShell 包装脚本打的 `==== FLASH ====` 之类的分隔头。

## 1. 构建日志（“确实重新编译过”的直接证据）

| 文件 | 大小 | 内容 |
|---|---|---|
| `build-logs/projA_build2.log` | 276 947 B | 工程 A `idf.py build` 的**第二次全量/增量编译**输出（含 ninja 各目标） |
| `build-logs/projB_build3.log` | 303 768 B | 工程 B 用 `-B E:\esi_build\projB`（绕开 MAX_PATH）的第三次编译输出 |

> 注：A/B 的 build 目录（381 MB / 296 MB）和 `managed_components`（275+276 MB）**没有**随包，
> 因为 `.gitignore` 已忽略且新电脑会自动重新生成。

## 2. 实机运行日志（每个工程各一份正式归档 + 一份原始时间戳副本）

| 工程 | 正式归档（报告引用的是这一份） | 原始时间戳副本 | 一致性 |
|---|---|---|---|
| A 静态推理 | `extensions/03_catdog_static_infer/flash_output.txt` | `flash_output_firstrun_1329.txt` | 两次**独立运行**（13:29 首跑 / 14:47 复跑），`top1` 与 `infer` 逐位一致 |
| B 实时摄像头 | `extensions/03_live_catdog_assignment/flash_output.txt` | `flash_output_live_run_1412.txt` | 同一次运行的拷贝（14:12） |
| C 播种工具 | `extensions/_tools/sdcard_seed/flash_output.txt` | `flash_output_seed_run_1251.txt` | 同一次运行的拷贝（12:51） |

另有一份**临时实验**日志：`extensions/03_catdog_static_infer/flash_output_dogjpg_demo.txt`
—— 只把 `main/app_main.cpp` 的 `kImagePath` 临时改成 `/sdcard/images/dog.jpg`（确实为狗的图），
验证“流水线对狗图能给对类别”；抓完日志后源码已改回并重新编译烧录（板上最终跑的仍是原固件）。

## 3. 板卡身份（三份日志一致，用于确认是同一块板）

```text
Chip is ESP32-S3 (QFN56) (revision v0.2)
USB mode: USB-Serial/JTAG
MAC: 94:a9:90:1c:6f:88
Serial port COM6
```

## 4. 关键数字（与 `docs/` 中报告一致）

| 项目 | 期望值 |
|---|---|
| 工程 A `catdog_static_infer.bin` | `0x21ab50`（2 091 856 B），app 分区 `0x7d0000`，剩余 73% |
| 工程 B `camera_catdog_live.bin` | `0x4b4360`（4 933 472 B），app 分区 `0x6d6000`，剩余 31% |
| 播种工具 `sdcard_seed.bin` | `0x299ac0`（2 726 080 B），app 分区 `0x7d0000`，剩余 67% |
| Bootloader | `0x51c0`，剩余 36% |
| A 的 Top-1 | `top1=dog score=0.626124 infer=3240357 us` |
| B 的第 1 / 第 10 次推理 | `[1] cat: 0.6926` / `[10] cat: 0.7311` |
| 卡上三件 | `.espdl` 2 372 240 B、`sample.jpg` 23 099 B、`dog.jpg` 24 211 B（均 `written+verified`） |

编码说明：工程 B 的日志里“推理耗时”四个字是**采集终端当时的 GBK 字节**，用 UTF-8 打开会显示乱码；
新电脑上重新运行得到的是正常 UTF-8 日志，不影响任何结论。