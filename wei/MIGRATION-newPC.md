# 换电脑操作指南（小白版）

> 目标：在一台**全新的 Windows 电脑**上，用 `wei\` 这一个文件夹把 ESP32-S3-EYE 猫狗分类的三条路线（静态图推理 / 实时摄像头 / SD 卡播种）**原样跑起来**。
> 本指南中所有“预期输出”都取自随包的原始日志（`evidence/` 与各工程目录里的 `flash_output*.txt`）。

---

## 0. 一句话流程

```
新电脑装 ESP-IDF v5.4.4 → 把 wei\ 文件夹放到 C:\esp\lesson\wei → 插板子查 COM 号
→ 编译 A/B → idf.py flash monitor → 对日志（不需要 -B，也不用重写 SD 卡）
```

---

## 1. 新电脑先装什么

### 1.1 ESP-IDF v5.4.4（唯一必需）

1. 打开官方下载页：<https://dl.espressif.com/dl/esp-idf/>（文档：<https://docs.espressif.com/projects/esp-idf/zh_CN/v5.4.4/esp32s3/get-started/windows-setup.html>）
2. 下载 **ESP-IDF Windows Installer**（`esp-idf-tools-setup-online-…exe`），运行时**选择版本 `v5.4.4`**（旧电脑实测就是 v5.4.4）
3. **安装目录保持默认 `C:\Espressif`**（短路径，不要放桌面 / 中文目录 / 深层目录）
4. 目标芯片勾上 `esp32s3`（全勾也不影响）
5. 装完从开始菜单打开 **“ESP-IDF 5.4 PowerShell”**（自动加载环境），验证：

```powershell
idf.py --version                    # 必须显示 ESP-IDF v5.4.4
python --version                    # IDF 自带 Python 3.12
xtensa-esp32s3-elf-gcc --version    # 交叉编译器可用
```

> 用普通 PowerShell 时先手动加载环境：
> `& 'C:\Espressif\frameworks\esp-idf-v5.4.4\export.ps1'`

### 1.2 USB 驱动（大概率不用装）

实测这块板走 **ESP32-S3 原生 USB-Serial/JTAG**（日志里 `USB mode: USB-Serial/JTAG`），Win10/11 **免驱**，设备管理器里出现 “USB 串行设备 (COMx)”。
只有当设备管理器出现**带黄色感叹号的未知设备**时，才需要装桥接驱动：`CP210x`（VID_10C4）或 `CH34x`（VID_1A86）。

### 1.3 Python 线（**可选**，仅当你还想重新训练/量化）

```powershell
conda create -n esp32s3 python=3.11 -y
conda activate esp32s3
pip install -r C:\esp\lesson\wei\extensions\01_train_catdog_model\requirements.txt
pip install esp-ppq                 # 旧电脑实测可用版本 1.2.10
python -c "import torch, esp_ppq; print('ok', torch.__version__)"
```

⚠️ **精简包不含真实数据集**（2000 训练图 / 400 验证图已剔除，只留播种工具必需的两张）。想跑通训练-量化链路：
- 执行 `python prepare_data.py`（只需 pillow+numpy，无需下载 Kaggle）→ 生成 240 张**合成**图片；
- 或按 `01_train_catdog_model/README.md` 恢复 Kaggle Cats & Dogs subset 真实数据；
- **新得到的 `.espdl` 与随包的这份不同**（哈希不会等于 `5b33fb72…`），**不要覆盖** `02_quantize_catdog_model\outputs\catdog_mobilenet_v2.espdl`，否则板端结果就对不上报告了。

> 用 IDF 编译/烧录时**不要**激活 conda 环境（避免 Python 冲突）。

---

## 2. 项目文件夹放哪（重点：路径要短）

把 **`wei\` 这一个文件夹**放到短路径下，推荐：

```
C:\esp\lesson\wei\
```

关键目录（同级目录之间是**相对引用**，一个都不能改名、不能拆开）：

```
C:\esp\lesson\wei\
├─ extensions\01_train_catdog_model\       训练（含两张样例图）
├─ extensions\02_quantize_catdog_model\    量化（含 .espdl）
├─ extensions\03_catdog_static_infer\      工程 A：SD 卡静态图推理
├─ extensions\03_live_catdog_assignment\   工程 B：LCD 实时猫狗分类
├─ extensions\_tools\sdcard_seed\          SD 卡播种工具
├─ docs\                                  报告与验证文档
└─ evidence\                              原始日志 / 构建日志
```

**为什么必须短**：Windows 未开启长路径时单条路径上限 260 字符，而工程 B 构建树里最深的 `.obj.d` 路径又长。旧电脑实测：工程目录 **119 字符 → 最深 258 ✅**；**122 字符 → 261 ❌**（当时只能加 `-B` 绕开）。

放好后量一下（建议 ≤115）：

```powershell
(Resolve-Path C:\esp\lesson\wei\extensions\03_live_catdog_assignment).Path.Length
```

- `C:\esp\lesson\wei\extensions\03_live_catdog_assignment` = **52 字符** → 完全没问题，**不需要 `-B`**
- 若只能放在 `C:\Users\<用户名>\Documents\...`，先量长度；>115 就用第 4.2 节的 `-B` 写法

**千万不要**放在“下载”里的深层解压目录，例如：
`C:\Users\x\Downloads\lesson-wei-2026\lesson-wei\wei\extensions\...`

---

## 3. 代码怎么从旧电脑搬到新电脑（二选一）

### 方式 A：U 盘（最快，推荐）

1. 旧电脑：把整个 **`wei\`** 文件夹拷到 U 盘（约 24 MB）
2. 新电脑：拷到 `C:\esp\lesson\wei\`
3. 检查相对目录完整：`extensions\`、`docs\` 必须是 `wei\` 的**直接子目录**

> 想省下新电脑首次联网下载托管组件的 20–40 分钟，可顺手再拷两个目录（各约 275 MB，**不属于 wei 包**）：
> `...\extensions\03_catdog_static_infer\managed_components\`、`...\extensions\03_live_catdog_assignment\managed_components\`
> 放到新电脑同名位置。注意旧机上 `managed_components\espressif__esp_video` 是指向 `C:\Users\36064\ev_video` 的**目录联接（Junction）**；
> 若拷过去结构不完整，就在新机跑一次 `extensions\_tools\fix_esp_video_long_path.ps1`（幂等）。不拷也没关系，联网 build 会自动重新拉取。

### 方式 B：GitHub

```powershell
git clone -b wei https://github.com/lsf06/lesson.git C:\esp\lesson
# 结果：C:\esp\lesson\wei\...   （路径长度同样是 52，安全）
```

### 搬完先做自检（1 分钟）

```powershell
cd C:\esp\lesson\wei
(Get-ChildItem -Recurse -File).Count                                                # 114（含 CHECKSUMS.txt 与 .gitattributes）
powershell -ExecutionPolicy Bypass -File .\verify-checksums.ps1                     # 期望 RESULT: ALL FILES VERIFIED
Test-Path extensions\01_train_catdog_model\cats-dogs-data\valid\cat\cat.1001.jpg    # 必须 True（播种工具硬依赖）
Test-Path extensions\02_quantize_catdog_model\outputs\catdog_mobilenet_v2.espdl     # True
Get-FileHash extensions\02_quantize_catdog_model\outputs\catdog_mobilenet_v2.espdl -Algorithm SHA256
# 期望 5B33FB728E7F8B2DA964C2C137DCDB2D73D615AE87CCEC13409BF656935BE78E
```

---

## 4. 新电脑上的完整编译 / 烧录命令

> 全部在 **“ESP-IDF 5.4 PowerShell”** 里执行；下面的 `COM6` 按第 5 节改成你的实际口号。

### 4.1 工程 A：`03_catdog_static_infer`（SD 卡静态图推理，跑一次就结束）

```powershell
cd C:\esp\lesson\wei\extensions\03_catdog_static_infer
idf.py build                     # 随包已带 sdkconfig（已锁定 esp32s3），可直接 build
idf.py -p COM6 flash monitor
```

预期（与旧电脑一致）：

```text
catdog_static_infer.bin binary size 0x21ab50 bytes. Smallest app partition is 0x7d0000 bytes. 0x5b54b0 bytes (73%) free.
Hash of data verified.
I (1193) catdog_static_infer: SD card mounted at /sdcard
I (3953) catdog_static_infer: decoded /sdcard/images/sample.jpg: 336 x 499 in 54132 us
I (7193) catdog_static_infer: top1=dog score=0.626124 infer=3240357 us
```

- 打印这几行后程序就结束了（**不是卡死**），想再跑一次按板上的 **RST** 键
- 退出监视器：**`Ctrl + ]`**
- **必须先插好 SD 卡**（模型与图片都在卡上）
- 解码耗时会有十几微秒抖动、推理耗时会有毫秒级浮动，属正常
- 关于 `top1=dog`：被推理的 `sample.jpg` 在仓库里是 `valid/cat/cat.1001.jpg`（**一张猫图**），
  被判成 dog 是**模型误判**（只训 3 epoch，`val_accuracy` ≈ 0.61），不是程序问题；
  详细说明见 `docs/catdog-run-report.md`

### 4.2 工程 B：`03_live_catdog_assignment`（LCD 实时猫狗分类，循环不停）

```powershell
cd C:\esp\lesson\wei\extensions\03_live_catdog_assignment
idf.py build                     # 路径短（52 字符）→ 不需要 -B
idf.py -p COM6 flash monitor
```

> 只有工程目录长度 >115 时才改成：
> `idf.py -B C:\esi_build\projB build` 与 `idf.py -B C:\esi_build\projB -p COM6 flash monitor`

预期：

```text
camera_catdog_live.bin binary size 0x4b4360 bytes. Smallest app partition is 0x6d6000 bytes. 0x221ca0 bytes (31%) free.
I (2131) camera_catdog_live: Classifier loaded successfully
I (2561) LVGL: Starting LVGL task
I (2681) camera_catdog_live: System ready — camera preview + periodic inference running
I (6451) camera_catdog_live: [1] cat: 0.6926 (推理耗时 3269503 us / 3269.503 ms)
I (40391) camera_catdog_live: [10] cat: 0.7311 (推理耗时 3263743 us / 3263.743 ms)
```

- **不需要 SD 卡**（模型烧写在 flash 里）
- 持续循环打印，按 RST 或 `Ctrl + ]` 结束

### 4.3 可选：SD 卡播种工具 `_tools\sdcard_seed`

```powershell
cd C:\esp\lesson\wei\extensions\_tools\sdcard_seed
idf.py build                     # 只用 IDF 自带组件，无需联网拉托管组件
idf.py -p COM6 flash monitor     # 预期三条 written+verified，然后 Ctrl + ]
```

预期：

```text
sdcard_seed.bin binary size 0x299ac0 bytes. Smallest app partition is 0x7d0000 bytes. 0x536540 bytes (67%) free.
I (1282) sdcard_seed: SD card mounted at /sdcard
I (9452) sdcard_seed: written+verified: /sdcard/models/s3/catdog_mobilenet_v2.espdl (2372240 bytes)
I (9552) sdcard_seed: written+verified: /sdcard/images/sample.jpg (23099 bytes)
I (9652) sdcard_seed: written+verified: /sdcard/images/dog.jpg (24211 bytes)
```

---

## 5. COM 口号变了怎么办

1. **查口号**（插上板子后任选其一）：

```powershell
[System.IO.Ports.SerialPort]::GetPortNames()                                   # 最直观
Get-PnpDevice -Class Ports | Where-Object Status -eq 'OK' | Select-Object FriendlyName
# 或：设备管理器 → 端口(COM 和 LPT)
```

   小技巧：拔掉板子看哪个口消失，插上又出现的就是它。

2. **改命令**：把 `COM6` 换成新口号，其它参数一个都不用动，例如 `idf.py -p COM12 flash monitor`
3. **确认连的是同一块板**（旧电脑实测，三份日志一致）：

```text
Chip is ESP32-S3 (QFN56) (revision v0.2)
USB mode: USB-Serial/JTAG
MAC: 94:a9:90:1c:6f:88        ← 与旧电脑完全一致 = 就是这块板
```

4. `could not open port` 排查：关掉占用串口的程序（另一个 monitor、串口助手、Arduino IDE）；确认没有两个终端同时开监视器；拔插一次 USB 重新枚举。
5. 波特率：烧录 460800、监视器 115200，都已写在随包的 `sdkconfig` 里，不用改。

---

## 6. SD 卡里的模型和图片要不要重写？

**不用，插上就能跑。** 卡里的是烧在卡上的数据，与“用哪台电脑编译”毫无关系。

跑 4.1 看 A 的日志：

| 日志现象 | 含义 | 处理 |
|---|---|---|
| `SD card mounted at /sdcard` + `decoded … in N us` + `top1=…` | 卡完全正常 | **什么都不用做** |
| `SD card mount failed: …` | 卡没插好 / 不是 FAT32 / 卡坏了 | 重跑 4.3 播种（已开 `format_if_mount_failed`，空白卡会自动格式化） |
| `cat/dog model load failed: /sdcard/models/s3/catdog_mobilenet_v2.espdl` | 卡里缺文件（新卡或换过卡） | 重跑 4.3 播种 |

用读卡器核对卡内容时，对 `models\s3\catdog_mobilenet_v2.espdl`、`images\sample.jpg`、`images\dog.jpg`
算 SHA-256，与 `CHECKSUMS.txt` 里 `# ================= SD-CARD-3 =================` 那一段比对即可。

