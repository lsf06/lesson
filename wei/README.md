# ESP32-S3-EYE 猫狗图像分类 · 精简复现包（`wei/`）

这是“猫狗图像分类”这条课程案例链路的**完整可复现快照**：源码、模型产物（`.pth` / `.onnx` / `.espdl`）、
两张样例图、全部原始日志、报告与验证文档，以及工程配置（`sdkconfig` / `dependencies.lock` / `partitions.csv`）。
总体积 ≈ **24 MB / 114 个文件**，可以直接 U 盘拷走，或 `git clone -b wei` 到另一台电脑。

> 🚚 换电脑怎么操作？看 **[MIGRATION-newPC.md](MIGRATION-newPC.md)**
> ⚡ 只想照着命令敲一遍？看 **[RUNBOOK.md](RUNBOOK.md)**
> 📋 具体数字 / 证据来源？看 **[docs/catdog-run-report.md](docs/catdog-run-report.md)** 与 **[evidence/README.md](evidence/README.md)**

---

## 1. 三条可跑路线（都已在真机验证过）

| # | 路线 | 工程目录 | 硬件前置 | 固件大小 | 实测结果 |
|---|---|---|---|---|---|
| **A** | SD 卡静态图推理 | `extensions/03_catdog_static_infer` | SD 卡（模型+图在卡上） | `0x21ab50` | `top1=dog score=0.626124 infer=3240357 us`（13:29 / 14:47 两次独立运行逐位一致） |
| **B** | LCD 实时猫狗分类 | `extensions/03_live_catdog_assignment` | 摄像头+LCD（**不用 SD 卡**） | `0x4b4360` | `[1] cat: 0.6926` … `[10] cat: 0.7311` |
| **C** | SD 卡播种工具 | `extensions/_tools/sdcard_seed` | 一张 FAT32 SD 卡 | `0x299ac0` | `written+verified` ×3（模型 2 372 240 B + 两张图） |
| 附 | 训练 / 量化（PC 线，可选） | `extensions/01_train_catdog_model`<br>`extensions/02_quantize_catdog_model` | conda + torch + esp-ppq | `catdog_mobilenet_v2.{pth,onnx,espdl}` | `val_accuracy` ≈ 0.61（仅 3 epoch） |

同一块板、同一份固件，三条路线都可以在新电脑上从零编译并复现（板卡身份：
`ESP32-S3 (QFN56) rev v0.2`、`USB-Serial/JTAG`、MAC `94:a9:90:1c:6f:88`）。

---

## 2. 目录结构

```
wei/
├─ README.md                     ← 本文件（总入口）
├─ RUNBOOK.md                    ← 从零到跑通的最小命令序列（含预期输出/故障表）
├─ MIGRATION-newPC.md            ← 换电脑操作指南（小白版）
├─ verify-checksums.ps1          ← 一条命令校验 CHECKSUMS.txt 里列出的所有文件
├─ CHECKSUMS.txt                 ← 全部文件的 SHA-256 校验清单（ASCII，兼容 sha256sum -c）
├─ .gitattributes                ← `* -text`：禁止 CRLF/LF 转换，保证 clone 后哈希不变
├─ extensions/
│  ├─ 01_train_catdog_model/     训练脚本 + README + 产物(onnx/pth/metrics/loss_curve)
│  │  └─ cats-dogs-data/valid/{cat,dog}/*.jpg   ← 仅 2 张（播种工具编译期硬依赖，见 README-PRUNED.md）
│  ├─ 02_quantize_catdog_model/  量化脚本 + README + outputs/(espdl,json,run.log…)
│  ├─ 03_catdog_static_infer/    工程 A（源码/sdkconfig/partitions/dependencies.lock + 3 份运行日志）
│  ├─ 03_live_catdog_assignment/ 工程 B（源码/components/main + 内嵌 espdl + 运行日志 + MAX_PATH 错误摘录）
│  └─ _tools/
│     ├─ fix_esp_video_long_path.ps1   ← 长路径导致 esp_video 装不上时用的修复脚本（幂等）
│     └─ sdcard_seed/                  ← 播种工具（源码/sdkconfig + 运行日志）
├─ docs/                         报告、构建验证、环境说明、README 证据索引、课程映射
├─ evidence/
│  ├─ README.md                  原始证据索引（本文件之外的所有日志都从哪来）
│  └─ build-logs/                projA_build2.log、projB_build3.log（编译过 A/B 的原始输出）
└─ extras/card-images/            sample.jpg / dog.jpg（哈希与卡上一致，供读卡器直拷）
```

---

## 3. 30 秒上手（全新电脑）

