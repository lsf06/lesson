"""Create a small synthetic cat/dog ImageFolder dataset for quick pipeline testing.

Generates random colored images (not real cats/dogs, just verifying the pipeline works).
Each image is 224x224 RGB JPEG.
"""
import os, random
from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "cats-dogs-data"

# Skip if already done
if (DATA_DIR / "train" / "cat").exists() and (DATA_DIR / "train" / "dog").exists():
    import sys
    d = DATA_DIR
    print(f"Data already exists at {d}")
    for s in ["train", "valid"]:
        for c in ["cat", "dog"]:
            n = len(list((d / s / c).glob("*.jpg")))
            print(f"  {s}/{c}: {n} images")
    sys.exit(0)

random.seed(42)
np.random.seed(42)

# Small counts for fast pipeline test
N_TRAIN_PER_CLASS = 100
N_VALID_PER_CLASS = 20

def make_image(color_bias):
    """Generate a random 224x224 RGB image with a bias toward red(dog) or blue(cat)."""
    arr = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)
    # cat: bias toward blue/green channel
    # dog: bias toward red channel
    arr[:, :, color_bias] = np.clip(arr[:, :, color_bias].astype(int) + 80, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)

for sub, n in [("train", N_TRAIN_PER_CLASS), ("valid", N_VALID_PER_CLASS)]:
    for cls, bias in [("cat", 2), ("dog", 0)]:  # cat=blue bias(ch2), dog=red bias(ch0)
        d = DATA_DIR / sub / cls
        d.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            img = make_image(bias)
            img.save(d / f"{cls}_{i:04d}.jpg", quality=85)

print("Synthetic dataset created:")
for s in ["train", "valid"]:
    for c in ["cat", "dog"]:
        n = len(list((DATA_DIR / s / c).glob("*.jpg")))
        print(f"  {s}/{c}: {n} images")