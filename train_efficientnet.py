import argparse
import csv
import multiprocessing
import os
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import ConcatDataset, DataLoader, Sampler
from torchvision import models
from tqdm import tqdm

from rice_dataset import RiceGrainDataset

# Configuration
BASE_DIR = Path(__file__).resolve().parent
TRAIN_CSV = BASE_DIR / "full_manifests" / "train.csv"
VALID_CSV = BASE_DIR / "full_manifests" / "valid.csv"
MODEL_DIR = BASE_DIR / "models" / "version_1"
RESULT_DIR = BASE_DIR / "results" / "version_1"
BEST_MODEL = MODEL_DIR / "best_efficientnet_b0.pth"
HISTORY_FILE = RESULT_DIR / "training_history.csv"

BATCH_SIZE = 32
EPOCHS = 50
LEARNING_RATE = 0.0001
WEIGHT_DECAY = 0.0001
SEED = 42
NUM_CLASSES = 4
# Prepare training images with up to eight parallel workers.
NUM_WORKERS = min(8, os.cpu_count() or 1)
USE_AMP = True
CLASSES = ["broken_grain", "chalky_grain", "discolored_grain", "whole_grain"]


def seed_worker(worker_id):
    # PyTorch seeds each worker; seed the other random libraries too.
    worker_seed = torch.initial_seed() % (2 ** 32)
    np.random.seed(worker_seed)
    random.seed(worker_seed)


class PhaseSampler(Sampler):
    """Switch between shuffled training and ordered validation samples."""

    def __init__(self, train_size, valid_size, seed=SEED):
        self.train_size = train_size
        self.valid_size = valid_size
        self.generator = torch.Generator().manual_seed(seed)
        self.phase = "train"

    def set_phase(self, phase):
        if phase not in ("train", "valid"):
            raise ValueError("phase must be 'train' or 'valid'.")
        self.phase = phase

    def __iter__(self):
        if self.phase == "train":
            return iter(torch.randperm(self.train_size,
                                       generator=self.generator).tolist())
        return iter(range(self.train_size, self.train_size + self.valid_size))

    def __len__(self):
        return self.train_size if self.phase == "train" else self.valid_size


def create_data_loader(dataset, *, shuffle, num_workers=NUM_WORKERS,
                       batch_size=BATCH_SIZE, seed=SEED, sampler=None):
    if num_workers < 0:
        raise ValueError("num_workers must be zero or greater.")
    if sampler is not None and shuffle:
        raise ValueError("Use either shuffle or a sampler, not both.")
    options = {
        "batch_size": batch_size,
        "shuffle": shuffle,
        "sampler": sampler,
        "num_workers": num_workers,
        "pin_memory": True,
        "worker_init_fn": seed_worker,
        "generator": torch.Generator().manual_seed(seed),
    }
    if num_workers > 0:
        # Keep workers between epochs and prepare batches ahead of GPU work.
        options.update(persistent_workers=True, prefetch_factor=2)
    return DataLoader(dataset, **options)


def train_one_epoch(model, loader, criterion, optimizer, scaler, device):
    model.train()
    running_loss = torch.zeros((), device=device)
    correct = torch.zeros((), dtype=torch.int64, device=device)
    total = 0

    progress_bar = tqdm(loader, desc="Training", unit="batch",
                        dynamic_ncols=True, mininterval=0.5)
    for images, labels in progress_bar:
        images = images.to(device, non_blocking=True,
                           memory_format=torch.channels_last)
        labels = labels.to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)

        with torch.amp.autocast("cuda", enabled=USE_AMP):
            outputs = model(images)
            loss = criterion(outputs, labels)

        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()

        batch_size = labels.size(0)
        # Accumulate on the GPU instead of synchronizing it every batch.
        running_loss += loss.detach().float() * batch_size
        correct += (outputs.argmax(dim=1) == labels).sum()
        total += batch_size

    if total == 0:
        raise ValueError("The training loader has no samples.")
    return running_loss.item() / total, correct.item() / total


@torch.inference_mode()
def validate(model, loader, criterion, device):
    # Windows workers import this module; only the main process needs metrics.
    from sklearn.metrics import accuracy_score, f1_score

    model.eval()
    running_loss = torch.zeros((), device=device)
    correct = torch.zeros((), dtype=torch.int64, device=device)
    total = 0
    all_labels = []
    all_predictions = []

    progress_bar = tqdm(loader, desc="Validation", unit="batch",
                        dynamic_ncols=True, mininterval=0.5)
    for batch_idx, (images, labels) in enumerate(progress_bar, start=1):
        images = images.to(device, non_blocking=True,
                           memory_format=torch.channels_last)
        labels = labels.to(device, non_blocking=True)
        with torch.amp.autocast("cuda", enabled=USE_AMP):
            outputs = model(images)
            loss = criterion(outputs, labels)

        predictions = outputs.argmax(dim=1)
        batch_size = labels.size(0)
        running_loss += loss.float() * batch_size
        correct += (predictions == labels).sum()
        total += batch_size
        all_labels.append(labels)
        all_predictions.append(predictions)

        if batch_idx % 10 == 0 or batch_idx == len(loader):
            progress_bar.set_postfix(
                Loss=f"{running_loss.item() / total:.4f}",
                Acc=f"{correct.item() / total * 100:.2f}%",
                refresh=False,
            )

    if total == 0:
        raise ValueError("The validation loader has no samples.")
    # Transfer the small validation result arrays once per epoch.
    all_labels = torch.cat(all_labels).cpu().numpy()
    all_predictions = torch.cat(all_predictions).cpu().numpy()
    accuracy = accuracy_score(all_labels, all_predictions)
    macro_f1 = f1_score(all_labels, all_predictions,
                        labels=list(range(NUM_CLASSES)), average="macro",
                        zero_division=0)
    return running_loss.item() / total, accuracy, macro_f1


