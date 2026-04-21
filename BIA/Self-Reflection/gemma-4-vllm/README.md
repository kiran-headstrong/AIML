# Gemma 4 Local Inference — Setup & API Reference

Running Google's **Gemma 4 E2B** model locally via [Ollama](https://ollama.com) on an Intel Mac.

---

## Model Details

| Property | Value |
|---|---|
| Model | `gemma4:e2b` (Effective 2B) |
| Total Parameters | 5.1B (2.3B effective) |
| Context Window | 128K tokens (configured: 4096) |
| Supported Inputs | Text, Image, Audio |
| Download Size | 7.2 GB |
| Architecture | Dense |
| Quantization | Q4_K_M |
| Thinking Mode | Supported (can be disabled) |

> The "E" in E2B stands for "effective" — this variant is purpose-built for edge and laptop deployments with minimal resource usage while maintaining strong performance.

> **Note on Q2_K:** No Q2_K quantization is available for gemma4 on Ollama. `gemma4:e2b` (Q4_K_M) is the smallest/fastest available variant.

---

## Inference Engine

| Component | Detail |
|---|---|
| Engine | [Ollama](https://ollama.com) v0.21.0 |
| Installation | `brew install ollama` |
| Service Port | `11434` |
| API Style | OpenAI-compatible REST API |
| Base URL | `http://localhost:11434` |
| Custom Model | `gemma4-fast` (built from `Modelfile`) |

---

## Starting & Stopping the Server

```bash
# Check if server is already running (returns PID if up)
pgrep -x ollama

# Start as a background service (auto-restarts on login)
brew services start ollama

# Stop the service
brew services stop ollama

# Run manually in background (logs to /tmp/ollama.log)
ollama serve &> /tmp/ollama.log &

# Run manually in foreground with performance flags (Flash Attention + quantized KV cache)
OLLAMA_FLASH_ATTENTION="1" OLLAMA_KV_CACHE_TYPE="q8_0" ollama serve

# Check service status
brew services info ollama

# Tail server logs (when running manually)
tail -f /tmp/ollama.log
```

> **Tested:** Server confirmed running on PID 64083 with `ollama v0.21.0` on 18 April 2026.

---

## Running the Model

### Interactive CLI

```bash
# Base model
ollama run gemma4:e2b

# Custom fast model (reduced context, no GPU, tuned sampling)
ollama run gemma4-fast
```

Type your prompt and press Enter. Type `/bye` or `Ctrl+D` to exit.

### One-shot CLI

```bash
ollama run gemma4:e2b "Explain quantum computing in simple terms."
```

### One-shot with Thinking Disabled (faster)

```bash
# Pipe /set nothink before the prompt to skip the reasoning chain
echo -e "/set nothink\nYour prompt here" | ollama run gemma4:e2b
```

### Python Chat Script (this repo)

```bash
pip install openai
python3 chat.py
```

### Build the Custom Model from Modelfile

```bash
# Create/recreate gemma4-fast from the Modelfile in this repo
ollama create gemma4-fast -f Modelfile
```

---

## REST API Reference

The Ollama server exposes a fully **OpenAI-compatible** API at `http://localhost:11434/v1`.

### Chat Completions

**Endpoint:** `POST /v1/chat/completions`

```bash
curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma4:e2b",
    "messages": [
      { "role": "user", "content": "What is the capital of France?" }
    ]
  }'
```

**With a system prompt:**

```bash
curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma4:e2b",
    "messages": [
      { "role": "system", "content": "You are a helpful assistant." },
      { "role": "user", "content": "Summarize the theory of relativity." }
    ],
    "temperature": 1.0,
    "top_p": 0.95
  }'
```

**Streaming response:**

```bash
curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma4:e2b",
    "messages": [{ "role": "user", "content": "Tell me a joke." }],
    "stream": true
  }'
```

### List Available Models

**Endpoint:** `GET /v1/models`

```bash
curl http://localhost:11434/v1/models
```

### Generate (Ollama native endpoint)

**Endpoint:** `POST /api/generate`

```bash
curl http://localhost:11434/api/generate \
  -d '{
    "model": "gemma4:e2b",
    "prompt": "Why is the sky blue?",
    "stream": false
  }'
```

---

## Python Usage

### Using the OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",  # required by SDK but not validated
)

response = client.chat.completions.create(
    model="gemma4:e2b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is machine learning?"},
    ],
    temperature=1.0,
    top_p=0.95,
)

print(response.choices[0].message.content)
```

### Streaming

```python
stream = client.chat.completions.create(
    model="gemma4:e2b",
    messages=[{"role": "user", "content": "Write a short poem."}],
    stream=True,
)

for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="", flush=True)
```

### Using the Ollama Python Library

```bash
pip install ollama
```

```python
import ollama

response = ollama.chat(
    model="gemma4:e2b",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.message.content)
