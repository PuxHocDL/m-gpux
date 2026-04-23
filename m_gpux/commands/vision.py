import os
import re
from datetime import datetime
from pathlib import Path
from pprint import pformat
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, FloatPrompt, IntPrompt, Prompt
from rich.table import Table

from m_gpux.commands._ui import arrow_select
from m_gpux.commands.hub import (
    AVAILABLE_GPUS,
    _activate_profile,
    _select_profile,
    execute_modal_temp_script,
)

app = typer.Typer(
    help="Train computer vision models on Modal GPUs with local datasets.",
    short_help="Vision Training",
    no_args_is_help=True,
)
console = Console()

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".gif",
    ".webp",
    ".tif",
    ".tiff",
}

DEFAULT_DATASET_IGNORES = ["__pycache__", ".DS_Store", "Thumbs.db"]
DEFAULT_ARTIFACT_VOLUME = "m-gpux-vision-artifacts"

MODEL_CATALOG = [
    {
        "name": "resnet18",
        "description": "Fast baseline, excellent first run",
        "image_size": 224,
        "batch_size": 64,
    },
    {
        "name": "resnet34",
        "description": "Stronger ResNet baseline with modest cost",
        "image_size": 224,
        "batch_size": 48,
    },
    {
        "name": "resnet50",
        "description": "Classic production backbone",
        "image_size": 224,
        "batch_size": 32,
    },
    {
        "name": "resnet101",
        "description": "Deeper ResNet for higher accuracy",
        "image_size": 224,
        "batch_size": 24,
    },
    {
        "name": "wide_resnet50_2",
        "description": "Wide ResNet with strong accuracy",
        "image_size": 224,
        "batch_size": 24,
    },
    {
        "name": "resnext50_32x4d",
        "description": "ResNeXt variant with good accuracy-speed balance",
        "image_size": 224,
        "batch_size": 24,
    },
    {
        "name": "convnext_tiny",
        "description": "Modern ConvNet, strong general-purpose choice",
        "image_size": 224,
        "batch_size": 32,
    },
    {
        "name": "convnext_small",
        "description": "Higher capacity ConvNeXt variant",
        "image_size": 224,
        "batch_size": 24,
    },
    {
        "name": "convnext_base",
        "description": "Large ConvNeXt backbone for stronger accuracy",
        "image_size": 224,
        "batch_size": 16,
    },
    {
        "name": "efficientnet_b0",
        "description": "Very efficient baseline for small/medium datasets",
        "image_size": 224,
        "batch_size": 48,
    },
    {
        "name": "efficientnet_b1",
        "description": "Slightly stronger EfficientNet",
        "image_size": 240,
        "batch_size": 40,
    },
    {
        "name": "efficientnet_b2",
        "description": "EfficientNet with more capacity",
        "image_size": 260,
        "batch_size": 32,
    },
    {
        "name": "efficientnet_b3",
        "description": "Common upgrade from ResNet50",
        "image_size": 300,
        "batch_size": 24,
    },
    {
        "name": "efficientnet_v2_s",
        "description": "EfficientNetV2 small, fast and accurate",
        "image_size": 300,
        "batch_size": 24,
    },
    {
        "name": "efficientnet_v2_m",
        "description": "EfficientNetV2 medium for stronger accuracy",
        "image_size": 384,
        "batch_size": 12,
    },
    {
        "name": "mobilenet_v2",
        "description": "Mobile-friendly and very lightweight",
        "image_size": 224,
        "batch_size": 64,
    },
    {
        "name": "mobilenet_v3_small",
        "description": "Very fast small-footprint model",
        "image_size": 224,
        "batch_size": 64,
    },
    {
        "name": "mobilenet_v3_large",
        "description": "Larger MobileNetV3 variant",
        "image_size": 224,
        "batch_size": 56,
    },
    {
        "name": "densenet121",
        "description": "DenseNet baseline with good feature reuse",
        "image_size": 224,
        "batch_size": 32,
    },
    {
        "name": "densenet169",
        "description": "Larger DenseNet with improved accuracy",
        "image_size": 224,
        "batch_size": 24,
    },
    {
        "name": "regnet_y_8gf",
        "description": "High-throughput RegNet for classification",
        "image_size": 224,
        "batch_size": 24,
    },
    {
        "name": "shufflenet_v2_x1_0",
        "description": "Lightweight model for fast iteration",
        "image_size": 224,
        "batch_size": 64,
    },
    {
        "name": "vit_b_16",
        "description": "Vision Transformer base",
        "image_size": 224,
        "batch_size": 16,
    },
    {
        "name": "vit_b_32",
        "description": "Vision Transformer with larger patch size",
        "image_size": 224,
        "batch_size": 20,
    },
    {
        "name": "vit_l_16",
        "description": "Large Vision Transformer for high-end GPUs",
        "image_size": 224,
        "batch_size": 8,
    },
    {
        "name": "swin_t",
        "description": "Shifted-window transformer, compact variant",
        "image_size": 224,
        "batch_size": 16,
    },
    {
        "name": "swin_s",
        "description": "Mid-sized Swin Transformer",
        "image_size": 224,
        "batch_size": 12,
    },
    {
        "name": "swin_b",
        "description": "Large Swin Transformer for stronger accuracy",
        "image_size": 224,
        "batch_size": 8,
    },
    {
        "name": "maxvit_t",
        "description": "Modern hybrid backbone with strong accuracy",
        "image_size": 224,
        "batch_size": 12,
    },
    {
        "name": "inception_v3",
        "description": "Older but still useful baseline for 299x299 inputs",
        "image_size": 299,
        "batch_size": 20,
    },
    {
        "name": "custom",
        "description": "Type any torchvision classification model builder",
        "image_size": 224,
        "batch_size": 32,
    },
]

VISION_TEMPLATE = '''import json
import os
import random
import time
from pathlib import Path

import modal

CONFIG = __CONFIG__
LOCAL_DATASET_PATH = __LOCAL_DATASET_PATH__
REMOTE_DATASET_PATH = __REMOTE_DATASET_PATH__
DATASET_IGNORE_PATTERNS = __DATASET_IGNORE_PATTERNS__
ARTIFACT_VOLUME_NAME = __ARTIFACT_VOLUME_NAME__
TIMEOUT_SECONDS = __TIMEOUT_SECONDS__

# __METRICS__

app = modal.App("m-gpux-vision-classification")
artifacts_volume = modal.Volume.from_name(ARTIFACT_VOLUME_NAME, create_if_missing=True)

image = (
    modal.Image.debian_slim()
    .pip_install(
        "torch>=2.4.0",
        "torchvision>=0.19.0",
        "pillow>=10.0.0",
    )
    .add_local_dir(
        LOCAL_DATASET_PATH,
        remote_path=REMOTE_DATASET_PATH,
        ignore=DATASET_IGNORE_PATTERNS,
    )
)


@app.function(
    image=image,
    gpu=CONFIG["gpu"],
    timeout=TIMEOUT_SECONDS,
    volumes={"/artifacts": artifacts_volume},
)
def train():
    import math

    import torch
    from torch import nn
    from torch.optim import AdamW, RMSprop, SGD
    from torch.optim.lr_scheduler import CosineAnnealingLR, OneCycleLR, StepLR
    from torch.utils.data import DataLoader, Subset
    from torchvision import datasets, transforms
    from torchvision.models import get_model, get_model_weights

    _print_metrics()
    _monitor_metrics()

    def seed_everything(seed: int) -> None:
        random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.benchmark = True
        torch.backends.cudnn.deterministic = False

    def build_transforms(image_size: int, augmentation: str):
        normalize = transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        )
        train_steps = [transforms.RandomResizedCrop(image_size)]
        if augmentation in {"light", "medium", "strong"}:
            train_steps.append(transforms.RandomHorizontalFlip())
        if augmentation in {"medium", "strong"}:
            train_steps.append(transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.02))
        if augmentation == "strong":
            train_steps.extend(
                [
                    transforms.RandomRotation(20),
                    transforms.RandomPerspective(distortion_scale=0.2, p=0.25),
                    transforms.RandomAutocontrast(p=0.2),
                ]
            )
        train_steps.extend([transforms.ToTensor(), normalize])
        eval_steps = [
            transforms.Resize(int(image_size * 1.15)),
            transforms.CenterCrop(image_size),
            transforms.ToTensor(),
            normalize,
        ]
        return transforms.Compose(train_steps), transforms.Compose(eval_steps)

    def replace_classifier(model: nn.Module, num_classes: int, dropout: float):
        def make_head(in_features: int):
            layers = []
            if dropout > 0:
                layers.append(nn.Dropout(p=dropout))
            layers.append(nn.Linear(in_features, num_classes))
            if len(layers) == 1:
                return layers[0]
            return nn.Sequential(*layers)

        if hasattr(model, "fc") and isinstance(model.fc, nn.Linear):
            new_head = make_head(model.fc.in_features)
            model.fc = new_head
            return [new_head]

        if hasattr(model, "classifier"):
            classifier = model.classifier
            if isinstance(classifier, nn.Linear):
                new_head = make_head(classifier.in_features)
                model.classifier = new_head
                return [new_head]
            if isinstance(classifier, nn.Sequential):
                for idx in range(len(classifier) - 1, -1, -1):
                    if isinstance(classifier[idx], nn.Linear):
                        new_head = make_head(classifier[idx].in_features)
                        classifier[idx] = new_head
                        return [new_head]

        if hasattr(model, "heads"):
            heads = model.heads
            if hasattr(heads, "head") and isinstance(heads.head, nn.Linear):
                new_head = make_head(heads.head.in_features)
                heads.head = new_head
                return [new_head]
            if isinstance(heads, nn.Sequential):
                for idx in range(len(heads) - 1, -1, -1):
                    if isinstance(heads[idx], nn.Linear):
                        new_head = make_head(heads[idx].in_features)
                        heads[idx] = new_head
                        return [new_head]

        if hasattr(model, "head") and isinstance(model.head, nn.Linear):
            new_head = make_head(model.head.in_features)
            model.head = new_head
            return [new_head]

        raise RuntimeError(f"Unsupported classifier head for model '{CONFIG['model_name']}'")

    def maybe_freeze_backbone(model: nn.Module, head_modules):
        if not CONFIG["freeze_backbone"]:
            return
        for parameter in model.parameters():
            parameter.requires_grad = False
        for module in head_modules:
            for parameter in module.parameters():
                parameter.requires_grad = True

    def create_model(num_classes: int):
        model_name = CONFIG["model_name"]
        kwargs = {}
        if model_name in {"googlenet", "inception_v3"}:
            kwargs["aux_logits"] = False

        weights = None
        if CONFIG["pretrained"]:
            try:
                weight_enum = get_model_weights(model_name)
                weights = weight_enum.DEFAULT
            except Exception:
                weights = "DEFAULT"

        model = get_model(model_name, weights=weights, **kwargs)
        head_modules = replace_classifier(model, num_classes, CONFIG["dropout"])
        maybe_freeze_backbone(model, head_modules)
        return model, weights

    def create_datasets():
        dataset_root = Path(REMOTE_DATASET_PATH)
        train_transform, eval_transform = build_transforms(CONFIG["image_size"], CONFIG["augmentation"])

        if CONFIG["dataset_mode"] == "pre_split":
            train_root = dataset_root / "train"
            val_root = dataset_root / "val"
            test_root = dataset_root / "test"

            train_dataset = datasets.ImageFolder(train_root, transform=train_transform)
            val_dataset = datasets.ImageFolder(val_root, transform=eval_transform)
            test_dataset = datasets.ImageFolder(test_root, transform=eval_transform) if test_root.is_dir() else None

            if train_dataset.classes != val_dataset.classes:
                raise RuntimeError("Train/val class folders do not match.")
            if test_dataset is not None and train_dataset.classes != test_dataset.classes:
                raise RuntimeError("Train/test class folders do not match.")

            return train_dataset, val_dataset, test_dataset, train_dataset.classes

        if CONFIG["dataset_mode"] == "train_only":
            source_root = dataset_root / "train"
        else:
            source_root = dataset_root

        base_dataset = datasets.ImageFolder(source_root)
        if len(base_dataset.classes) < 2:
            raise RuntimeError("Image classification requires at least 2 classes.")

        num_samples = len(base_dataset.samples)
        val_size = max(1, int(num_samples * CONFIG["validation_split"]))
        if val_size >= num_samples:
            raise RuntimeError("Validation split leaves no samples for training. Reduce --validation-split.")

        generator = torch.Generator().manual_seed(CONFIG["seed"])
        indices = torch.randperm(num_samples, generator=generator).tolist()
        train_indices = indices[val_size:]
        val_indices = indices[:val_size]

        train_dataset_all = datasets.ImageFolder(source_root, transform=train_transform)
        val_dataset_all = datasets.ImageFolder(source_root, transform=eval_transform)

        train_dataset = Subset(train_dataset_all, train_indices)
        val_dataset = Subset(val_dataset_all, val_indices)

        test_root = dataset_root / "test"
        test_dataset = datasets.ImageFolder(test_root, transform=eval_transform) if test_root.is_dir() else None
        return train_dataset, val_dataset, test_dataset, base_dataset.classes

    def create_loader(dataset, shuffle: bool):
        workers = max(0, min(CONFIG["num_workers"], os.cpu_count() or 0))
        return DataLoader(
            dataset,
            batch_size=CONFIG["batch_size"],
            shuffle=shuffle,
            num_workers=workers,
            pin_memory=True,
            persistent_workers=workers > 0,
        )

    def create_optimizer(model: nn.Module):
        params = [parameter for parameter in model.parameters() if parameter.requires_grad]
        optimizer_name = CONFIG["optimizer"]
        if optimizer_name == "adamw":
            return AdamW(params, lr=CONFIG["learning_rate"], weight_decay=CONFIG["weight_decay"])
        if optimizer_name == "sgd":
            return SGD(
                params,
                lr=CONFIG["learning_rate"],
                momentum=CONFIG["momentum"],
                weight_decay=CONFIG["weight_decay"],
                nesterov=True,
            )
        if optimizer_name == "rmsprop":
            return RMSprop(
                params,
                lr=CONFIG["learning_rate"],
                momentum=CONFIG["momentum"],
                weight_decay=CONFIG["weight_decay"],
            )
        raise RuntimeError(f"Unsupported optimizer '{optimizer_name}'")

    def create_scheduler(optimizer, train_loader):
        scheduler_name = CONFIG["scheduler"]
        if scheduler_name == "none":
            return None
        if scheduler_name == "cosine":
            return CosineAnnealingLR(optimizer, T_max=max(1, CONFIG["epochs"]))
        if scheduler_name == "step":
            return StepLR(optimizer, step_size=max(1, CONFIG["epochs"] // 3), gamma=0.1)
        if scheduler_name == "onecycle":
            steps_per_epoch = max(1, math.ceil(len(train_loader) / CONFIG["grad_accumulation_steps"]))
            return OneCycleLR(
                optimizer,
                max_lr=CONFIG["learning_rate"],
                epochs=CONFIG["epochs"],
                steps_per_epoch=steps_per_epoch,
            )
        raise RuntimeError(f"Unsupported scheduler '{scheduler_name}'")

    def unpack_logits(outputs):
        if hasattr(outputs, "logits"):
            return outputs.logits
        if isinstance(outputs, tuple):
            return outputs[0]
        return outputs

    def evaluate(model, loader, criterion, device):
        model.eval()
        total_loss = 0.0
        total_correct = 0
        total_seen = 0
        predictions = []
        targets = []

        with torch.no_grad():
            for images, labels in loader:
                images = images.to(device, non_blocking=True)
                labels = labels.to(device, non_blocking=True)
                with torch.autocast(
                    device_type=device.type,
                    dtype=torch.float16,
                    enabled=CONFIG["mixed_precision"] and device.type == "cuda",
                ):
                    outputs = unpack_logits(model(images))
                    loss = criterion(outputs, labels)
                total_loss += loss.item() * labels.size(0)
                preds = outputs.argmax(dim=1)
                total_correct += (preds == labels).sum().item()
                total_seen += labels.size(0)
                predictions.extend(preds.detach().cpu().tolist())
                targets.extend(labels.detach().cpu().tolist())

        return {
            "loss": total_loss / max(1, total_seen),
            "accuracy": total_correct / max(1, total_seen),
            "predictions": predictions,
            "targets": targets,
        }

    def build_confusion_matrix(targets, predictions, num_classes):
        matrix = [[0 for _ in range(num_classes)] for _ in range(num_classes)]
        for target, prediction in zip(targets, predictions):
            matrix[target][prediction] += 1
        return matrix

    def per_class_metrics(targets, predictions, class_names):
        matrix = build_confusion_matrix(targets, predictions, len(class_names))
        metrics = {}
        f1_values = []
        for index, class_name in enumerate(class_names):
            tp = matrix[index][index]
            fp = sum(row[index] for row in matrix) - tp
            fn = sum(matrix[index]) - tp
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            support = sum(matrix[index])
            metrics[class_name] = {
                "precision": round(precision, 6),
                "recall": round(recall, 6),
                "f1": round(f1, 6),
                "support": support,
            }
            f1_values.append(f1)
        return {
            "confusion_matrix": matrix,
            "per_class": metrics,
            "macro_f1": round(sum(f1_values) / max(1, len(f1_values)), 6),
        }

    def save_json(path: Path, payload) -> None:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    seed_everything(CONFIG["seed"])

    train_dataset, val_dataset, test_dataset, class_names = create_datasets()
    train_loader = create_loader(train_dataset, shuffle=True)
    val_loader = create_loader(val_dataset, shuffle=False)
    test_loader = create_loader(test_dataset, shuffle=False) if test_dataset is not None else None

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, weights = create_model(len(class_names))
    model = model.to(device)

    criterion = nn.CrossEntropyLoss(label_smoothing=CONFIG["label_smoothing"])
    optimizer = create_optimizer(model)
    scheduler = create_scheduler(optimizer, train_loader)
    scaler = torch.cuda.amp.GradScaler(enabled=CONFIG["mixed_precision"] and device.type == "cuda")

    run_dir = Path("/artifacts") / CONFIG["experiment_name"]
    checkpoints_dir = run_dir / "checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)

    console_lines = [
        f"Experiment: {CONFIG['experiment_name']}",
        f"Dataset mode: {CONFIG['dataset_mode']}",
        f"Model: {CONFIG['model_name']}",
        f"Train samples: {len(train_dataset)}",
        f"Val samples: {len(val_dataset)}",
        f"Test samples: {len(test_dataset) if test_dataset is not None else 0}",
        f"Classes: {', '.join(class_names)}",
        f"Device: {device}",
    ]
    print("\\n".join(console_lines))

    history = []
    best_val_acc = -1.0
    best_epoch = 0
    stale_epochs = 0
    training_started = time.time()

    for epoch in range(1, CONFIG["epochs"] + 1):
        epoch_start = time.time()
        model.train()
        optimizer.zero_grad(set_to_none=True)

        running_loss = 0.0
        running_correct = 0
        running_seen = 0

        for step, (images, labels) in enumerate(train_loader, start=1):
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)

            with torch.autocast(
                device_type=device.type,
                dtype=torch.float16,
                enabled=CONFIG["mixed_precision"] and device.type == "cuda",
            ):
                outputs = unpack_logits(model(images))
                loss = criterion(outputs, labels)
                loss = loss / CONFIG["grad_accumulation_steps"]

            scaler.scale(loss).backward()

            should_step = (
                step % CONFIG["grad_accumulation_steps"] == 0
                or step == len(train_loader)
            )
            if should_step:
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
                if scheduler is not None and CONFIG["scheduler"] == "onecycle":
                    scheduler.step()

            logits = outputs.detach()
            preds = logits.argmax(dim=1)
            batch_size = labels.size(0)
            running_loss += loss.item() * batch_size * CONFIG["grad_accumulation_steps"]
            running_correct += (preds == labels).sum().item()
            running_seen += batch_size

        if scheduler is not None and CONFIG["scheduler"] in {"cosine", "step"}:
            scheduler.step()

        train_loss = running_loss / max(1, running_seen)
        train_acc = running_correct / max(1, running_seen)
        val_metrics = evaluate(model, val_loader, criterion, device)

        epoch_payload = {
            "epoch": epoch,
            "train_loss": round(train_loss, 6),
            "train_accuracy": round(train_acc, 6),
            "val_loss": round(val_metrics["loss"], 6),
            "val_accuracy": round(val_metrics["accuracy"], 6),
            "learning_rate": optimizer.param_groups[0]["lr"],
            "epoch_seconds": round(time.time() - epoch_start, 2),
        }
        history.append(epoch_payload)

        print(
            f"[Epoch {epoch:03d}/{CONFIG['epochs']:03d}] "
            f"train_loss={train_loss:.4f} train_acc={train_acc:.4f} "
            f"val_loss={val_metrics['loss']:.4f} val_acc={val_metrics['accuracy']:.4f} "
            f"lr={optimizer.param_groups[0]['lr']:.6f}"
        )

        if val_metrics["accuracy"] > best_val_acc:
            best_val_acc = val_metrics["accuracy"]
            best_epoch = epoch
            stale_epochs = 0

            best_payload = {
                "model_state_dict": model.state_dict(),
                "class_names": class_names,
                "config": CONFIG,
                "epoch": epoch,
                "best_val_accuracy": best_val_acc,
                "weights": str(weights) if weights is not None else None,
            }
            torch.save(best_payload, checkpoints_dir / "best_model.pt")
            save_json(
                checkpoints_dir / "best_validation_metrics.json",
                {
                    "loss": val_metrics["loss"],
                    "accuracy": val_metrics["accuracy"],
                },
            )
            artifacts_volume.commit()
        else:
            stale_epochs += 1

        if CONFIG["early_stopping_patience"] > 0 and stale_epochs >= CONFIG["early_stopping_patience"]:
            print(
                f"Early stopping triggered after {stale_epochs} stale epoch(s). "
                f"Best val_acc={best_val_acc:.4f} at epoch {best_epoch}."
            )
            break

    total_training_seconds = round(time.time() - training_started, 2)

    final_payload = {
        "model_state_dict": model.state_dict(),
        "class_names": class_names,
        "config": CONFIG,
        "epoch": history[-1]["epoch"],
        "best_val_accuracy": best_val_acc,
        "weights": str(weights) if weights is not None else None,
    }
    torch.save(final_payload, checkpoints_dir / "last_model.pt")

    save_json(run_dir / "config.json", CONFIG)
    save_json(run_dir / "history.json", history)
    save_json(
        run_dir / "dataset_summary.json",
        {
            "train_samples": len(train_dataset),
            "val_samples": len(val_dataset),
            "test_samples": len(test_dataset) if test_dataset is not None else 0,
            "classes": class_names,
            "num_classes": len(class_names),
        },
    )

    test_report = None
    if test_loader is not None:
        best_checkpoint = torch.load(checkpoints_dir / "best_model.pt", map_location=device)
        model.load_state_dict(best_checkpoint["model_state_dict"])
        test_metrics = evaluate(model, test_loader, criterion, device)
        test_report = per_class_metrics(test_metrics["targets"], test_metrics["predictions"], class_names)
        save_json(run_dir / "test_metrics.json", test_metrics)
        save_json(run_dir / "test_report.json", test_report)

    summary = {
        "experiment_name": CONFIG["experiment_name"],
        "model_name": CONFIG["model_name"],
        "best_epoch": best_epoch,
        "best_val_accuracy": round(best_val_acc, 6),
        "epochs_completed": history[-1]["epoch"],
        "training_seconds": total_training_seconds,
        "artifact_volume": ARTIFACT_VOLUME_NAME,
        "artifact_path": f"{CONFIG['experiment_name']}",
        "download_examples": {
            "best_model": f"modal volume get {ARTIFACT_VOLUME_NAME} {CONFIG['experiment_name']}/checkpoints/best_model.pt best_model.pt",
            "history": f"modal volume get {ARTIFACT_VOLUME_NAME} {CONFIG['experiment_name']}/history.json history.json",
        },
    }
    if test_report is not None:
        summary["test_macro_f1"] = test_report["macro_f1"]

    save_json(run_dir / "summary.json", summary)
    artifacts_volume.commit()

    print("\\nTraining complete.")
    print(json.dumps(summary, indent=2))
'''

PREDICT_TEMPLATE = '''import json
import os
import time
from pathlib import Path

import modal

CONFIG = __CONFIG__
ARTIFACT_VOLUME_NAME = __ARTIFACT_VOLUME_NAME__
CHECKPOINT_PATH = __CHECKPOINT_PATH__
REMOTE_INPUT_PATH = __REMOTE_INPUT_PATH__
INPUT_MODE = __INPUT_MODE__
TIMEOUT_SECONDS = __TIMEOUT_SECONDS__
OUTPUT_JSON_PATH = __OUTPUT_JSON_PATH__
TOP_K = __TOP_K__
MAX_IMAGES = __MAX_IMAGES__

# __METRICS__

app = modal.App("m-gpux-vision-predict")
artifacts_volume = modal.Volume.from_name(ARTIFACT_VOLUME_NAME)

image = (
    modal.Image.debian_slim()
    .pip_install(
        "torch>=2.4.0",
        "torchvision>=0.19.0",
        "pillow>=10.0.0",
    )
    __INPUT_ADDITION__
)


@app.function(
    image=image,
    gpu=CONFIG["gpu"],
    timeout=TIMEOUT_SECONDS,
    volumes={"/artifacts": artifacts_volume},
)
def predict():
    import torch
    from PIL import Image
    from torch import nn
    from torch.utils.data import DataLoader, Dataset
    from torchvision import transforms
    from torchvision.models import get_model

    _print_metrics()
    _monitor_metrics()

    def replace_classifier(model: nn.Module, num_classes: int, dropout: float):
        def make_head(in_features: int):
            layers = []
            if dropout > 0:
                layers.append(nn.Dropout(p=dropout))
            layers.append(nn.Linear(in_features, num_classes))
            if len(layers) == 1:
                return layers[0]
            return nn.Sequential(*layers)

        if hasattr(model, "fc") and isinstance(model.fc, nn.Linear):
            model.fc = make_head(model.fc.in_features)
            return

        if hasattr(model, "classifier"):
            classifier = model.classifier
            if isinstance(classifier, nn.Linear):
                model.classifier = make_head(classifier.in_features)
                return
            if isinstance(classifier, nn.Sequential):
                for idx in range(len(classifier) - 1, -1, -1):
                    if isinstance(classifier[idx], nn.Linear):
                        classifier[idx] = make_head(classifier[idx].in_features)
                        return

        if hasattr(model, "heads"):
            heads = model.heads
            if hasattr(heads, "head") and isinstance(heads.head, nn.Linear):
                heads.head = make_head(heads.head.in_features)
                return
            if isinstance(heads, nn.Sequential):
                for idx in range(len(heads) - 1, -1, -1):
                    if isinstance(heads[idx], nn.Linear):
                        heads[idx] = make_head(heads[idx].in_features)
                        return

        if hasattr(model, "head") and isinstance(model.head, nn.Linear):
            model.head = make_head(model.head.in_features)
            return

        raise RuntimeError("Unsupported classifier head in checkpoint model.")

    def build_model(train_config, class_names):
        model_name = train_config["model_name"]
        kwargs = {}
        if model_name in {"googlenet", "inception_v3"}:
            kwargs["aux_logits"] = False
        model = get_model(model_name, weights=None, **kwargs)
        replace_classifier(model, len(class_names), train_config.get("dropout", 0.0))
        return model

    def build_transform(image_size: int):
        return transforms.Compose(
            [
                transforms.Resize(int(image_size * 1.15)),
                transforms.CenterCrop(image_size),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )

    def collect_image_paths():
        if INPUT_MODE == "single":
            return [Path(REMOTE_INPUT_PATH)]

        root = Path(REMOTE_INPUT_PATH)
        image_paths = sorted(
            [
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
            ]
        )
        if MAX_IMAGES is not None:
            image_paths = image_paths[:MAX_IMAGES]
        return image_paths

    class PredictionDataset(Dataset):
        def __init__(self, image_paths, transform):
            self.image_paths = image_paths
            self.transform = transform

        def __len__(self):
            return len(self.image_paths)

        def __getitem__(self, index):
            image_path = self.image_paths[index]
            image = Image.open(image_path).convert("RGB")
            return self.transform(image), str(image_path)

    def unpack_logits(outputs):
        if hasattr(outputs, "logits"):
            return outputs.logits
        if isinstance(outputs, tuple):
            return outputs[0]
        return outputs

    checkpoint_file = Path("/artifacts") / CHECKPOINT_PATH
    if not checkpoint_file.exists():
        raise RuntimeError(f"Checkpoint not found in volume: {checkpoint_file}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(checkpoint_file, map_location=device)
    train_config = checkpoint.get("config", {})
    class_names = checkpoint["class_names"]
    image_size = int(train_config.get("image_size", CONFIG["fallback_image_size"]))
    model = build_model(train_config, class_names)
    model.load_state_dict(checkpoint["model_state_dict"])
    model = model.to(device)
    model.eval()

    image_paths = collect_image_paths()
    if not image_paths:
        raise RuntimeError("No input images found for prediction.")

    transform = build_transform(image_size)
    dataset = PredictionDataset(image_paths, transform)
    loader = DataLoader(
        dataset,
        batch_size=CONFIG["batch_size"],
        shuffle=False,
        num_workers=max(0, CONFIG["num_workers"]),
        pin_memory=True,
    )

    prediction_rows = []
    started = time.time()
    with torch.no_grad():
        for images, paths in loader:
            images = images.to(device, non_blocking=True)
            with torch.autocast(
                device_type=device.type,
                dtype=torch.float16,
                enabled=CONFIG["mixed_precision"] and device.type == "cuda",
            ):
                outputs = unpack_logits(model(images))
                probabilities = torch.softmax(outputs, dim=1)
                top_probs, top_indices = probabilities.topk(k=min(TOP_K, len(class_names)), dim=1)

            for row_index, image_path in enumerate(paths):
                ranked = []
                for prob, idx in zip(top_probs[row_index], top_indices[row_index]):
                    class_index = int(idx.item())
                    ranked.append(
                        {
                            "label": class_names[class_index],
                            "score": round(float(prob.item()), 6),
                        }
                    )
                prediction_rows.append(
                    {
                        "image": image_path,
                        "top_prediction": ranked[0]["label"],
                        "top_score": ranked[0]["score"],
                        "predictions": ranked,
                    }
                )

    output_file = Path("/artifacts") / OUTPUT_JSON_PATH
    output_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "checkpoint_path": CHECKPOINT_PATH,
        "artifact_volume": ARTIFACT_VOLUME_NAME,
        "model_name": train_config.get("model_name"),
        "image_size": image_size,
        "num_images": len(prediction_rows),
        "elapsed_seconds": round(time.time() - started, 2),
        "predictions": prediction_rows,
    }
    output_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    artifacts_volume.commit()

    summary = {
        "num_images": len(prediction_rows),
        "output_json_path": OUTPUT_JSON_PATH,
        "top_k": TOP_K,
        "first_predictions": prediction_rows[: min(5, len(prediction_rows))],
    }
    print(json.dumps(summary, indent=2))
'''

EVALUATE_TEMPLATE = '''import json
from pathlib import Path

import modal

CONFIG = __CONFIG__
LOCAL_DATASET_PATH = __LOCAL_DATASET_PATH__
REMOTE_DATASET_PATH = __REMOTE_DATASET_PATH__
DATASET_IGNORE_PATTERNS = __DATASET_IGNORE_PATTERNS__
ARTIFACT_VOLUME_NAME = __ARTIFACT_VOLUME_NAME__
CHECKPOINT_PATH = __CHECKPOINT_PATH__
OUTPUT_JSON_PATH = __OUTPUT_JSON_PATH__
TIMEOUT_SECONDS = __TIMEOUT_SECONDS__
TOP_K = __TOP_K__

# __METRICS__

app = modal.App("m-gpux-vision-evaluate")
artifacts_volume = modal.Volume.from_name(ARTIFACT_VOLUME_NAME)

image = (
    modal.Image.debian_slim()
    .pip_install(
        "torch>=2.4.0",
        "torchvision>=0.19.0",
        "pillow>=10.0.0",
    )
    .add_local_dir(
        LOCAL_DATASET_PATH,
        remote_path=REMOTE_DATASET_PATH,
        ignore=DATASET_IGNORE_PATTERNS,
    )
)


@app.function(
    image=image,
    gpu=CONFIG["gpu"],
    timeout=TIMEOUT_SECONDS,
    volumes={"/artifacts": artifacts_volume},
)
def evaluate():
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, Subset
    from torchvision import datasets, transforms
    from torchvision.models import get_model

    _print_metrics()
    _monitor_metrics()

    def replace_classifier(model: nn.Module, num_classes: int, dropout: float):
        def make_head(in_features: int):
            layers = []
            if dropout > 0:
                layers.append(nn.Dropout(p=dropout))
            layers.append(nn.Linear(in_features, num_classes))
            if len(layers) == 1:
                return layers[0]
            return nn.Sequential(*layers)

        if hasattr(model, "fc") and isinstance(model.fc, nn.Linear):
            model.fc = make_head(model.fc.in_features)
            return

        if hasattr(model, "classifier"):
            classifier = model.classifier
            if isinstance(classifier, nn.Linear):
                model.classifier = make_head(classifier.in_features)
                return
            if isinstance(classifier, nn.Sequential):
                for idx in range(len(classifier) - 1, -1, -1):
                    if isinstance(classifier[idx], nn.Linear):
                        classifier[idx] = make_head(classifier[idx].in_features)
                        return

        if hasattr(model, "heads"):
            heads = model.heads
            if hasattr(heads, "head") and isinstance(heads.head, nn.Linear):
                heads.head = make_head(heads.head.in_features)
                return
            if isinstance(heads, nn.Sequential):
                for idx in range(len(heads) - 1, -1, -1):
                    if isinstance(heads[idx], nn.Linear):
                        heads[idx] = make_head(heads[idx].in_features)
                        return

        if hasattr(model, "head") and isinstance(model.head, nn.Linear):
            model.head = make_head(model.head.in_features)
            return

        raise RuntimeError("Unsupported classifier head in checkpoint model.")

    def build_model(train_config, class_names):
        model_name = train_config["model_name"]
        kwargs = {}
        if model_name in {"googlenet", "inception_v3"}:
            kwargs["aux_logits"] = False
        model = get_model(model_name, weights=None, **kwargs)
        replace_classifier(model, len(class_names), train_config.get("dropout", 0.0))
        return model

    def build_transform(image_size: int):
        return transforms.Compose(
            [
                transforms.Resize(int(image_size * 1.15)),
                transforms.CenterCrop(image_size),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )

    def create_dataset(train_config, class_names):
        dataset_root = Path(REMOTE_DATASET_PATH)
        transform = build_transform(int(train_config.get("image_size", CONFIG["fallback_image_size"])))
        mode = CONFIG["dataset_mode"]
        requested_split = CONFIG["split"]

        if mode == "pre_split":
            if requested_split == "auto":
                if (dataset_root / "test").is_dir():
                    resolved_split = "test"
                elif (dataset_root / "val").is_dir():
                    resolved_split = "val"
                else:
                    resolved_split = "train"
            else:
                resolved_split = requested_split

            split_root = dataset_root / resolved_split
            if not split_root.is_dir():
                raise RuntimeError(f"Requested split '{resolved_split}' does not exist in dataset.")
            dataset = datasets.ImageFolder(split_root, transform=transform)
            if dataset.classes != class_names:
                raise RuntimeError("Dataset classes do not match checkpoint classes.")
            return dataset, resolved_split

        if requested_split == "auto":
            resolved_split = "val"
        else:
            resolved_split = requested_split

        if resolved_split not in {"train", "val"}:
            raise RuntimeError("Single-root/train-only datasets support only train or val evaluation.")

        source_root = dataset_root / "train" if mode == "train_only" else dataset_root
        base_dataset = datasets.ImageFolder(source_root)
        if base_dataset.classes != class_names:
            raise RuntimeError("Dataset classes do not match checkpoint classes.")

        num_samples = len(base_dataset.samples)
        val_split = float(train_config.get("validation_split", CONFIG["fallback_validation_split"]))
        seed = int(train_config.get("seed", CONFIG["fallback_seed"]))
        val_size = max(1, int(num_samples * val_split))
        if val_size >= num_samples:
            raise RuntimeError("Validation split leaves no training samples.")

        generator = torch.Generator().manual_seed(seed)
        indices = torch.randperm(num_samples, generator=generator).tolist()
        val_indices = indices[:val_size]
        train_indices = indices[val_size:]

        dataset_all = datasets.ImageFolder(source_root, transform=transform)
        subset_indices = train_indices if resolved_split == "train" else val_indices
        return Subset(dataset_all, subset_indices), resolved_split

    def build_confusion_matrix(targets, predictions, num_classes):
        matrix = [[0 for _ in range(num_classes)] for _ in range(num_classes)]
        for target, prediction in zip(targets, predictions):
            matrix[target][prediction] += 1
        return matrix

    def per_class_metrics(targets, predictions, class_names):
        matrix = build_confusion_matrix(targets, predictions, len(class_names))
        metrics = {}
        f1_values = []
        for index, class_name in enumerate(class_names):
            tp = matrix[index][index]
            fp = sum(row[index] for row in matrix) - tp
            fn = sum(matrix[index]) - tp
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            support = sum(matrix[index])
            metrics[class_name] = {
                "precision": round(precision, 6),
                "recall": round(recall, 6),
                "f1": round(f1, 6),
                "support": support,
            }
            f1_values.append(f1)
        return {
            "confusion_matrix": matrix,
            "per_class": metrics,
            "macro_f1": round(sum(f1_values) / max(1, len(f1_values)), 6),
        }

    checkpoint_file = Path("/artifacts") / CHECKPOINT_PATH
    if not checkpoint_file.exists():
        raise RuntimeError(f"Checkpoint not found in volume: {checkpoint_file}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint = torch.load(checkpoint_file, map_location=device)
    train_config = checkpoint.get("config", {})
    class_names = checkpoint["class_names"]
    model = build_model(train_config, class_names)
    model.load_state_dict(checkpoint["model_state_dict"])
    model = model.to(device)
    model.eval()

    dataset, resolved_split = create_dataset(train_config, class_names)
    loader = DataLoader(
        dataset,
        batch_size=CONFIG["batch_size"],
        shuffle=False,
        num_workers=max(0, CONFIG["num_workers"]),
        pin_memory=True,
    )

    criterion = nn.CrossEntropyLoss()
    total_loss = 0.0
    total_correct = 0
    total_topk = 0
    total_seen = 0
    predictions = []
    targets = []

    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)

            with torch.autocast(
                device_type=device.type,
                dtype=torch.float16,
                enabled=CONFIG["mixed_precision"] and device.type == "cuda",
            ):
                outputs = model(images)
                if hasattr(outputs, "logits"):
                    outputs = outputs.logits
                elif isinstance(outputs, tuple):
                    outputs = outputs[0]
                loss = criterion(outputs, labels)

            total_loss += loss.item() * labels.size(0)
            preds = outputs.argmax(dim=1)
            total_correct += (preds == labels).sum().item()
            k = min(TOP_K, len(class_names))
            topk_indices = outputs.topk(k=k, dim=1).indices
            total_topk += sum(
                1 for row_index in range(labels.size(0))
                if int(labels[row_index].item()) in topk_indices[row_index].tolist()
            )
            total_seen += labels.size(0)
            predictions.extend(preds.detach().cpu().tolist())
            targets.extend(labels.detach().cpu().tolist())

    report = {
        "checkpoint_path": CHECKPOINT_PATH,
        "split": resolved_split,
        "num_samples": total_seen,
        "loss": round(total_loss / max(1, total_seen), 6),
        "accuracy": round(total_correct / max(1, total_seen), 6),
        "topk_accuracy": round(total_topk / max(1, total_seen), 6),
        "top_k": min(TOP_K, len(class_names)),
        "class_names": class_names,
    }
    report.update(per_class_metrics(targets, predictions, class_names))

    output_file = Path("/artifacts") / OUTPUT_JSON_PATH
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    artifacts_volume.commit()

    print(
        json.dumps(
            {
                "split": resolved_split,
                "num_samples": total_seen,
                "accuracy": report["accuracy"],
                "topk_accuracy": report["topk_accuracy"],
                "macro_f1": report["macro_f1"],
                "output_json_path": OUTPUT_JSON_PATH,
            },
            indent=2,
        )
    )
'''

EXPORT_TEMPLATE = '''import json
from pathlib import Path

import modal

CONFIG = __CONFIG__
ARTIFACT_VOLUME_NAME = __ARTIFACT_VOLUME_NAME__
CHECKPOINT_PATH = __CHECKPOINT_PATH__
OUTPUT_DIR = __OUTPUT_DIR__
TIMEOUT_SECONDS = __TIMEOUT_SECONDS__

# __METRICS__

app = modal.App("m-gpux-vision-export")
artifacts_volume = modal.Volume.from_name(ARTIFACT_VOLUME_NAME)

image = (
    modal.Image.debian_slim()
    .pip_install(
        "torch>=2.4.0",
        "torchvision>=0.19.0",
        "onnx>=1.16.0",
    )
)


@app.function(
    image=image,
    timeout=TIMEOUT_SECONDS,
    volumes={"/artifacts": artifacts_volume},
)
def export():
    import torch
    from torch import nn
    from torchvision.models import get_model

    _print_metrics()
    _monitor_metrics()

    def replace_classifier(model: nn.Module, num_classes: int, dropout: float):
        def make_head(in_features: int):
            layers = []
            if dropout > 0:
                layers.append(nn.Dropout(p=dropout))
            layers.append(nn.Linear(in_features, num_classes))
            if len(layers) == 1:
                return layers[0]
            return nn.Sequential(*layers)

        if hasattr(model, "fc") and isinstance(model.fc, nn.Linear):
            model.fc = make_head(model.fc.in_features)
            return

        if hasattr(model, "classifier"):
            classifier = model.classifier
            if isinstance(classifier, nn.Linear):
                model.classifier = make_head(classifier.in_features)
                return
            if isinstance(classifier, nn.Sequential):
                for idx in range(len(classifier) - 1, -1, -1):
                    if isinstance(classifier[idx], nn.Linear):
                        classifier[idx] = make_head(classifier[idx].in_features)
                        return

        if hasattr(model, "heads"):
            heads = model.heads
            if hasattr(heads, "head") and isinstance(heads.head, nn.Linear):
                heads.head = make_head(heads.head.in_features)
                return
            if isinstance(heads, nn.Sequential):
                for idx in range(len(heads) - 1, -1, -1):
                    if isinstance(heads[idx], nn.Linear):
                        heads[idx] = make_head(heads[idx].in_features)
                        return

        if hasattr(model, "head") and isinstance(model.head, nn.Linear):
            model.head = make_head(model.head.in_features)
            return

        raise RuntimeError("Unsupported classifier head in checkpoint model.")

    def build_model(train_config, class_names):
        model_name = train_config["model_name"]
        kwargs = {}
        if model_name in {"googlenet", "inception_v3"}:
            kwargs["aux_logits"] = False
        model = get_model(model_name, weights=None, **kwargs)
        replace_classifier(model, len(class_names), train_config.get("dropout", 0.0))
        return model

    checkpoint_file = Path("/artifacts") / CHECKPOINT_PATH
    if not checkpoint_file.exists():
        raise RuntimeError(f"Checkpoint not found in volume: {checkpoint_file}")

    checkpoint = torch.load(checkpoint_file, map_location="cpu")
    train_config = checkpoint.get("config", {})
    class_names = checkpoint["class_names"]
    image_size = int(train_config.get("image_size", CONFIG["fallback_image_size"]))

    model = build_model(train_config, class_names)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    dummy_input = torch.randn(1, 3, image_size, image_size)

    output_dir = Path("/artifacts") / OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    exported_files = {}
    requested_formats = set(CONFIG["formats"])

    if "torchscript" in requested_formats:
        traced = torch.jit.trace(model, dummy_input)
        torchscript_path = output_dir / "model.ts"
        traced.save(str(torchscript_path))
        exported_files["torchscript"] = str(Path(OUTPUT_DIR) / "model.ts")

    if "onnx" in requested_formats:
        onnx_path = output_dir / "model.onnx"
        torch.onnx.export(
            model,
            dummy_input,
            str(onnx_path),
            export_params=True,
            do_constant_folding=True,
            input_names=["input"],
            output_names=["logits"],
            dynamic_axes={
                "input": {0: "batch"},
                "logits": {0: "batch"},
            },
            opset_version=17,
        )
        exported_files["onnx"] = str(Path(OUTPUT_DIR) / "model.onnx")

    labels_payload = {
        "class_names": class_names,
        "num_classes": len(class_names),
    }
    (output_dir / "labels.json").write_text(json.dumps(labels_payload, indent=2), encoding="utf-8")

    summary = {
        "checkpoint_path": CHECKPOINT_PATH,
        "output_dir": OUTPUT_DIR,
        "model_name": train_config.get("model_name"),
        "image_size": image_size,
        "formats": sorted(requested_formats),
        "exported_files": exported_files,
    }
    (output_dir / "export_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    artifacts_volume.commit()
    print(json.dumps(summary, indent=2))
'''


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "run"


def _count_images(folder: Path) -> int:
    return sum(
        1
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def _class_dirs(folder: Path) -> list[Path]:
    return sorted(
        [
            path
            for path in folder.iterdir()
            if path.is_dir()
            and not path.name.startswith(".")
            and path.name not in {"__pycache__"}
            and _count_images(path) > 0
        ],
        key=lambda item: item.name.lower(),
    )


def _inspect_dataset_layout(dataset_root: Path) -> dict:
    train_dir = dataset_root / "train"
    val_dir = dataset_root / "val"
    test_dir = dataset_root / "test"

    if train_dir.is_dir():
        train_classes = [path.name for path in _class_dirs(train_dir)]
        if len(train_classes) < 2:
            raise typer.BadParameter(
                "The train split must contain at least 2 class folders with images."
            )

        layout = {
            "mode": "pre_split" if val_dir.is_dir() else "train_only",
            "classes": train_classes,
            "train_count": _count_images(train_dir),
            "val_count": _count_images(val_dir) if val_dir.is_dir() else 0,
            "test_count": _count_images(test_dir) if test_dir.is_dir() else 0,
        }

        if val_dir.is_dir():
            val_classes = [path.name for path in _class_dirs(val_dir)]
            if set(train_classes) != set(val_classes):
                raise typer.BadParameter(
                    "Train/val class folders do not match. Please fix the dataset layout first."
                )

        if test_dir.is_dir():
            test_classes = [path.name for path in _class_dirs(test_dir)]
            if test_classes and set(train_classes) != set(test_classes):
                raise typer.BadParameter(
                    "Train/test class folders do not match. Please fix the dataset layout first."
                )

        return layout

    if val_dir.is_dir() or test_dir.is_dir():
        raise typer.BadParameter(
            "Single-root datasets cannot also contain top-level val/test folders. "
            "Use train/val/test splits or keep only class folders at the root."
        )

    root_classes = [path.name for path in _class_dirs(dataset_root)]
    if len(root_classes) < 2:
        raise typer.BadParameter(
            "Expected either train/val folders or direct class folders with images."
        )

    return {
        "mode": "single_root",
        "classes": root_classes,
        "train_count": _count_images(dataset_root),
        "val_count": 0,
        "test_count": 0,
    }


def _resolve_dataset_path(dataset: Optional[str]) -> Path:
    default_path = "data" if Path("data").is_dir() else "."
    raw_value = dataset or Prompt.ask("Local dataset folder", default=default_path)
    dataset_root = Path(raw_value).expanduser().resolve()
    if not dataset_root.exists():
        raise typer.BadParameter(f"Dataset folder does not exist: {dataset_root}")
    if not dataset_root.is_dir():
        raise typer.BadParameter(f"Dataset path must be a directory: {dataset_root}")
    return dataset_root


def _resolve_gpu_name(gpu: Optional[str]) -> str:
    if gpu:
        for _, (name, _) in AVAILABLE_GPUS.items():
            if gpu.lower() == name.lower():
                return name
        raise typer.BadParameter(
            f"Unsupported GPU '{gpu}'. Choose one of: {', '.join(v[0] for v in AVAILABLE_GPUS.values())}"
        )

    console.print("\n[bold cyan]Step 1: Choose GPU[/bold cyan]")
    gpu_options = [(value[0], value[1]) for value in AVAILABLE_GPUS.values()]
    selected_index = arrow_select(gpu_options, title="Select GPU", default=1)
    return gpu_options[selected_index][0]


def _resolve_model_config(model: Optional[str]) -> dict:
    catalog_by_name = {item["name"]: item for item in MODEL_CATALOG}

    if model:
        if model in catalog_by_name and model != "custom":
            return catalog_by_name[model]
        return {
            "name": model,
            "description": "Custom torchvision classification model",
            "image_size": 224,
            "batch_size": 32,
        }

    console.print("\n[bold cyan]Step 2: Choose model[/bold cyan]")
    options = [(item["name"], item["description"]) for item in MODEL_CATALOG]
    selected_index = arrow_select(options, title="Select model", default=0)
    selected = MODEL_CATALOG[selected_index]
    if selected["name"] != "custom":
        return selected

    custom_name = Prompt.ask(
        "TorchVision classification model builder name",
        default="resnet50",
    ).strip()
    return {
        "name": custom_name,
        "description": "Custom torchvision classification model",
        "image_size": 224,
        "batch_size": 32,
    }


def _prompt_optimizer(default_value: str = "adamw") -> str:
    optimizer_options = [
        ("adamw", "Great default for modern CNNs and transformers"),
        ("sgd", "Classic momentum SGD"),
        ("rmsprop", "Often useful for EfficientNet-style baselines"),
    ]
    default_index = next(
        (index for index, item in enumerate(optimizer_options) if item[0] == default_value),
        0,
    )
    selected_index = arrow_select(
        optimizer_options,
        title="Select optimizer",
        default=default_index,
    )
    return optimizer_options[selected_index][0]


def _prompt_scheduler(default_value: str = "cosine") -> str:
    scheduler_options = [
        ("cosine", "Cosine annealing over the full run"),
        ("onecycle", "Aggressive schedule for faster convergence"),
        ("step", "Step down learning rate every few epochs"),
        ("none", "Keep the learning rate fixed"),
    ]
    default_index = next(
        (index for index, item in enumerate(scheduler_options) if item[0] == default_value),
        0,
    )
    selected_index = arrow_select(
        scheduler_options,
        title="Select scheduler",
        default=default_index,
    )
    return scheduler_options[selected_index][0]


def _prompt_augmentation(default_value: str = "medium") -> str:
    augmentation_options = [
        ("none", "Only resize/crop and normalize"),
        ("light", "Horizontal flip and light augmentation"),
        ("medium", "Practical default for most datasets"),
        ("strong", "Heavier augmentation for harder tasks"),
    ]
    default_index = next(
        (index for index, item in enumerate(augmentation_options) if item[0] == default_value),
        2,
    )
    selected_index = arrow_select(
        augmentation_options,
        title="Select augmentation strength",
        default=default_index,
    )
    return augmentation_options[selected_index][0]


def _render_dataset_summary(dataset_root: Path, layout: dict) -> None:
    table = Table(title="Dataset Summary")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Path", str(dataset_root))
    table.add_row("Layout", layout["mode"])
    table.add_row("Classes", ", ".join(layout["classes"]))
    table.add_row("Train images", str(layout["train_count"]))
    table.add_row("Val images", str(layout["val_count"]))
    table.add_row("Test images", str(layout["test_count"]))
    console.print(table)


def _resolve_image_input_path(input_path: Optional[str]) -> Path:
    default_path = "samples" if Path("samples").exists() else "."
    raw_value = input_path or Prompt.ask(
        "Local image file or folder to predict",
        default=default_path,
    )
    resolved = Path(raw_value).expanduser().resolve()
    if not resolved.exists():
        raise typer.BadParameter(f"Input path does not exist: {resolved}")
    if resolved.is_file() and resolved.suffix.lower() not in IMAGE_EXTENSIONS:
        raise typer.BadParameter(
            f"Unsupported image file type: {resolved.suffix}. "
            f"Supported: {', '.join(sorted(IMAGE_EXTENSIONS))}"
        )
    if not resolved.is_file() and not resolved.is_dir():
        raise typer.BadParameter("Input path must be a file or directory.")
    return resolved


def _collect_local_images(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(
        [
            image_path
            for image_path in path.rglob("*")
            if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS
        ]
    )


def _build_prediction_input_addition(input_path: Path) -> tuple[str, str, str]:
    if input_path.is_file():
        remote_file = f"/inputs/{input_path.name}"
        addition = (
            f'.add_local_file({repr(input_path.as_posix())}, '
            f'remote_path={repr(remote_file)})'
        )
        return addition, remote_file, "single"

    addition = (
        f'.add_local_dir({repr(input_path.as_posix())}, '
        f'remote_path={repr("/inputs")}, ignore={repr(DEFAULT_DATASET_IGNORES)})'
    )
    return addition, "/inputs", "directory"


def _normalize_volume_path(raw_path: str) -> str:
    return raw_path.strip().lstrip("/").replace("\\", "/")


def _resolve_checkpoint_reference(
    run_name: Optional[str],
    checkpoint_path: Optional[str],
    *,
    prompt_label: str = "Experiment / run name",
    default_run_name: str = "imgclf-run",
) -> tuple[str, str]:
    if checkpoint_path:
        resolved_checkpoint_path = _normalize_volume_path(checkpoint_path)
        path_parts = Path(resolved_checkpoint_path).parts
        inferred_run_name = path_parts[0] if path_parts else default_run_name
        return resolved_checkpoint_path, inferred_run_name

    resolved_run_name = _slugify(
        (run_name or Prompt.ask(prompt_label, default=default_run_name)).strip()
    )
    return f"{resolved_run_name}/checkpoints/best_model.pt", resolved_run_name


def _resolve_evaluation_split(layout: dict, requested_split: Optional[str]) -> str:
    if layout["mode"] == "pre_split":
        options = [("auto", "Prefer test, then val, then train"), ("train", "Evaluate training split"), ("val", "Evaluate validation split")]
        if layout["test_count"] > 0:
            options.append(("test", "Evaluate test split"))
    else:
        options = [("auto", "Use validation subset"), ("train", "Evaluate training subset"), ("val", "Evaluate validation subset")]

    valid_values = [item[0] for item in options]
    if requested_split:
        if requested_split not in valid_values:
            raise typer.BadParameter(
                f"Unsupported split '{requested_split}'. Choose one of: {', '.join(valid_values)}"
            )
        return requested_split

    console.print("\n[bold cyan]Step 2: Choose evaluation split[/bold cyan]")
    selected_index = arrow_select(options, title="Select split", default=0)
    return options[selected_index][0]


def _resolve_export_formats(format_name: Optional[str]) -> list[str]:
    format_options = [
        ("all", "Export both ONNX and TorchScript"),
        ("onnx", "Export only ONNX"),
        ("torchscript", "Export only TorchScript"),
    ]
    valid_values = [item[0] for item in format_options]

    if format_name:
        if format_name not in valid_values:
            raise typer.BadParameter(
                f"Unsupported export format '{format_name}'. Choose one of: {', '.join(valid_values)}"
            )
        resolved = format_name
    else:
        console.print("\n[bold cyan]Step 2: Choose export format[/bold cyan]")
        selected_index = arrow_select(format_options, title="Select export format", default=0)
        resolved = format_options[selected_index][0]

    if resolved == "all":
        return ["onnx", "torchscript"]
    return [resolved]


@app.command("train")
def train(
    dataset: Optional[str] = typer.Option(None, "--dataset", "-d", help="Local dataset folder"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="TorchVision classification model"),
    gpu: Optional[str] = typer.Option(None, "--gpu", "-g", help="Modal GPU type"),
    epochs: Optional[int] = typer.Option(None, "--epochs", help="Training epochs"),
    batch_size: Optional[int] = typer.Option(None, "--batch-size", help="Batch size"),
    image_size: Optional[int] = typer.Option(None, "--image-size", help="Input resolution"),
    learning_rate: Optional[float] = typer.Option(None, "--learning-rate", "--lr", help="Learning rate"),
    validation_split: Optional[float] = typer.Option(
        None,
        "--validation-split",
        help="Validation fraction when the dataset is not pre-split",
    ),
    pretrained: bool = typer.Option(True, "--pretrained/--no-pretrained", help="Initialize from pretrained weights"),
    mixed_precision: bool = typer.Option(
        True,
        "--mixed-precision/--no-mixed-precision",
        help="Use automatic mixed precision on GPU",
    ),
    artifact_volume: str = typer.Option(
        DEFAULT_ARTIFACT_VOLUME,
        "--artifact-volume",
        help="Modal Volume name for checkpoints and metrics",
    ),
):
    """
    Launch an end-to-end image classification training job on Modal GPUs.

    The command validates a local dataset, prompts for the important training
    settings, generates a complete Modal runner, and then executes it.
    """

    console.print(
        Panel.fit(
            "[bold magenta]m-gpux Vision Train[/bold magenta]\n"
            "Train an image classification model from a local dataset on Modal.",
            border_style="cyan",
        )
    )

    selected_profile = _select_profile()
    if selected_profile is None:
        raise typer.Exit(1)
    _activate_profile(selected_profile)

    dataset_root = _resolve_dataset_path(dataset)
    dataset_layout = _inspect_dataset_layout(dataset_root)
    _render_dataset_summary(dataset_root, dataset_layout)

    selected_gpu = _resolve_gpu_name(gpu)
    model_config = _resolve_model_config(model)

    console.print("\n[bold cyan]Step 3: Configure training[/bold cyan]")

    if dataset_layout["mode"] in {"single_root", "train_only"}:
        resolved_validation_split = validation_split if validation_split is not None else FloatPrompt.ask(
            "Validation split",
            default=0.2,
        )
        if not 0.05 <= resolved_validation_split < 0.5:
            raise typer.BadParameter("Validation split must be between 0.05 and 0.5.")
    else:
        resolved_validation_split = 0.0

    resolved_epochs = epochs if epochs is not None else IntPrompt.ask("Epochs", default=10)
    resolved_batch_size = (
        batch_size
        if batch_size is not None
        else IntPrompt.ask("Batch size", default=model_config["batch_size"])
    )
    resolved_image_size = (
        image_size
        if image_size is not None
        else IntPrompt.ask("Image size", default=model_config["image_size"])
    )
    resolved_learning_rate = (
        learning_rate
        if learning_rate is not None
        else FloatPrompt.ask("Learning rate", default=3e-4)
    )
    optimizer_name = _prompt_optimizer()
    scheduler_name = _prompt_scheduler()
    augmentation_name = _prompt_augmentation()

    weight_decay = FloatPrompt.ask("Weight decay", default=1e-4)
    momentum = FloatPrompt.ask("Momentum (used by SGD/RMSprop)", default=0.9)
    label_smoothing = FloatPrompt.ask("Label smoothing", default=0.0)
    dropout = FloatPrompt.ask("Head dropout", default=0.0)
    grad_accumulation_steps = IntPrompt.ask("Gradient accumulation steps", default=1)
    num_workers = IntPrompt.ask("Data loader workers", default=4)
    seed = IntPrompt.ask("Random seed", default=42)
    timeout_hours = FloatPrompt.ask("Timeout in hours", default=8.0)
    early_stopping_patience = IntPrompt.ask(
        "Early stopping patience (0 disables)",
        default=5,
    )
    freeze_backbone = Confirm.ask("Freeze backbone and train only the classification head?", default=False)

    default_experiment = (
        f"imgclf-{_slugify(model_config['name'])}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    experiment_name = Prompt.ask("Experiment name", default=default_experiment).strip()
    experiment_name = _slugify(experiment_name)

    dataset_ignore_input = Prompt.ask(
        "Dataset ignore patterns (comma-separated)",
        default=",".join(DEFAULT_DATASET_IGNORES),
    )
    dataset_ignore_patterns = [
        pattern.strip()
        for pattern in dataset_ignore_input.split(",")
        if pattern.strip()
    ]

    config = {
        "experiment_name": experiment_name,
        "model_name": model_config["name"],
        "gpu": selected_gpu,
        "dataset_mode": dataset_layout["mode"],
        "pretrained": pretrained,
        "validation_split": resolved_validation_split,
        "epochs": resolved_epochs,
        "batch_size": resolved_batch_size,
        "image_size": resolved_image_size,
        "learning_rate": resolved_learning_rate,
        "optimizer": optimizer_name,
        "scheduler": scheduler_name,
        "weight_decay": weight_decay,
        "momentum": momentum,
        "label_smoothing": label_smoothing,
        "dropout": dropout,
        "augmentation": augmentation_name,
        "mixed_precision": mixed_precision,
        "num_workers": num_workers,
        "seed": seed,
        "early_stopping_patience": early_stopping_patience,
        "freeze_backbone": freeze_backbone,
        "grad_accumulation_steps": grad_accumulation_steps,
    }

    summary = Table(title="Training Plan")
    summary.add_column("Setting", style="cyan")
    summary.add_column("Value", style="white")
    summary.add_row("Profile", selected_profile)
    summary.add_row("GPU", selected_gpu)
    summary.add_row("Model", model_config["name"])
    summary.add_row("Dataset", str(dataset_root))
    summary.add_row("Dataset mode", dataset_layout["mode"])
    summary.add_row("Experiment", experiment_name)
    summary.add_row("Epochs", str(resolved_epochs))
    summary.add_row("Batch size", str(resolved_batch_size))
    summary.add_row("Image size", str(resolved_image_size))
    summary.add_row("Optimizer", optimizer_name)
    summary.add_row("Scheduler", scheduler_name)
    summary.add_row("Learning rate", str(resolved_learning_rate))
    summary.add_row("Artifact volume", artifact_volume)
    console.print()
    console.print(summary)

    timeout_seconds = max(3600, int(timeout_hours * 3600))
    script = VISION_TEMPLATE
    script = script.replace("__CONFIG__", pformat(config, sort_dicts=False, width=100))
    script = script.replace("__LOCAL_DATASET_PATH__", repr(dataset_root.as_posix()))
    script = script.replace("__REMOTE_DATASET_PATH__", repr("/dataset"))
    script = script.replace("__DATASET_IGNORE_PATTERNS__", repr(dataset_ignore_patterns))
    script = script.replace("__ARTIFACT_VOLUME_NAME__", repr(artifact_volume))
    script = script.replace("__TIMEOUT_SECONDS__", str(timeout_seconds))

    execute_modal_temp_script(
        script,
        f"image classification training ({model_config['name']}) on {selected_gpu}",
        detach=False,
    )


@app.command("predict")
def predict(
    input_path: Optional[str] = typer.Option(
        None,
        "--input",
        "-i",
        help="Local image file or folder for inference",
    ),
    run_name: Optional[str] = typer.Option(
        None,
        "--run-name",
        help="Experiment/run name inside the artifact volume",
    ),
    checkpoint_path: Optional[str] = typer.Option(
        None,
        "--checkpoint-path",
        help="Checkpoint path inside the artifact volume",
    ),
    gpu: Optional[str] = typer.Option(None, "--gpu", "-g", help="Modal GPU type"),
    top_k: Optional[int] = typer.Option(None, "--top-k", help="Number of classes to return per image"),
    batch_size: Optional[int] = typer.Option(None, "--batch-size", help="Inference batch size"),
    max_images: Optional[int] = typer.Option(
        None,
        "--max-images",
        help="Optional cap on images processed from an input folder",
    ),
    mixed_precision: bool = typer.Option(
        True,
        "--mixed-precision/--no-mixed-precision",
        help="Use automatic mixed precision on GPU",
    ),
    artifact_volume: str = typer.Option(
        DEFAULT_ARTIFACT_VOLUME,
        "--artifact-volume",
        help="Modal Volume name that stores checkpoints and predictions",
    ),
):
    """
    Run image classification inference on local images using a saved Modal checkpoint.
    """

    console.print(
        Panel.fit(
            "[bold magenta]m-gpux Vision Predict[/bold magenta]\n"
            "Load a saved checkpoint from Modal Volume and classify local images.",
            border_style="cyan",
        )
    )

    selected_profile = _select_profile()
    if selected_profile is None:
        raise typer.Exit(1)
    _activate_profile(selected_profile)

    resolved_input_path = _resolve_image_input_path(input_path)
    local_images = _collect_local_images(resolved_input_path)
    if not local_images:
        raise typer.BadParameter("No supported image files found in the provided input path.")

    selected_gpu = _resolve_gpu_name(gpu)
    resolved_top_k = top_k if top_k is not None else IntPrompt.ask("Top-k predictions per image", default=3)
    resolved_batch_size = batch_size if batch_size is not None else IntPrompt.ask("Batch size", default=16)
    num_workers = IntPrompt.ask("Data loader workers", default=2)
    timeout_hours = FloatPrompt.ask("Timeout in hours", default=2.0)

    if checkpoint_path:
        resolved_checkpoint_path = checkpoint_path.strip().lstrip("/").replace("\\", "/")
        inferred_run_name = Path(resolved_checkpoint_path).parts[0] if Path(resolved_checkpoint_path).parts else "predictions"
    else:
        resolved_run_name = (run_name or Prompt.ask("Experiment / run name", default="imgclf-run")).strip()
        resolved_run_name = _slugify(resolved_run_name)
        resolved_checkpoint_path = f"{resolved_run_name}/checkpoints/best_model.pt"
        inferred_run_name = resolved_run_name

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default_output_json = f"{inferred_run_name}/predictions/predictions-{timestamp}.json"
    output_json_path = Prompt.ask(
        "Output JSON path inside artifact volume",
        default=default_output_json,
    ).strip().lstrip("/").replace("\\", "/")

    input_addition, remote_input_path, input_mode = _build_prediction_input_addition(resolved_input_path)

    summary = Table(title="Prediction Plan")
    summary.add_column("Setting", style="cyan")
    summary.add_column("Value", style="white")
    summary.add_row("Profile", selected_profile)
    summary.add_row("GPU", selected_gpu)
    summary.add_row("Input", str(resolved_input_path))
    summary.add_row("Images", str(len(local_images) if max_images is None else min(len(local_images), max_images)))
    summary.add_row("Checkpoint", resolved_checkpoint_path)
    summary.add_row("Artifact volume", artifact_volume)
    summary.add_row("Top-k", str(resolved_top_k))
    summary.add_row("Batch size", str(resolved_batch_size))
    summary.add_row("Output JSON", output_json_path)
    console.print()
    console.print(summary)

    config = {
        "gpu": selected_gpu,
        "batch_size": resolved_batch_size,
        "num_workers": num_workers,
        "mixed_precision": mixed_precision,
        "fallback_image_size": 224,
    }

    timeout_seconds = max(1800, int(timeout_hours * 3600))
    script = PREDICT_TEMPLATE
    script = script.replace("__CONFIG__", pformat(config, sort_dicts=False, width=100))
    script = script.replace("__ARTIFACT_VOLUME_NAME__", repr(artifact_volume))
    script = script.replace("__CHECKPOINT_PATH__", repr(resolved_checkpoint_path))
    script = script.replace("__REMOTE_INPUT_PATH__", repr(remote_input_path))
    script = script.replace("__INPUT_MODE__", repr(input_mode))
    script = script.replace("__TIMEOUT_SECONDS__", str(timeout_seconds))
    script = script.replace("__OUTPUT_JSON_PATH__", repr(output_json_path))
    script = script.replace("__TOP_K__", str(resolved_top_k))
    script = script.replace("__MAX_IMAGES__", "None" if max_images is None else str(max_images))
    script = script.replace("__INPUT_ADDITION__", input_addition)

    execute_modal_temp_script(
        script,
        f"image classification prediction on {selected_gpu}",
        detach=False,
    )


@app.command("evaluate")
def evaluate(
    dataset: Optional[str] = typer.Option(None, "--dataset", "-d", help="Local dataset folder"),
    run_name: Optional[str] = typer.Option(
        None,
        "--run-name",
        help="Experiment/run name inside the artifact volume",
    ),
    checkpoint_path: Optional[str] = typer.Option(
        None,
        "--checkpoint-path",
        help="Checkpoint path inside the artifact volume",
    ),
    gpu: Optional[str] = typer.Option(None, "--gpu", "-g", help="Modal GPU type"),
    split: Optional[str] = typer.Option(
        None,
        "--split",
        help="Dataset split to evaluate: auto, train, val, or test when available",
    ),
    top_k: Optional[int] = typer.Option(None, "--top-k", help="Top-k accuracy to compute"),
    batch_size: Optional[int] = typer.Option(None, "--batch-size", help="Evaluation batch size"),
    validation_split: Optional[float] = typer.Option(
        None,
        "--validation-split",
        help="Fallback validation split for single-root datasets when checkpoint metadata is missing",
    ),
    mixed_precision: bool = typer.Option(
        True,
        "--mixed-precision/--no-mixed-precision",
        help="Use automatic mixed precision on GPU",
    ),
    artifact_volume: str = typer.Option(
        DEFAULT_ARTIFACT_VOLUME,
        "--artifact-volume",
        help="Modal Volume name that stores checkpoints and evaluation reports",
    ),
):
    """
    Evaluate a saved image-classification checkpoint on a local dataset.
    """

    console.print(
        Panel.fit(
            "[bold magenta]m-gpux Vision Evaluate[/bold magenta]\n"
            "Score a saved checkpoint on a local dataset and persist the report.",
            border_style="cyan",
        )
    )

    selected_profile = _select_profile()
    if selected_profile is None:
        raise typer.Exit(1)
    _activate_profile(selected_profile)

    dataset_root = _resolve_dataset_path(dataset)
    dataset_layout = _inspect_dataset_layout(dataset_root)
    _render_dataset_summary(dataset_root, dataset_layout)

    resolved_split = _resolve_evaluation_split(dataset_layout, split)
    resolved_checkpoint_path, inferred_run_name = _resolve_checkpoint_reference(
        run_name,
        checkpoint_path,
    )
    selected_gpu = _resolve_gpu_name(gpu)
    resolved_top_k = top_k if top_k is not None else IntPrompt.ask("Top-k accuracy", default=5)
    resolved_batch_size = batch_size if batch_size is not None else IntPrompt.ask("Batch size", default=32)
    num_workers = IntPrompt.ask("Data loader workers", default=2)
    timeout_hours = FloatPrompt.ask("Timeout in hours", default=2.0)

    dataset_ignore_input = Prompt.ask(
        "Dataset ignore patterns (comma-separated)",
        default=",".join(DEFAULT_DATASET_IGNORES),
    )
    dataset_ignore_patterns = [
        pattern.strip()
        for pattern in dataset_ignore_input.split(",")
        if pattern.strip()
    ]

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default_output_json = f"{inferred_run_name}/evaluations/eval-{resolved_split}-{timestamp}.json"
    output_json_path = _normalize_volume_path(
        Prompt.ask(
            "Output JSON path inside artifact volume",
            default=default_output_json,
        )
    )

    summary = Table(title="Evaluation Plan")
    summary.add_column("Setting", style="cyan")
    summary.add_column("Value", style="white")
    summary.add_row("Profile", selected_profile)
    summary.add_row("GPU", selected_gpu)
    summary.add_row("Dataset", str(dataset_root))
    summary.add_row("Dataset mode", dataset_layout["mode"])
    summary.add_row("Requested split", resolved_split)
    summary.add_row("Checkpoint", resolved_checkpoint_path)
    summary.add_row("Top-k", str(resolved_top_k))
    summary.add_row("Batch size", str(resolved_batch_size))
    summary.add_row("Artifact volume", artifact_volume)
    summary.add_row("Output JSON", output_json_path)
    console.print()
    console.print(summary)

    config = {
        "gpu": selected_gpu,
        "batch_size": resolved_batch_size,
        "num_workers": num_workers,
        "mixed_precision": mixed_precision,
        "fallback_image_size": 224,
        "dataset_mode": dataset_layout["mode"],
        "split": resolved_split,
        "fallback_validation_split": validation_split if validation_split is not None else 0.2,
        "fallback_seed": 42,
    }

    timeout_seconds = max(1800, int(timeout_hours * 3600))
    script = EVALUATE_TEMPLATE
    script = script.replace("__CONFIG__", pformat(config, sort_dicts=False, width=100))
    script = script.replace("__LOCAL_DATASET_PATH__", repr(dataset_root.as_posix()))
    script = script.replace("__REMOTE_DATASET_PATH__", repr("/dataset"))
    script = script.replace("__DATASET_IGNORE_PATTERNS__", repr(dataset_ignore_patterns))
    script = script.replace("__ARTIFACT_VOLUME_NAME__", repr(artifact_volume))
    script = script.replace("__CHECKPOINT_PATH__", repr(resolved_checkpoint_path))
    script = script.replace("__OUTPUT_JSON_PATH__", repr(output_json_path))
    script = script.replace("__TIMEOUT_SECONDS__", str(timeout_seconds))
    script = script.replace("__TOP_K__", str(resolved_top_k))

    execute_modal_temp_script(
        script,
        f"image classification evaluation on {selected_gpu}",
        detach=False,
    )


@app.command("export")
def export(
    run_name: Optional[str] = typer.Option(
        None,
        "--run-name",
        help="Experiment/run name inside the artifact volume",
    ),
    checkpoint_path: Optional[str] = typer.Option(
        None,
        "--checkpoint-path",
        help="Checkpoint path inside the artifact volume",
    ),
    export_format: Optional[str] = typer.Option(
        None,
        "--format",
        help="Export format: onnx, torchscript, or all",
    ),
    output_dir: Optional[str] = typer.Option(
        None,
        "--output-dir",
        help="Output directory inside the artifact volume",
    ),
    artifact_volume: str = typer.Option(
        DEFAULT_ARTIFACT_VOLUME,
        "--artifact-volume",
        help="Modal Volume name that stores checkpoints and exported artifacts",
    ),
):
    """
    Export a saved checkpoint to ONNX and/or TorchScript.
    """

    console.print(
        Panel.fit(
            "[bold magenta]m-gpux Vision Export[/bold magenta]\n"
            "Convert a saved checkpoint into deployable ONNX and TorchScript artifacts.",
            border_style="cyan",
        )
    )

    selected_profile = _select_profile()
    if selected_profile is None:
        raise typer.Exit(1)
    _activate_profile(selected_profile)

    resolved_checkpoint_path, inferred_run_name = _resolve_checkpoint_reference(
        run_name,
        checkpoint_path,
    )
    resolved_formats = _resolve_export_formats(export_format)
    timeout_hours = FloatPrompt.ask("Timeout in hours", default=1.0)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default_output_dir = f"{inferred_run_name}/exports/export-{timestamp}"
    resolved_output_dir = _normalize_volume_path(
        output_dir
        or Prompt.ask(
            "Output directory inside artifact volume",
            default=default_output_dir,
        )
    )

    summary = Table(title="Export Plan")
    summary.add_column("Setting", style="cyan")
    summary.add_column("Value", style="white")
    summary.add_row("Profile", selected_profile)
    summary.add_row("Checkpoint", resolved_checkpoint_path)
    summary.add_row("Formats", ", ".join(resolved_formats))
    summary.add_row("Artifact volume", artifact_volume)
    summary.add_row("Output dir", resolved_output_dir)
    console.print()
    console.print(summary)

    config = {
        "formats": resolved_formats,
        "fallback_image_size": 224,
    }

    timeout_seconds = max(900, int(timeout_hours * 3600))
    script = EXPORT_TEMPLATE
    script = script.replace("__CONFIG__", pformat(config, sort_dicts=False, width=100))
    script = script.replace("__ARTIFACT_VOLUME_NAME__", repr(artifact_volume))
    script = script.replace("__CHECKPOINT_PATH__", repr(resolved_checkpoint_path))
    script = script.replace("__OUTPUT_DIR__", repr(resolved_output_dir))
    script = script.replace("__TIMEOUT_SECONDS__", str(timeout_seconds))

    execute_modal_temp_script(
        script,
        "image classification export",
        detach=False,
    )
