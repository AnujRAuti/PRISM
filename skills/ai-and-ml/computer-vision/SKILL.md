---
name: computer-vision
description: Build vision systems—classification, detection, segmentation—with pretrained backbones, correct augmentation, annotation QA, and deployment that matches training preprocessing.
metadata:
  domain: ai-and-ml
  version: 1.0.0
  risk: medium
---

# Computer Vision

## 1. Purpose

Deliver working vision models for classification, object detection, and segmentation with correct data handling and deployment parity. Vision pipelines fail in specific ways: augmentation mismatched between train and inference, broken color spaces, annotation errors, and evaluation metrics that hide per-class failures. This skill covers backbone selection, transfer learning, annotation quality control, and inference-time preprocessing that matches training exactly.

**Scope:** images you have the right to use. Face/identity recognition and surveillance applications carry legal and ethical constraints—confirm permissible use before building.

## 2. Activation Conditions

- Image classification, detection, segmentation, keypoints, or OCR tasks.
- Fine-tuning a pretrained vision model.
- Debugging a vision model that performs well offline but poorly in deployment.
- Designing an image annotation or QA process.
- Keywords: CNN, ViT, YOLO, segmentation, detection, mAP, IoU, augmentation, transfer learning, OpenCV, torchvision, ONNX.

## 3. When Not to Use

- Pure classical image processing with a deterministic algorithm (thresholding, template matching) — write the algorithm.
- Video analytics with heavy temporal modeling where a dedicated pipeline exists.
- OCR of text documents where a document-AI service already solves the problem well.

## 4. Required Context

1. Task and output format (class label, boxes, masks, keypoints).
2. Dataset size, class distribution, and annotation source/quality.
3. Deployment target: cloud GPU, edge device, mobile; latency and memory budgets.
4. Image acquisition conditions: camera, lighting, resolution, expected variation.
5. Privacy classification of images (faces, license plates, documents).

## 5. Operating Procedure

1. **Baseline first**: zero-shot pretrained model or a linear probe on frozen features. Record its metric.
2. **Audit annotations**: sample 100 images, verify labels/boxes/masks, measure inter-annotator agreement if possible, and fix systematic errors.
3. **Split by acquisition group**, not randomly: images from the same session/device/scene must not straddle train and test (near-duplicate leakage is severe in vision).
4. **Choose the architecture**: ResNet/EfficientNet/ConvNeXt for classification; YOLO/RT-DETR/Faster R-CNN for detection; U-Net/Mask2Former for segmentation; ViT for large datasets.
5. **Match preprocessing exactly** between training and inference: resize interpolation, crop strategy, color order (RGB vs BGR), normalization constants, and channel layout.
6. **Augment for invariance, not for volume**: flips/hue only if semantically valid (no horizontal flip for text or left/right-specific classes).
7. **Train with transfer learning**: freeze backbone initially, then unfreeze at a lower learning rate; use discriminative learning rates.
8. **Evaluate per class and at the right IoU** (mAP@0.5 and mAP@0.5:0.95 for detection; per-class IoU/Dice for segmentation).
9. **Inspect failure cases visually**: build a montage of top losses; errors often cluster by lighting, occlusion, or a specific class.
10. **Optimize for deployment** (ONNX/TensorRT/quantization) and re-verify metrics after conversion.
11. **Serve with the same preprocessing library version**; pin and test.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Frameworks | PyTorch, torchvision, timm, Ultralytics, Detectron2, MMDetection |
| Classical CV | OpenCV, scikit-image, Pillow |
| Augmentation | torchvision.transforms v2, Albumentations |
| Annotation | CVAT, Label Studio, Roboflow |
| Evaluation | `pycocotools`, torchmetrics detection metrics |
| Export | ONNX, TensorRT, Core ML, TFLite |
| Visualization | matplotlib, FiftyOne |

## 7. Practical Implementation

**Shared transform definition used for train and inference:**

```python
import torch
from torchvision import transforms
from PIL import Image

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

def build_transform(train: bool, image_size: int = 224) -> transforms.Compose:
    if train:
        return transforms.Compose([
            transforms.RandomResizedCrop(image_size, scale=(0.65, 1.0), ratio=(0.8, 1.25)),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
            transforms.RandomErasing(p=0.25, scale=(0.02, 0.15)),
        ])
    return transforms.Compose([
        transforms.Resize(int(image_size * 256 / 224)),
        transforms.CenterCrop(image_size),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])

def load_rgb(path: str) -> Image.Image:
    with Image.open(path) as im:
        return im.convert("RGB")      # never rely on the file's native mode
```

**Fine-tune a backbone with discriminative learning rates:**

```python
import timm, torch.nn as nn

model = timm.create_model("convnext_tiny.fb_in22k_ft_in1k", pretrained=True, num_classes=0)
head = nn.Linear(model.num_features, num_classes)

for p in model.parameters():
    p.requires_grad = False
for p in model.stages[-1].parameters():
    p.requires_grad = True

optimizer = torch.optim.AdamW([
    {"params": model.stages[-1].parameters(), "lr": 1e-5},
    {"params": head.parameters(), "lr": 1e-3},
], weight_decay=0.05)
```

**Detection evaluation (COCO-style):**

