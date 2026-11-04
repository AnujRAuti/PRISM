---
name: natural-language-processing
description: Build NLP pipelines—tokenization, classical baselines, transformer fine-tuning, NER and classification—with text normalization, evaluation, and multilingual handling.
metadata:
  domain: ai-and-ml
  version: 1.0.0
  risk: medium
---

# Natural Language Processing

## 1. Purpose

Deliver NLP components (classification, extraction, similarity, translation routing) that parse real text correctly and are evaluated with the right metrics. Text pipelines break on unicode normalization, language mixing, long documents exceeding context windows, and label definitions that humans disagree on. This skill covers baseline selection, tokenizer-aware preprocessing, fine-tuning with Hugging Face, span evaluation for extraction, and text-specific data hygiene.

**Scope:** text you are licensed to process. Text may contain personal data, confidential business information, or third-party copyrighted content—apply the organization's data policy and never send content to external APIs without approval.

## 2. Activation Conditions

- Text classification, sentiment, intent detection, NER, relation extraction, or summarization.
- Choosing between classical methods (TF-IDF) and transformers.
- Fine-tuning or distilling a transformer for a specific task.
- Debugging poor performance on multilingual or noisy text.
- Keywords: NLP, tokenization, TF-IDF, transformer, BERT, fine-tuning, NER, embeddings, Hugging Face, text classification, spaCy, sentence transformers.

## 3. When Not to Use

- LLM prompting for a task without training (use advanced-prompt-engineering or llm-integration).
- Retrieval over documents (use retrieval-augmented-generation).
- Speech-to-text (different pipeline).

## 4. Required Context

1. Task definition with examples of correct and incorrect outputs.
2. Languages present and expected mix.
3. Label taxonomy and inter-annotator agreement.
4. Document length distribution and structure.
5. Latency and cost budget (determines model size).
6. Whether data may leave the environment (external API eligibility).

## 5. Operating Procedure

1. **Build a labeled sample** (200–1000 examples) and compute agreement; if annotators disagree, fix the guidelines first.
2. **Establish a classical baseline**: TF-IDF + linear model for classification; regex/dictionary for extraction. Record its metric.
3. **Normalize text deterministically**: unicode NFKC, whitespace collapse, control character removal—and keep raw text for span offsets if extraction is required.
4. **Choose the model**: small transformer (MiniLM/DistilBERT) for latency-sensitive; base model for accuracy; multilingual (`xlm-roberta`) when languages mix.
5. **Respect the tokenizer**: do not truncate blindly—chunk long documents with overlap and aggregate predictions (max or attention-weighted).
6. **Fine-tune** with a small learning rate (2e-5–5e-5), 3–5 epochs, early stopping on the validation metric, and a fixed max length matching the data's p95 length.
7. **Evaluate with task-appropriate metrics**: macro-F1 for imbalanced classification; span-level precision/recall/F1 for NER; entity-level exact match; per-language breakdown.
8. **Error analysis by slice**: language, length bucket, class, and source channel.
9. **Export** for serving (ONNX or TorchScript) and verify parity.
10. **Package the tokenizer with the model**; a tokenizer mismatch silently destroys quality.

## 6. Tools and Technologies

| Purpose | Tools |
|---|---|
| Baselines | scikit-learn `TfidfVectorizer`, `LogisticRegression` |
| Transformers | Hugging Face `transformers`, `datasets`, `Trainer` |
| Efficient training | `peft` (LoRA), `accelerate`, `bitsandbytes` |
| Classic NLP | spaCy, NLTK (tokenization/stemming) |
| Embeddings | sentence-transformers, fastText |
| Evaluation | `seqeval` (NER), scikit-learn metrics |
| Serving | ONNX Runtime, FastAPI, `optimum` |
| Text quality | `ftfy`, `unicodedata`, `langdetect`/`fasttext` lid |

## 7. Practical Implementation

**Classical baseline (always run this first):**

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report

baseline = Pipeline([
    ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=50_000,
                              sublinear_tf=True, strip_accents="unicode")),
    ("clf", LogisticRegression(max_iter=2000, class_weight="balanced")),
])
baseline.fit(train_texts, train_labels)
print(classification_report(val_labels, baseline.predict(val_texts), digits=3, zero_division=0))
```

**Fine-tuning with Hugging Face `Trainer`:**

```python
from datasets import Dataset
from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                          TrainingArguments, Trainer, DataCollatorWithPadding)
import numpy as np
from sklearn.metrics import f1_score

MODEL = "distilbert-base-multilingual-cased"
tok = AutoTokenizer.from_pretrained(MODEL)

def tokenize(batch):
    return tok(batch["text"], truncation=True, max_length=256)

ds_train = Dataset.from_dict({"text": train_texts, "label": train_labels}).map(tokenize, batched=True)
ds_val = Dataset.from_dict({"text": val_texts, "label": val_labels}).map(tokenize, batched=True)

model = AutoModelForSequenceClassification.from_pretrained(MODEL, num_labels=len(label_names))

def metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    return {"macro_f1": f1_score(labels, preds, average="macro")}

args = TrainingArguments(
    output_dir="runs/intent-v1",
    learning_rate=3e-5,
    per_device_train_batch_size=32,
    per_device_eval_batch_size=64,
    num_train_epochs=4,
    weight_decay=0.01,
    eval_strategy="epoch",
    save_strategy="epoch",
    load_best_model_at_end=True,
    metric_for_best_model="macro_f1",
    warmup_ratio=0.1,
    lr_scheduler_type="cosine",
    logging_steps=50,
    seed=42,
    report_to=["mlflow"],
)

