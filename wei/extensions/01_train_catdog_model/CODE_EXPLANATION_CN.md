# train_catdog.py 小白也能看懂的超详细讲解

> 本文档面向**完全没有机器学习基础的小白**，逐段拆解 `train_catdog.py` 的每一部分在做什么、为什么这样做。

---

## 整体概念：这个脚本在干什么？

想象你教一个小朋友区分猫和狗——你拿一堆猫的照片说"这是猫"，再拿一堆狗的照片说"这是狗"，
小朋友看多了就学会了。这个脚本做的事情完全一样，只不过把"小朋友"换成了**电脑里的神经网络模型**。

整个流程可以概括为 **5 步**：

```
 猫狗图片  →  喂给模型  →  模型猜测  →  算分（对/错）→  模型改进
   (数据)      (训练)       (推理)       (损失函数)     (反向传播)
```

每跑完一轮，模型就比上一轮更"聪明"一点。跑 3 轮后，模型就能以一定的准确率区分猫狗了。

---

## 第一部分：导入库（第 1-22 行）

```python
import argparse
import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch
from torch import nn, optim
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms
```

### 每个库的作用（大白话）

| 库名 | 它是干嘛的 |
|------|-----------|
| `argparse` | 让你在命令行敲 `--epochs 3` 这样的参数来配置脚本，不用改代码 |
| `csv` | 把训练结果写到 Excel 能打开的 `.csv` 表格文件里 |
| `pathlib.Path` | 处理文件路径，创建目录等，比手动拼字符串 `/` 更安全 |
| `matplotlib` | 画图用的——这里用来画 loss 曲线图 |
| `torch` (PyTorch) | **核心**：Facebook 出的深度学习框架，整个神经网络的计算全靠它 |
| `torch.nn` | 神经网络的"积木块"——各种层、损失函数都在这里 |
| `torch.optim` | 优化器——模型"学习"靠的就是它来调整参数 |
| `DataLoader` | 数据搬运工——把图片一批一批地喂给模型 |
| `torchvision` | PyTorch 的视觉工具包——读取图片、图片预处理、现成的模型都在这里 |

> `matplotlib.use("Agg")` 的意思是：用"非交互模式"画图，画完直接保存成 PNG，不弹出窗口。服务器没有屏幕，必须这样设置。

---

## 第二部分：评估函数 evaluate()（第 25-36 行）

```python
def evaluate(model, loader, criterion, device):
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            logits = model(images)
            total_loss += criterion(logits, labels).item() * labels.size(0)
            correct += (logits.argmax(1) == labels).sum().item()
            total += labels.size(0)
    return total_loss / total, correct / total
```

| 代码 | 大白话 |
|------|--------|
| `model.eval()` | "模型，进入考试模式！"——关掉训练专用功能（如 Dropout），只做推理 |
| `total_loss / correct / total` | 三个计数器：累计错误量 / 猜对次数 / 总图片数 |
| `with torch.no_grad():` | "不用记笔记！"——推理时不计算梯度，省内存、加速 |
| `logits = model(images)` | 把图片扔进模型，得到两个分数（猫分数、狗分数） |
| `criterion(logits, labels)` | 计算"模型猜测"和"正确答案"的差距（交叉熵损失） |
| `logits.argmax(1) == labels` | 取分数高的那个类别，看是否等于正确答案 |

> `logits`（发音 lo-jits）= 模型输出的原始分数，如 `[3.2, -1.5]` 表示模型觉得更像猫（分数大=猫）。`argmax(1)` 取最大值索引——`3.2` 最大，索引 `0`，对应 `cat`。
---

## 第三部分：主函数参数解析（第 39-59 行）

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `--data-dir` | 必填 | 训练图片在哪个文件夹 |
| `--valid-data-dir` | None | 验证图片在哪个文件夹（必须指定） |
| `--output-dir` | `outputs` | 产物（模型、图表）保存到哪里 |
| `--epochs` | 3 | 把全部数据看几遍——3 遍就是 3 轮 |
| `--batch-size` | 16 | 一次喂给模型多少张图——16 张一批 |
| `--seed` | 42 | 随机种子——固定后每次结果一样，方便复现 |