```python
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval

coco_gt = COCO("annotations/instances_val.json")
coco_dt = coco_gt.loadRes("predictions/val_results.json")
ev = COCOeval(coco_gt, coco_dt, iouType="bbox")
ev.evaluate(); ev.accumulate()
ev.summarize()   # mAP@[.5:.95], mAP@.5, per-size breakdowns
```

**Per-class report (do not ship on the mean alone):**

```python
from sklearn.metrics import classification_report, confusion_matrix
print(classification_report(y_true, y_pred, target_names=class_names, digits=3, zero_division=0))
print(confusion_matrix(y_true, y_pred))
```

**Worst-error montage for inspection:**

```python
import numpy as np, matplotlib.pyplot as plt
from PIL import Image

losses = -(np.log(np.clip(probs[np.arange(len(y_true)), y_true], 1e-9, 1)))
worst = np.argsort(losses)[-16:][::-1]

fig, axes = plt.subplots(4, 4, figsize=(12, 12))
for ax, idx in zip(axes.ravel(), worst):
    ax.imshow(Image.open(paths[idx]).convert("RGB"))
    ax.set_title(f"true={class_names[y_true[idx]]}\npred={class_names[y_pred[idx]]}\np={probs[idx, y_pred[idx]]:.2f}",
                 fontsize=8)
    ax.axis("off")
plt.tight_layout(); plt.savefig("reports/worst_errors.png", dpi=120)
```

**ONNX export and metric re-verification:**

```python
import torch, onnxruntime as ort, numpy as np
model.eval()
torch.onnx.export(model, torch.randn(1, 3, 224, 224), "model.onnx",
                  input_names=["input"], output_names=["logits"],
                  dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
                  opset_version=17)

sess = ort.InferenceSession("model.onnx", providers=["CPUExecutionProvider"])
x = torch.randn(4, 3, 224, 224)
with torch.inference_mode():
    ref = model(x).numpy()
got = sess.run(None, {"input": x.numpy()})[0]
assert np.allclose(ref, got, atol=1e-3), "ONNX parity failed"
```

**Preprocessing parity check (catches the #1 deployment bug):**

```python
def test_preprocess_parity():
    img = load_rgb("tests/fixtures/sample.jpg")
    a = build_transform(train=False)(img)
    b = serving_preprocess("tests/fixtures/sample.jpg")   # production code path
    assert torch.allclose(a, b, atol=1e-5), "train/serve preprocessing mismatch"
```

## 8. Quality Standards

- Splits are grouped by acquisition session/device; duplicate and near-duplicate images are removed across splits.
- Pretrained baseline recorded before fine-tuning.
- Training and inference use one preprocessing implementation, verified by a parity test.
- Metrics reported per class and at the operating threshold; confusion matrix reviewed.
- Augmentations are semantically valid for the task.
- Exported model verified numerically against the original.
- Annotation quality sampled and measured, not assumed.

## 9. Verification and Testing

```bash
pytest -q tests/test_transforms.py tests/test_model_export.py
python scripts/evaluate.py --split val --report reports/val_report.json
python scripts/visual_check.py --n 32    # montages for manual review
```

Expected evidence: parity tests pass; val metrics by class; worst-error montage reviewed with written notes; ONNX vs. PyTorch outputs match; latency measured on the target hardware.

## 10. Security Considerations

- Images are untrusted input: decode in an isolated process, cap dimensions, and guard against decompression bombs (Pillow `MAX_IMAGE_PIXELS`).
- Strip EXIF metadata before storing or serving (GPS, device IDs).
- Face recognition and biometric analysis are regulated in many jurisdictions (GDPR Art. 9, BIPA, India DPDP)—require explicit legal review and consent.
- Adversarial images can evade classifiers; for security-critical use, add detection of anomalous inputs and human review.
- Model files from untrusted sources can execute code on load; use safetensors and verified artifacts only.
- Do not log raw images containing personal data; log hashes/IDs instead.

## 11. Failure Handling

- **Good validation, bad production:** preprocessing mismatch (BGR vs. RGB, resize method), camera/lighting domain shift, or JPEG artifacts. Run the parity test and compare production image statistics to training.
- **Overfitting with small datasets:** freeze more layers, stronger augmentation, or use a larger pretrained model with fewer trainable parameters.
- **Detection mAP low but boxes look right:** check IoU threshold and NMS settings; verify annotations use the same box convention (xywh vs xyxy).
- **Class imbalance:** use class weights or focal loss; report per-class recall for rare classes.
- **Latency too high on edge:** export to TensorRT/TFLite, reduce input resolution, or use a smaller backbone; re-verify accuracy afterwards.

## 12. Expected Deliverables

1. Dataset audit report and grouped split manifest.
2. Baseline metrics from a pretrained model.
3. Training configuration and fine-tuned model.
4. Per-class evaluation and confusion matrix.
5. Worst-error visual report with notes.
6. Exported artifact with parity verification and latency measurement.
7. Serving preprocessing code shared with training.

## 13. References

- torchvision transforms v2 — https://pytorch.org/vision/stable/transforms.html
- timm model library — https://huggingface.co/docs/timm/
- Ultralytics YOLO docs — https://docs.ultralytics.com/
- Albumentations — https://albumentations.ai/docs/
- pycocotools — https://github.com/cocodataset/cocoapi
- FiftyOne dataset inspection — https://docs.voxel51.com/
- "Deep Learning for Computer Vision" (Szeliski, *Computer Vision: Algorithms and Applications*) — https://szeliski.org/Book/
