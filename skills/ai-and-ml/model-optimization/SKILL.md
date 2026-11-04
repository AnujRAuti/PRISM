---
name: model-optimization
description: Make models faster and smaller without unacceptable quality loss—distillation, pruning, fusion, compilation, and runtime selection, validated by measured speed and accuracy.
metadata:
  domain: ai-and-ml
  version: 1.0.0
  risk: medium
---

# Model Optimization

## 1. Purpose

Reduce inference latency, memory, and cost while keeping quality within an agreed tolerance. This skill sequences the optimizations by payoff and risk—graph/runtime optimization first, then precision reduction, then structural changes (pruning/distillation), then specialized compilers—and requires measurement at every step. It also covers the failure mode of optimizing the wrong layer: a model that is 3× faster in isolation but bottlenecked by preprocessing in production.

**Scope:** models you own or are licensed to modify. Respect license terms of pretrained weights when redistributing optimized derivatives.

## 2. Activation Conditions

- Latency or cost targets are missed in serving.
- Model must fit an edge/mobile/CPU-only device.
- GPU memory limits prevent deployment.
- Choosing between quantization, distillation, pruning, and a smaller architecture.
- Keywords: latency, throughput, inference optimization, distillation, pruning, ONNX Runtime, TensorRT, torch.compile, int8, batching, KV cache, model size.

## 3. When Not to Use

- Pure numerical quantization workflows with a specific format (use model-quantization).
- Serving infrastructure problems (batching, autoscaling) that are not model-bound.
- Before you have measured where time is actually spent.

## 4. Required Context

1. Current latency breakdown: preprocessing, inference, postprocessing, network.
2. Hardware target: GPU model, CPU ISA (AVX2/AVX-512), NPU, mobile SoC.
3. Quality tolerance: maximum acceptable metric drop and the evaluation set to prove it.
4. Batch/concurrency profile: single-request low-latency vs. offline bulk.
5. Deployment constraints: framework runtimes allowed in production.

## 5. Operating Procedure

1. **Profile the whole path** first (`torch.profiler`, `nsys`, or simple timing around each stage). Optimize the dominant component.
2. **Establish the quality baseline** on a fixed eval set and record it.
3. **Apply baseline runtime optimizations**: no-grad inference, `model.eval()`, fixed input shapes, fused operators, thread/stream configuration.
4. **Batch where the workload allows**, with a bounded queue and timeout-based batching; measure the latency/throughput trade-off.
5. **Use a compiled runtime**: `torch.compile` for PyTorch; ONNX Runtime or TensorRT for deployment; `openvino` for Intel CPUs.
6. **Reduce precision** (fp16/bf16 → int8) and evaluate quality; keep a full-precision fallback for anomalies.
7. **Prune structurally** (channels/heads/layers) only with fine-tuning to recover accuracy; unstructured sparsity rarely helps on commodity hardware.
8. **Distill** into a smaller student when the target hardware cannot run the teacher acceptably; train on teacher logits plus labels.
9. **Cache where valid**: KV cache for autoregressive decoding, embedding caches, and memoization for identical requests.
10. **Re-measure end-to-end** on target hardware with realistic concurrency; verify quality on the eval set.
11. **Document** the configuration, expected quality delta, and rollback path.

## 6. Tools and Technologies

| Layer | Tools |
|---|---|
| Profiling | `torch.profiler`, Nsight Systems, `perf`, `onnxruntime` profiling |
| Compilation | `torch.compile`, ONNX export, TensorRT, OpenVINO, TVM |
| Precision | AMP, `bitsandbytes`, ONNX Runtime int8, TensorRT fp16/int8 |
| Pruning | `torch.nn.utils.prune`, structured pruning libraries |
| Distillation | Custom teacher-student training, Hugging Face distillation examples |
| Serving | ONNX Runtime, Triton Inference Server, vLLM (LLM), TGI |

## 7. Practical Implementation

**Profile before optimizing:**

```python
import torch, time
from torch.profiler import profile, ProfilerActivity

model.eval()
x = torch.randn(8, 3, 224, 224, device="cuda")

with torch.inference_mode():
    for _ in range(5):
        model(x)                              # warmup
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(50):
        model(x)
    torch.cuda.synchronize()
    print(f"batched latency {(time.perf_counter()-t0)/50*1000:.2f} ms")

with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as prof:
    with torch.inference_mode():
        model(x)
print(prof.key_averages().table(sort_by="cuda_time_total", row_limit=12))
```

**torch.compile with dynamic shapes choice:**

```python
import torch

model = torch.compile(model, mode="max-autotune", fullgraph=False)
# Warm up with the exact input shapes used in production; recompile per distinct shape.
with torch.inference_mode():
    model(torch.randn(1, 3, 224, 224, device="cuda"))
```

**ONNX + ORT with int8 dynamic quantization and accuracy check:**

```python
import numpy as np, onnxruntime as ort
from onnxruntime.quantization import quantize_dynamic, QuantType

quantize_dynamic("model_fp32.onnx", "model_int8.onnx", weight_type=QuantType.QInt8)

so = ort.SessionOptions()
so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
sess_fp32 = ort.InferenceSession("model_fp32.onnx", so, providers=["CPUExecutionProvider"])
sess_int8 = ort.InferenceSession("model_int8.onnx", so, providers=["CPUExecutionProvider"])

x = np.random.randn(8, 3, 224, 224).astype(np.float32)
a = sess_fp32.run(None, {"input": x})[0]
b = sess_int8.run(None, {"input": x})[0]
print("max abs diff:", float(np.abs(a - b).max()))
print("pred agreement:", float((a.argmax(1) == b.argmax(1)).mean()))
```

