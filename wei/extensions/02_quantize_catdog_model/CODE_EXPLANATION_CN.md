# quantize_catdog.py 小白也能看懂的超详细讲解

> 本文档面向**完全没接触过"模型量化"的小白**，逐段拆解 `quantize_catdog.py` 的每一部分在做什么、为什么这样做。
> 同级参考：[`../01_train_catdog_model/CODE_EXPLANATION_CN.md`](../01_train_catdog_model/CODE_EXPLANATION_CN.md)（训练部分）。
> 文末附**本机实测记录**（含一次真实踩坑与修复过程）。

---

## 整体概念：这个脚本在干什么？

扩展案例 1 训练出了一个会分辨猫狗的模型，导出成 `catdog_mobilenet_v2.onnx`，**8.87 MB**。
但 ESP32-S3 是一块只有几百 KB 内存的小芯片，这个模型对它来说**又占地方又慢**。

打个比方：

> 你写了一本 **500 页的精装词典**（float32 模型），每个字都用最精细的字体排版。
> 现在要把它塞进**口袋**（ESP32-S3）里随身带。
> 办法是：把它**重排成 150 页的袖珍手册**（INT8 模型）——字变小了、纸变薄了，
> 内容还是那些内容，查起来快得多，只是极个别生僻字的笔画会有一点点失真。

这个"重排"的过程就叫 **量化（Quantization）**。本脚本做的就是：

```
  catdog_mobilenet_v2.onnx   ──┐
  （float32，8.87 MB）          │
                               ├──►  ESP-PPQ 量化  ──►  catdog_mobilenet_v2.espdl
  200 张猫狗图片（校准集）  ──┘    （INT8，esp32s3）      （ESP-DL 能直接加载）
```

**关键点：量化不是"压缩文件"（不是 zip），而是"换一种更省的数字表示法"。**

---

## 第 0 部分：先搞懂 5 个关键词

不理解这 5 个词，后面的代码就是天书。

| 关键词 | 大白话解释 |
|---|---|
| **float32** | 每个数字用 32 位（4 字节）存，精度极高，能表示 `0.123456789` 这种小数。模型里几百万个数字都这么存 → 体积大 |
| **INT8** | 每个数字只用 8 位（1 字节）存，**只有 256 个档位**（-128 ~ 127）。体积直接变 1/4，整数运算芯片算得飞快，代价是有微小误差 |
| **量化 / Quantization** | 把 float32 换成 INT8 的过程。核心是给每一层算一把"尺子"（scale/exponent），决定"浮点数值 ↔ 整数档位"怎么对应 |
| **校准 / Calibration** | 尺子不能凭空画。**拿一批真实图片跑一遍浮点模型**，统计每一层实际出现过的数值范围（最小值~最大值），据此定刻度。这批图片就叫**校准集** |
| **`.espdl`** | 乐鑫 ESP-DL 推理引擎的模型文件格式。`.espdl` 之于 ESP32，就像 `.pt` 之于 PyTorch——是**最终要烧进开发板**的那个文件 |

> **为什么必须有校准集？**
> 假设某一层浮点输出范围是 `-3.2 ~ +5.8`。INT8 只有 256 档，就得把这 9.0 的宽度均分成 256 份，每份约 0.035。
> 如果你**没看真实数据**、瞎猜范围是 `-100 ~ +100`，那每份就变成 0.78 —— 精度直接损失 20 多倍，模型上板就废了。
> 所以"尺子画得准不准，全看校准集像不像模型将来真正遇到的输入"。

---

## 第一部分：导入库（第 3-10 行）

```python
import argparse
import os
from pathlib import Path

import torch
from esp_ppq.api import espdl_quantize_onnx
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
```

| 库名 | 它是干嘛的 |
|---|---|
| `argparse` | 让你在命令行敲 `--onnx xxx` 这样的参数，不用改代码 |
| `os` | 这里只用到一个功能：`os.path.getsize()` 取文件字节数 |
| `pathlib.Path` | 处理路径、创建目录，比手动拼 `/` 字符串更安全（Windows/Mac 斜杠方向不一样，它自动搞定） |
| `torch` (PyTorch) | 深度学习框架，负责所有张量计算。**量化过程中要在电脑上模拟跑模型，靠的就是它** |
| `esp_ppq.api.espdl_quantize_onnx` | ⭐ **本脚本的主角**：乐鑫 ESP-PPQ 提供的"一键量化"函数，输入 ONNX、输出 `.espdl` |
| `DataLoader` | 数据搬运工——把图片一批一批（batch）喂给量化流程 |
| `torchvision.datasets` / `transforms` | 读图片文件夹 + 图片预处理（缩放、归一化） |

