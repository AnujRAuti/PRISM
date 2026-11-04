---
name: model-quantization
description: Reduce model precision deliberately—GPTQ/AWQ/GGUF/bitsandbytes/ONNX int8—choosing schemes, calibrating, and verifying quality and speed on real hardware.
metadata:
  domain: ai-and-ml
  version: 1.0.0
  risk: medium
---

# Model Quantization

## 1. Purpose

Lower numeric precision to cut memory and increase throughput, with measured quality retention. Quantization is not a single technique: post-training quantization (PTQ), quantization-aware training (QAT), and weight-only schemes (GPTQ/AWQ/GGUF) behave very differently, and the same 4-bit model can be excellent on one runtime and broken on another. This skill covers scheme selection, calibration data, per-layer sensitivity, kernel/runtime compatibility, and a verification protocol that catches silent quality collapse.

**Scope:** models you own or are licensed to modify. Some licenses restrict redistribution of derivatives—check before publishing quantized weights.

## 2. Activation Conditions

- A model does not fit in the target memory (GPU VRAM, edge device RAM).
- LLM inference is memory-bandwidth-bound and needs 4/8-bit weights.
- Throughput must improve on CPU with int8 kernels.
- Comparing GPTQ vs. AWQ vs. GGUF vs. bitsandbytes for a deployment.
- Keywords: quantization, int8, int4, GPTQ, AWQ, GGUF, llama.cpp, bitsandbytes, QAT, calibration, perplexity, accuracy drop, KV cache quantization.

## 3. When Not to Use

- The model already fits and meets latency targets.
- The task is extremely precision-sensitive (some scientific/medical numeric outputs) without a validated tolerance.
- Runtime/hardware lacks efficient low-precision kernels (quantization may be slower).

## 4. Required Context

1. Target hardware and runtime (CUDA + vLLM, CPU + llama.cpp, mobile NPU, ONNX Runtime).
2. Memory budget and the current model footprint (weights + KV cache + activations).
3. Quality metric and tolerance on a fixed evaluation set.
4. Whether QAT is feasible (training data, compute, code access).
5. Deployment constraints: can you ship custom kernels? Is the runtime fixed by the platform?

## 5. Operating Procedure

1. **Measure baseline quality and speed** on the target hardware with full precision (or the reference precision).
2. **Choose the scheme by runtime, not by paper results**:
   - GPU serving (vLLM/TGI): AWQ or GPTQ 4-bit weight-only; fp8 on Hopper+.
   - CPU/Apple/edge (llama.cpp/Ollama): GGUF `Q4_K_M`/`Q5_K_M`.
   - PyTorch quick path: `bitsandbytes` 8-bit/4-bit (`nf4`) with `device_map`.
   - Non-LLM CNNs on CPU: ONNX Runtime dynamic int8; or static QDQ with calibration.
3. **Prepare calibration data** representative of real inputs (200–1000 samples), excluding evaluation data.
4. **Quantize** with a pinned tool version and record all flags.
5. **Sensitivity-check layers**: keep embeddings/lm_head/first-last blocks in higher precision when quality drops.
6. **Evaluate** the quantized model on the same eval set: task metric, plus generation-specific checks (coherence, instruction following, refusal behavior).
7. **Benchmark** latency/throughput/memory on the target hardware with realistic concurrency.
8. **Test the extreme inputs**: very long contexts, rare tokens, numeric reasoning, code generation—quantization damage often shows here first.
9. **Deploy behind a flag** with the full-precision model available for fallback.
10. **Document** the recipe (tool, version, flags, calibration set, sensitivity decisions) so it is reproducible.

## 6. Tools and Technologies

