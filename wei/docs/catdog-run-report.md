# 猫狗分类示例：编译 / 烧录 / 运行报告

> 报告人：____________（请填写） ｜ 日期：2026-09-27 ｜ 硬件：ESP32-S3-EYE ｜ 工具链：ESP-IDF v5.4.4（Windows）

> 覆盖工程：`extensions/03_catdog_static_infer`（SD 卡静态图片推理）、`extensions/03_live_catdog_assignment`（LCD 实时猫狗分类），以及给它们准备素材的 `extensions/_tools/sdcard_seed`。
>
> 记录原则：**只写真正跑过、有原始日志的内容**。下面所有数值与日志都来自 2026-09-27 这一次实机验证，日志摘录按终端原样保留（包含正常出现的告警行，便于对照）。

## 0. 摘要

| 目标 | 关键命令 | 实测结果 |
|---|---|---|
| 扩展案例 3（静态推理） | `idf.py build` → `idf.py -p COM6 flash monitor` | ✅ 构建通过 + 实机运行：`top1=dog score=0.626124 infer=3240357 us`（13:29 与 14:47 两次独立运行逐位一致） |
| 阶段性作业（LCD 实时） | `idf.py -B E:\esi_build\projB build` → `idf.py -B E:\esi_build\projB -p COM6 flash monitor` | ✅ 构建通过 + 实机运行：`[1] cat: 0.6926` … `[10] cat: 0.7311`，单次推理 ≈3.26 s |
| SD 卡播种工具 | `idf.py -p COM6 build flash monitor`（**不需要** `-B`） | ✅ 模型 + 2 张 JPEG 写入卡，逐个回读 SHA-256 校验通过 |

一句话结论：**两个猫狗工程都能在这台 Windows 机器上编译、烧录、运行**；区别只在于——**阶段性作业（工程 B）必须用短构建目录 `-B`**，因为它的路径比静态推理工程多 3 个字符，越过了 Windows 的 260 字符路径上限；静态推理工程（工程 A）不需要任何绕行。

## 1. 验证环境

| 项 | 值 |
|---|---|
| 日期 | 2026-09-27 |
| 主机 / 终端 | Windows + PowerShell（VS Code 内终端） |
| ESP-IDF | v5.4.4（`D:\Download\esp\Espressif\frameworks\esp-idf-v5.4.4`） |
| 工具链 / 构建 | xtensa-esp32s3-elf、CMake 3.30.2、ninja、Python 3.12（`idf5.4_py3.12_env`） |
| 开发板 | ESP32-S3-EYE，8 MB flash + 8 MB 八线 PSRAM @80 MHz，板载 OV2640 + LCD |
| 串口 | COM6（烧录 460800，监视器 115200） |
| microSD 卡 | FAT32，容量约 32 GB（`sdcard_seed` 挂载日志：`total=31146768 KiB free=31139632 KiB`） |
| 仓库路径 | `E:\study\lsf\daima\ganzhi\esi-mvp-code-main\esi-mvp-code-main\esi-mvp-code-main`；`extensions` 这一层就有 **90 个字符**，是本报告大部分麻烦的根源 |
| Windows 长路径支持 | 本机注册表 `LongPathsEnabled = 0`（未开启），因此一律按 260 字符上限处理 |

终端里先加载 IDF 环境（新开终端必做，否则 `idf.py` 不存在）：

```powershell
& 'D:\Download\esp\Espressif\frameworks\esp-idf-v5.4.4\export.ps1'
idf.py --version      # 预期：ESP-IDF v5.4.4
```

## 2. 前置准备（只做一次）

### 2.1 修复 `esp_video` 托管组件装不进去

托管组件管理器会把 `espressif/esp_video` 复制到 `<工程>\managed_components\espressif__esp_video`。本仓库里这个目标前缀已经约 132 字符，而 `esp_video` 内部路径最长约 150 字符，复制时越界，结果是目录写了一半、`.component_hash` 没生成，之后每次构建都被判定为“组件不存在”。

```powershell
# 默认处理 03_catdog_static_infer 和 03_live_catdog_assignment 两个工程；幂等，可重复跑
powershell -ExecutionPolicy Bypass -File extensions\_tools\fix_esp_video_long_path.ps1
```

预期：脚本打印两个工程的组件哈希，并把 `managed_components\espressif__esp_video` 建成本机短路径目录（`%USERPROFILE%\ev_video`）的目录联接（junction）。原理与注意事项见 [`extensions/_tools/README.md`](../extensions/_tools/README.md) 第 2 节。

### 2.2 给 SD 卡放模型和测试图（没有读卡器也能做）

`extensions/_tools/sdcard_seed` 把模型和两张 JPEG 用 `EMBED_FILES` 嵌进自己的固件，上电后用**和 BSP 相同的 SDMMC 引脚**写卡并逐个回读 SHA-256 校验：

```powershell
cd extensions\_tools\sdcard_seed
idf.py set-target esp32s3      # 首次
idf.py -p COM6 build flash monitor
```

预期输出（实测摘录）：

```text
I (1192) sdcard_seed: seeding ESP32-S3-EYE microSD card (model + sample images)
I (1282) sdcard_seed: SD card mounted at /sdcard
I (1292) sdcard_seed: FATFS: total=31146768 KiB free=31139632 KiB
I (9452) sdcard_seed: written+verified: /sdcard/models/s3/catdog_mobilenet_v2.espdl (2372240 bytes)
I (9552) sdcard_seed: written+verified: /sdcard/images/sample.jpg (23099 bytes)
I (9652) sdcard_seed: written+verified: /sdcard/images/dog.jpg (24211 bytes)
```

