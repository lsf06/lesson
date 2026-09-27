"""扩展案例 2 附加验证：用真实猫狗图片对量化源浮点 ONNX 逐张推理。

用途：
    quantize_catdog.py 只对照量化前后的文件大小，不看分类行为。
    本脚本用 onnxruntime 加载浮点 ONNX（即量化源模型，已被 onnxsim 简化过，
    网络结构与量化前一致），按与训练逐字一致的预处理对 train / valid 的
    cat、dog 图片逐张推理，给出"真实标签 vs 预测标签 + 置信度"，
    并把结果写入 outputs/verify_report.md。

说明：
    - 这里验证的是**浮点 ONNX** 的分类行为；INT8 的 `.espdl` 供 ESP-DL 在
      开发板端加载运行，本脚本不在电脑上模拟 INT8 数值。
    - 类别顺序与 ImageFolder / labels.txt 一致：0=cat，1=dog。

用法示例：
    python verify_cat_images.py ^
        --onnx ..\\01_train_catdog_model\\outputs\\catdog_mobilenet_v2.onnx ^
        --data-dir ..\\01_train_catdog_model\\cats-dogs-data\\train ^
        --valid-dir ..\\01_train_catdog_model\\cats-dogs-data\\valid
"""

import argparse
import hashlib
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image
from torchvision import transforms

CLASS_NAMES = ["cat", "dog"]
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".bmp")


def build_transform():
    """与扩展案例 1 训练时逐字一致的预处理，一个字符都不能改。"""
    return transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


def list_images(folder: Path, max_count: int):
    """按文件名排序列出目录中的图片（与 ImageFolder 的读取顺序一致）。"""
    files = sorted(f for f in folder.iterdir()
                   if f.is_file() and f.suffix.lower() in IMAGE_SUFFIXES)
    if max_count > 0:
        files = files[:max_count]
    return files


def softmax(logits: np.ndarray) -> np.ndarray:
    """把 logits 变成概率：先减最大值防溢出，再 exp 归一化。"""
    shifted = logits - logits.max(axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=-1, keepdims=True)


def evaluate_split(session, input_name, transform, split_dir: Path, max_per_class: int):
    """对 split_dir 下 cat/ dog/ 的全部图片逐张推理。

    返回行列表，每行：(类别目录名, 文件名, 真实类别下标, 预测类别下标, 置信度)。
    """
    rows = []
    for true_idx, cls in enumerate(CLASS_NAMES):
        folder = split_dir / cls
        if not folder.is_dir():
            raise ValueError(f"missing class folder: {folder}")
        for path in list_images(folder, max_per_class):
            image = Image.open(path).convert("RGB")
            tensor = transform(image).unsqueeze(0).numpy()  # (1,3,224,224) float32
            logits = session.run(None, {input_name: tensor})[0]
            probs = softmax(logits.astype(np.float64))[0]
            pred_idx = int(probs.argmax())
            rows.append((cls, path.name, true_idx, pred_idx, float(probs[pred_idx])))
    return rows


def summarize(rows):
    """统计混淆计数 stats[真实类][预测类] 与每类置信度列表。"""
    stats = {t: {p: 0 for p in CLASS_NAMES} for t in CLASS_NAMES}
    conf = {t: [] for t in CLASS_NAMES}
    for _cls, _name, true_idx, pred_idx, confidence in rows:
        stats[CLASS_NAMES[true_idx]][CLASS_NAMES[pred_idx]] += 1
        conf[CLASS_NAMES[true_idx]].append(confidence)
    return stats, conf


