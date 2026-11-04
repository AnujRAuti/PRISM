---
name: local-llm-deployment
description: Deploy LLMs on your own hardware—runtime selection (vLLM, llama.cpp, Ollama, TGI), GPU sizing, KV-cache planning, OpenAI-compatible serving, and capacity validation.
metadata:
  domain: ai-and-ml
  version: 1.0.0
  risk: medium
---

# Local LLM Deployment

## 1. Purpose

Run open-weight models on infrastructure you control, with predictable throughput and latency. This skill covers runtime choice for the hardware you actually have (single consumer GPU, multi-GPU server, CPU-only, Apple Silicon), the memory arithmetic that determines what fits, serving configuration (batching, context length, KV cache), and the operational concerns of self-hosted inference: model distribution, upgrades, observability, and abuse control.

**Scope:** your own hardware. Serving a public endpoint makes you responsible for abuse, content policy, and rate limiting. Verify the model license permits your intended commercial use.

## 2. Activation Conditions

- Data cannot leave the premises (regulated, confidential, or cost-driven).
- Need offline inference or predictable per-token cost.
- Choosing between vLLM, llama.cpp, Ollama, TGI, or SGLang.
- Sizing GPU memory for a specific model/context length.
- Keywords: local LLM, self-hosted inference, vLLM, llama.cpp, Ollama, GGUF, VRAM, KV cache, quantization, OpenAI-compatible API, GPU sizing.

## 3. When Not to Use

- Bursty low-volume workloads where an API is cheaper than idle GPUs.
- No hardware with sufficient memory, and no plans to acquire it.
- Frontier-model capability is required beyond what open weights provide.

## 4. Required Context

1. Hardware: GPU model/VRAM, CPU cores/RAM, disk speed, interconnect (PCIe/NVLink).
2. Workload: prompts/sec, tokens in/out, max context, concurrency, latency SLO.
3. Model candidates and licenses.
4. Operational constraints: container vs. bare metal, systemd, Kubernetes.
5. Data classification and whether the endpoint is internal or public.

## 5. Operating Procedure

1. **Do the memory arithmetic first**:
   ```
   weights  = params × bytes_per_param (fp16=2, int8=1, 4-bit≈0.5 + scales)
   kv_cache = 2 × layers × kv_heads × head_dim × seq_len × batch × bytes_per_elem
   total    = weights + kv_cache + activations + overhead(~10%)
   ```
2. **Pick the runtime**:
   - GPU server, high throughput: vLLM or SGLang (PagedAttention, continuous batching).
   - Single GPU / Apple Silicon / CPU: llama.cpp (`llama-server`) with GGUF.
   - Simple local dev: Ollama (wraps llama.cpp); not ideal for multi-user throughput.
   - HF-native enterprise: TGI.
3. **Choose quantization** based on VRAM headroom (fp16 if it fits; AWQ/GPTQ 4–8 bit otherwise; GGUF Q4_K_M/Q5_K_M on CPU/Apple).
4. **Set context and concurrency deliberately**: `max-model-len`, `max-num-seqs`, `gpu-memory-utilization`; long context multiplies KV cache and starves batch slots.
5. **Expose an OpenAI-compatible API** (`/v1/chat/completions`) so clients are portable; put it behind an auth proxy.
6. **Run as a service**: systemd unit or container with restart policy, health endpoint, and structured logs.
7. **Add guardrails**: request size limits, token caps, per-key rate limits, timeouts, and output length limits.
8. **Benchmark** with realistic prompt/output lengths: measure TTFT (time to first token), inter-token latency, tokens/sec, and p95 under concurrency.
9. **Monitor**: queue depth, KV-cache utilization, preemption count, GPU memory, and error rate.
10. **Plan upgrades**: model version pinning, blue/green model swap, and rollback.

## 6. Tools and Technologies

