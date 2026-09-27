"""扩展案例 2：将猫狗 ONNX 分类模型量化为 ESPDL。"""

import argparse
import os
from pathlib import Path

import torch
from esp_ppq.api import espdl_quantize_onnx
from torch.utils.data import DataLoader
from torchvision import datasets, transforms


def collate_fn(batch):
    """校准只需要图片张量，把标签丢掉。

    注意：esp-ppq 传进来的 batch 是 DataLoader **已经自动拼好的一批**，
    默认 collate 下它是长度为 2 的列表 [images(8,3,224,224), labels(8,)]，
    而不是 8 个 (image, label) 样本元组，所以直接取第 0 项即可。
    （写成 torch.stack([s[0] for s in batch]) 会分别取到 images[0] 的
    (3,224,224) 和 labels[0] 的标量 ()，导致 stack 尺寸不一致而报错。）
    """
    return batch[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--onnx", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--output-dir", default="outputs")
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    dataset = datasets.ImageFolder(args.data_dir, transform=transform)
    if dataset.classes != ["cat", "dog"]:
        raise ValueError(f"expected classes ['cat', 'dog'], got {dataset.classes}")
    loader = DataLoader(dataset, batch_size=8, shuffle=False, num_workers=0)
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
    print(f"float model size: {os.path.getsize(args.onnx)} bytes")
    print(f"espdl model size: {espdl_path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