```

---

## Request Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `model` | string | — | Model name, e.g. `gemma4:e2b` |
| `messages` | array | — | Conversation history (system/user/assistant roles) |
| `temperature` | float | `1.0` | Randomness — higher = more creative |
| `top_p` | float | `0.95` | Nucleus sampling cutoff |
| `top_k` | int | `64` | Limits token candidates at each step |
| `stream` | bool | `false` | Stream tokens as they are generated |
| `max_tokens` | int | — | Max output tokens (unlimited if unset) |

> **Recommended sampling settings for Gemma 4:** `temperature=1.0`, `top_p=0.95`, `top_k=64`

---

## Thinking Mode & Latency

Gemma 4 supports an internal reasoning ("thinking") mode that causes the model to work through problems before answering.

### Observed Latency (Intel Core i9, CPU-only, 18 Apr 2026)

| Mode | Model | Time to first response |
|---|---|---|
| Thinking ON (default) | `gemma4:e2b` Q4_K_M | ~28.6s |
| Thinking ON (default) | `gemma4-fast` (Modelfile) | ~28.7s |
| Thinking OFF (`/set nothink`) | `gemma4:e2b` Q4_K_M | ~22.4s |

> **Note:** The `PARAMETER think false` in the Modelfile does **not** suppress thinking in ollama v0.21.0. Use `/set nothink` in the CLI or strip `<think>` tokens in code instead.

### Disable Thinking — CLI

```bash
echo -e "/set nothink\nYour prompt here" | ollama run gemma4:e2b
```

### Disable Thinking — API

Set `think: false` in the request body (Ollama native endpoint):

```bash
curl http://localhost:11434/api/chat \
  -d '{
    "model": "gemma4:e2b",
    "think": false,
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

**Enable thinking** by including `<|think|>` at the start of the system prompt:

```python
{"role": "system", "content": "<|think|> You are a helpful assistant."}
```

**Disable thinking** by omitting the token:

```python
{"role": "system", "content": "You are a helpful assistant."}
```

When thinking is active, the model outputs its internal reasoning wrapped in `<|channel>thought\n ... <channel|>` before the final answer. In multi-turn conversations, strip these thought blocks from history before appending the next user turn.

---

## Multimodal: Image Input

```python
import base64

with open("image.jpg", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode()

response = client.chat.completions.create(
    model="gemma4:e2b",
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            {"type": "text", "text": "What is in this image?"},
        ],
    }],
)
print(response.choices[0].message.content)
```

> **Tip:** Place image/audio content *before* the text in the message for best results.

---

## Hardware Requirements

| Resource | Minimum | This Machine |
|---|---|---|
| RAM | 8 GB | 64 GB |
| Disk | 8 GB free | — |
| CPU | Any modern CPU | Intel Core i9 (8-core, 2.4 GHz) |
| GPU | Optional | — |

Ollama runs entirely on CPU if no compatible GPU is detected. On Apple Silicon, it uses the Metal GPU automatically.

---

## Managing Models

```bash
# List downloaded models
ollama list

# Pull a different Gemma 4 variant
ollama pull gemma4:e4b   # Effective 4B  (9.6 GB)
ollama pull gemma4:26b   # MoE 26B       (18 GB)
ollama pull gemma4:31b   # Dense 31B     (20 GB)

# Remove a model
ollama rm gemma4:e2b

# Show model info
ollama show gemma4:e2b
```

---

## Available Gemma 4 Models on Ollama

| Tag | Size | Quantization | Context | Notes |
|---|---|---|---|---|
| `gemma4:e2b` ✅ | 7.2 GB | Q4_K_M | 128K | Smallest, edge-optimized — **locally available** |
| `gemma4:e4b` | 9.6 GB | Q4_K_M | 128K | Balanced edge model |
| `gemma4:26b` | 18 GB | Q4_K_M | 256K | MoE, workstation |
| `gemma4:31b` | 20 GB | Q4_K_M | 256K | Dense, workstation |
| `gemma4:e2b-it-q8_0` | 8.1 GB | Q8_0 | 128K | Higher precision |
| `gemma4:e4b-it-q8_0` | 12 GB | Q8_0 | 128K | Higher precision |

> **Q2_K is not available for any gemma4 variant.** Q4_K_M is the smallest quantization offered.

## Local Model Config (`Modelfile`)

```
FROM gemma4:e2b

PARAMETER num_ctx    4096   # Reduced from 128K for faster inference & lower RAM
PARAMETER num_thread 8      # Match physical core count (i9, 8-core)
PARAMETER num_gpu    0      # CPU-only (no GPU on this machine)
PARAMETER temperature 1.0
PARAMETER top_p      0.95
PARAMETER top_k      64
PARAMETER think      false  # Note: not effective in ollama v0.21.0 — use /set nothink

SYSTEM "You are a helpful assistant."
```

Build the model:

```bash
ollama create gemma4-fast -f Modelfile
```