| Runtime | Best for |
|---|---|
| vLLM | Multi-user GPU serving, continuous batching, prefix caching |
| SGLang | High-throughput serving with structured output/RadixAttention |
| llama.cpp (`llama-server`) | CPU, Apple Silicon, single consumer GPU, GGUF |
| Ollama | Local developer ergonomics, model management |
| TGI | Hugging Face-native deployments |
| Inference backends | Triton, TensorRT-LLM (max GPU perf) |
| Packaging | Docker/Podman, systemd, Kubernetes (with GPU device plugin) |
| Metrics | Prometheus (vLLM exposes `/metrics`), DCGM exporter |

## 7. Practical Implementation

**VRAM sizing script:**

```python
def vram_gb(params_b: float, bits: int, layers: int, kv_heads: int, head_dim: int,
            ctx: int, batch: int, kv_bits: int = 16) -> dict:
    weights = params_b * 1e9 * (bits / 8) / 1e9
    kv = 2 * layers * kv_heads * head_dim * ctx * batch * (kv_bits / 8) / 1e9
    overhead = 0.12 * (weights + kv)
    return {"weights_gb": round(weights, 2), "kv_cache_gb": round(kv, 2),
            "overhead_gb": round(overhead, 2), "total_gb": round(weights + kv + overhead, 2)}

# Llama-3.1-8B, 4-bit, 8k context, batch 16
print(vram_gb(params_b=8, bits=4, layers=32, kv_heads=8, head_dim=128, ctx=8192, batch=16))
```

**vLLM server as a systemd service (GPU):**

```ini
# /etc/systemd/system/vllm.service
[Unit]
Description=vLLM OpenAI-compatible server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=vllm
Group=vllm
WorkingDirectory=/opt/vllm
Environment="HF_HOME=/var/lib/vllm/hf"
ExecStart=/opt/vllm/venv/bin/vllm serve meta-llama/Llama-3.1-8B-Instruct \
  --host 127.0.0.1 --port 8000 \
  --max-model-len 8192 \
  --max-num-seqs 64 \
  --gpu-memory-utilization 0.90 \
  --enable-prefix-caching \
  --served-model-name llama3.1-8b
Restart=on-failure
RestartSec=10
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now vllm
curl -s http://127.0.0.1:8000/v1/models | jq -r '.data[].id'
```

**Client call (OpenAI-compatible, provider-portable):**

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="local-key")
resp = client.chat.completions.create(
    model="llama3.1-8b",
    messages=[{"role": "user", "content": "Explain PagedAttention in 3 sentences."}],
    max_tokens=200, temperature=0.2,
)
print(resp.choices[0].message.content)
print(resp.usage)
```

**llama.cpp on CPU/Apple (GGUF):**

```bash
llama-server -m models/llama31-8b-Q4_K_M.gguf \
  --host 127.0.0.1 --port 8081 \
  --ctx-size 8192 --parallel 4 \
  --threads "$(nproc)" --n-gpu-layers 0
```

```bash
# Apple Silicon: offload layers to Metal
llama-server -m models/llama31-8b-Q4_K_M.gguf --n-gpu-layers 99 --ctx-size 8192
```

**Ollama for local development:**

```bash
ollama pull llama3.1:8b-instruct-q4_K_M
ollama serve &
curl -s http://127.0.0.1:11434/api/generate -d '{"model":"llama3.1:8b-instruct-q4_K_M","prompt":"hi","stream":false}' | jq -r .response
```

**Benchmark TTFT and throughput:**

```python
import time, httpx, concurrent.futures as cf

def one_call(prompt_len: int, max_tokens: int = 128) -> tuple[float, float]:
    prompt = "word " * prompt_len
    t0 = time.perf_counter()
    with httpx.stream("POST", "http://127.0.0.1:8000/v1/chat/completions",
                      json={"model": "llama3.1-8b", "stream": True, "max_tokens": max_tokens,
                            "messages": [{"role": "user", "content": prompt}]},
                      timeout=120) as r:
        first = None
        for line in r.iter_lines():
            if line and first is None:
                first = time.perf_counter()
    end = time.perf_counter()
    return (first - t0) * 1000, (end - t0) * 1000

