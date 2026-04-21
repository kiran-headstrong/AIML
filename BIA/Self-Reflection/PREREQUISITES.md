# Prerequisites & Setup Guide — BIA Lecture 11

Everything you need to get **Gemma 4 running locally via Ollama** before the session.  
Follow the section for your operating system, then complete the shared Python steps at the bottom.

## 📥 Download the Lecture Materials

All notebooks and code for this session are on GitHub:

```
https://github.com/themuneebhashmi/BIA-lecture-11
```

**Quick download (terminal):**
```bash
git clone https://github.com/themuneebhashmi/BIA-lecture-11.git
cd BIA-lecture-11
```

Or download the ZIP directly from:  
👉 **https://github.com/themuneebhashmi/BIA-lecture-11/archive/refs/heads/main.zip**

> **Note:** The Gemini notebook requires you to add your own API key in the setup cell.  
> Get a free key at: https://aistudio.google.com/app/apikey

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Install Ollama](#2-install-ollama)
3. [Pull the Gemma 4 Model](#3-pull-the-gemma-4-model)
4. [Build the Custom Fast Model](#4-build-the-custom-fast-model)
5. [Start the Ollama Server](#5-start-the-ollama-server)
6. [Verify the Setup](#6-verify-the-setup)
7. [Python Environment Setup](#7-python-environment-setup)
8. [Quick Smoke Test](#8-quick-smoke-test)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| RAM | 8 GB | 16 GB+ |
| Free Disk | 10 GB | 15 GB+ |
| CPU | 4 cores | 8 cores (i7/i9/Ryzen 7+) |
| GPU | Not required | NVIDIA (speeds things up significantly) |
| OS | macOS 12+, Ubuntu 20.04+, Windows 10/11 | Any |
| Python | 3.9+ | 3.11+ |

> The model download is **~7.2 GB**. Make sure you have a stable connection and enough disk space before starting.

---

## 2. Install Ollama

### macOS

```bash
brew install ollama
```

> Don't have Homebrew? Install it first:
> ```bash
> /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
> ```

Alternatively, download the macOS app from [ollama.com/download](https://ollama.com/download).

---

### Linux (Ubuntu / Debian / Fedora / any distro)

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

This single command installs Ollama and registers it as a `systemd` service. No Homebrew needed.

---

### Windows 10 / 11

1. Go to [ollama.com/download](https://ollama.com/download) and download the **Windows installer** (`.exe`).
2. Run the installer — Ollama installs silently and starts automatically in the background.
3. Open **PowerShell** or **Command Prompt** for all subsequent commands below.

> On Windows, Ollama runs as a background tray application. You can see it in the system tray (bottom-right of the taskbar).

---

## 3. Pull the Gemma 4 Model

This step downloads the model weights (~7.2 GB). Run this **before the session** so you are not waiting during class.

```bash
ollama pull gemma4:e2b
```

Wait for the download to complete — you should see a progress bar followed by a success message.

**Check that it downloaded correctly:**

```bash
ollama list
```

You should see `gemma4:e2b` in the output.

---

## 4. Build the Custom Fast Model

The session uses a tuned model called `gemma4-fast` that has a smaller context window and thinking mode disabled for faster CPU inference.

From the **root of this repository**, run:

```bash
ollama create gemma4-fast -f gemma-4-vllm/Modelfile
```

Confirm it was created:

```bash
ollama list
```

Both `gemma4:e2b` and `gemma4-fast` should now appear.

---

## 5. Start the Ollama Server

### macOS (recommended — auto-restarts on login)

```bash
brew services start ollama
```

To stop it later:

```bash
brew services stop ollama
```

### macOS / Linux — manual background start

```bash
ollama serve &> /tmp/ollama.log &
```

### Linux (systemd)

```bash
sudo systemctl start ollama
# Enable auto-start on boot (optional)
sudo systemctl enable ollama
```

### Windows

Ollama starts automatically after installation. If you need to restart it, find the **Ollama** icon in the system tray and click **Restart**, or run from PowerShell:

```powershell
ollama serve
```

### Performance flags (optional, recommended on macOS)

Enables Flash Attention and quantized KV cache for faster inference:

```bash
OLLAMA_FLASH_ATTENTION="1" OLLAMA_KV_CACHE_TYPE="q8_0" ollama serve
```

---

## 6. Verify the Setup

### Check the server is listening

```bash
curl http://localhost:11434
```

Expected response: `Ollama is running`

### Quick model test

```bash
ollama run gemma4-fast "Say hello in one sentence."
```

You should get a short reply within a few seconds. Type `/bye` to exit the interactive prompt.

### Check the port (if curl is unavailable)

**macOS / Linux:**
```bash
lsof -i :11434
```

**Windows (PowerShell):**
```powershell
netstat -an | findstr 11434
```

---

## 7. Python Environment Setup

All session notebooks run against a local virtual environment. Follow these steps from the **repo root**.

### Create a virtual environment

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> If you get an execution-policy error on Windows, run this first:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### Install required packages

```bash
pip install --upgrade pip
pip install openai
```

That is the only external dependency for this session. Everything else (`json`, `textwrap`, `time`) is part of Python's standard library.

### Select the kernel in VS Code / Jupyter

1. Open `Self_Reflection_Critique_Tutorial.ipynb` in VS Code.
2. Click the kernel selector in the top-right (shows something like "Python 3.x.x").
3. Choose **Python Environments…** → select `.venv` (the one inside this repo folder).

---

## 8. Quick Smoke Test

With the virtual environment active and Ollama running, run this from the repo root:

```bash
python3 -c "
from openai import OpenAI
client = OpenAI(base_url='http://localhost:11434/v1', api_key='ollama')
resp = client.chat.completions.create(
    model='gemma4-fast',
    messages=[{'role': 'user', 'content': 'Ping!'}],
    temperature=1.0,
)
print('OK:', resp.choices[0].message.content)
"
```

If you see `OK:` followed by any text, you are fully set up.

---

## 9. Troubleshooting

### `ollama: command not found`
- **macOS:** Make sure Homebrew's bin is in your PATH: `export PATH="/opt/homebrew/bin:$PATH"` (add to `~/.zshrc`).
- **Linux:** Re-run the install script or add `/usr/local/bin` to your PATH.
- **Windows:** Restart PowerShell after installation.

### `Connection refused` on port 11434
The server is not running. Start it with `ollama serve` (see Step 5).

### `model "gemma4-fast" not found`
You haven't built the custom model yet. Re-run Step 4.

### Slow responses
- Close other RAM-heavy applications.
- You can lower the context further by editing `gemma-4-vllm/Modelfile`: change `num_ctx 4096` to `num_ctx 2048`, then re-run `ollama create gemma4-fast -f gemma-4-vllm/Modelfile`.

### `error loading model` (Windows)
Run Ollama as Administrator or check that the model file is not corrupted — re-pull with `ollama pull gemma4:e2b`.

### Python `ModuleNotFoundError: openai`
Your virtual environment is not activated. Run `source .venv/bin/activate` (macOS/Linux) or `.\.venv\Scripts\Activate.ps1` (Windows), then retry.

### Windows: `activate.ps1 cannot be loaded`
Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` in PowerShell, then try activating again.

---

## Summary Checklist

- [ ] Ollama installed and available on PATH
- [ ] `ollama pull gemma4:e2b` completed (~7.2 GB download)
- [ ] `ollama create gemma4-fast -f gemma-4-vllm/Modelfile` completed
- [ ] Ollama server running on `http://localhost:11434`
- [ ] Python virtual environment created (`.venv/`)
- [ ] `openai` package installed inside `.venv`
- [ ] Smoke test passes (`OK:` message printed)
- [ ] Correct kernel selected in VS Code notebook

---

*Reach out before the session if you are stuck — setup issues are much easier to fix before we start.*