写卡不是"写完就算"：每个文件都**回读全文并用 SHA-256 比对**，实测卡上文件的哈希与 PC 端对**仓库源文件**执行 `Get-FileHash -Algorithm SHA256` 的结果**逐位相同**，说明卡里放的就是仓库里的那份产物：

| 卡上路径 | 大小 | SHA-256（板子回读 = PC 端计算） | 仓库来源 |
|---|---|---|---|
| `/sdcard/models/s3/catdog_mobilenet_v2.espdl` | 2 372 240 B | `5b33fb728e7f8b2da964c2c137dcdb2d73d615ae87ccec13409bf656935be78e` | `extensions/02_quantize_catdog_model/outputs/catdog_mobilenet_v2.espdl` |
| `/sdcard/images/sample.jpg` | 23 099 B | `b32166fed6526078aa5bf7a986c4ecaa1b377ad3f65153f09bde3f9176ae306b` | `extensions/01_train_catdog_model/cats-dogs-data/valid/**cat**/cat.1001.jpg` ← **猫图** |
| `/sdcard/images/dog.jpg` | 24 211 B | `ff581e37e606c9a468b08e245a02564133f253c1c64a64c5bc8570e1ef5e0c47` | `extensions/01_train_catdog_model/cats-dogs-data/valid/**dog**/dog.1001.jpg` ← 狗图 |

卡本身的信息（来自 `sdmmc_card_print_info`）：名称 `SB32G`、类型 `SDHC`、容量 **30 436 MB**、FATFS 可用 **31 139 632 KiB**（≈ 29.7 GiB）。完整写卡日志（挂载、写入、逐个回读、`========== sdcard_seed summary ==========` 汇总表）已留档：[`extensions/_tools/sdcard_seed/flash_output.txt`](../extensions/_tools/sdcard_seed/flash_output.txt)。

- 看到三行 `written+verified` 即成功，按 `Ctrl + ]` 退出监视器；`format_if_mount_failed` 已打开，空白卡 / 非 FAT 卡会被自动格式化。
- **不用拔卡、不用读卡器**：整块卡的内容由板子自己写进去，写成后也可以把卡拔下来插到电脑上核对（能看到 `models/s3/catdog_mobilenet_v2.espdl`、`images/sample.jpg`、`images/dog.jpg` 三个文件）。
- 这个工程只依赖 `fatfs`、`sdmmc`、`esp_driver_sdmmc`、`mbedtls`，**不依赖 BSP / esp_video**，所以既不用跑 2.1，也不用 `-B`：本次实测它的构建根目录 115 字符、构建树最长文件 252 字符，都在上限内。
- 构建结果：`sdcard_seed.bin binary size 0x299ac0`（约 2.60 MiB），app 分区剩余 67%。

## 3. 工程 A：`extensions/03_catdog_static_infer`（SD 卡静态图片推理）

### 3.1 编译

```powershell
cd extensions\03_catdog_static_infer

idf.py set-target esp32s3   # 首次（或换目标芯片 / 删过 sdkconfig 时）生成配置并下载托管组件
idf.py build
```

预期结尾 `Project build complete.`。实测摘录：

```text
Generated ...\03_catdog_static_infer\build\bootloader\bootloader.bin
Bootloader binary size 0x51c0 bytes. 0x2e40 bytes (36%) free.
catdog_static_infer.bin binary size 0x21ab50 bytes. Smallest app partition is 0x7d0000 bytes. 0x5b54b0 bytes (73%) free.
Project build complete. To flash, run: ...
```

- 固件 `0x21ab50` = 2 207 568 B ≈ **2.11 MiB**，app 分区 8 MB，剩余 **73%**。
- 全量构建耗时随网络波动（首次要联网拉 `esp-dl`、`esp32_s3_eye` BSP、`esp_video` 等托管组件，本次在 20～40 分钟量级）；组件已缓存后增量构建约 1～2 分钟。
- **本工程不需要 `-B` 短构建目录**：构建根目录 119 字符，构建树实测最长文件 256 字符，都在 259 字符可用上限内。

配置前提（本次已满足；换机器或删过 `sdkconfig` 时自查）：模型文件名 `catdog_mobilenet_v2.espdl` 超出 FAT **8.3 短名**限制，必须开启长文件名支持。

```powershell
# 两个工程的 sdkconfig.defaults 里已经带了 CONFIG_FATFS_LFN_HEAP=y，正常不必手改；
# 仅当你的 sdkconfig 是旧配置生成的，才需要重新生成一次：
Remove-Item sdkconfig -ErrorAction SilentlyContinue
idf.py set-target esp32s3
Select-String -Path sdkconfig -Pattern 'FATFS_LFN'   # 必须看到 CONFIG_FATFS_LFN_HEAP=y
```

### 3.2 烧录 + 串口监视

```powershell
idf.py -p COM6 flash monitor
```

预期：esptool 依次写 3 个区域（`0x0` bootloader、`0x10000` app、`0x8000` 分区表），每个都打印 `Hash of data verified.`，随后板子复位进入监视器。退出监视器按 **`Ctrl + ]`**。

注意：工程 A 是**跑一遍就结束**的（不循环），监视器里只会出现一次结果；想再看一次，要么重新执行 `idf.py -p COM6 flash`（烧录结束会复位），要么按板子上的 **RST** 键——**单独开 `monitor` 看到的是空闲状态，不会有新结果**。

### 3.3 实测输出（原始日志）

本工程是**跑一遍就结束**的一次性程序，所以每次验证都要靠"烧录 / 复位后那一次开机"抓日志（事后单独开 `monitor` 是看不到东西的，必须按板子上的 RST）。下面两次独立运行都在 2026-09-27、同一块板子（MAC `94:a9:90:1c:6f:88`）、同一张 SD 卡、未改任何代码。

**（1）13:29 首次实测**