**需要重写卡的情况**：换新卡 / 卡被格式化过 / 想换成新训练的模型（替换 `02_quantize_catdog_model\outputs\` 后再跑 4.3）。
注意：**工程 B 完全不读 SD 卡**，卡不影响它。

---

## 7. 换电脑后最常踩的 6 个坑

| 现象 | 原因 | 处理 |
|---|---|---|
| `fatal error: opening dependency file ….obj.d: No such file or directory` | 工程路径太长（MAX_PATH 260） | 挪到 `C:\esp\…`，或加 `-B C:\esi_build\projB` |
| `espressif/esp_video … not found` / `Failed to install component` | 托管组件目录太深，安装被长路径截断 | 跑 `powershell -ExecutionPolicy Bypass -File extensions\_tools\fix_esp_video_long_path.ps1`（幂等） |
| `idf.py: command not found` | 不在 IDF 环境终端里 | 开始菜单开“ESP-IDF 5.4 PowerShell”，或 `& 'C:\Espressif\frameworks\esp-idf-v5.4.4\export.ps1'` |
| build 卡住拉组件 / 网络错误 | 首次构建需联网拉 esp-dl 等托管组件（`dependencies.lock` 已锁定版本） | 联网重试；或从旧机拷 `managed_components`（见第 3 节备注） |
| 串口打不开 / 日志乱码 | 口号变了 / 终端编码 | 见第 5 节；B 的旧日志里“推理耗时”是 GBK 字节，新跑的日志是 UTF-8，正常 |
| `top1=` 与报告不同 | **不是环境问题**：模型只训 3 epoch，`val_accuracy` ≈ 0.61 | 想更准见 `extensions\01_train_catdog_model\README.md`（换预训练权重 / 加轮数） |

---

## 8. 一句话总结

| 变化项 | 换电脑时**会变**的 | 换电脑时**不会变**的 |
|---|---|---|
| 环境 | COM 口号、工程绝对路径、IDF 安装位置、托管组件缓存 | 源码、模型产物、`sdkconfig`、`dependencies.lock`、SD 卡内容 |
| 唯一硬性约束 | **工程目录要短（≤115 字符）**，否则加 `-B` | `-B` 只是绕过长路径，不改变任何产物 |
| 复现判据 | —— | A：`top1=dog score=0.626124 infer=3240357 us`；B：`[1] cat: 0.6926`；固件大小 `0x21ab50` / `0x4b4360` / `0x299ac0` |