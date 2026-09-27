# ⚠️ 这个目录是“有意裁剪”过的

本目录**不是**完整的 Cats & Dogs 数据集，只有两张图：

```
cats-dogs-data/
└─ valid/
   ├─ cat/cat.1001.jpg     23 099 B  sha256 b32166fe…
   └─ dog/dog.1001.jpg     24 211 B  sha256 ff581e37…
```

## 为什么只留两张

`extensions/_tools/sdcard_seed/main/CMakeLists.txt` 会在**编译期**把这两张图作为
`EMBED_FILES` 嵌进播种工具固件，编译成 `sample.jpg` / `dog.jpg` 写进 SD 卡：

| CMake 里硬编码的源路径（必须先存在，否则配置阶段直接 `FATAL ERROR`） | 卡上路径 |
|---|---|
| `cats-dogs-data/valid/cat/cat.1001.jpg` | `/sdcard/images/sample.jpg` |
| `cats-dogs-data/valid/dog/dog.1001.jpg` | `/sdcard/images/dog.jpg` |

所以为了“换电脑后播种工具还能编译”，这两张图必须原样保留在这两个路径下。
`extras/card-images/{sample.jpg,dog.jpg}` 是同样两张图的副本（哈希相同），
方便用读卡器直接往卡里拷贝。

## 怎么恢复完整数据集

```powershell
cd C:\esp\lesson\wei\extensions\01_train_catdog_model
python prepare_data.py            # 合成数据：240 张，只需 pillow + numpy，不联网
```

合成数据会写入本目录下的 `train/{cat,dog}`、`valid/{cat,dog}`，与上面两张真实图共存。
`torchvision.datasets.ImageFolder` 会把它们一起读进去（每个类别 100+1 张训练图、20+1 张验证图）——
因此**用合成数据重训得到的模型与随包的 `catdog_mobilenet_v2.espdl` 不是同一份**，
`metrics.csv`、`train_log.txt` 里的准确率也对不上。

真实数据集（Kaggle Dogs vs. Cats subset，1000 类×2、共 2400 张）的下载方式见
`extensions/01_train_catdog_model/README.md`。

## 与报告的关系

`docs/catdog-run-report.md` 里 `sample.jpg` 的来源标注（`valid/cat/cat.1001.jpg` ← **猫图**）
依赖这两个文件，裁剪后依然成立：板端 `top1=dog score=0.626124` 就是**这张猫图被误判**的实测记录
（模型只训了 3 epoch，`val_accuracy` ≈ 0.61，属模型能力问题，不是程序问题）。