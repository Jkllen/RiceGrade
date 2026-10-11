
import torch

from pathlib import Path
from torch.utils.data import DataLoader

from rice_dataset import RiceGrainDataset


BASE_DIR = Path(__file__).resolve().parent

TRAIN_CSV = BASE_DIR / "full_manifests" / "train.csv"
VALID_CSV = BASE_DIR / "full_manifests" / "valid.csv"

BATCH_SIZE = 16

# Create datasets
train_dataset = RiceGrainDataset(
    TRAIN_CSV,
    train=True
)

valid_dataset = RiceGrainDataset(
    VALID_CSV,
    train=False
)

# Create DataLoaders
train_loader = DataLoader(
    train_dataset,
    batch_size=BATCH_SIZE,
    shuffle=True,
    num_workers=0,
    pin_memory=torch.cuda.is_available()
)

valid_loader = DataLoader(
    valid_dataset,
    batch_size=BATCH_SIZE,
    shuffle=False,
    num_workers=0,
    pin_memory=torch.cuda.is_available()
)

print("\nDATASET SUMMARY")
print("Training grains:", len(train_dataset))
print("Validation grains:", len(valid_dataset))

# Test one training batch
images, labels = next(iter(train_loader))

print("\nBATCH VERIFICATION")
print("Image batch:", images.shape)
print("Label batch:", labels.shape)
print("Image dtype:", images.dtype)
print("Label range:", labels.min().item(),
      "to", labels.max().item())

print("\nGPU VERIFICATION")
print("CUDA Available:", torch.cuda.is_available())

if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))

print("\nDATALOADER CHECK COMPLETED!")