```powershell
# 0) 前置：装好 ESP-IDF v5.4.4（详见 MIGRATION-newPC.md 第 1 节），打开 “ESP-IDF 5.4 PowerShell”
# 1) 把 wei\ 放到短路径下，例如 C:\esp\lesson\wei
# 2) 工程 B（不用 SD 卡，最快看到结果）
cd C:\esp\lesson\wei\extensions\03_live_catdog_assignment
idf.py build
idf.py -p COM6 flash monitor      # 看到 "System ready" 与 "[1] cat: 0.69…" 即成功

# 3) 工程 A（需要先插好已播种的 SD 卡）
cd C:\esp\lesson\wei\extensions\03_catdog_static_infer
idf.py build
idf.py -p COM6 flash monitor      # 看到 top1=… / infer=… us 即成功

# 4)（可选但推荐）一条命令校验包完整性
cd C:\esp\lesson\wei
powershell -ExecutionPolicy Bypass -File .\verify-checksums.ps1   # 期望 RESULT: ALL FILES VERIFIED
```

> `COM6` 是本机的口号，换机器后按 `MIGRATION-newPC.md` 第 5 节改成实际口号。

---

## 4. 关键哈希与大小（自检用）

| 文件 | 大小 (B) | SHA-256 |
|---|---|---|
| `extensions/02_quantize_catdog_model/outputs/catdog_mobilenet_v2.espdl` | 2 372 240 | `5B33FB728E7F8B2DA964C2C137DCDB2D73D615AE87CCEC13409BF656935BE78E` |
| `extensions/03_live_catdog_assignment/main/models/s3/catdog_mobilenet_v2.espdl` | 2 372 224 | `A6A75A1C76A976015BFFFF6B2FC7A1A2DB825C255B29ACCDB6C2944E9A64F24F` |
| `extensions/01_train_catdog_model/cats-dogs-data/valid/cat/cat.1001.jpg` | 23 099 | `B32166FED6526078AA5BF7A986C4ECAA1B377AD3F65153F09BDE3F9176AE306B` |
| `extensions/01_train_catdog_model/cats-dogs-data/valid/dog/dog.1001.jpg` | 24 211 | `FF581E37E606C9A468B08E245A02564133F253C1C64A64C5BC8570E1EF5E0C47` |
| `extras/card-images/sample.jpg` / `dog.jpg` | 同上 | 同上（与卡上 `/sdcard/images/*.jpg` 同源同哈希） |

> ⚠️ 工程 B 内嵌的那份 `.espdl` 与 `02_quantize…/outputs/` 的那份**相差 16 字节、哈希不同**，
> 是仓库里既有的两份独立文件——**不要互相覆盖**。全部文件的哈希清单见 `CHECKSUMS.txt`。

> 本包自带 `.gitattributes`（`* -text`）：git 不会在 CRLF/LF 之间做转换，
> 因此 `git clone` 到新电脑后每个文件的 SHA-256 仍与 `CHECKSUMS.txt` 一致
> （二进制产物本来就与行尾无关，风险只在于文本文件）。

**SD 卡上的三件（用读卡器核对时）**：`models/s3/catdog_mobilenet_v2.espdl`（2 372 240 B，同上一行）、
`images/sample.jpg`（23 099 B）、`images/dog.jpg`（24 211 B）。

---

## 5. 精简包“砍掉”了什么、怎么补回

| 被砍掉的 | 体积 | 为什么 | 怎么补回 |
|---|---|---|---|
| `extensions/*/build/` | A 381 MB、B 296 MB、seed 165 MB | 构建产物，`.gitignore` 已忽略 | `idf.py build` 重新生成 |
| `extensions/*/managed_components/` | 275 MB + 276 MB | 托管组件，`.gitignore` 已忽略 | 首次 `idf.py build` 按 `dependencies.lock` 自动拉取（需联网） |
| `01_train_catdog_model/cats-dogs-data/` 的数据集 | zip 52.6 MB + 2000 训练图 / 400 验证图 | 太大，且与“换电脑跑板端”无关 | `python prepare_data.py`（合成）或 Kaggle subset（真实），见该目录 `cats-dogs-data/README-PRUNED.md` |
| `02_quantize…/outputs/*.raw.onnx` | 8.5 MB | 量化中间产物 | 重跑 `quantize_catdog.py` |
| `02_quantize…/outputs/*.info` | 13.6 MB | PPQ 量化过程报告 | 重跑 `quantize_catdog.py` |
| `__pycache__/`、`.vscode/` | 少量 | 无用 | — |
| 其它扩展案例（sin 案例 / `microcourses/` / `extensions/04…10` 等） | —— | 本包只镜像“猫狗图像分类”这一条链路 | 在旧电脑的上游工作区（`esi-mvp-code-main`）里；目标仓库 `lsf06/lesson` 的 `main` 分支本身只含 `2/`、`esp32_firmware/`、`server/` |

> `docs/readme-evidence-manifest.yml` 是上游 README 的证据索引；其中极少数条目指向上面已剔除的
> `.info` / `.raw.onnx`，其余条目在本包内均可直接核对。