Trainer(model=model, args=args, train_dataset=ds_train, eval_dataset=ds_val,
        tokenizer=tok, data_collator=DataCollatorWithPadding(tok),
        compute_metrics=metrics).train()
```

**Long-document chunking with overlap and aggregation:**

```python
def chunks_with_overlap(token_ids: list[int], max_len: int = 512, stride: int = 64) -> list[list[int]]:
    if len(token_ids) <= max_len:
        return [token_ids]
    out = []
    start = 0
    while start < len(token_ids):
        out.append(token_ids[start:start + max_len])
        if start + max_len >= len(token_ids):
            break
        start += max_len - stride
    return out

def classify_long(text: str, model, tok, aggregate: str = "max"):
    ids = tok(text, add_special_tokens=False)["input_ids"]
    probs = [model_softmax(tok.prepare_for_model(c, truncation=True, max_length=512))
             for c in chunks_with_overlap(ids)]
    import numpy as np
    return np.max(probs, axis=0) if aggregate == "max" else np.mean(probs, axis=0)
```

**NER with alignment-safe offsets (avoid offset bugs from normalization):**

```python
import spacy
from spacy.training import Example

# Keep raw text for offsets; never normalize away characters before alignment.
nlp = spacy.blank("en")
nlp.add_pipe("ner")
ner = nlp.get_pipe("ner")
for label in ["PRODUCT", "AMOUNT", "DATE"]:
    ner.add_label(label)

train_data = [Example.from_dict(nlp.make_doc(t), a) for t, a in train_examples]
optimizer = nlp.initialize()
for epoch in range(20):
    import random
    random.shuffle(train_data)
    losses = {}
    nlp.update(train_data, sgd=optimizer, losses=losses)
    print(epoch, losses)
```

**Span-level evaluation:**

```python
from seqeval.metrics import classification_report as seq_report
print(seq_report([true_tags], [pred_tags], digits=3))
# For extraction tasks, evaluate exact-span match AND partial overlap separately.
```

**Slice evaluation:**

```python
import pandas as pd
from sklearn.metrics import f1_score

results = pd.DataFrame({"lang": langs, "len_bucket": buckets, "y": val_labels, "pred": preds})
for (lang, bucket), g in results.groupby(["lang", "len_bucket"]):
    print(f"{lang:6} {bucket:10} n={len(g):5d} macro_f1={f1_score(g.y, g.pred, average='macro'):.3f}")
```

**Export with tokenizer bundled:**

```python
from optimum.onnxruntime import ORTModelForSequenceClassification
from transformers import AutoTokenizer

ORTModelForSequenceClassification.from_pretrained("runs/intent-v1", export=True)\
    .save_pretrained("artifacts/intent-v1-onnx")
AutoTokenizer.from_pretrained("distilbert-base-multilingual-cased").save_pretrained("artifacts/intent-v1-onnx")
```

## 8. Quality Standards

- A classical baseline is measured before transformer training.
- Tokenizer and model are always packaged and versioned together.
- Max sequence length derives from data statistics; truncation policy is explicit.
- Metrics are macro-averaged for imbalanced classes and reported per language/slice.
- Label guidelines exist and agreement is measured.
- Text normalization is deterministic and applied identically in training and serving.
- Span-based tasks are evaluated on spans, not token accuracy.

## 9. Verification and Testing

```bash
pytest -q tests/test_tokenization.py tests/test_inference_parity.py
python scripts/evaluate.py --model runs/intent-v1 --split test --per-language
```

Tests: tokenizer round-trips offsets correctly on emoji and combining characters; long documents are chunked without dropping tail content; ONNX output matches PyTorch within tolerance; unknown language inputs do not crash; empty and whitespace-only strings return a defined result.

## 10. Security Considerations

- Text input is hostile: escape before rendering (XSS), reject control characters, cap length to avoid memory exhaustion.
- Prompt injection applies if text feeds an LLM downstream—treat document content as data, never as instructions.
- Sending text to external APIs may violate data policy or leak secrets; check for credentials/PII before any outbound call.
- Model files from untrusted hubs can contain malicious code (`trust_remote_code=True` is a code-execution decision).
- Unicode homoglyph and zero-width character attacks can bypass keyword filters; normalize before matching.
- Log text samples minimally; redact PII and confidential data.

## 11. Failure Handling

- **Transformer worse than TF-IDF:** dataset too small or labels noisy; use the baseline, add data, or use a smaller model with fewer frozen layers.
- **Crashes on some languages:** tokenizer not multilingual; verify with `AutoTokenizer` coverage and add language detection routing.
- **Performance collapse on long text:** truncation discarded the evidence—switch to chunking.
- **Entity offsets wrong:** normalization changed character counts; align on raw text or use `return_offsets_mapping=True` and map back explicitly.
- **Slow inference:** quantize (ONNX int8), reduce max length, batch requests, or distill to a smaller model.

## 12. Expected Deliverables

1. Labeled sample with guidelines and agreement metric.
2. Classical baseline results.
3. Fine-tuned model with tokenizer bundle.
4. Evaluation report by class, language, and length bucket.
5. Error analysis notes with representative examples.
6. Serving code and export parity test.

## 13. References

- Hugging Face Transformers — https://huggingface.co/docs/transformers/
- Hugging Face course — https://huggingface.co/learn/nlp-course
- spaCy documentation — https://spacy.io/usage
- seqeval — https://github.com/chakki-works/seqeval
- Optimum (ONNX export) — https://huggingface.co/docs/optimum/
- Jurafsky & Martin, *Speech and Language Processing* — https://web.stanford.edu/~jurafsky/slp3/
- Unicode normalization (UAX #15) — https://www.unicode.org/reports/tr15/