def main():
    parser = argparse.ArgumentParser(description="猫狗图片推理验证（浮点 ONNX）")
    parser.add_argument("--onnx", required=True)
    parser.add_argument("--data-dir", required=True, help="训练集目录（含 cat/ dog/ 子目录）")
    parser.add_argument("--valid-dir", default=None, help="留出验证集目录（含 cat/ dog/ 子目录）")
    parser.add_argument("--max-per-class", type=int, default=0, help="每类最多测几张，0 表示全部")
    parser.add_argument("--report", default="outputs/verify_report.md")
    args = parser.parse_args()

    transform = build_transform()
    session = ort.InferenceSession(args.onnx, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name

    onnx_bytes = Path(args.onnx).read_bytes()
    onnx_sha = hashlib.sha256(onnx_bytes).hexdigest()

    splits = [("train", Path(args.data_dir))]
    if args.valid_dir:
        splits.append(("valid", Path(args.valid_dir)))

    started = time.time()
    all_rows = {}
    for split_name, split_dir in splits:
        all_rows[split_name] = evaluate_split(
            session, input_name, transform, split_dir, args.max_per_class)
        print(f"[{split_name}] evaluated {len(all_rows[split_name])} images")
    elapsed = time.time() - started

    lines = []
    lines.append("# 猫狗图片推理验证报告（浮点 ONNX）")
    lines.append("")
    lines.append(f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 被测模型：`{args.onnx}`（SHA256 `{onnx_sha}`，{len(onnx_bytes)} bytes）")
    lines.append(f"- 推理引擎：onnxruntime {ort.__version__}（CPUExecutionProvider）")
    lines.append("- 预处理：Resize(224,224) → ToTensor → Normalize(ImageNet 均值/标准差)，与训练逐字一致")
    lines.append("- 类别顺序：0=cat，1=dog（ImageFolder / labels.txt 约定）")
    lines.append(f"- 评估图片总数：{sum(len(r) for r in all_rows.values())}，耗时 {elapsed:.1f} s")
    lines.append("")
    lines.append("> 说明：本报告验证的是**浮点 ONNX（量化源模型）**的分类行为；")
    lines.append("> INT8 `.espdl` 由 ESP-DL 在开发板端加载运行，本报告不在电脑上模拟 INT8 数值。")
    lines.append("")
    for split_name, _split_dir in splits:
        rows = all_rows[split_name]
        stats, conf = summarize(rows)
        lines.append(f"## {split_name} 集结果")
        lines.append("")
        lines.append("| 真实 \\ 预测 | 预测 cat | 预测 dog | 准确率 |")
        lines.append("|---|---|---|---|")
        for t in CLASS_NAMES:
            total = sum(stats[t].values())
            acc = stats[t][t] / total if total else float("nan")
            lines.append(f"| 真实 {t} | {stats[t]['cat']} | {stats[t]['dog']} | {acc:.2%} |")
        correct_all = sum(stats[t][t] for t in CLASS_NAMES)
        total_all = len(rows)
        lines.append("")
        lines.append(f"总体准确率：{correct_all}/{total_all} = {correct_all / total_all:.2%}")
        lines.append("")
        for t in CLASS_NAMES:
            if conf[t]:
                lines.append(f"- 真实 {t} 图片的平均置信度：{np.mean(conf[t]):.3f}")
        lines.append("")
    train_rows = all_rows.get("train", [])
    cat_rows = [r for r in train_rows if r[2] == 0][:20]
    if cat_rows:
        lines.append("## 训练集前 20 张猫图片逐张明细")
        lines.append("")
        lines.append("| 文件 | 真实 | 预测 | 置信度 |")
        lines.append("|---|---|---|---|")
        for _cls, name, true_idx, pred_idx, confidence in cat_rows:
            lines.append(f"| {name} | {CLASS_NAMES[true_idx]} | {CLASS_NAMES[pred_idx]} | {confidence:.3f} |")
        lines.append("")

    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"report written: {report}")

    for split_name, _split_dir in splits:
        stats, _conf = summarize(all_rows[split_name])
        for t in CLASS_NAMES:
            total = sum(stats[t].values())
            if total:
                print(f"{split_name} true-{t}: {stats[t][t]}/{total} correct ({stats[t][t] / total:.2%})")


if __name__ == "__main__":
    main()
