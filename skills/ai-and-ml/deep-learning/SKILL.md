---
name: deep-learning
description: Design, train, and debug neural networks—architecture selection, data loading, mixed precision, gradient problems, and reproducible experiment discipline.
metadata:
  domain: ai-and-ml
  version: 1.0.0
  risk: medium
---

# Deep Learning

## 1. Purpose

Build neural networks that train reliably and are diagnosable when they do not. This skill covers architecture selection against the data type, the training loop (optimizer, schedule, precision, augmentation), the classic failure signatures (loss not moving, NaNs, overfitting, underfitting, dead ReLUs, exploding gradients), and the reproducibility practices that make experiments trustworthy.

**Scope:** your own compute and data. GPU jobs are expensive—budget them, checkpoint often, and avoid leaving idle instances running.

## 2. Activation Conditions

- Training a CNN, transformer, or MLP for a real task.
- Loss is stuck, diverging, or producing NaNs.
- Need to decide architecture, batch size, or precision strategy.
- Porting a research repo to a production training pipeline.
- Keywords: PyTorch, neural network, training loop, overfitting, gradient clipping, mixed precision, AMP, learning rate schedule, DataLoader, GPU memory, checkpoint.

## 3. When Not to Use

- Tabular problems where gradient boosting wins (try that first).
- Fine-tuning an LLM (use llm-integration / local-llm-deployment).
- Model compression after training (use model-quantization / model-optimization).

## 4. Required Context

1. Task type: classification, detection, segmentation, regression, generation, embedding.
2. Dataset size, label quality, and class balance.
3. Compute: GPU model and memory, number of devices, time budget.
4. Baseline: classical model or pretrained network result.
5. Constraints: inference latency, model size, training reproducibility.

## 5. Operating Procedure

1. **Start from a known-good baseline**: pretrained backbone for vision/NLP, a small MLP for tabular. Prove the pipeline learns on a tiny subset (overfit 100 samples to loss ≈ 0) before scaling.
2. **Inspect the data pipeline** before the model: shapes, dtypes, label alignment, augmentation sanity, normalization statistics computed on train only.
3. **Set up a deterministic run**: seed everything, record library/CUDA versions, log configs.
4. **Choose architecture** matched to data type and budget; prefer smaller models with more epochs over huge models when data is limited.
5. **Configure training**: AdamW (lr 1e-4–3e-4 for fine-tuning, higher for small models), cosine or warmup+linear schedule, weight decay, gradient clipping (1.0), mixed precision (bf16/fp16 with loss scaling).
6. **Use a validation split and an epoch-level checkpoint** of the best metric, not the last epoch.
7. **Monitor learning curves**: train/val loss gap (overfit), both flat (lr too low / bug), oscillation (lr too high).
8. **Debug in this order**: data → labels → loss function → architecture → hyperparameters. Most "model doesn't learn" bugs are data bugs.
9. **Regularize** as needed: augmentation, dropout, weight decay, early stopping, label smoothing.
10. **Reproduce** the reported result from the saved config in a clean run.
11. **Export** the model (TorchScript/ONNX) and verify numerical parity with the PyTorch output.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Frameworks | PyTorch, JAX/Flax, TensorFlow/Keras |
| Training helpers | PyTorch Lightning, Hugging Face `Trainer`, Accelerate |
| Data | `torch.utils.data.DataLoader`, DALI, `webdataset` |
| Experiment tracking | MLflow, W&B, TensorBoard |
| Profiling | `torch.profiler`, Nsight Systems, `nvidia-smi` |
| Export | `torch.onnx.export`, TorchScript, TensorRT |
| Distributed | DDP, FSDP, DeepSpeed |

## 7. Practical Implementation

**Minimal, correct training loop (PyTorch):**

```python
import torch, torch.nn as nn
from torch.utils.data import DataLoader

def set_seed(seed: int = 42) -> None:
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

set_seed()
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

model = nn.Sequential(
    nn.Conv2d(3, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(),
    nn.MaxPool2d(2),
    nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
    nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Linear(64, 10),
).to(device)

criterion = nn.CrossEntropyLoss(label_smoothing=0.05)
optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=0.05)
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=30)
scaler = torch.amp.GradScaler("cuda", enabled=torch.cuda.is_available())

train_loader = DataLoader(train_ds, batch_size=64, shuffle=True, num_workers=4,
                          pin_memory=True, persistent_workers=True)
val_loader = DataLoader(val_ds, batch_size=128, shuffle=False, num_workers=4)

best_val = float("inf")
for epoch in range(30):
    model.train()
    for x, y in train_loader:
        x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            loss = criterion(model(x), y)
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        scaler.step(optimizer)
        scaler.update()

    model.eval()
    val_loss, correct, total = 0.0, 0, 0
    with torch.inference_mode():
        for x, y in val_loader:
            x, y = x.to(device), y.to(device)
            logits = model(x)
            val_loss += criterion(logits, y).item() * y.size(0)
            correct += (logits.argmax(1) == y).sum().item()
            total += y.size(0)
    val_loss /= total
    print(f"epoch={epoch:02d} val_loss={val_loss:.4f} acc={correct/total:.4f} "
          f"lr={scheduler.get_last_lr()[0]:.2e}")
    if val_loss < best_val:
        best_val = val_loss
        torch.save({"model": model.state_dict(), "epoch": epoch, "val_loss": best_val},
                   "checkpoints/best.pt")
    scheduler.step()
```