| Scheme | Typical tool |
|---|---|
| Weight-only 4-bit (GPU) | AutoAWQ, GPTQModel, `llm-compressor`, vLLM quantization support |
| GGUF (CPU/edge) | `llama.cpp` `quantize`, Ollama |
| Runtime 8/4-bit (PyTorch) | `bitsandbytes` |
| Static/dynamic int8 (CV) | ONNX Runtime quantization, OpenVINO NNCF, TensorRT |
| fp8 | vLLM/TensorRT-LLM on Hopper/Ada |
| QAT | PyTorch `torch.ao.quantization`, `pytorch-quantization` |
| Evaluation | lm-evaluation-harness, task-specific harness, perplexity on held-out text |

## 7. Practical Implementation

**AWQ 4-bit for GPU serving (AutoAWQ):**

```python
from awq import AutoAWQForCausalLM
from transformers import AutoTokenizer

model_path = "meta-llama/Llama-3.1-8B-Instruct"
quant_path = "artifacts/llama31-8b-awq"

model = AutoAWQForCausalLM.from_pretrained(model_path, low_cpu_mem_usage=True)
tokenizer = AutoTokenizer.from_pretrained(model_path)

model.quantize(
    tokenizer,
    quant_config={"zero_point": True, "q_group_size": 128, "w_bit": 4, "version": "GEMM"},
    calib_data="calibration/corpus.jsonl",   # 128–512 representative samples
)
model.save_quantized(quant_path)
tokenizer.save_pretrained(quant_path)
```

**Serving the quantized model (vLLM):**

```bash
vllm serve artifacts/llama31-8b-awq \
  --quantization awq_marlin \
  --dtype float16 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90
```

**bitsandbytes 4-bit NF4 (fast path, prototype-quality):**

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

bnb = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)
tok = AutoTokenizer.from_pretrained("mistralai/Mistral-7B-Instruct-v0.3")
model = AutoModelForCausalLM.from_pretrained(
    "mistralai/Mistral-7B-Instruct-v0.3", quantization_config=bnb, device_map="auto"
)
```

**GGUF conversion and quantization for CPU (llama.cpp):**

```bash
python convert_hf_to_gguf.py models/llama31-8b --outfile artifacts/llama31-8b-f16.gguf --outtype f16
llama-quantize artifacts/llama31-8b-f16.gguf artifacts/llama31-8b-Q4_K_M.gguf Q4_K_M
llama-cli -m artifacts/llama31-8b-Q4_K_M.gguf -p "Explain idempotency in one paragraph." -n 200
```

**ONNX int8 for a vision model with calibration:**

```python
from onnxruntime.quantization import quantize_static, CalibrationDataReader, QuantFormat, QuantType

class Reader(CalibrationDataReader):
    def __init__(self, batches):
        self._it = iter(batches)
    def get_next(self):
        try:
            b = next(self._it)
            return {"input": b}
        except StopIteration:
            return None

quantize_static(
    "model_fp32.onnx", "model_int8.onnx", Reader(calib_batches),
    quant_format=QuantFormat.QDQ, per_channel=True, weight_type=QuantType.QInt8,
    activation_type=QuantType.QInt8,
)
```

**Quality verification harness:**

```python
import json, numpy as np

def evaluate(runner, cases) -> dict:
    correct = 0
    exact = 0
    for case in cases:
        out = runner(case["prompt"])
        correct += int(case["check"](out))
        exact += int(out.strip() == case["expected"].strip())
    n = len(cases)
    return {"task_accuracy": correct / n, "exact_match": exact / n, "n": n}

baseline = evaluate(run_fp16, cases)
quantized = evaluate(run_awq, cases)
delta = quantized["task_accuracy"] - baseline["task_accuracy"]
assert delta > -0.02, f"quality regression {-delta:.3%} exceeds 2% tolerance"
print(f"fp16={baseline['task_accuracy']:.3f} awq={quantized['task_accuracy']:.3f} delta={delta:+.3f}")
```

**Perplexity guard on held-out text:**

```python
import torch

@torch.inference_mode()
def perplexity(model, tok, text: str, max_len: int = 2048) -> float:
    ids = tok(text, return_tensors="pt", truncation=True, max_length=max_len).input_ids
    loss = model(ids, labels=ids).loss
    return float(torch.exp(loss))