```text
rst:0x15 (USB_UART_CHIP_RESET),boot:0x2a (SPI_FAST_FLASH_BOOT)
I (41) boot.esp32s3: SPI Flash Size : 8MB
I (1005) app_init: Project name:     catdog_static_infer
I (1023) app_init: ESP-IDF:          v5.4.4
I (1066) esp_psram: Adding pool of 8192K of PSRAM memory to heap allocator
W (1103) ESP32-S3-EYE: Warning: Long filenames on SD card are disabled in menuconfig!
I (1193) catdog_static_infer: SD card mounted at /sdcard
W (3863) dl::Model: minimize() will delete unused inference variables, breaking model testing/debugging.
I (3953) catdog_static_infer: decoded /sdcard/images/sample.jpg: 336 x 499 in 54132 us
I (7193) catdog_static_infer: top1=dog score=0.626124 infer=3240357 us
I (7223) main_task: Returned from app_main()
```

**（2）14:47 复跑**（重新 `idf.py -p COM6 flash monitor`）

```text
rst:0x15 (USB_UART_CHIP_RESET),boot:0x2a (SPI_FAST_FLASH_BOOT)
I (41) boot.esp32s3: SPI Flash Size : 8MB
W (1103) ESP32-S3-EYE: Warning: Long filenames on SD card are disabled in menuconfig!
I (1183) catdog_static_infer: SD card mounted at /sdcard
W (3853) dl::Model: minimize() will delete unused inference variables, breaking model testing/debugging.
I (3943) catdog_static_infer: decoded /sdcard/images/sample.jpg: 336 x 499 in 54149 us
I (7183) catdog_static_infer: top1=dog score=0.626124 infer=3240357 us
I (7213) main_task: Returned from app_main()
```

两次对照：

| 项 | 13:29 首次 | 14:47 复跑 | 结论 |
|---|---|---|---|
| SD 卡挂载 | `SD card mounted at /sdcard` | 同 | 稳定 |
| JPEG 解码 | 336 × 499，`54132 us` | 336 × 499，`54149 us` | 解码尺寸一致；耗时差 **17 µs**（微秒级抖动） |
| Top-1 结果 | `top1=dog score=0.626124 infer=3240357 us` | `top1=dog score=0.626124 infer=3240357 us` | **类别、置信度、纯推理耗时逐位一致** —— 同一输入 + 同一模型下推理是确定性的，这两行可直接当作可复现指标 |
| 结束方式 | `Returned from app_main()` | 同 | 一次性任务正常结束，不是崩溃 |

> 完整终端输出（`idf.py flash` + `idf.py monitor` 全文）已随仓库留档：[`extensions/03_catdog_static_infer/flash_output.txt`](../extensions/03_catdog_static_infer/flash_output.txt)。

### 3.4 怎么读这几行

| 日志行 | 含义 |
|---|---|
| `SD card mounted at /sdcard` | 卡挂载成功；挂载失败会打印 `SD card mount failed` 并**直接退出**（BSP 配置 `format_if_mount_failed=false`，不会自动格式化你的卡） |
| `decoded /sdcard/images/sample.jpg: 336 x 499 in 54132 us` | 解码后的像素尺寸（**就是你原图的尺寸**，缩放到 224×224 在预处理阶段做）与软件 JPEG 解码耗时 **54.1 ms** |
| `top1=dog score=0.626124 infer=3240357 us` | Top-1 类别、softmax 置信度、**纯推理耗时 3.240 s**；解码耗时与推理耗时是两个独立的数，正是本案例要观察的重点 |
| ⚠️ 关于这条结果本身（必须说清楚） | 被推理的 `/sdcard/images/sample.jpg` 在仓库里的来源是 `extensions/01_train_catdog_model/cats-dogs-data/valid/**cat**/cat.1001.jpg`（见 `_tools/sdcard_seed/main/CMakeLists.txt` 第 8 行），也就是**一张猫图被模型判成了 dog（置信度 0.626）**。这是**模型的误判，不是程序问题**：本案例用的是上游从零训练、只跑 3 个 epoch 的 MobileNetV2，`val_accuracy` 仅 0.6175 / 0.6075 / 0.615（见下方说明）。反过来说，它证明了"读图 → 解码 → 推理 → 打印类别与置信度"这条流水线本身工作正常——验收点就在这里，不在刷准确率 |
| `Returned from app_main()` | 本工程**跑一遍就结束、不循环**，这是正常结束，不是崩溃 |
| 两条 `W` 开头 | **都是正常现象，可忽略**：`Warning: Long filenames ... disabled` 是 BSP 检查旧版配置符号造成的固定输出（开启 LFN 后照样打印）；`minimize()` 警告表示推理前删掉用不到的中间变量以节省内存 |

> 关于结果的正确性：本案例用的上游模型是**从零训练、只跑 3 个 epoch** 的 MobileNetV2（见 [`extensions/01_train_catdog_model`](../extensions/01_train_catdog_model/)），实测 `outputs/metrics.csv` 三轮 `val_accuracy` 为 **0.6175 / 0.6075 / 0.615**，也就是“略好于瞎猜”，`extensions/01_train_catdog_model/README.md`（第 134、161 行）也把 50%～70% 记为正常预期。所以**分类结果不稳定、猫狗都可能判错属模型能力问题，不是编译或烧录问题**：本案例的验收重点是流水线跑通与指标可复现，而不是刷准确率。要更准，按扩展案例 1 的说明把 `weights=None` 改成预训练权重或增加数据/轮数。

### 3.5 附：把输入换成确实是狗的图会怎样（一次性演示，源码已改回）