> **ESP-PPQ 是什么？** PPQ = Post-Processing Quantization（训练后量化）。
> "训练后"的意思是：**不需要重新训练模型**，拿现成的 ONNX 直接量化。
> 乐鑫把它 fork 了一份、加了导出 `.espdl` 的能力，叫 **ESP-PPQ**，`pip install esp-ppq` 安装。

---

## 第二部分：`collate_fn` —— 本次真实踩的坑（第 13-22 行）

```python
def collate_fn(batch):
    """校准只需要图片张量，把标签丢掉。"""
    return batch[0]
```

### 它的作用

`ImageFolder` 读出来的每张图都带着标签：`(图片张量, 类别编号)`，比如 `(tensor(3,224,224), 0)`（0=cat）。
但**量化校准根本不需要标签**——它只关心"图片喂进去后，每一层的数值范围是多少"，不关心"这张图是猫还是狗"。
所以 `collate_fn` 的职责就一句话：**把标签扔掉，只留图片。**

### ⚠️ 这里原本是个 bug，实测直接崩了

课程原始代码写的是：

```python
def collate_fn(batch):
    return torch.stack([sample[0] for sample in batch])   # ← 会报错
```

它**假设** `batch` 是"8 个 `(图片, 标签)` 样本组成的列表"。运行时报错：

```text
RuntimeError: stack expects each tensor to be equal size,
but got [3, 224, 224] at entry 0 and [] at entry 1
```

**真正的原因**：ESP-PPQ 传给 `collate_fn` 的 `batch`，是 `DataLoader` **已经自动拼好的一整批**，
而不是 8 个散样本。实测打印出来是这样：

```text
batch type <class 'list'>  outer len 2        ← 外层只有 2 项，不是 8 项！
b[0] (8, 3, 224, 224) torch.float32          ← 第 0 项 = 8 张图片
b[1] (8,)             torch.int64            ← 第 1 项 = 8 个标签
```

于是 `[sample[0] for sample in batch]` 实际取到的是：

| 循环 | `sample` 是 | `sample[0]` 是 | 形状 |
|---|---|---|---|
| 第 1 圈 | 图片张量 `(8,3,224,224)` | **第 0 张图** | `(3,224,224)` |
| 第 2 圈 | 标签张量 `(8,)` | **第 0 个标签**（一个整数） | `()` 标量 |

`torch.stack` 要求所有张量形状一致，一个 `(3,224,224)` 一个 `()` → **崩溃**，错误信息和上面完全对上。

### 修复

```python
def collate_fn(batch):
    return batch[0]        # batch = [图片张量, 标签张量]，取第 0 项就是图片
```

实测修复后：`batch[0].shape == (8, 3, 224, 224)` ✅，校准 25 步顺利完成。

> **另一种等价修法**（二选一即可，不要两个都改）：
> 保留原 `collate_fn` 不动，改 `DataLoader` 让它**别自动拼批**：
> ```python
> loader = DataLoader(dataset, batch_size=8, shuffle=False, num_workers=0,
>                     collate_fn=lambda b: b)   # b 就是 8 个 (图片,标签) 元组
> ```
> 这样 `batch` 才真的是 8 个样本，原写法就成立了。
> **本文采用改 `collate_fn` 的方案**，因为它更符合 ESP-PPQ 官方模板 `collate_fn_template` 的语义
> （官方模板也是把传进来的东西当"已拼好的批"处理）。

> 💡 **顺便一提**：微课最小案例 2（`microcourses/02_quantize_sin_model/quantize_onnx_model.py`）
> 用的是同一个错误写法。它之所以"没崩"，是因为那边 `x` 和 `y` 的形状凑巧都是 `[N,1]`，
> `X[0]` 和 `Y[0]` 形状都是 `[1]`，`torch.stack` 侥幸不报错——但**喂给模型的其实是 2 个标量拼起来的错误数据**。
> 属于"能跑通但语义不对"的隐性 bug，本案例的 224×224 图片形状对不上，才把它暴露出来。

---

## 第三部分：命令行参数（第 26-32 行）