> **Epoch vs Batch**：epoch = "把全部数据看一遍"，batch = "一口吃多少张图"。200 张图、batch=16，一个 epoch 要吃 200/16≈13 口。

---

## 第四部分：选择设备（第 61-62 行）

```python
torch.manual_seed(args.seed)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
```

- `torch.manual_seed(42)`：锁死随机数——同样 seed 永远得到同样结果
- `"cuda" if ... else "cpu"`："有 NVIDIA 显卡吗？有就用 GPU，没有用 CPU"——GPU 快几十倍

---

## 第五部分：图像预处理 transform——最关键的坑（第 68-72 行）

```python
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])
```

| 步骤 | 作用 | 大白话 |
|------|------|--------|
| `Resize((224,224))` | 统一缩放 | 模型只认 224×224，就像自动门只认标准身高 |
| `ToTensor()` | 格式转换 | 像素值 0~255 → 0.0~1.0 小数，方便计算 |
| `Normalize(mean, std)` | 标准化 | (像素值-均值)/标准差 → 标准正态分布 |

> **为什么要用 ImageNet 的统计值？** MobileNetV2 在 ImageNet 上验证，用同一套参数最安全。**训练和部署时必须完全一致，否则模型"不认识"图片。**

---

## 第六部分：ImageFolder 加载数据（第 74-91 行）

`ImageFolder` 是 PyTorch 的魔法：**自动把子目录名当类别名**，按字母序编号（cat=0, dog=1）。

```
cats-dogs-data/
├── train/
│   ├── cat/    ← 自动标签=0
│   └── dog/    ← 自动标签=1
└── valid/
    ├── cat/
    └── dog/
```

`dataset.classes == ["cat", "dog"]` 检查是**安全锁**——目录名错了（如 cats/dogs）会直接报错，防止编号混乱的"无声 bug"。

---

## 第七部分：DataLoader——数据传送带（第 93-98 行）

```python
train_loader = DataLoader(train_set, batch_size=16, shuffle=True, num_workers=0)
val_loader = DataLoader(val_set, batch_size=16, shuffle=False, num_workers=0)
```

| 参数 | 训练 | 验证 | 原因 |
|------|------|------|------|
| `shuffle` | True | False | 训练打乱防"记顺序"，验证无所谓 |
| `num_workers` | 0 | 0 | Windows 设 0 最稳 |
---

## 第八部分：创建模型——MobileNetV2 + 换头（第 100-103 行）

```python
model = models.mobilenet_v2(weights=None)
model.classifier[1] = nn.Linear(model.last_channel, 2)
model.to(device)
```

| 代码 | 大白话 |
|------|--------|
| `mobilenet_v2(weights=None)` | 拿 MobileNetV2 骨架。`weights=None`="从零开始学" |
| `.classifier[1] = nn.Linear(..., 2)` | **最关键的一行！** 原模型 1000 类 → 换成 2 类（猫/狗） |

> **什么是 MobileNetV2？** Google 设计给手机/嵌入式的轻量 CNN。用"深度可分离卷积"把计算量降到传统 CNN 的 1/8，350 万参数却有不错的准确率，非常适合 ESP32。

> **为什么换分类头？** 把模型理解为"眼睛"（提取特征）+ "嘴巴"（说出类别）。保留眼睛，只换嘴巴——从说 1000 种变成只说"猫/狗"。

---

## 第九部分：损失函数 + 优化器（第 105-106 行）

```python
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters(), lr=1e-4)
```

| 概念 | 大白话 |
|------|--------|
| `CrossEntropyLoss` | **打分标准**：模型输出猫=0.7 狗=0.3，正确答案是猫，算出"不满意分数" |
| `Adam(lr=1e-4)` | **模型的老师**：根据损失反馈调整参数。lr=学习率=每次调多大步 |