为了回答"模型对**确实是狗**的图能不能判对"，本次额外做了一次**临时实验**：只改 `main/app_main.cpp` 第 14 行的 `kImagePath`，从 `/sdcard/images/sample.jpg` 改成 `/sdcard/images/dog.jpg`（该狗图已由写卡工具放在卡上，来源 `valid/dog/dog.1001.jpg`），然后 `idf.py -p COM6 build flash monitor`；**抓完日志立刻把源码改回原样，并重新编译烧录**，因此板上最终运行的仍是 3.3 那版原固件（`catdog_static_infer.bin` 仍为 `0x21ab50`）。

```text
I (1193) catdog_static_infer: SD card mounted at /sdcard
I (3963) catdog_static_infer: decoded /sdcard/images/dog.jpg: 347 x 500 in 57251 us
I (7193) catdog_static_infer: top1=dog score=0.527316 infer=3234556 us
I (7223) main_task: Returned from app_main()
```

| 输入图片 | 图片真值 | 模型输出 | 判断 |
|---|---|---|---|
| `/sdcard/images/sample.jpg`（3.3 正式路径） | cat | `top1=dog` 置信度 0.626124 | ❌ 判错（模型欠训练） |
| `/sdcard/images/dog.jpg`（本演示） | dog | `top1=dog` 置信度 0.527316 | ✅ 判对，但置信度只有 0.53，只是勉强过半 |

结论：流水线在两张**不同尺寸**的图上都正常（336×499 与 347×500 都能解码并完成推理），说明解码与预处理对尺寸不敏感；两次都能打印出 cat/dog 类别与置信度。判错/低置信都属于模型精度问题，提升办法见 [`extensions/01_train_catdog_model`](../extensions/01_train_catdog_model/)（改用预训练权重或增加训练轮数）。

演示的完整日志（含重编过程）：[`extensions/03_catdog_static_infer/flash_output_dogjpg_demo.txt`](../extensions/03_catdog_static_infer/flash_output_dogjpg_demo.txt)。

## 4. 工程 B：`extensions/03_live_catdog_assignment`（LCD 实时猫狗分类）

### 4.1 为什么这个工程必须用短构建目录 `-B`

两个工程的路径只差 3 个字符，就决定了成不成功（同一台机器、同一套工具链实测）：

| 工程 | 工程目录总长度 | 构建根目录（多一个 `\build`） | 同一个 `.obj.d` 依赖文件全路径 | 结果 |
|---|---|---|---|---|
| `03_catdog_static_infer` | 113 字符 | 119 字符 | 258 字符 | ✅ 通过（可用上限 259） |
| `03_live_catdog_assignment` | 116 字符 | 122 字符 | **261 字符** | ❌ 失败 |

不加 `-B` 时，构建会在编译引导加载程序这一步中断，日志末尾是这种“看着像缺文件、其实是路径太长”的报错：

```text
...\components\bootloader_support\bootloader_flash\src\bootloader_flash_config_esp32s3.c:308:1:
fatal error: opening dependency file
esp-idf\bootloader_support\CMakeFiles\__idf_bootloader_support.dir\bootloader_flash\src\bootloader_flash_config_esp32s3.c.obj.d:
No such file or directory
```

原因：Windows 未开启长路径支持时单条路径上限 260 字符（含结尾 NUL，可用 259），而 `build\bootloader` 子构建里编译器写依赖文件用的绝对路径已经到 261 字符。**把这一个工程的构建目录挪到短路径下即可**，`sdkconfig` 仍留在工程根目录，配置（LFN、八线 PSRAM、LCD 缓冲）不受影响。完整推导、以及“以后如何不用 `-B`”的目录改名方案见本报告第 7 节和 [`extensions/_tools/README.md`](../extensions/_tools/README.md) 第 3 节。

### 4.2 编译

```powershell
cd extensions\03_live_catdog_assignment

idf.py -B E:\esi_build\projB set-target esp32s3   # 仅首次/换目标芯片时需要
idf.py -B E:\esi_build\projB build
```

**本工程的每一次构建和烧录都要带 `-B`。** 实测结尾：

```text
[116/116] ...check_sizes.py --offset 0x8000 bootloader ... E:/esi_build/projB/bootloader/bootloader.bin
Bootloader binary size 0x51c0 bytes. 0x2e40 bytes (36%) free.
camera_catdog_live.bin binary size 0x4b4360 bytes. Smallest app partition is 0x6d6000 bytes. 0x221ca0 bytes (31%) free.
Project build complete.
```

- 固件 `0x4b4360` = 4 932 960 B ≈ **4.70 MiB**（模型嵌在固件里），app 分区 ≈ 6.84 MiB，剩余 **31%**。
- `Project build complete` 后面那行 `To flash, run:` 打印的是 `..\..\..\..\..\..\..\..\..\esi_build\projB\...` 这种相对路径，**直接照抄容易出错，请用下面的 `idf.py flash`**。
- 两个注意点：① 不要手工移动已生成的构建目录——`build.ninja` / `CMakeCache.txt` 里存的是绝对路径，移动后 ninja 会去旧路径找文件；要换目录就删掉新目录重新构建。② 短路径目录名保持简短（如 `E:\esi_build\projB`），路径里不要有空格或中文。

### 4.3 烧录 + 串口监视

```powershell
idf.py -B E:\esi_build\projB -p COM6 flash monitor
```

预期：esptool 写 3 个区域并各打印一次 `Hash of data verified.`；进入监视器后 LCD 亮起显示实时画面，串口按下面的顺序输出。退出按 **`Ctrl + ]`**。

### 4.4 实测输出（原始日志）

烧录部分：