for concurrency in (1, 8, 32):
    with cf.ThreadPoolExecutor(concurrency) as ex:
        res = list(ex.map(lambda _: one_call(200), range(64)))
    ttft = sorted(r[0] for r in res)[len(res) // 2]
    print(f"c={concurrency:2d} median_ttft={ttft:7.1f}ms")
```

**Docker Compose with GPU:**

```yaml
services:
  vllm:
    image: vllm/vllm-openai:latest
    command: ["--model", "meta-llama/Llama-3.1-8B-Instruct",
              "--max-model-len", "8192", "--gpu-memory-utilization", "0.9"]
    ports: ["127.0.0.1:8000:8000"]
    volumes: ["hf-cache:/root/.cache/huggingface"]
    deploy:
      resources:
        reservations:
          devices: [{driver: nvidia, count: 1, capabilities: [gpu]}]
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 5

volumes:
  hf-cache: {}
```

**Metrics scrape config:**

```yaml
scrape_configs:
  - job_name: vllm
    static_configs: [{targets: ["127.0.0.1:8000"]}]
    metrics_path: /metrics
```

## 8. Quality Standards

- Model fits in VRAM with ≥ 10% headroom at target context and concurrency.
- Runtime is pinned by image digest/version, not `latest`.
- Server binds to localhost or a private interface; public exposure goes through an authenticated proxy.
- Request limits (max tokens, max context, body size) are enforced at the gateway.
- TTFT and inter-token latency are measured at production-like prompt lengths.
- Model version and license are recorded.
- Graceful restart and model-swap procedure documented.

## 9. Verification and Testing

```bash
curl -sf http://127.0.0.1:8000/health && echo ok
curl -s http://127.0.0.1:8000/v1/models | jq -r '.data[0].id'
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv
python bench/ttft.py --concurrency 1,8,32
```

Tests: a request exceeding `max-model-len` returns a clear 400 rather than crashing; concurrent requests do not OOM; a restart resumes serving within the startup budget; metrics show queue depth and cache utilization.

## 10. Security Considerations

- Self-hosting does not make a model safe: apply input/output policies, jailbreak monitoring, and rate limits for public endpoints.
- Prompt injection through retrieved or user-supplied content remains a risk; isolate tools and follow agent-permission-management.
- Run the server as a non-root user; containers should drop capabilities and avoid `--privileged`.
- Model downloads execute nothing at inference, but tokenizer code (`trust_remote_code=True`) can execute arbitrary Python—avoid it or audit the code.
- Protect `/metrics`, `/health`, and admin/model-loading endpoints from public access.
- Log prompts and completions only with consent and redaction; they may contain PII or secrets.
- GPU hosts are expensive hijack targets: patch drivers, restrict SSH, and monitor for cryptomining.

## 11. Failure Handling

- **CUDA OOM at startup:** lower `--gpu-memory-utilization`, reduce `--max-model-len`, use a more quantized model, or set `--max-num-seqs` lower.
- **OOM under load:** KV cache exhausted—reduce concurrency or context; enable preemption-friendly settings; add a second replica.
- **Very slow first token:** prompt too long (prefill cost), no prefix caching for repeated system prompts, or CPU offload.
- **Throughput plateaus:** batch size limited by memory; quantize KV cache, shorten context, or scale horizontally.
- **Garbage output:** wrong chat template—use the model's documented template via the tokenizer config; verify with a simple prompt.
- **Model download fails:** HF token/network issues; pre-download to a shared cache and mount it.

## 12. Expected Deliverables

1. Hardware and memory sizing calculation.
2. Runtime and model selection with rationale and license note.
3. Service definition (systemd/Compose) with pinned versions.
4. Benchmark results: TTFT, tokens/sec, concurrency curve.
5. Gateway configuration (auth, rate limits, size limits).
6. Monitoring dashboard and alerts.
7. Upgrade/rollback procedure.

## 13. References

- vLLM documentation — https://docs.vllm.ai/
- llama.cpp — https://github.com/ggml-org/llama.cpp
- Ollama — https://github.com/ollama/ollama
- TGI — https://huggingface.co/docs/text-generation-inference/
- SGLang — https://docs.sglang.ai/
- PagedAttention paper — https://arxiv.org/abs/2309.06180
- NVIDIA container toolkit — https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/
- OWASP LLM Top 10 — https://owasp.org/www-project-top-10-for-large-language-model-applications/