```python
parser = argparse.ArgumentParser()
parser.add_argument("--onnx", required=True)
parser.add_argument("--data-dir", required=True)
parser.add_argument("--output-dir", default="outputs")
args = parser.parse_args()
output_dir = Path(args.output_dir)
output_dir.mkdir(parents=True, exist_ok=True)
```

| 参数 | 是否必填 | 含义 | 本次实测填的值 |
|---|---|---|---|
| `--onnx` | ✅ 必填 | **要被量化的模型**，必须是扩展案例 1 导出的 ONNX | `../01_train_catdog_model/outputs/catdog_mobilenet_v2.onnx` |
| `--data-dir` | ✅ 必填 | **校准图片目录**，里面必须正好有 `cat`、`dog` 两个子文件夹 | `../01_train_catdog_model/cats-dogs-data/train` |
| `--output-dir` | 选填，默认 `outputs` | 产物 `.espdl` 存哪 | `outputs` |

| 代码 | 大白话 |
|---|---|
| `required=True` | "这个参数不给就直接报错退出"，避免用了默认空值跑到一半才崩 |
| `output_dir.mkdir(parents=True, exist_ok=True)` | "目录不存在就创建（`parents=True` 连父目录一起建），已存在也别报错（`exist_ok=True`）" |

> ⚠️ **相对路径是相对"你当前所在目录"，不是相对脚本文件**。
> 所以必须先 `cd extensions/02_quantize_catdog_model` 再运行，否则 `../01_train_catdog_model/...` 会指错地方。

---

## 第四部分：图片预处理 transform —— 全文最容易翻车的地方（第 33-37 行）

```python
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])
```

`Compose` = "把下面这几步**按顺序串成流水线**"。一张图片依次经过 3 道工序：

| 工序 | 输入 → 输出 | 大白话 |
|---|---|---|
| `Resize((224,224))` | 任意尺寸 JPG → 224×224 | **统一尺寸**。原图有大有小，模型只吃 224×224，必须先缩放成一样大 |
| `ToTensor()` | 224×224×3 图片 → `tensor(3,224,224)` | ①把像素从 `0~255` 整数**除以 255** 变成 `0.0~1.0` 小数；②把通道顺序从 `HWC`（高,宽,通道）换成 PyTorch 要的 `CHW`（通道,高,宽） |
| `Normalize(mean, std)` | `0.0~1.0` → 约 `-2.1~2.6` | **标准化**：`(像素 - 均值) / 标准差`。让每个通道的数值都分布在 0 附近、幅度接近 |

`[0.485, 0.456, 0.406]` 和 `[0.229, 0.224, 0.225]` 是 **ImageNet 数据集**上千万张图片统计出来的 R/G/B 三通道均值和标准差，
是行业约定俗成的"通用值"，MobileNetV2 预训练时用的就是它。

### 🔴 为什么这 3 行必须和训练时**逐字一致**？

这是量化最容易翻车、而且**翻车了还不报错**的地方：

```
训练时：  图片 → Resize(224) → ToTensor → Normalize → 模型学会了这套输入
校准时：  图片 → Resize(224) → ToTensor → Normalize → 统计数值范围，画出 INT8 尺子
上板时：  摄像头 → 必须也是同一套 → 模型才能正确识别
```

三处只要有一处不一样（比如校准忘了 `Normalize`），后果是：

- **校准时看到的数值范围**（比如 `0.0~1.0`）
- **上板后真实的数值范围**（比如 `-2.1~2.6`）

对不上 → **尺子刻度画错** → INT8 表示严重失真 → 开发板上猫狗乱猜，而且**电脑上一切正常、日志一片祥和**，非常难查。

> 所以这段代码是从 `train_catdog.py` **刻意原样复制**过来的，不是巧合。改一处就要三处同步改。

---

## 第五部分：读图片 + 类别防呆（第 38-40 行）

```python
dataset = datasets.ImageFolder(args.data_dir, transform=transform)
if dataset.classes != ["cat", "dog"]:
    raise ValueError(f"expected classes ['cat', 'dog'], got {dataset.classes}")
```

| 代码 | 大白话 |
|---|---|
| `ImageFolder(目录, transform=...)` |  torchvision 的"傻瓜读图器"：**按文件夹结构自动打标签**。`cat/` 下的图标签=0，`dog/` 下的图标签=1 |
| `dataset.classes` | 它自动扫出来的类别名列表，**按字母顺序排**，所以正好是 `['cat', 'dog']` |
| `if ... != ["cat","dog"]: raise` | **防呆检查**：万一你 `--data-dir` 指错了目录，立刻报错停下，而不是闷头量化出一个废模型 |