```text
esptool.py --chip esp32s3 -p COM6 -b 460800 ... write_flash ... 0x0 bootloader/bootloader.bin 0x10000 camera_catdog_live.bin 0x8000 partition_table/partition-table.bin
Wrote 20928 bytes (13320 compressed) at 0x00000000 in 0.2 seconds (effective 694.1 kbit/s)...
Hash of data verified.
Wrote 4932448 bytes (2911574 compressed) at 0x00010000 in 26.3 seconds (effective 1501.6 kbit/s)...
Hash of data verified.
Wrote 3072 bytes (119 compressed) at 0x00008000 in 0.0 seconds (effective 858.7 kbit/s)...
Hash of data verified.
Leaving...
```

上电启动 + 初始化（按时间顺序摘录；为可读性省略了若干重复的 gpio 探测行）：

```text
rst:0x15 (USB_UART_CHIP_RESET),boot:0x2a (SPI_FAST_FLASH_BOOT)
I (992) octal_psram: vendor id    : 0x0d (AP)
I (1035) esp_psram: Found 8MB PSRAM device
I (1039) esp_psram: Speed: 80MHz
I (1478) esp_psram: SPI SRAM memory test OK
I (1493) app_init: Project name:     camera_catdog_live
I (1511) app_init: ESP-IDF:          v5.4.4
I (1554) esp_psram: Adding pool of 8192K of PSRAM memory to heap allocator
I (1621) camera_catdog_live: Loading cat/dog classifier from flash rodata
I (2131) camera_catdog_live: Classifier loaded successfully
I (2141) cam_hal: cam init ok
I (2161) camera: Detected OV2640 camera
I (2231) cam_hal: PSRAM DMA mode disabled          ← 第一遍：探测像素格式/分辨率
I (2251) cam_hal: Allocating 115200 Byte frame buffer in PSRAM     （连续 3 行）
I (2271) cam_hal: cam config ok
I (2341) cam_hal: cam init ok                      ← 第二遍：按最终配置重建
I (2431) cam_hal: PSRAM DMA mode enabled
I (2451) cam_hal: Allocating 126736 Byte frame buffer in PSRAM     （连续 3 行）
I (2461) cam_hal: Frame[0]: Offset: 16, Addr: 0x3C888B00
I (2471) cam_hal: Frame[1]: Offset: 16, Addr: 0x3C8A7A30
I (2481) cam_hal: Frame[2]: Offset: 16, Addr: 0x3C8C6960
I (2561) LVGL: Starting LVGL task
I (2681) camera_catdog_live: System ready — camera preview + periodic inference running
I (2681) main_task: Returned from app_main()
```

周期推理结果（连续 10 次，节选首 2 次与末 2 次）：

```text
I (6451) camera_catdog_live: [1] cat: 0.6926 (推理耗时 3269503 us / 3269.503 ms)
I (10241) camera_catdog_live: [2] cat: 0.7058 (推理耗时 3264031 us / 3264.031 ms)
...
I (36631) camera_catdog_live: [9] cat: 0.7663 (推理耗时 3264073 us / 3264.073 ms)
I (40391) camera_catdog_live: [10] cat: 0.7311 (推理耗时 3263743 us / 3263.743 ms)
```

### 4.5 怎么读，以及和工程 A 的差异

| 日志行 | 含义 |
|---|---|
| `Loading cat/dog classifier from flash rodata` → `Classifier loaded successfully` | 模型在构建时被 `EMBED_FILES` 嵌进固件只读区，**所以本工程不需要 SD 卡**（也就不会出现 A 里那条 LFN 警告） |
| `Detected OV2640 camera` | 摄像头自检通过；`cam init` 出现两次是正常流程（先探测像素格式，再启用 PSRAM DMA 重建缓冲），第二次才有 3 块 126 736 B 的帧缓冲 |
| `LVGL: Starting LVGL task` / `System ready — ...` | LCD 显示任务与实时推理管线启动完成 |
| `[1] cat: 0.6926` | `[n]` 是**推理序号**（不是摄像头帧号）；`cat` 是 Top-1 类别；`0.6926` 是 softmax 置信度 |
| `推理耗时 3269503 us / 3269.503 ms` | 同一耗时两种单位；本次 10 次落在 **3.2637～3.2695 s**（波动 < 0.2%，非常稳定） |
| `main_task: Returned from app_main()` | 正常：`app_main()` 只负责创建任务，之后三个任务自己循环跑，**不会结束** |

- **推理期间画面卡顿是设计内现象**：推理任务优先级 3 且不绑核，跑起来的约 3.2 s 里同核的预览任务（优先级 2）只能等——这正是阶段性作业要观察的“卡顿”来源，也是后续优化案例的起点。
- **10 次结果全是 `cat`、置信度 0.69～0.77**：与第 3.4 节同一个模型（`val_accuracy` ≈ 0.61，尚未学出区分能力），属模型能力问题。把镜头分别对准真实的猫和狗复测、把结果如实记录即可；评测看的是“实时推理链路跑通 + 数据可复现”，不是准确率。
- 采集窗口（约 40 s、10 次推理）内未出现 task watchdog 或复位日志；更长时间的稳定性按本工程 README 的排查表第 6 条另行审计。

## 5. 排错指南（症状 → 原因 → 解决）

按“先看报错在哪里、再对号入座”使用。前 3 条是这台 Windows 机器上真正踩过的坑。

