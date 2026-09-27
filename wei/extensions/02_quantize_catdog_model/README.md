# 扩展案例 2：猫狗分类模型量化

> 类型：`PY` ｜ 验证状态：**已验证**（2026-09-17，Windows / Python 3.10.1 / esp-ppq 1.2.10 / CPU，详见[本次实测记录](#本次实测记录2026-09-17windows)） ｜ 前置：[`extensions/01_train_catdog_model`](../01_train_catdog_model/)
>
> 📘 逐行小白讲解见 [`CODE_EXPLANATION_CN.md`](CODE_EXPLANATION_CN.md)。

## 摘要

扩展案例 1 训出了猫狗模型的 ONNX，但它还是 float32 浮点模型——对 ESP32-S3 来说太大、太慢。本案例把微课最小案例 2 的量化流程搬到这个"真模型"上：用 **ESP-PPQ** 以 `esp32s3` 为目标做 **INT8 量化**，产出 ESP-DL 能加载的 **`.espdl`** 文件（后续端侧部署 LCD 实时猫狗分类等的模型来源），并打印量化前后的文件大小对照。**本案例只在电脑上运行，不需要开发板。**和微课最小案例 2 的三个不同点：

1. **校准数据变成真实图片**：用和训练完全相同的预处理读取 ImageFolder 里的猫狗图片；
2. **输入形状变成 `[1, 3, 224, 224]`**：一张 3 通道彩色图片；
3. **脚本只自动对照文件大小，不自动对照精度**：量化前后的分类准确率需按拓展挑战的方法在同一测试集上另行测量；实验报告里**不得把未执行的精度结果写成已实测**，也不得从文件大小推断精度。

## Quick Start

**预备知识**

- **已完成扩展案例 1**，需要两个上游产物：ONNX 模型 `../01_train_catdog_model/outputs/catdog_mobilenet_v2.onnx` 和校准图片 `../01_train_catdog_model/cats-dogs-data/train/`（cat/dog 两个子目录，本仓库各 100 张）；**已完成微课最小案例 2**：量化概念（INT8、校准、scale/exponent、`.espdl`）最小案例 2 已讲过，这里不再从零解释；
- **注意 esp-ppq 依赖**：扩展 1 的 requirements.txt 里**没有**它（微课最小案例 1 的有 `esp-ppq==1.2.10`）。按顺序学过微课第 1、2 集的环境里应已装好；否则按 Quick Start 第 3 步单独安装；
- **时间预算**：量化 224×224 的 MobileNetV2 比 sin 小模型慢，但本机实测**仅约 70 秒**（32 GB 内存、25 个校准 batch、CPU）。机器慢时预留几分钟即可，不必按"几十分钟"准备。


假设终端位于仓库根目录 `esi-mvp-code/`，且扩展案例 1 已完整跑完。

**第 1 步：激活 conda 环境**（成功后提示符出现 `(esp32s3)`）

```bash
conda activate esp32s3
```

> 💡 **本机没有 conda 就跳过这一步。** 本次实测环境用的是系统 Python 3.10.1
> （`C:\Users\user\AppData\Local\Python310\python.exe`），依赖齐全即可，不强制 conda。
> 验证方法见第 3 步末尾的 `python -c "import esp_ppq"`。

**第 2 步：进入案例目录**（`ls` 应能看到 `quantize_catdog.py`；本目录没有自己的 requirements.txt）

```bash
cd extensions/02_quantize_catdog_model
```

**第 3 步：安装依赖（注意 esp-ppq）**（第一条装基础依赖，扩展 1 装过则秒完；**第二条不能省**：脚本第一行就 `from esp_ppq.api import espdl_quantize_onnx`，而扩展 1 的依赖清单不含 esp-ppq，学过微课最小案例 1 的环境里已有它、pip 会提示已满足；装完用 `python -c "import esp_ppq"` 验证）

```bash
python -m pip install -r ../01_train_catdog_model/requirements.txt
python -m pip install esp-ppq==1.2.10
```

**第 4 步：检查前置产物**（第一条无输出且退出码 0 表示 ONNX 存在；第二条应输出 `cat`、`dog` 两行——校准图片就是扩展 1 的训练数据目录；不满足先回扩展 1 补齐，不要手工造文件绕过）

```bash
test -f ../01_train_catdog_model/outputs/catdog_mobilenet_v2.onnx
ls ../01_train_catdog_model/cats-dogs-data/train
```

> ⚠️ **本仓库的校准图片目录是 `cats-dogs-data/train`，不是 `data/catdog`**（早期文档写错过，照抄会 `FileNotFoundError`）。
> Windows PowerShell 下等价命令：
> ```powershell
> Test-Path ..\01_train_catdog_model\outputs\catdog_mobilenet_v2.onnx
> Get-ChildItem ..\01_train_catdog_model\cats-dogs-data\train | Select-Object Name
> ```

**第 5 步：运行量化**（三个参数分别指定：被量化的模型、校准图片目录、产物输出目录；ESP-PPQ 会打印大量日志属正常；本机实测约 70 秒，机器慢时预留几分钟，不要中途强杀）

```bash
python quantize_catdog.py \
  --onnx ../01_train_catdog_model/outputs/catdog_mobilenet_v2.onnx \
  --data-dir ../01_train_catdog_model/cats-dogs-data/train \
  --output-dir outputs
```

Windows PowerShell 用反引号 `` ` `` 续行（不是 `\`）：

```powershell
python quantize_catdog.py `
  --onnx ../01_train_catdog_model/outputs/catdog_mobilenet_v2.onnx `
  --data-dir ../01_train_catdog_model/cats-dogs-data/train `
  --output-dir outputs
```

> 🔴 **`espdl_quantize_onnx` 会就地改写你的 ONNX 文件。**
> 它内部先跑 `onnxsim.simplify()` 再 `onnx.save(model_sim, onnx_import_file)` 覆盖原文件
> （`esp_ppq/api/espdl_interface.py:216-218`）。本次实测 ONNX 从 8,878,502 → 8,875,417 字节。
> 因此脚本打印的 `float model size` 是**化简后**的大小；若还要用"原始未化简版"做对照，**先自行备份**。
> 已验证化简未破坏模型：`onnx.checker` 通过，输入 `input[1,3,224,224]`、输出 `output[1,2]`、节点数 100。

**第 6 步：核对并记录**（确认 `catdog_mobilenet_v2.espdl` 已生成，ESP-PPQ 可能附带同名报告类文件；把终端最后两行字节数抄进实验记录并算缩小比例；若要填精度对照，必须用同一测试样本和相同标签映射，另存原始结果，不得凭文件大小推断精度）

```bash
ls outputs
```

## 预期现象

成功时终端末尾输出如下（**下列为 2026-09-17 本机实测原文**，其他机器数值会有差异）：

```text
...（ESP-PPQ 自身的校准/量化/导出日志，含量化误差报告）...
float model size: 8875417 bytes
espdl model size: 2373648 bytes
```

ESP-PPQ 自身日志里的关键几行（本次实测）：

```text
--------- Network Snapshot ---------
Num of Op:                    [100]
Num of Quantized Op:          [100]
Num of Variable:              [277]
Num of Quantized Var:         [277]
------- Quantization Snapshot ------
Num of Quant Config:          [386]
ACTIVATED:                    [108]
OVERLAPPED:                   [125]
PASSIVE:                      [153]
Network Quantization Finished.
```

- 脚本自身只打印最后两行，其余海量日志来自 ESP-PPQ；
- **本次实测对照**：float `8,875,417` bytes → espdl `2,373,648` bytes，即缩小到 **26.74%**、压缩 **3.74 倍**、省下 **73.26%**；
- 伴随产物：`catdog_mobilenet_v2.json`（298,367 bytes，量化参数 scale/exponent）、`catdog_mobilenet_v2.info`（14,277,859 bytes，`error_report=True` 的逐层误差报告，很大属正常）；`.espdl` 文件头 magic 为 `EDL2`；
- 脚本当前**未**自动输出量化前后分类准确率，这项数据应在扩展作业中补充记录，不得从文件大小推断精度；
- 失败时：ONNX 不存在先完成扩展 1；类别不对修正数据目录；校准或导出失败检查 shape、依赖版本和磁盘空间；`.espdl` 生成但精度异常时保留校准数据、模型 hash 和完整报告，暂停部署。

**常见问题排查**

| 现象 | 原因 | 解决办法 |
|---|---|---|
| 🔴 `RuntimeError: stack expects each tensor to be equal size, but got [3, 224, 224] at entry 0 and [] at entry 1` | **本次实测真实踩到**。`collate_fn` 误以为传进来的 `batch` 是 8 个 `(图片,标签)` 样本；实际 DataLoader 默认已自动拼批，`batch` 是 `[图片张量(8,3,224,224), 标签张量(8,)]` 这 2 项 | 已修复为 `return batch[0]`（只取图片、丢掉标签）。等价替代方案：保留原 `collate_fn`，给 `DataLoader` 加 `collate_fn=lambda b: b` 关掉自动拼批 |
| `FileNotFoundError: ... data\catdog` | 早期文档里的 `data/catdog` 路径在本仓库不存在 | 用 `../01_train_catdog_model/cats-dogs-data/train` |
| `ModuleNotFoundError: No module named 'esp_ppq'` | 扩展 1 的依赖清单不含 esp-ppq，环境里没装过 | 执行 `python -m pip install esp-ppq==1.2.10` |
| `ValueError: expected classes ['cat', 'dog']` | `--data-dir` 指错，或混入其他子目录/大小写不对 | 指向扩展 1 的 `cats-dogs-data/train`，清理 `__MACOSX` 等多余目录 |
| `FileNotFoundError: ... catdog_mobilenet_v2.onnx` | 扩展 1 没跑完或路径写错 | 先完成扩展 1；`--onnx` 相对路径是相对**当前目录**的，逐字核对 |
| shape 不匹配类报错 | `input_shape` 与 ONNX 实际输入不一致 | 保持 `[1, 3, 224, 224]`；扩展 1 改过尺寸要两边同步 |
| `WARNING: Ignoring invalid distribution -nnx` | site-packages 里有 `~nnx` / `~nnx-1.22.0.dist-info` 残留坏目录（早前 onnx 安装被中断） | 无害噪音，删掉这两个目录即可 |
| 量化非常慢、疑似卡死 | MobileNetV2 在 CPU 上量化比小模型慢，日志多不代表卡住 | 观察日志是否仍在滚动；本机实测约 70 秒；确需提速可减小 `calib_steps`（须记录） |
| 后台运行但日志文件半天是空的 | Python 输出重定向到文件时是**块缓冲** | 加 `-u`：`python -u quantize_catdog.py ... > run.log 2>&1` |
| 内存不足/进程被杀 | 224×224 图片批量校准占内存较多（本机峰值约 1.5 GB） | 关闭其他大程序，把 `batch_size=8` 调小，记录改动 |
| `.espdl` 生成了但上板识别异常 | 校准预处理与训练/端侧不一致 | 逐字核对三处 transform；需要自检时改 `export_test_values=True` 重新量化；保留报告并暂停部署 |

## 学习目标

- 准备与训练类别、预处理完全一致的校准数据，并解释为什么必须一致；
- 运行量化脚本，确认 `.espdl` 正常生成；
- 从终端读出并记录 float（ONNX）与 ESPDL 两个文件的字节数；
- 解释本案例 `export_test_values=False` 与微课最小案例 2 `True` 的区别及影响；
- 设计"同一测试集上的量化前后精度对照"实验，诚实标注哪些实测、哪些未测。

## 原理讲解

**为什么校准数据要"一样的图片、一样的预处理"**

校准是拿代表性输入跑一遍浮点模型、统计每层数值范围，据此确定 INT8 刻度；刻度准不准，完全取决于这批输入像不像模型将来真正会遇到的输入。对猫狗模型来说，真实输入是"经过 `Resize(224,224) → ToTensor → Normalize(ImageNet 统计值)` 的猫狗图片张量"，所以脚本逐字复用扩展 1 的 transform，并读同一个 `cats-dogs-data/train` 目录。如果校准忘了 Normalize 或用了别的尺寸，量化刻度就画错，上板后分类会莫名其妙地乱；脚本同样有类别防呆检查：`dataset.classes != ["cat", "dog"]` 直接抛 `ValueError`。

**量化调用：与最小案例 2 同构，三处不同**

校准 DataLoader 用 `batch_size=8`（量化内存压力比训练大）、`shuffle=False`（同最小案例 2：多次遍历必须可比较）、`calib_steps=min(32, len(loader))`（图片不足 32 批时用实际批数）。`espdl_quantize_onnx()` 参数结构与最小案例 2 一致，不同点：

| 参数 | 微课最小案例 2（sin） | 本案例（猫狗） | 说明 |
|---|---|---|---|
| `input_shape` | `[1, 1]` | `[1, 3, 224, 224]` | 1 张 3 通道 224×224 图片 |
| `export_test_values` | `True` | `False` | 不把测试值嵌入 `.espdl`；后续若需板上 `model->test()` 自检，改成 `True` 重新量化 |
| `calib_steps` | 固定 `32` | `min(32, len(loader))` | 数据不足时自动收敛到实际批数 |

其余相同：`target="esp32s3"`、`num_of_bits=8`、`device="cpu"`、`error_report=True`。

![浮点模型到 INT8 ESP-DL 模型的量化示意图（AI 生成示意）](../../docs/assets/ai_generated/float_to_int8_quantization.png)

> 图：代表性图片用于估计量化范围，量化后得到更适合端侧部署的整数模型。体积与精度关系是概念说明，实际结论以同一测试集测量为准。

**本脚本能证明什么、不能证明什么**

脚本最后只打印两行：`float model size`（ONNX 字节数）和 `espdl model size`（`.espdl` 字节数），能证明**存储收益**（INT8 通常明显更小）。但脚本**没有**在测试集上跑量化前后的分类推理，所以不能证明精度损失是多少——"文件更小"不等于"模型更好"。精度对照必须按拓展挑战第 1 条补充：用同一批测试图片、同样的标签映射（cat=0、dog=1），分别测浮点和量化的 Top-1 准确率后记录。

## 整体流程图

```text
扩展 1 产物：catdog_mobilenet_v2.onnx + cats-dogs-data/train（ImageFolder）
             ↓ Resize(224,224)/ToTensor/Normalize（与训练逐字一致）
             ↓ DataLoader(batch_size=8, shuffle=False)
             ↓ espdl_quantize_onnx(target=esp32s3, num_of_bits=8,
                                   calib_steps=min(32, len(loader)),
                                   export_test_values=False)
outputs/catdog_mobilenet_v2.espdl → float/espdl model size 字节数对照
             ↓（需自行补充的实验）同一测试集上的量化前后 Top-1 精度记录
```

## 关键代码解析

片段来自 [`quantize_catdog.py`](quantize_catdog.py)。

**1. 预处理与类别检查：和训练脚本逐字一致**

```python
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])
dataset = datasets.ImageFolder(args.data_dir, transform=transform)
if dataset.classes != ["cat", "dog"]:
    raise ValueError(f"expected classes ['cat', 'dog'], got {dataset.classes}")
loader = DataLoader(dataset, batch_size=8, shuffle=False, num_workers=0)
```

这段 transform 与 `train_catdog.py` 完全一致是刻意复制："校准看到的分布 = 训练看到的分布 = 端侧将要看到的分布"。另有 `collate_fn` 只保留图片张量、丢掉标签。

> 🔴 **`collate_fn` 原写法是错的，已修复。** 原代码 `return torch.stack([sample[0] for sample in batch])`
> 假设 `batch` 是 8 个 `(图片, 标签)` 样本；但 ESP-PPQ 传进来的其实是 DataLoader **已自动拼好的一批**，
> 即 `[图片张量(8,3,224,224), 标签张量(8,)]` 这个长度为 2 的列表。于是 `sample[0]` 分别取到
> `images[0]`→`(3,224,224)` 和 `labels[0]`→标量 `()`，`torch.stack` 尺寸不一致直接崩：
> `RuntimeError: stack expects each tensor to be equal size, but got [3, 224, 224] at entry 0 and [] at entry 1`。
> 现改为 `return batch[0]`，实测校准 25 步顺利完成。
> （微课最小案例 2 用的是同一个错误写法，只因那边 `x`、`y` 形状凑巧都是 `[N,1]` 才没崩，属隐性 bug。）

**2. 量化主调用**

```python
espdl_quantize_onnx(
    onnx_import_file=args.onnx,              # 扩展 1 导出的 ONNX
    espdl_export_file=str(espdl_path),       # outputs/catdog_mobilenet_v2.espdl
    calib_dataloader=loader,
    calib_steps=min(32, len(loader)),        # 数据不足 32 批时用实际批数
    input_shape=[1, 3, 224, 224],            # 必须与 ONNX 输入一致
    target="esp32s3",
    num_of_bits=8,                           # INT8
    collate_fn=collate_fn,
    device="cpu",
    error_report=True,                       # 打印量化误差报告
    export_test_values=False,                # 不嵌入板上自检用的测试值
    verbose=1,
)
```

**3. 文件大小对照**

```python
print(f"float model size: {os.path.getsize(args.onnx)} bytes")
print(f"espdl model size: {espdl_path.stat().st_size} bytes")   # 两种写法都是取文件字节数
```

## 本次实测记录（2026-09-17，Windows）

### 环境

| 项 | 实测值 |
|---|---|
| 操作系统 | Windows（win32） |
| Python | 3.10.1 @ `C:\Users\user\AppData\Local\Python310\python.exe`（**未使用 conda**，跳过第 1 步） |
| esp-ppq | 1.2.10 |
| torch / torchvision | 2.14.0+cpu / 0.29.0+cpu（纯 CPU，无 CUDA） |
| onnx / onnxsim / onnxruntime | 1.17.0 / 0.4.36 / 1.23.2 |
| numpy / pillow | 2.2.6 / 12.3.0 |
| 内存 | 32 GB（量化峰值约 1.5 GB） |

依赖全部已就绪，未重新安装。清理项：删除 site-packages 里残留的 `~nnx`、`~nnx-1.22.0.dist-info`
（早前 onnx 安装被中断留下的坏目录），消除 `WARNING: Ignoring invalid distribution -nnx` 噪音。

### 实际执行的命令

```powershell
cd extensions\02_quantize_catdog_model
python quantize_catdog.py `
  --onnx ../01_train_catdog_model/outputs/catdog_mobilenet_v2.onnx `
  --data-dir ../01_train_catdog_model/cats-dogs-data/train `
  --output-dir outputs
```

### 结果

| 项 | 实测值 |
|---|---|
| 耗时 | 约 **70 秒**（15:48:03 → 15:49:13） |
| 校准集 | 200 张（cat 100 + dog 100），batch_size=8 → `calib_steps = min(32, 25) = 25` |
| 网络 | Op 100（全部量化）、Variable 277（全部量化）、Quant Config 386（ACTIVATED 108 / OVERLAPPED 125 / PASSIVE 153） |
| float model size | **8,875,417 bytes**（onnxsim 化简后） |
| espdl model size | **2,373,648 bytes** |
| 压缩效果 | 缩小到 **26.74%**，压缩 **3.74 倍**，省下 **73.26%** |
| 产物校验 | `.espdl` magic = `EDL2` ✅；`.json` 顶层键 `configs`/`dispatchings`/`values` ✅ |
| ONNX 完整性 | 化简后 `onnx.checker` 通过，`input[1,3,224,224]` / `output[1,2]` / 节点数 100，未被破坏 ✅ |

### 本次对课程代码做的修改（仅 1 处）

| 文件 | 改动 | 原因 |
|---|---|---|
| `quantize_catdog.py` | `collate_fn` 由 `return torch.stack([sample[0] for sample in batch])` 改为 `return batch[0]` | 原写法误解了 `batch` 的结构，运行即 `RuntimeError: stack expects each tensor to be equal size, but got [3, 224, 224] at entry 0 and [] at entry 1`。详见上方"关键代码解析 1" |

未改动的项：`batch_size` 仍为 8、`calib_steps` 仍为 `min(32, len(loader))`、`error_report` 仍为 `True`、
`target`/`num_of_bits`/`device`/`input_shape` 全部保持课程默认值。**没有为了让它跑通而降低任何量化质量参数。**

### ⚠️ 未实测项

- **量化前后 Top-1 准确率对照：未实测。** 本脚本不测精度；`.espdl` 更小**不代表**精度损失可接受。
- **开发板上的推理延迟 / 内存占用：未实测**（本案例只在电脑上运行，不上板）。
- 另注：扩展案例 1 的 `metrics.csv` 显示 `val_accuracy` 三轮均为 `0.5`，即**上游模型本身尚未学出区分能力**。
  量化只"换表示法"，不会把一个 50% 的模型变准；上板前建议先回扩展 1 把模型训好。

## 关键文件说明

| 文件/目录 | 职责 | 类型 |
|---|---|---|
| [`quantize_catdog.py`](quantize_catdog.py) | 校准、量化和大小输出（本案例入口） | 课程代码 |
| [`CODE_EXPLANATION_CN.md`](CODE_EXPLANATION_CN.md) | 逐行小白讲解 + 本次实测记录 | 讲解文档 |
| [`../01_train_catdog_model/train_catdog.py`](../01_train_catdog_model/train_catdog.py) | 训练预处理和类别约定的来源（transform 需逐字一致） | 上游课程代码 |
| `../01_train_catdog_model/outputs/catdog_mobilenet_v2.onnx` | 量化输入（⚠️ 会被 onnxsim 就地改写） | 上游生成物 |
| `../01_train_catdog_model/cats-dogs-data/train/` | 校准图片来源（ImageFolder 结构，cat/dog 各 100 张） | 外部数据 |
| `outputs/catdog_mobilenet_v2.espdl` | ESP-DL 部署模型（实测 2,373,648 bytes，magic `EDL2`） | 生成物 |
| `outputs/catdog_mobilenet_v2.json` | 量化参数 scale/exponent（实测 298,367 bytes） | 生成物 |
| `outputs/catdog_mobilenet_v2.info` | 逐层量化误差报告（实测 14,277,859 bytes） | 生成物 |
| `outputs/run.log` | 本次实测完整终端日志（归档证据） | 生成物 |

## 配置说明

配置写在 `quantize_catdog.py` 里或通过命令行传入，改后重跑：

| 修改位置 | 配置项 | 现象变化 |
|---|---|---|
| 命令行 | `--onnx` / `--data-dir` / `--output-dir` | 被量化的模型（须是扩展 1 产物）/ 校准图片目录（须保持 cat/dog 结构）/ 产物目录 |
| [`quantize_catdog.py`](quantize_catdog.py) | `input_shape=[1,3,224,224]` | 必须与 ONNX 输入一致，改错直接失败 |
| 同上 | `target="esp32s3"` / `num_of_bits=8` | 部署目标芯片 / 量化位宽，影响体积和误差 |
| 同上 | `calib_steps=min(32, len(loader))` | 校准覆盖范围，增大更稳但更耗时 |
| 同上 | `export_test_values=False` | 改为 `True` 会嵌入测试值，供板上 `model->test()` 自检 |
| 同上 | `device="cpu"` | 改 GPU 前须确认 CUDA 与 esp-ppq 兼容 |

## 术语小表

| 术语 | 解释 |
|---|---|
| 量化 | 把模型里的 float32 换成 INT8（8 位整数，只有 256 个档位），省存储、算得快，代价是少量精度 |
| 校准集 | 用来估计量化刻度的代表性输入；本例是与训练同预处理的猫狗图片 |
| 预处理一致性 | 校准、训练、端侧三方的 Resize/Normalize 必须逐字一致，否则刻度画错 |
| ESP-PPQ | 乐鑫的训练后量化工具，输入 ONNX、输出 `.espdl` |
| `espdl_quantize_onnx` | ESP-PPQ 核心 API，一个函数完成校准、量化、导出 |
| calib_steps | 校准使用的 batch 数；本例 `min(32, len(loader))` |
| `export_test_values` | 是否把测试值嵌入 `.espdl` 供板上自检；本例为 False |
| Top-1 准确率 | 概率最高的一个类别判对的比率；补充精度对照实验的指标 |
| 量化误差 | 量化表示与浮点表示之间的输出差异，error_report 会给出相关信息 |
| hash | 文件内容摘要（如 sha256），用于确认模型版本、归档实验记录 |

## 验证清单

- [x] ONNX、校准数据和类别顺序来自同一次扩展 1 运行（实测 `dataset.classes == ['cat','dog']`，200 张）；
- [x] `python -c "import esp_ppq"` 无报错（esp-ppq 1.2.10）；
- [x] 记录目标芯片（esp32s3）、shape（[1,3,224,224]）、位宽（8）、校准步数（25）和依赖版本 —— 见[本次实测记录](#本次实测记录2026-09-17windows)；
- [x] 保存 `float model size` / `espdl model size` 两行日志原文：`8875417` / `2373648` bytes；
- [ ] 另用同一测试集记录量化前后精度 —— **未实测**，不得用文件大小替代（属拓展挑战）；
- [x] 量化报告（`outputs/run.log` + `outputs/catdog_mobilenet_v2.info`）和模型 hash 已归档（见下）。

**产物 SHA256（归档用）**

| 文件 | SHA256 |
|---|---|
| `outputs/catdog_mobilenet_v2.espdl` | `6530322CCA0A8313227D87BFD222C92BC91A7587853062FD17B0B10EFABF627B` |
| `outputs/catdog_mobilenet_v2.json` | `2D358810EF1BF9617C4803FF72F11407A575E67068B36D89C54C03DEA186F9E4` |
| `../01_.../catdog_mobilenet_v2.onnx`（化简后） | `18506F5F646C00132D43EF3DAD2CBE0991664FB77FBCE4205378C1226E450548` |

## 思考题与拓展挑战

**思考题**

1. 为什么校准预处理必须和训练/端侧预处理一致？

   **参考答案：**量化范围由输入分布决定；预处理不一致会让校准范围与部署输入对不上，导致误差变大或分类偏移。

2. 为什么不能从 `.espdl` 文件更小就判断模型更好？

   **参考答案：**更小只说明存储成本可能降低，不能说明精度、延迟、内存和稳定性满足系统需求。

3. 本脚本 `export_test_values=False`，微课最小案例 2 是 `True`。后续要在板上用 `model->test()` 自检怎么办？

   **参考答案：**把 `export_test_values` 改为 `True` 重新量化，让测试值嵌入 `.espdl`，并记录配置变化；沿用 `False` 的产物无法通过自检。

4. （本次实测新增）为什么脚本打印的 `float model size` 和扩展 1 刚导出时的 ONNX 大小不一样？

   **参考答案：**`espdl_quantize_onnx` 内部会先跑 `onnxsim.simplify()` 化简模型，再 `onnx.save(model_sim, onnx_import_file)` **覆盖写回原 ONNX 文件**（`esp_ppq/api/espdl_interface.py:216-218`）。本次实测从 8,878,502 变为 8,875,417 字节。要做"原始未化简版"对照实验须先自行备份。

**拓展挑战**

- 为脚本增加同一测试集上的 float/quant Top-1 对照，输出 CSV；
- 在不改变类别顺序的约束下比较两种校准集规模。