`ImageFolder` 要求的目录结构（本次实测就是这个）：

```
cats-dogs-data/train/          ← --data-dir 指这里
├── cat/   cat_0000.jpg ... cat_0099.jpg    （100 张 → 标签 0）
└── dog/   dog_0000.jpg ... dog_0099.jpg    （100 张 → 标签 1）
```

> **为什么这个防呆很重要？** 因为标签顺序 = 模型输出的含义。
> `labels.txt` 写的是 `cat` 在第 0 行、`dog` 在第 1 行，开发板端就是按"输出[0]大=猫"来判断的。
> 如果目录里多混进一个 `Cat`（大写）或 `__MACOSX` 文件夹，`classes` 会变成 3 项或顺序颠倒，
> 模型输出的含义就全错了——**而且不会报任何错**，只会表现为"上板后猫狗永远反着判"。

---

## 第六部分：DataLoader 数据搬运工（第 41 行）

```python
loader = DataLoader(dataset, batch_size=8, shuffle=False, num_workers=0)
```

| 参数 | 值 | 为什么这么填 |
|---|---|---|
| `batch_size` | `8` | 一次喂 8 张图。太大吃内存（224×224×3 的图不小），太小校准慢。内存不够就调成 4 |
| `shuffle` | `False` | 🔴 **必须 False**！ESP-PPQ 算量化误差时会**多次遍历数据集**，若每次顺序都随机，两次遍历对不上，**算出来的误差就是错的** |
| `num_workers` | `0` | 用主进程读图，不开多进程子线程。**Windows 上多进程 + DataLoader 极容易报 `BrokenPipe`/卡死**，0 最稳 |

实测：200 张图 ÷ 8 = **25 个 batch**，所以 `len(loader) == 25`。

---

## 第七部分：⭐ 核心调用 `espdl_quantize_onnx`（第 42-57 行）

```python
espdl_path = output_dir / "catdog_mobilenet_v2.espdl"
espdl_quantize_onnx(
    onnx_import_file=args.onnx,
    espdl_export_file=str(espdl_path),
    calib_dataloader=loader,
    calib_steps=min(32, len(loader)),
    input_shape=[1, 3, 224, 224],
    target="esp32s3",
    num_of_bits=8,
    collate_fn=collate_fn,
    device="cpu",
    error_report=True,
    skip_export=False,
    export_test_values=False,
    verbose=1,
)
```

**这一个函数就把"读 ONNX → 校准 → 量化 → 导出 .espdl"全干完了**，是 ESP-PPQ 的一站式入口。

| 参数 | 本次值 | 大白话解释 |
|---|---|---|
| `onnx_import_file` | 扩展 1 的 `.onnx` | **输入**：要被量化的浮点模型 |
| `espdl_export_file` | `outputs/catdog_mobilenet_v2.espdl` | **输出**：量化后的模型存哪。注意要 `str()` 转成字符串，因为这个参数不接受 `Path` 对象 |
| `calib_dataloader` | 上面的 `loader` | **校准集**：拿哪些数据去统计数值范围、画 INT8 尺子 |
| `calib_steps` | `min(32, 25)` = **25** | **用几个 batch 来校准**。`min()` 是防呆：数据不够 32 批时就用实际批数，否则 ESP-PPQ 会反复绕圈。本次实测正好 25 |
| `input_shape` | `[1, 3, 224, 224]` | 🔴 **必须和 ONNX 的真实输入逐字一致**：1 张图、3 通道(RGB)、224×224。写错直接失败 |
| `target` | `"esp32s3"` | **给哪块芯片用**。可选 `'c'`（通用 C 代码）、`'esp32s3'`、`'esp32p4'`。不同芯片支持的指令不同，量化策略也不同 |
| `num_of_bits` | `8` | **量化位宽**，8 = INT8（256 档）。改成 16 精度更高但体积翻倍、速度更慢 |
| `collate_fn` | 上面那个函数 | 告诉 ESP-PPQ"从 DataLoader 拿到一批数据后，怎么取出模型真正要的输入"（就是丢标签） |
| `device` | `"cpu"` | 量化过程在哪算。改 `"cuda"` 前必须确认 CUDA 与 esp-ppq 版本兼容，否则容易崩 |
| `error_report` | `True` | **打印量化误差报告**：逐层告诉你"量化后和量化前差多少"，用来判断量化质量。关掉能省点时间，但就看不到质量了 |
| `skip_export` | `False` | `False` = 正常导出 `.espdl`；`True` = 只量化不导出（调试用） |
| `export_test_values` | `False` | 是否把一组"标准答案输入输出"**嵌进 `.espdl`**，供开发板上调用 `model->test()` 自检。本案例为 `False`，所以**这块产物不能在板上自检**；要自检得改成 `True` 重量化 |
| `verbose` | `1` | 日志啰嗦程度。`0` 安静、`1` 正常、`2` 最详细 |