| # | 症状 | 原因 | 解决 |
|---|---|---|---|
| 1 | 工程 B 构建中途失败：`fatal error: opening dependency file ... .obj.d: No such file or directory` | 仓库路径 + 本工程目录名太长，越过 Windows 260 字符上限，`build\bootloader` 下写不出依赖文件（**不是文件缺失**） | 加 `-B`：`idf.py -B E:\esi_build\projB build`；想彻底摆脱见第 7 节 |
| 2 | 构建早期报托管组件错误，`managed_components\espressif__esp_video` 目录不完整 / 缺 `.component_hash` | `esp_video` 内部长路径导致组件管理器复制失败 | 跑一次 `powershell -ExecutionPolicy Bypass -File extensions\_tools\fix_esp_video_long_path.ps1`（幂等；需要重装时加 `-Force`） |
| 3 | 改过构建目录位置后，ninja 报找不到文件 / “构建目录搬过去就不能用” | `build.ninja`、`CMakeCache.txt` 里存的是绝对路径 | 删掉新目录重新 `idf.py -B <新目录> build`；**不要手工剪切已生成的 `build` 目录** |
| 4 | `idf.py: command not found` | 新终端没加载 IDF 环境 | `& 'D:\Download\esp\Espressif\frameworks\esp-idf-v5.4.4\export.ps1'` |
| 5 | 工程 B 构建报 `Missing model file` | 模型没放到 `main/models/s3/` | 从 `extensions/02_quantize_catdog_model/outputs/` 复制 `.espdl` 到该目录再构建 |
| 6 | 工程 A：`SD card mount failed` | 卡没插到位、不是 FAT32、卡损坏 | 重新插拔；电脑上格式化为 FAT32（建议 ≤32 GB）；或先用 `sdcard_seed` 重刷一次 |
| 7 | 工程 A：`cat/dog model load failed` + `model has no input/output tensors` | 模型路径/文件名不对，或未开启 FAT 长文件名 | 确认卡上是 `models/s3/catdog_mobilenet_v2.espdl`；`Select-String sdkconfig -Pattern FATFS_LFN` 必须是 `CONFIG_FATFS_LFN_HEAP=y`，否则删 `sdkconfig` 后重新 `set-target` + 构建 |
| 8 | 工程 A：`cannot open image: /sdcard/images/sample.jpg` | 图片没拷进去、名字不对（`.jpeg`、大小写不符）、`images/` 没建 | 严格按 `images/sample.jpg` 放置，全小写、无空格、无中文 |
| 9 | 工程 A：`image read failed` / `JPEG decode failed` | 空文件、PSRAM 不足，或不是合法 baseline JPEG（改名的 PNG、渐进式、CMYK） | 换普通 RGB JPEG；确认 `CONFIG_SPIRAM=y`；不要用超大分辨率图 |
| 10 | 运行日志里总有一条 `W ESP32-S3-EYE: Warning: Long filenames on SD card are disabled in menuconfig!` | BSP 检查旧版配置符号造成的**固定输出**，开启 LFN 后照样打印 | 忽略它；以电脑上 `sdkconfig` 里的 `CONFIG_FATFS_LFN_HEAP=y` 为准 |
| 11 | 串口里中文显示成 `?????`（`推理耗时` 变问号） | 终端编码不是 UTF-8 | 用 VS Code 的 UTF-8 终端或先 `chcp 65001`；纯显示问题，不影响功能 |
| 12 | `idf.py flash` 打不开串口 / `Permission denied` | 端口写错，或监视器/其他程序仍占用 COM6 | 先 `Ctrl + ]` 退出旧监视器；确认端口号（本机为 COM6）；Linux 需 `sudo usermod -aG dialout $USER` |
| 13 | 工程 B：启动即重启 / `Guru Meditation Error` | `sdkconfig` 与板子不匹配或分区表被改 | 删 `sdkconfig` → `idf.py -B E:\esi_build\projB set-target esp32s3` → 重新构建烧录；确认 `partitions.csv` 未被修改 |
| 14 | 工程 B：运行几分钟后 `task watchdog` 告警或复位 | 某核长期无空闲 | 保留完整日志作为审计证据，按 Kconfig 帮助检查 `CONFIG_ESP_TASK_WDT_TIMEOUT_S` |
| 15 | 工程 B：LCD 画面正常但一直不打印分类结果 | peek 拿不到帧或结果为空 | 看有无 `Unable to peek from an empty frame buffer.`；持续无帧则检查摄像头排线和 `CONFIG_SPIRAM_MODE_OCT=y` |

## 6. 实测数据汇总

| 指标 | 工程 A 静态推理 | 工程 B 实时分类 | SD 卡播种工具 |
|---|---|---|---|
| 构建命令 | `idf.py build` | `idf.py -B E:\esi_build\projB build` | `idf.py build` |
| 是否需要 `-B` | ❌ 不需要 | ✅ **每次都要** | ❌ 不需要（不依赖 BSP/esp_video） |
| 构建结果 | ✅ `Project build complete`（`[116/116]`） | ✅ `Project build complete`（`[116/116]`） | ✅ `Project build complete` |
| bootloader | 0x51c0 = 20 928 B（36% 空闲） | 同左 | 同左 |
| 应用固件 | 0x21ab50 = 2 207 568 B ≈ 2.11 MiB | 0x4b4360 = 4 932 960 B ≈ 4.70 MiB | 0x299ac0 = 2 725 568 B ≈ 2.60 MiB |
| app 分区剩余 | 73% | 31% | 67% |
| 模型来源 | SD 卡 `/sdcard/models/s3/catdog_mobilenet_v2.espdl` | **固件内嵌**（flash rodata，`EMBED_FILES`） | 固件内嵌（用于写卡） |
| 是否需要 SD 卡 | ✅ | ❌ | ✅（写入对象） |
| 烧录命令 | `idf.py -p COM6 flash monitor` | `idf.py -B E:\esi_build\projB -p COM6 flash monitor` | `idf.py -p COM6 build flash monitor` |
| 板上运行 | ✅ 两次独立运行结果一致（13:29 首次 / 14:47 复跑）：`top1=dog score=0.626124 infer=3240357 us`；JPEG 解码 336×499 用 54 132 / 54 149 us | ✅ `[1] cat: 0.6926` … `[10] cat: 0.7311`；单次推理 3.2637～3.2695 s | ✅ 3 个文件 `written+verified`（SHA-256 回读，与仓库源文件哈希一致） |
| 运行次数 | 执行一次后结束（不循环） | 每 ≈3.2 s 一次，持续循环 | 写入完一次后结束 |
| 附：换图演示（§3.5） | ✅ dog 图 `top1=dog score=0.527316`（临时改 1 行 `kImagePath`、跑完已改回原源码并重烧） | — | — |