```

**Memory calculation (LLM weights):**

```text
fp16:  params × 2 bytes      → 8B params ≈ 15 GB
int8:  params × 1 byte       → ≈ 8 GB
4-bit: params × 0.5 bytes + scales ≈ 5 GB (+ KV cache + activations)
KV cache ≈ 2 × layers × heads × head_dim × seq_len × batch × bytes
```

## 8. Quality Standards

- Baseline (reference precision) numbers are recorded before quantizing.
- The quantization recipe is reproducible: tool version, flags, calibration data version.
- Quality delta is measured on a fixed eval set and is within the agreed tolerance.
- Long-context and edge-case behavior is tested, not just short prompts.
- Speed/memory claims are measured on the target hardware and runtime.
- Full-precision fallback is available and deployable.
- Licenses permit redistribution of the quantized artifact.

## 9. Verification and Testing

```bash
pytest -q tests/test_quantized_quality.py
python scripts/bench.py --model artifacts/llama31-8b-awq --concurrency 1,8,32
lm_eval --model vllm --model_args pretrained=artifacts/llama31-8b-awq --tasks mmlu,gsm8k --batch_size 8
```

Expected evidence: eval-table with fp16 vs. quantized on the same tasks; latency/throughput/memory comparison; a canary run with real prompts reviewed by a human; no crashes on max-length inputs.

## 10. Security Considerations

- Quantized weights from third parties are untrusted binaries: prefer safetensors, verify hashes, and never load pickles.
- Quantization can degrade refusal/safety behavior—re-run safety evaluations, not only capability benchmarks.
- Calibration data may contain confidential text; keep it access-controlled and delete after use.
- Custom quantization kernels can be a supply-chain risk; use official runtimes and pin versions.
- Lower precision can change numeric outputs in security-sensitive scoring—validate thresholds after quantization.
- Do not use quantization to fit a model into a device that then lacks memory headroom for logging/monitoring—crashes are outages.

## 11. Failure Handling

- **Quality collapse (gibberish at 4-bit):** embedding/LM head quantization damage; exclude those layers or use a higher bit width (`Q5_K_M`, 6-bit AWQ) or a better calibration set.
- **Model fails to load in vLLM:** quantization format mismatch (`awq` vs. `awq_marlin` vs. `gptq`); check the runtime's supported list and re-export with the matching tool.
- **Slower than fp16:** kernels not optimized for your hardware/batch size; benchmark at production batch sizes; CPU int8 may need `OMP_NUM_THREADS` tuning.
- **Works in English, fails in other languages:** calibration data was monolingual; use multilingual calibration.
- **Out of memory despite quantization:** KV cache dominates at long context; quantize the KV cache (fp8/int8) or cap `max-model-len`.
- **Inconsistent outputs between runs:** nondeterministic kernels/mixed precision; set seeds and accept documented nondeterminism for sampling.

## 12. Expected Deliverables

1. Baseline quality and performance measurements.
2. Scheme and runtime selection with rationale.
3. Reproducible quantization recipe and artifacts.
4. Quality comparison table across precisions.
5. Performance/memory measurements on target hardware.
6. Deployment configuration and fallback plan.
7. License and redistribution check.

## 13. References

- GPTQ paper — https://arxiv.org/abs/2210.17323
- AWQ paper — https://arxiv.org/abs/2306.00978
- llama.cpp quantization docs — https://github.com/ggml-org/llama.cpp/blob/master/docs/quantization.md
- ONNX Runtime quantization — https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html
- bitsandbytes — https://huggingface.co/docs/bitsandbytes/
- vLLM quantization support — https://docs.vllm.ai/en/latest/features/quantization/
- PyTorch quantization docs — https://pytorch.org/docs/stable/quantization.html
- NIST AI 600-1 — https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf
