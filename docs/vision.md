# Vision Training

`m-gpux vision train`, `vision evaluate`, `vision predict`, and `vision export` form a complete image-classification workflow on Modal without making the user rewrite training, evaluation, inference, or export boilerplate.

## What it does

The command:

1. Validates a local dataset folder
2. Prompts for model, GPU, and training hyperparameters
3. Generates a complete `modal_runner.py`
4. Runs the job on Modal
5. Saves checkpoints and metrics to a Modal Volume

## Supported dataset layouts

### Pre-split

```text
dataset/
  train/
    cat/
    dog/
  val/
    cat/
    dog/
  test/
    cat/
    dog/
```

### Single root

```text
dataset/
  cat/
  dog/
```

For a single-root dataset, `m-gpux` creates the validation split automatically.

## Example

```bash
m-gpux vision train --dataset ./data/cats-vs-dogs --model resnet50 --gpu A10G
```

After training, run inference on new images with:

```bash
m-gpux vision predict --input ./samples --run-name imgclf-resnet50-20260420-113500 --gpu T4
```

Evaluate the checkpoint on a dataset split:

```bash
m-gpux vision evaluate --dataset ./data/cats-vs-dogs --run-name imgclf-resnet50-20260420-113500 --split test --gpu T4
```

Export the trained model for deployment:

```bash
m-gpux vision export --run-name imgclf-resnet50-20260420-113500 --format all
```

If you omit those flags, the wizard will guide you through:

- Dataset folder
- Model selection
- GPU selection
- Epochs, batch size, image size
- Optimizer and scheduler
- Augmentation strength
- Mixed precision, early stopping, gradient accumulation
- Artifact volume and experiment name

## Model choices

The built-in picker includes a broad set of TorchVision classification models, including:

- ResNet and Wide ResNet
- ResNeXt
- EfficientNet and EfficientNetV2
- ConvNeXt
- DenseNet
- MobileNet
- ShuffleNet
- RegNet
- Vision Transformer
- Swin Transformer
- MaxVit
- Inception V3

You can also type a custom TorchVision model builder name manually.

## Stored artifacts

Each run is saved into a persistent Modal Volume, by default `m-gpux-vision-artifacts`.

Typical output:

```text
<run-name>/
  checkpoints/
    best_model.pt
    last_model.pt
  config.json
  history.json
  summary.json
  test_metrics.json
  test_report.json
```

Download them later with:

```bash
modal volume get m-gpux-vision-artifacts <run-name>/summary.json summary.json
modal volume get m-gpux-vision-artifacts <run-name>/checkpoints/best_model.pt best_model.pt
```

`vision predict` also writes a JSON report back into the same volume, usually under:

```text
<run-name>/predictions/predictions-YYYYMMDD-HHMMSS.json
```

`vision evaluate` writes JSON metric reports, typically under:

```text
<run-name>/evaluations/eval-<split>-YYYYMMDD-HHMMSS.json
```

`vision export` writes deployment artifacts, typically under:

```text
<run-name>/exports/export-YYYYMMDD-HHMMSS/
  model.onnx
  model.ts
  labels.json
  export_summary.json
```

## Practical notes

- Smaller datasets and simpler models work well with `T4`, `L4`, or `A10G`.
- Transformer backbones and larger ConvNeXt variants usually benefit from `A100`, `H100`, or better.
- Local datasets are forwarded into the container with `Image.add_local_dir`, so very large datasets may take longer to start.
- Checkpoints are persisted with a Modal Volume so they survive container shutdown.