## 7. 附：以后想用普通终端（不用 `-B`）重编工程 B，该怎么改目录名

### 7.1 先看规则（由两个实测点反推）

- Windows 未启用长路径支持时，单条路径上限 260 字符（含结尾 NUL，**可用 259**）；本机 `LongPathsEnabled = 0`。
- 构建树里最长的**相对路径**（相对构建根目录）是引导加载程序的依赖文件 `.obj.d`，实测 **139 字符**。
- 两个实测点夹逼出规则：

| 工程 | 工程目录全路径 | 构建根目录（`\build`） | 最长文件 | 结果 |
|---|---|---|---|---|
| 工程 A `03_catdog_static_infer` | 113 | 119 | 258 | ✅ 通过 |
| 工程 B `03_live_catdog_assignment` | 116 | 122 | 261 | ❌ 失败 |

⇒ **构建根目录 ≤ 120 字符**（= 259 − 139），也就是 **工程目录全路径 ≤ 114 字符**；建议再留 10 字符余量，即 **≤ 104 字符**。

> 补充说明（解释性细节，不影响结论）：构建树里 mbedtls 那批对象文件的路径其实更长，但 CMake 在对象路径可能超长时会改用哈希目录名，所以它们不会成为瓶颈。实测：短构建目录（`E:\esi_build\projB`，构建根 18 字符）下最长是 182 字符相对路径；工程 A（构建根 119 字符）下同一批文件被哈希成 129～131 字符相对路径。两种情况都不超过 259。

### 7.2 结论：**只改 `03_live_catdog_assignment` 这一层的名字，收益很小**

当前 `extensions` 这一层就已经 90 字符，其中 `esi-mvp-code-main\esi-mvp-code-main\esi-mvp-code-main` 三层重复占了 57 字符。如果只改工程目录名：

- 硬上限：`03_live_catdog_assignment`（25 字符）**最多只能缩到 23 字符**（此时构建根正好 120，余量 0）；
- 想留 10 字符余量：必须缩到 **≤ 13 字符**（例如 `03_live`，按规则推算构建根 104、最长文件 243 ✔）；
- 代价：这个目录名在仓库多处文档与清单里被引用（各工程 README、`_tools/README.md`、`docs/` 下的记录等），改名会断链，**不推荐**。

### 7.3 推荐做法：缩短它**上面**的路径

| 方案 | 怎么做 | 改后工程目录全路径 | 构建根目录 | 余量（上限 259） |
|---|---|---|---|---|
| **① 缩短最外层仓库名（推荐，改动最小）** | 把最外层 `esi-mvp-code-main`（17 字符）改名成 `esi`（3 字符），省 14 字符 → `…\ganzhi\esi\esi-mvp-code-main\esi-mvp-code-main\extensions\03_live_catdog_assignment` | **102** | 108 | ≈ 9～12，够用 |
| ② 消除重复嵌套（最彻底） | 只保留一层仓库目录，如 `E:\esi-mvp-code-main\extensions\...`（相当于省 59 字符） | **57** | 63 | ≥ 14，宽松 |
| ③ 只改工程目录名（不推荐，会断文档链接） | `03_live_catdog_assignment` → `03_live` | **98** | 104 | ≈ 9 |
| ④ 一个名字都不改 | 继续用 `-B`（本报告采用），或 `subst X: <仓库>\extensions` 后在 `X:\03_live_catdog_assignment` 里正常 `idf.py build` | 28 | 34 | ≈ 43，最宽松 |

说明：

- 方案 ① 只需要在资源管理器里把最外层那个文件夹改个名，仓库内部结构、所有工程目录名和文档链接都保持不变，是最省事的做法。
- 方案 ④ 的 `subst` 用法（盘符映射，不改任何目录名）：

  ```powershell
  subst X: E:\study\lsf\daima\ganzhi\esi-mvp-code-main\esi-mvp-code-main\esi-mvp-code-main\extensions
  cd X:\03_live_catdog_assignment
  idf.py build            # 这里就不需要 -B 了
  subst X: /D             # 用完后删除映射（重启也会失效）
  ```

- 参考：工程 A 目前的构建根是 119 字符，**只剩 1 个字符余量**（踩线通过）。这正是建议留 10 字符左右余量的原因——路径里再多一个字符就轮到你踩坑了。
- 以上长度都是按 7.1 的规则推算的（由工程 A 通过、工程 B 失败两个实测点夹逼），没有实际改过你的目录名做验证。

### 7.4 改完之后必须做的事

1. **删掉所有工程已有的 `build/` 目录**，再重新 `set-target` / `build`：`build.ninja`、`CMakeCache.txt` 里存的是绝对路径，路径一变旧构建目录就不可用（改了祖先目录，仓库里**每个**工程都要重建一次）。
2. `sdkconfig` 与 `sdkconfig.defaults` 不受影响，无需重配；工程 B 的 LFN / 八线 PSRAM / LCD 缓冲配置照旧。
3. `managed_components\espressif__esp_video` 是指向 `C:\Users\36064\ev_video` 的 junction（绝对目标），改名后依然有效；但**不要用资源管理器删除或移动这个 junction 目录**（可能连带删掉目标里的真实文件），需要重装就用脚本加 `-Force`。
4. 不建议依赖“开启 Windows 长路径支持”来绕过：本机 `LongPathsEnabled = 0`，而且即使改成 1，也需要工具链 / CMake / ninja / Python 都声明支持长路径才真正生效（此条未实测）。本报告一律按 260 字符上限处理。