def main():
    parser = argparse.ArgumentParser(description="Train EfficientNet-B0 on rice grains.")
    parser.add_argument("--num-workers", type=int, default=NUM_WORKERS,
                        help="Parallel training image-loading workers (default: %(default)s; 0 disables multiprocessing).")
    args = parser.parse_args()
    if args.num_workers < 0:
        parser.error("--num-workers must be zero or greater.")

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable. Verify GPU support before starting full training.")

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    device = torch.device("cuda")
    # All grain crops are 224x224, so cuDNN can reuse tuned convolution kernels.
    # Autotuning favors speed; it does not guarantee bit-for-bit reproducibility.
    torch.backends.cudnn.benchmark = True

    print("Device:", device)
    print("GPU:", torch.cuda.get_device_name(0))
    print("PyTorch:", torch.__version__)
    print("Shared training/validation DataLoader workers:", args.num_workers)

    train_dataset = RiceGrainDataset(TRAIN_CSV, train=True)
    valid_dataset = RiceGrainDataset(VALID_CSV, train=False)
    if not len(train_dataset) or not len(valid_dataset):
        raise ValueError("Training and validation manifests must both contain samples.")
    # Both phases use one persistent pool, so validation can load in
    # parallel without keeping a second set of workers in memory.
    combined_dataset = ConcatDataset([train_dataset, valid_dataset])
    phase_sampler = PhaseSampler(len(train_dataset), len(valid_dataset))
    loader = create_data_loader(combined_dataset, shuffle=False,
                                num_workers=args.num_workers,
                                sampler=phase_sampler)

    print("\nDATASET")
    print("Training grains:", len(train_dataset))
    print("Validation grains:", len(valid_dataset))

    weights = models.EfficientNet_B0_Weights.IMAGENET1K_V1
    model = models.efficientnet_b0(weights=weights)
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, NUM_CLASSES)
    model = model.to(device, memory_format=torch.channels_last)

    print("\nMODEL")
    print("Architecture: EfficientNet-B0")
    print("Classes:", NUM_CLASSES)
    print("Features before classifier:", in_features)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE,
                                  weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="max", factor=0.5, patience=2)
    scaler = torch.amp.GradScaler("cuda", enabled=USE_AMP)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    best_f1 = -1.0
    best_epoch = 0
    history = []
    print("\nSTARTING FULL TRAINING")

    for epoch in range(1, EPOCHS + 1):
        print(f"\n{'=' * 50}\nEPOCH {epoch}/{EPOCHS}\n{'=' * 50}")
        phase_sampler.set_phase("train")
        train_loss, train_accuracy = train_one_epoch(
            model, loader, criterion, optimizer, scaler, device)
        phase_sampler.set_phase("valid")
        valid_loss, valid_accuracy, valid_f1 = validate(
            model, loader, criterion, device)
        scheduler.step(valid_f1)
        current_lr = optimizer.param_groups[0]["lr"]

        print("\nEPOCH RESULTS")
        print(f"Train Loss:      {train_loss:.4f}")
        print(f"Train Accuracy:  {train_accuracy * 100:.2f}%")
        print(f"Valid Loss:      {valid_loss:.4f}")
        print(f"Valid Accuracy:  {valid_accuracy * 100:.2f}%")
        print(f"Valid Macro F1:  {valid_f1 * 100:.2f}%")
        print(f"Learning Rate:   {current_lr:.6f}")

        history.append({
            "epoch": epoch,
            "train_loss": train_loss,
            "train_accuracy": train_accuracy,
            "valid_loss": valid_loss,
            "valid_accuracy": valid_accuracy,
            "valid_macro_f1": valid_f1,
            "learning_rate": current_lr,
        })
        with open(HISTORY_FILE, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=list(history[0].keys()))
            writer.writeheader()
            writer.writerows(history)

        if valid_f1 > best_f1:
            best_f1 = valid_f1
            best_epoch = epoch
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "best_valid_f1": best_f1,
                "classes": CLASSES,
                "architecture": "efficientnet_b0",
                "num_classes": NUM_CLASSES,
            }, BEST_MODEL)
            print("\nBest model saved!")

    print("\n" + "=" * 50)
    print("TRAINING COMPLETED")
    print("=" * 50)
    print(f"Total Epochs: {EPOCHS}")
    print(f"Best Epoch: {best_epoch}")
    print(f"Best Validation Macro F1: {best_f1 * 100:.2f}%")
    print("Best Model:", BEST_MODEL)
    print("Training History:", HISTORY_FILE)


# Windows starts workers by importing this module in each child process.
# Only the original process may initialize CUDA and start training.
if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
