
import argparse
from pathlib import Path

import torch
import torch.nn as nn
import matplotlib.pyplot as plt

from torch.utils.data import DataLoader
from torchvision import models
from tqdm import tqdm

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix,
    ConfusionMatrixDisplay
)

from rice_dataset import RiceGrainDataset


BASE_DIR = Path(__file__).resolve().parent

MODEL_PATH = (
    BASE_DIR / "models" / "version_1"
    / "best_efficientnet_b0.pth"
)


def main():

    parser = argparse.ArgumentParser(
        description="Evaluate trained RiceGrade EfficientNet-B0"
    )

    parser.add_argument(
        "--split",
        choices=["valid", "test"],
        default="valid"
    )

    parser.add_argument(
        "--batch",
        type=int,
        default=32
    )

    args = parser.parse_args()

    # ----------------------------------
    # 1. CONFIGURATION
    # ----------------------------------

    device = torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )

    output_dir = (
        BASE_DIR / "results" / "version_1"
        / f"cnn_{args.split}"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    print("Device:", device)
    print("Evaluation split:", args.split)

    # ----------------------------------
    # 2. LOAD BEST MODEL
    # ----------------------------------

    checkpoint = torch.load(
        MODEL_PATH,
        map_location="cpu",
        weights_only=True
    )

    classes = checkpoint["classes"]
    num_classes = len(classes)

    model = models.efficientnet_b0(
        weights=None
    )

    in_features = model.classifier[1].in_features

    model.classifier[1] = nn.Linear(
        in_features,
        num_classes
    )

    model.load_state_dict(
        checkpoint["model_state_dict"]
    )

    model = model.to(device)
    model.eval()

    print("Best Epoch:", checkpoint["epoch"])

    print(
        "Best Validation Macro F1:",
        f"{checkpoint['best_valid_f1'] * 100:.2f}%"
    )

    # ----------------------------------
    # 3. LOAD EVALUATION DATASET
    # ----------------------------------

    manifest = (
        BASE_DIR / "full_manifests"
        / f"{args.split}.csv"
    )

    dataset = RiceGrainDataset(
        manifest,
        train=False
    )

    loader = DataLoader(
        dataset,
        batch_size=args.batch,
        shuffle=False,
        num_workers=0,
        pin_memory=device.type == "cuda"
    )

    print("Total rice grains:", len(dataset))

    # ----------------------------------
    # 4. GENERATE PREDICTIONS
    # ----------------------------------

    actual = []
    predicted = []

    with torch.inference_mode():

        for images, labels in tqdm(
            loader,
            desc="Evaluating",
            unit="batch"
        ):

            images = images.to(device)

            outputs = model(images)

            predictions = outputs.argmax(dim=1)

            actual.extend(
                labels.numpy().tolist()
            )

            predicted.extend(
                predictions.cpu().numpy().tolist()
            )

    # ----------------------------------
    # 5. CALCULATE METRICS
    # ----------------------------------

    labels = list(range(num_classes))

    accuracy = accuracy_score(
        actual, predicted
    )

    precision = precision_score(
        actual, predicted,
        labels=labels,
        average="macro",
        zero_division=0
    )

    recall = recall_score(
        actual, predicted,
        labels=labels,
        average="macro",
        zero_division=0
    )

    macro_f1 = f1_score(
        actual, predicted,
        labels=labels,
        average="macro",
        zero_division=0
    )

    report = classification_report(
        actual,
        predicted,
        labels=labels,
        target_names=classes,
        zero_division=0
    )

    print("\nEFFICIENTNET-B0 EVALUATION")
    print("=" * 45)

    print(f"Accuracy:        {accuracy * 100:.2f}%")
    print(f"Macro Precision: {precision * 100:.2f}%")
    print(f"Macro Recall:    {recall * 100:.2f}%")
    print(f"Macro F1:        {macro_f1 * 100:.2f}%")

    print("\nCLASSIFICATION REPORT")
    print(report)

    # ----------------------------------
    # 6. SAVE CLASSIFICATION REPORT
    # ----------------------------------

    report_file = (
        output_dir / "classification_report.txt"
    )

    with open(report_file, "w", encoding="utf-8") as f:

        f.write("EfficientNet-B0 Evaluation\n\n")
        f.write(f"Split: {args.split}\n")
        f.write(f"Best Training Epoch: {checkpoint['epoch']}\n\n")
        f.write(f"Accuracy: {accuracy:.6f}\n")
        f.write(f"Macro Precision: {precision:.6f}\n")
        f.write(f"Macro Recall: {recall:.6f}\n")
        f.write(f"Macro F1: {macro_f1:.6f}\n\n")
        f.write(report)

    # ----------------------------------
    # 7. CONFUSION MATRIX
    # ----------------------------------

    cm = confusion_matrix(
        actual,
        predicted,
        labels=labels
    )

    display = ConfusionMatrixDisplay(
        confusion_matrix=cm,
        display_labels=classes
    )

    fig, ax = plt.subplots(
        figsize=(10, 8)
    )

    display.plot(
        ax=ax,
        cmap="Blues",
        values_format="d",
        xticks_rotation=30,
        colorbar=False
    )

    ax.set_title(
        f"EfficientNet-B0 {args.split.title()} Confusion Matrix"
    )

    fig.tight_layout()

    fig.savefig(
        output_dir / "confusion_matrix.png",
        dpi=200
    )

    plt.close(fig)

    print("\nEvaluation completed!")
    print("Results saved to:", output_dir)


if __name__ == "__main__":
    main()