## 8. 一键复现清单（照这个顺序执行）

```powershell
# 0) 新终端先加载 IDF 环境
& 'D:\Download\esp\Espressif\frameworks\esp-idf-v5.4.4\export.ps1'

# 1) 一次性：修复 esp_video 长路径安装问题（幂等）
powershell -ExecutionPolicy Bypass -File extensions\_tools\fix_esp_video_long_path.ps1

# 2) 给 SD 卡放模型 + 测试图（不依赖读卡器；已完成过可跳过）
cd extensions\_tools\sdcard_seed
idf.py -p COM6 build flash monitor     # 看到 3 行 written+verified 后按 Ctrl + ]
cd ..\..

# 3) 工程 A：静态猫狗推理（不需要 -B）
cd extensions\03_catdog_static_infer
idf.py set-target esp32s3              # 仅首次
idf.py build
idf.py -p COM6 flash monitor           # 看 top1=... score=... infer=... us，然后 Ctrl + ]

# 4) 工程 B：LCD 实时猫狗分类（每次都要带 -B）
cd ..\03_live_catdog_assignment
idf.py -B E:\esi_build\projB set-target esp32s3   # 仅首次
idf.py -B E:\esi_build\projB build
idf.py -B E:\esi_build\projB -p COM6 flash monitor   # 看 [1] cat/dog: 0.xxxx（约每 3.2 s 一次）
```

留证据的小提示：监视器输出可以手工复制，也可以重定向留档（本报告 §9 的那几个 `flash_output.txt` 就是这么留下的）；但用管道重定向时 `Ctrl + ]` 可能失效，需用 `Ctrl + C` 停止：

```powershell
cd extensions\03_catdog_static_infer
idf.py -p COM6 flash monitor | Tee-Object -FilePath flash_output.txt
```

## 9. 附：证据与相关文档

- 完整原始日志已**随仓库留档**（用 `.txt` 后缀，因为仓库 `.gitignore` 忽略 `*.log`），报告中的日志摘录都能在这些文件里逐字找到：

| 日志文件 | 内容 |
|---|---|
| [`extensions/03_catdog_static_infer/flash_output.txt`](../extensions/03_catdog_static_infer/flash_output.txt) | 工程 A 14:47 复跑全文（`idf.py flash` + `idf.py monitor`，含 §3.3 两行结果） |
| [`extensions/03_catdog_static_infer/flash_output_dogjpg_demo.txt`](../extensions/03_catdog_static_infer/flash_output_dogjpg_demo.txt) | §3.5 换 dog 图演示全文（含增量重编过程） |
| [`extensions/03_live_catdog_assignment/flash_output.txt`](../extensions/03_live_catdog_assignment/flash_output.txt) | 工程 B 实机运行全文（含连续 10 次推理序列） |
| [`extensions/03_live_catdog_assignment/maxpath_build_error_excerpt.txt`](../extensions/03_live_catdog_assignment/maxpath_build_error_excerpt.txt) | 工程 B 不加 `-B` 时的 MAX_PATH 报错原文摘录（§4.1、§7 的证据） |
| [`extensions/_tools/sdcard_seed/flash_output.txt`](../extensions/_tools/sdcard_seed/flash_output.txt) | 写卡工具的挂载、写入、SHA-256 回读与汇总全文 |

- 本次会话的构建日志（`projA_build2.log`、`projB_build.log`、`projB_build3.log`，各约 300 KB）与工程 A 13:29 首次实测日志仍保存在临时目录 `%TEMP%\catdog_run\`，可能被系统清理；上表 5 个文件已复制进仓库，长期有效。
- **编码说明（只影响工程 B 的日志，务必知道）**：工程 B 源码 `main/app_main.cpp` 里的"推理耗时"是 UTF-8，但监视器是 Python 程序，在 Windows 上把输出写到文件时会按系统 ANSI 代码页（本机 CP936）重新编码，所以 `extensions/03_live_catdog_assignment/flash_output.txt` 里那三个汉字是 **GBK 字节**。用 VS Code 打开时这里会显示成乱码，把该文件编码切成 `GB18030`（或 `GBK`）即可正常显示；其余内容全为 ASCII，不影响阅读与核对。
- 想让日志整体保持 UTF-8，可在运行监视器前设置环境变量 `PYTHONIOENCODING=utf-8`（本次未实测，仅作为后续建议）；或者直接用 `idf.py` 之外的方式抓串口输出。

| 文档 | 内容 |
|---|---|
| [`extensions/03_catdog_static_infer/README.md`](../extensions/03_catdog_static_infer/README.md) | 工程 A 的 Quick Start、失败路径日志与排查表 |
| [`extensions/03_live_catdog_assignment/README.md`](../extensions/03_live_catdog_assignment/README.md) | 工程 B 的 Quick Start、字段对照表与排查表（含 Windows `-B` 说明） |
| [`extensions/_tools/README.md`](../extensions/_tools/README.md) | SD 卡播种工具、`esp_video` 长路径修复脚本、短构建目录的完整原理与实测数字 |
| [`extensions/01_train_catdog_model/README.md`](../extensions/01_train_catdog_model/README.md) | 模型训练来源；明确 `weights=None` + 3 epoch 时 `val_acc` 50%～70% 属正常 |
| [`extensions/02_quantize_catdog_model/README.md`](../extensions/02_quantize_catdog_model/README.md) | 模型量化来源（`outputs/catdog_mobilenet_v2.espdl`） |
| [`docs/build-verification.md`](build-verification.md) | 仓库级构建/运行验证记录（本轮结果已回填） |