> 学习率 = 学骑车时调整身体的幅度。太小：半天学不会；太大：左右乱晃摔倒。

---

## 第十部分：训练循环——脚本的心脏（第 108-131 行）

每一批图片进来，执行 **5 个标准动作**：

```
① zero_grad()      "擦干净上次的计算草稿纸"
     ↓
② forward + loss   "让模型猜，然后打分"
     ↓
③ backward()       "反推：每个零件对错误负多大责任"（反向传播）
     ↓
④ step()           "真正调整零件，变聪明了一点点"
     ↓
⑤ evaluate()       "拿没见过的新图考试，看是否真学会了"
```

| 代码 | 大白话 |
|------|--------|
| `model.train()` | 进入"学习模式"，开启 Dropout 等训练机制 |
| `optimizer.zero_grad()` | 清空上一轮的梯度，不擦会累加 |
| `loss.backward()` | 反向传播——自动算每个参数该调多少 |
| `optimizer.step()` | 真正调整参数，让下次猜得更准 |

---

## 第十一部分：保存 5 个产物（第 133-149 行）

| 文件 | 内容 | 用途 |
|------|------|------|
| `catdog_mobilenet_v2.pth` | 模型"大脑"——所有训练好的参数 | 下次直接用 |
| `labels.txt` | 两行：cat / dog | 告诉部署端：输出0=猫，1=狗 |
| `metrics.csv` | 每轮 loss 和准确率表格 | Excel 打开看过程 |
| `loss_curve.png` | 训练/验证 loss 曲线图 | 一眼看出过拟合 |
| `catdog_mobilenet_v2.onnx` | ONNX 通用格式模型 | 下一步做量化 |

---

## 第十二部分：导出 ONNX（第 151-157 行）

```python
model.eval()
dummy = torch.randn(1, 3, 224, 224)
torch.onnx.export(model.cpu(), dummy, "catdog_mobilenet_v2.onnx",
    opset_version=12, input_names=["input"], output_names=["output"], dynamo=False)
```

| 代码 | 大白话 |
|------|--------|
| `dummy = torch.randn(1,3,224,224)` | 生成一张假图片——ONNX 需要一个示例来追踪模型结构 |
| `torch.onnx.export(...)` | 把 PyTorch 模型翻译成 ONNX 通用格式 |
| `opset_version=12` | v12 算子集——ESP32 推理引擎支持 |
| `input_names=["input"]` | 部署端用 `input` 这个名字喂图片 |
| `output_names=["output"]` | 部署端用 `output` 这个名字取分数 |

> **为什么需要 ONNX？** ESP32 没有 PyTorch。ONNX 是"中间语言"，可被转换成 ESP32 能跑的格式。下一个案例 `02_quantize_catdog_model` 会对 ONNX 做量化压缩。

---

## 总结：完整流程图

```
 ① 准备数据                    ② 创建模型
 cats-dogs-data/              MobileNetV2
 train/{cat,dog}/         ──→  classifier → 2类
 valid/{cat,dog}/
      │                           │
      ▼                           ▼
 ③ 预处理                      ④ 训练 3 轮
 Resize(224,224)              每轮: 前向→算loss→反向→更新参数
 ToTensor()                         ↓
 Normalize(...)                验证: 算准确率
      │                           │
      └──────────┬────────────────┘
                 ▼
         ⑤ 保存 5 个产物
      .pth / .onnx / labels.txt
      metrics.csv / loss_curve.png
```

## 常见问题

**Q: 为什么 val_acc 只有 0.5？**  
A: 合成数据（随机噪声）时模型不可能学到规律，0.5=瞎猜（二分类 50%）。真实猫狗图片可达 90%+。

**Q: 训练 loss 降但 val_loss 涨？**  
A: "过拟合"——模型背下了训练数据，遇到新图就懵。解法：更多数据、预训练权重、Dropout。

**Q: CPU 太慢怎么办？**  
A: MobileNetV2 350 万参数，CPU 上 200 张图 3 轮可能要几分钟。有 GPU 自动加速 10-50 倍。