**Structured pruning with recovery fine-tune:**

```python
import torch.nn.utils.prune as prune

def prune_conv(model, amount: float = 0.2):
    for m in model.modules():
        if isinstance(m, torch.nn.Conv2d):
            prune.ln_structured(m, name="weight", amount=amount, n=2, dim=0)
            prune.remove(m, "weight")     # make the mask permanent
    return model

# Then fine-tune 1–3 epochs at a low LR and re-evaluate.
```

**Distillation loss:**

```python
import torch.nn.functional as F

def distill_loss(student_logits, teacher_logits, labels, T: float = 4.0, alpha: float = 0.6):
    soft = F.kl_div(
        F.log_softmax(student_logits / T, dim=-1),
        F.softmax(teacher_logits / T, dim=-1),
        reduction="batchmean",
    ) * (T * T)
    hard = F.cross_entropy(student_logits, labels)
    return alpha * soft + (1 - alpha) * hard
```

**vLLM serving flags for LLM throughput (illustrative):**

```bash
vllm serve meta-llama/Llama-3.1-8B-Instruct \
  --dtype bfloat16 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --enable-prefix-caching \
  --max-num-seqs 128
```

**End-to-end benchmark harness (latency percentiles under concurrency):**

```python
import concurrent.futures as cf, time, numpy as np

def timed_call(payload):
    t0 = time.perf_counter()
    _ = infer(payload)
    return (time.perf_counter() - t0) * 1000

for concurrency in (1, 8, 32):
    with cf.ThreadPoolExecutor(max_workers=concurrency) as ex:
        lat = list(ex.map(timed_call, payloads[:400]))
    print(f"c={concurrency:3d} p50={np.percentile(lat,50):7.1f}ms "
          f"p95={np.percentile(lat,95):7.1f}ms p99={np.percentile(lat,99):7.1f}ms "
          f"rps={len(lat)/(sum(lat)/1000):.1f}")
```

## 8. Quality Standards

- End-to-end latency is measured, not inferred from kernel times.
- Every optimization has before/after numbers at the same concurrency.
- Quality delta is measured on a fixed eval set and stated explicitly.
- Fallback to the unoptimized path exists for debugging and rollback.
- Input shapes and batch sizes are pinned and validated at the serving layer.
- Compilation artifacts are versioned per model + runtime + hardware.
- Memory usage is reported alongside latency (optimizations often trade one for the other).

## 9. Verification and Testing

```bash
pytest -q tests/test_export_parity.py tests/test_quality_regression.py
python bench/bench_serving.py --concurrency 1,8,32 --requests 400
```

Tests: exported/quantized model matches the reference on a fixture batch within tolerance; task metric on the eval set is within the agreed delta; latency percentiles meet the target at target concurrency; the model handles variable batch sizes without recompilation storms.

## 10. Security Considerations

- Optimized artifacts are still code-adjacent: only load models you built or verified; prefer safetensors.
- Quantized models can behave differently on edge inputs—evaluate on adversarial/edge cases if the model informs security decisions.
- TensorRT/ONNX plugins are native code: pin versions and verify provenance.
- Do not disable input validation to gain speed.
- Distillation can remove safety behavior learned by the teacher (for LLM guardrails)—re-run safety evaluations on the student.
- Serving frameworks expose admin endpoints; do not expose ONNX Runtime/Triton metrics ports publicly.

## 11. Failure Handling

- **Faster kernels but same end-to-end latency:** bottleneck is elsewhere (preprocessing, network, queue). Re-profile the full path.
- **Accuracy drop beyond tolerance:** fewer layers pruned, higher precision (`fp16` instead of `int8`), calibration on representative data, or skip quantization for sensitive layers.
- **torch.compile slow first request:** compilation happens at warmup; pre-warm during deploy and pin shapes.
- **OOM after optimization:** caching allocator fragmentation or larger compiled workspace; set memory fraction and reduce batch.
- **Runtime not available on target:** fall back to ONNX Runtime CPU with tuned threads (`OMP_NUM_THREADS`, `intra_op_num_threads`).
- **Quality regressions only in production traffic:** evaluation set is not representative; add production-like samples and re-tune.

## 12. Expected Deliverables

1. Profiling report identifying the dominant cost.
2. Optimization plan with expected gain and risk per step.
3. Applied changes with configuration.
4. Before/after latency, throughput, memory, and quality table.
5. Exported artifacts and parity tests.
6. Rollback instructions.

## 13. References

- PyTorch `torch.compile` docs — https://pytorch.org/docs/stable/torch.compiler.html
- ONNX Runtime performance — https://onnxruntime.ai/docs/performance/
- TensorRT best practices — https://docs.nvidia.com/deeplearning/tensorrt/latest/performance/best-practices.html
- "Distilling the Knowledge in a Neural Network" — https://arxiv.org/abs/1503.02531
- "The Lottery Ticket Hypothesis" — https://arxiv.org/abs/1803.03635
- vLLM documentation — https://docs.vllm.ai/
- Triton Inference Server — https://docs.nvidia.com/deeplearning/triton-inference-server/