**Overfit-a-batch sanity check (run this on every new pipeline):**

```python
x, y = next(iter(train_loader))
x, y = x[:8].to(device), y[:8].to(device)
model.train()
for step in range(200):
    optimizer.zero_grad()
    loss = criterion(model(x), y)
    loss.backward(); optimizer.step()
    if step % 50 == 0:
        print(step, float(loss))
# Expect loss -> near 0. If not, the bug is in data, labels, or loss.
```

**Detect dead ReLUs / saturated activations:**

```python
def activation_stats(model, x):
    stats = {}
    for name, m in model.named_modules():
        if isinstance(m, (torch.nn.ReLU, torch.nn.GELU)):
            out = m(x)
            stats[name] = float((out == 0).float().mean())
    return stats
```

**Onion-style augmentation and normalization (correct order, train statistics only):**

```python
from torchvision import transforms

train_tf = transforms.Compose([
    transforms.RandomResizedCrop(224, scale=(0.7, 1.0)),
    transforms.RandomHorizontalFlip(),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])
val_tf = transforms.Compose([
    transforms.Resize(256), transforms.CenterCrop(224), transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])
```

**Memory/throughput profiling:**

```bash
python -m torch.utils.bottleneck train.py
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv -l 2
```

**Export and verify parity:**

```python
import torch
model.eval()
dummy = torch.randn(1, 3, 224, 224, device=device)
torch.onnx.export(model, dummy, "model.onnx", input_names=["input"],
                  output_names=["logits"], opset_version=17, dynamic_axes={"input": {0: "batch"}})
with torch.inference_mode():
    ref = model(dummy).cpu().numpy()
import onnxruntime as ort
sess = ort.InferenceSession("model.onnx", providers=["CPUExecutionProvider"])
got = sess.run(None, {"input": dummy.cpu().numpy()})[0]
assert abs(ref - got).max() < 1e-3, "ONNX parity check failed"
```

## 8. Quality Standards

- The pipeline passes the overfit-a-batch test before any long run.
- Normalization statistics come from training data only.
- Validation is a held-out, non-leaking split; the best checkpoint is chosen by validation metric.
- Seeds, versions, and configs are recorded; runs are reproducible within documented nondeterminism.
- Mixed precision used with a scaler where needed and verified not to degrade accuracy.
- Exported model matches the PyTorch output within a stated tolerance.
- GPU utilization and memory are logged during training to detect data-loader starvation.

## 9. Verification and Testing

```bash
pytest -q tests/test_model_shapes.py tests/test_dataloader.py
python train.py --config configs/small.yaml --max-steps 50   # smoke test
python evaluate.py --ckpt checkpoints/best.pt --split test
```

Tests to include: forward pass output shapes for representative batch sizes; dataloader yields correctly aligned batches; augmentation is deterministic under a fixed seed; loss is finite for 10 steps; exported ONNX matches; the model beats the baseline on the test set.

## 10. Security Considerations

- Training data may contain PII or copyrighted material; keep datasets access-controlled and document provenance.
- Loading `.pt`/`.pkl` checkpoints executes pickle code: only load artifacts you produced or verified.
- Pretrained weights from unknown sources can contain malicious pickles—prefer safetensors and official repositories.
- GPU nodes often have broad network access; restrict egress and do not store cloud credentials on training hosts.
- Adversarial robustness is a separate concern: evaluate on perturbed inputs if the model is security-relevant.
- Model weights can leak training data (membership inference); avoid shipping models trained on sensitive data without review.

## 11. Failure Handling

- **Loss NaN:** reduce learning rate, disable AMP briefly to isolate, check for `log(0)`, division by zero, or inf in inputs; clip gradients.
- **Loss not decreasing:** verify labels align with inputs (visualize a batch), check the loss function matches the task (CrossEntropy vs. BCEWithLogits), and confirm the optimizer holds the right parameters.
- **Val loss rises while train falls:** overfitting—add augmentation/weight decay/dropout, reduce capacity, or gather more data; use early stopping.
- **Train and val both flat:** learning rate too low, frozen layers, or a broken data path (all-zero inputs).
- **OOM:** reduce batch size, enable gradient accumulation/checkpointing, use bf16, or shard with FSDP.
- **Slow epochs with low GPU utilization:** data loader bottleneck—increase `num_workers`, use `pin_memory`, precompute/decode ahead of time (e.g. webdataset/ffcv).
- **Results not reproducible:** nondeterministic ops (some cuDNN kernels, atomics); fix seeds and set deterministic flags, accepting a throughput cost.

## 12. Expected Deliverables

1. Training script with config file and seeded run.
2. Data pipeline with sanity checks and augmentation policy.
3. Learning-curve evidence and best checkpoint.
4. Baseline comparison table.
5. Export artifact and parity verification.
6. Documented hyperparameters and reproducible command.

## 13. References

- PyTorch tutorials — https://pytorch.org/tutorials/
- PyTorch AMP recipe — https://pytorch.org/tutorials/recipes/recipes/amp_recipe.html
- fast.ai "Practical Deep Learning" — https://course.fast.ai/
- "Deep Learning" (Goodfellow, Bengio, Courville) — https://www.deeplearningbook.org/
- Hugging Face Transformers docs — https://huggingface.co/docs/transformers/
- Karpathy, "A Recipe for Training Neural Networks" — http://karpathy.github.io/2019/04/25/recipe/