### 🔴 一个必须知道的副作用：它会**改写你的原始 ONNX 文件**

本次实测发现，量化前 ONNX 是 **8,878,502 字节**，量化后变成 **8,875,417 字节**，文件修改时间也变了。

原因在 ESP-PPQ 源码 `esp_ppq/api/espdl_interface.py` 第 216-218 行：

```python
model_sim, check = simplify(model)      # 用 onnxsim 化简模型
if check:
    onnx.save(model_sim, onnx_import_file)   # ← 直接写回原文件！
```

也就是说 `espdl_quantize_onnx` 会**先用 onnxsim 把 ONNX 化简（合并冗余节点），然后覆盖保存回原路径**。

由此带来两个后果，都要心里有数：

1. 脚本最后打印的 `float model size` 是**化简后**的大小，不是扩展 1 刚导出时的原始大小；
2. 上游 `extensions/01_train_catdog_model/outputs/catdog_mobilenet_v2.onnx` **被就地改掉了**。
   如果你还想拿"原始未化简版"做对照实验，**先自己备份一份**。

> 本次实测已确认化简**没有破坏模型**：`onnx.checker.check_model()` 通过，
> 输入仍是 `input [1,3,224,224]`、输出仍是 `output [1,2]`、节点数 100。

---

## 第八部分：文件大小对照（第 58-59 行）

```python
print(f"float model size: {os.path.getsize(args.onnx)} bytes")
print(f"espdl model size: {espdl_path.stat().st_size} bytes")
```

| 写法 | 说明 |
|---|---|
| `os.path.getsize(路径)` | 取文件字节数（`os` 模块风格） |
| `路径.stat().st_size` | 同样是取文件字节数（`pathlib` 风格） |

**两种写法完全等价**，脚本故意各用一次，是为了展示"同一件事的两种写法"。

> 🔴 **重要提醒：文件变小 ≠ 模型变好。**
> 变小只证明"存储成本降低了"，**不能证明精度、延迟、内存占用、稳定性达标**。
> 想知道量化后准不准，必须**另外在同一个测试集上实测 Top-1 准确率**，
> 绝不能拿"体积缩小了 73%"去推断"精度只掉了 x%"。本脚本**不测精度**，这项数据属于拓展作业。

---

## 第九部分：程序入口（第 62-63 行）

```python
if __name__ == "__main__":
    main()
```

Python 的标准写法：**"只有直接运行这个文件时才执行 `main()`；如果别的文件 `import` 它，就不自动跑。"**
这样这个脚本既能当命令行工具用，也能被别的代码安全地引用。

---

## 总结：完整流程图

```
① 上游产物（扩展案例 1 生成）
   catdog_mobilenet_v2.onnx  (float32, 100 个算子)
   cats-dogs-data/train/{cat,dog}/  (各 100 张，共 200 张)
              │
              ▼
② 预处理流水线（必须与训练逐字一致）
   Resize(224,224) → ToTensor() → Normalize(ImageNet 均值/标准差)
              │
              ▼
③ ImageFolder 自动打标签 + 类别防呆
   classes == ['cat','dog'] ？ 不是就 raise ValueError
              │
              ▼
④ DataLoader(batch_size=8, shuffle=False, num_workers=0)
   200 ÷ 8 = 25 个 batch
              │
              ▼
⑤ collate_fn：丢掉标签，只留 (8,3,224,224) 图片张量
              │
              ▼
⑥ espdl_quantize_onnx()  ← 一站式黑盒，内部依次做：
   ├─ onnxsim 化简模型（⚠️ 会覆盖写回原 ONNX 文件）
   ├─ ConvTranspose 分解 / 量化融合 / 图化简
   ├─ 参数量化（权重量化成 INT8）
   ├─ 运行时校准 Phase 1（25 步）→ 统计每层数值范围，定 INT8 刻度
   ├─ 运行时校准 Phase 2（25 步）→ 两阶段观察者精修
   ├─ 量化对齐 / 被动参数量化
   ├─ error_report：逐层量化误差分析（Graphwise + Layerwise）
   └─ 导出 .espdl（target=esp32s3, INT8）
              │
              ▼
⑦ 产物 + 大小对照
   catdog_mobilenet_v2.espdl / .json / .info
   float model size: 8875417 bytes
   espdl  model size: 2373648 bytes
```