> **链接自检结果**：本包内 87 条相对链接已逐条校验（本文件与其它新增文档全部通过）。
> 仅 5 条“指不到”，且**全部位于上游原有文档**、都不影响任何可运行内容：
>
> - 4 条图注：`extensions/{01,02,03_*}/README.md` 里的 `../../docs/assets/ai_generated/*.png`
>   （“AI 生成示意图”，单张 4.3–5.0 MB、共 3 个文件约 13.9 MB，为控制包体已剔除；
>   想补齐就从旧电脑 `esi-mvp-code-main\docs\assets\ai_generated\` 拷进 `wei\docs\assets\ai_generated\`）
> - 1 条目录链接：`extensions/01_train_catdog_model/README.md` 第 3 行的
>   `../../microcourses/01_train_sin_model/`（sin 案例微课目录，不在本包范围内）

---

## 6. 证据索引（结论 → 文件）

| 结论 | 证据文件 |
|---|---|
| 工程 A 真机运行成功且可复现（两次独立运行逐位一致） | `extensions/03_catdog_static_infer/flash_output.txt`、`flash_output_firstrun_1329.txt` |
| 工程 B 真机运行成功（摄像头预览 + 周期推理） | `extensions/03_live_catdog_assignment/flash_output.txt`、`flash_output_live_run_1412.txt` |
| SD 卡内容由板子自己写成并校验 | `extensions/_tools/sdcard_seed/flash_output.txt`、`flash_output_seed_run_1251.txt` |
| 确实在新环境下重新编译过（而非只拷贝产物） | `evidence/build-logs/projA_build2.log`、`projB_build3.log` |
| MAX_PATH 曾真实阻断构建（所以换电脑务必用短路径） | `extensions/03_live_catdog_assignment/maxpath_build_error_excerpt.txt` |
| 对“确实是狗”的图能给对类别（临时实验） | `extensions/03_catdog_static_infer/flash_output_dogjpg_demo.txt` |
| 板卡身份（同一块板） | 三份运行日志中的 `Chip is … / USB mode … / MAC …` |

---

## 7. 已知限制与 FAQ

1. **准确率只有 0.61**：上游模型从零训练 3 epoch。`sample.jpg`（猫图）被判成 `dog 0.626` 是**已知误判**，
   验收点在于“读图→解码→推理→打印”流水线正确，不在刷分。
2. **单帧推理 3.24 s**：`infer=3240357 us`。报告的重点正是把**解码耗时**（`54132 us`）与**纯推理耗时**分开观察。
3. **中文乱码**：工程 B 的旧日志里“推理耗时”四字是采集时的 GBK 字节，用 UTF-8 打开会花屏；新跑的日志是 UTF-8。
4. **文档在 PowerShell 里显示乱码？** 本包所有 `.md` / `.yml` 都是 **UTF-8（无 BOM）**，而 Windows PowerShell 5.1 的
   `Get-Content` 默认按 GBK 解码中文 → 会花屏（上游原有文档同样如此，不是本包引入的问题）。
   请用 VS Code 打开，或写 `Get-Content -Encoding UTF8 README.md`。`CHECKSUMS.txt` 是纯 ASCII，不受影响。
5. **能不能不装 IDF 直接跑？** 不能，必须本机 `idf.py build`（包里没有 `build/`）。但三个工程的 `sdkconfig` 都在，
   配置不用重来，直接 `idf.py build` 即可（随包已锁定 `esp32s3`）。
6. **`idf.py set-target esp32s3` 要不要跑？** 不用。只有在 `sdkconfig` 丢失或报 “target not set” 时才跑，
   届时会按 `sdkconfig.defaults` 重新生成配置（内容实质相同，但可能与随包 `sdkconfig` 有少量差异）。

---

## 8. 与上游文档的对应关系

| 文档 | 作用 |
|---|---|
| `docs/catdog-run-report.md` | **主报告**：结论、哈希表、两次运行对比、逐行日志解读 |
| `docs/build-verification.md` | 构建与验证方式（如何判定“真的编过、真的跑过”） |
| `docs/environment-setup.md` | IDF 版本、工具链、Python 环境 |
| `docs/readme-evidence-manifest.yml` | 上游 README 证据索引 |
| `docs/curriculum-map.md` | 课程/知识点映射 |
| `extensions/*/README.md` | 各工程详解（**上游原文，未做改动**） |
| `README.md` / `RUNBOOK.md` / `MIGRATION-newPC.md` / `evidence/README.md` / `cats-dogs-data/README-PRUNED.md` / `verify-checksums.ps1` / `CHECKSUMS.txt` | **本包新增**：总入口、最小命令序列、换机指南、证据索引、裁剪说明、哈希校验脚本、哈希清单 |