---

## 本次实测记录（2026-09-17，Windows）

### 环境

| 项 | 实测值 |
|---|---|
| 操作系统 | Windows（win32） |
| Python | 3.10.1 @ `C:\Users\user\AppData\Local\Python310\python.exe`（**本机没有 conda**，README 的 `conda activate esp32s3` 跳过即可） |
| esp-ppq | **1.2.10** |
| torch / torchvision | 2.14.0+cpu / 0.29.0+cpu（纯 CPU 版，无 CUDA） |
| onnx / onnxsim / onnxruntime | 1.17.0 / 0.4.36 / 1.23.2 |
| numpy / pillow | 2.2.6 / 12.3.0 |
| 内存 | 32 GB（运行时峰值约 1.5 GB） |

> 依赖**全部已就绪，无需重新安装**。唯一清理项：site-packages 里残留的 `~nnx`、`~nnx-1.22.0.dist-info`
> 两个坏目录（早前 onnx 安装被中断留下的），会让 pip 每次都打印
> `WARNING: Ignoring invalid distribution -nnx`。删掉即可，纯噪音、不影响功能。

### 命令

```powershell
cd extensions\02_quantize_catdog_model
python quantize_catdog.py `
  --onnx ../01_train_catdog_model/outputs/catdog_mobilenet_v2.onnx `
  --data-dir ../01_train_catdog_model/cats-dogs-data/train `
  --output-dir outputs
```

> ⚠️ README 原文写的 `--data-dir ../01_train_catdog_model/data/catdog` **在本仓库不存在**，
> 照抄会 `FileNotFoundError`。真实路径是 `cats-dogs-data/train`（扩展案例 1 的 README 第 112 行也是用这个）。

### 量化配置与结果

| 项 | 实测值 |
|---|---|
| target / num_of_bits | `esp32s3` / `8`（INT8） |
| input_shape | `[1, 3, 224, 224]`（与 ONNX 实测一致） |
| 校准集 | 200 张（cat 100 + dog 100），batch_size=8 → **calib_steps = min(32, 25) = 25** |
| 网络规模 | Op 100 个（**全部量化**）、Variable 277 个（**全部量化**） |
| 量化配置 | 386 条：ACTIVATED 108 / OVERLAPPED 125 / PASSIVE 153 |
| 耗时 | 约 **70 秒**（15:48:03 起，15:49:13 出 `.espdl`），远比 README 预估的"几分钟到几十分钟"快 |

### 脚本自己打印的两行（原文照抄）

```text
float model size: 8875417 bytes
espdl model size: 2373648 bytes
```

| 文件 | 字节数 | 说明 |
|---|---|---|
| `catdog_mobilenet_v2.onnx`（化简后） | 8,875,417 | float32 浮点模型 |
| `catdog_mobilenet_v2.espdl` | **2,373,648** | INT8 量化模型，**缩小到 26.74%，即压缩 3.74 倍 / 省了 73.26%** |
| `catdog_mobilenet_v2.json` | 298,367 | 量化参数（scale/exponent），顶层键 `configs` / `dispatchings` / `values` |
| `catdog_mobilenet_v2.info` | 14,277,859 | 量化误差报告（`error_report=True` 的产物，纯文本，很大属正常） |

> 产物有效性已校验：`.espdl` 文件头 magic 为 `EDL2`（ESP-DL v2 格式）✅；
> 化简后的 ONNX 通过 `onnx.checker.check_model()`，输入 `input[1,3,224,224]`、输出 `output[1,2]`、节点数 100，未被破坏 ✅。

### ⚠️ 未实测项（不要拿体积推断）

- **量化前后 Top-1 准确率对照：未实测。** 本脚本不测精度，`.espdl` 更小**不代表**精度损失可接受。
  要补这项数据，需按"拓展挑战"在同一测试集（`cats-dogs-data/valid`）上分别跑浮点与量化模型，用相同标签映射统计。
- **开发板上的实际推理延迟 / 内存占用：未实测**（本案例只在电脑上跑，不上板）。
- 另注：扩展案例 1 的 `metrics.csv` 显示 `val_accuracy` 三轮都是 `0.5`，即**上游模型本身还没学出区分能力**。
  量化只是"换表示法"，**不会把一个 50% 的模型变准**；上板前建议先回扩展 1 把模型训好。

---

## 常见报错速查表（含本次真实遇到的）

| 报错 / 现象 | 原因 | 解决办法 |
|---|---|---|
| 🔴 `RuntimeError: stack expects each tensor to be equal size, but got [3, 224, 224] at entry 0 and [] at entry 1` | **本次真实踩到**。`collate_fn` 以为 `batch` 是 8 个样本，实际是 `[图片张量, 标签张量]` 2 项 | 把 `collate_fn` 改成 `return batch[0]`（已修） |
| `FileNotFoundError: ... data\catdog` | README 里的路径在本仓库不存在 | 改用 `../01_train_catdog_model/cats-dogs-data/train` |
| `ModuleNotFoundError: No module named 'esp_ppq'` | 没装 ESP-PPQ | `python -m pip install esp-ppq==1.2.10` |
| `ValueError: expected classes ['cat', 'dog'], got [...]` | `--data-dir` 指错，或混入了 `__MACOSX`、大写 `Cat` 等多余子目录 | 指向 `cats-dogs-data/train`，清理多余目录 |
| `FileNotFoundError: ... catdog_mobilenet_v2.onnx` | 扩展 1 没跑完，或相对路径基准搞错 | 先完成扩展 1；确认已 `cd` 到 `02_quantize_catdog_model` 再运行 |
| shape 不匹配类报错 | `input_shape` 与 ONNX 实际输入不一致 | 保持 `[1, 3, 224, 224]`；扩展 1 改过尺寸要两边同步 |
| `WARNING: Ignoring invalid distribution -nnx` | site-packages 里有 `~nnx` 残留坏目录 | 无害，可删掉 `~nnx` 和 `~nnx-1.22.0.dist-info` |
| 量化非常慢、疑似卡死 | MobileNetV2 在 CPU 上量化本来就比小模型慢，日志多≠卡住 | 看日志是否仍在滚动；本次实测仅约 70 秒 |
| 内存不足 / 进程被杀 | 224×224 图片批量校准占内存 | 关掉其他大程序，`batch_size` 8→4，并记录改动 |
| 想后台跑又怕看不到进度 | Python 输出重定向到文件时是**块缓冲**，日志会半天不刷新 | 加 `-u` 参数：`python -u quantize_catdog.py ... > run.log 2>&1` |
| `.espdl` 生成了但上板识别异常 | 校准预处理与训练/端侧不一致 | 逐字核对三处 transform；需自检时改 `export_test_values=True` 重新量化 |

---

## 思考题（附本次实测能给出的答案）

**1. 为什么校准预处理必须和训练/端侧预处理一致？**
量化刻度（INT8 尺子）完全由"校准时看到的数值分布"决定。预处理不一致 → 校准范围与部署时对不上 →
刻度画错 → INT8 严重失真。最坑的是**它不报错**，只表现为上板后分类乱跳。

**2. 为什么不能从 `.espdl` 更小就判断模型更好？**
本次实测体积缩小 73.26%，但这**只说明存储成本降低**。精度、延迟、内存、稳定性都得单独实测。
极端情况下量化过度会让模型完全失效，而文件依然更小。

**3. 本脚本 `export_test_values=False`，想在板上用 `model->test()` 自检怎么办？**
改成 `True` 重新量化，把一组标准输入输出嵌进 `.espdl`。沿用 `False` 的产物**无法自检**。

**4.（本次新增）为什么 `float model size` 打出来的数字和扩展 1 刚导出时的不一样？**
因为 `espdl_quantize_onnx` 内部会跑 onnxsim 并**覆盖写回原 ONNX**
（`espdl_interface.py:216-218`）。本次从 8,878,502 变成 8,875,417 字节。要做原始版对照实验请先自行备份。




