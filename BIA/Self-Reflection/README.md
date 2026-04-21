# 🧠 BIA Lecture 11 — Self-Reflection & Critique in LLM Agents

**Boston Institute of Analytics**

This repository contains all notebooks and code for Lecture 11 on self-reflection and critique techniques for Large Language Model (LLM) agents.

---

## 📥 Getting Started

```bash
git clone https://github.com/themuneebhashmi/BIA-lecture-11.git
cd BIA-lecture-11
```

---

## 📓 Notebooks

| Notebook | Description | Backend |
|----------|-------------|---------|
| `Self_Reflection_Critique_Gemini.ipynb` | Main lecture notebook — runs in the cloud, no GPU needed | Google Gemini API (`gemini-2.0-flash`) |
| `Self_Reflection_Critique_Tutorial.ipynb` | Local alternative — runs fully offline | Ollama + Gemma 4 |

---

## 🧩 Techniques Covered

### 1. Reflexion Algorithm
A self-corrective retry loop where the agent critiques its own answer and retries until a quality criterion is met.

```
Attempt → Reflect → Retry (up to max_rounds)
```

### 2. Auto-Verbalization Grading
The agent answers a question, then grades itself with a verbal rationale — detecting hallucinations and low-confidence answers before they reach the user.

```
Answer → Self-Grade (score + confidence + flag_for_review)
```

### 3. AutoGen Evaluator Sub-Agent
A separate evaluator agent critiques the main agent's output. If the verdict is `fail`, the main agent revises using the feedback. Supports ensemble voting across multiple evaluators.

```
Main Agent → Evaluator → (optional Revision)
```

---

## ⚙️ Setup

### Option A — Gemini API Notebook (Recommended for class)

1. Install the dependency:
   ```bash
   pip install google-genai
   ```

2. Get a free API key from [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)

3. Open `Self_Reflection_Critique_Gemini.ipynb` and paste your key in the setup cell:
   ```python
   GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"
   ```

4. Run all cells. With `DEMO_MODE = True` (default), the notebook uses pre-scripted responses — no API quota needed.

### Option B — Local Ollama Notebook

See [PREREQUISITES.md](PREREQUISITES.md) for full Ollama + Gemma 4 setup instructions.

---

## 🎭 Demo Mode

The Gemini notebook ships with `DEMO_MODE = True`. This means:

- **No API calls are made** — all responses are pre-scripted
- Each demo starts with an **intentionally flawed answer**, then the technique visibly corrects it
- Flip to `DEMO_MODE = False` to use the live Gemini API

To edit what the "model" says during a demo, modify the `DEMO_*` variables in cell 5.

---

## 📁 Repository Structure

```
BIA-lecture-11/
├── README.md
├── PREREQUISITES.md                        # Full setup guide (Ollama + Python)
├── Self_Reflection_Critique_Gemini.ipynb   # Gemini API version (cloud)
├── Self_Reflection_Critique_Tutorial.ipynb # Ollama version (local)
└── gemma-4-vllm/
    ├── chat.py       # Gemma 4 chat helper via vLLM
    ├── Modelfile     # Custom Ollama Modelfile for fast inference
    └── README.md     # vLLM setup instructions
```

---

## 📚 References

- Shinn et al. (2023) *Reflexion: Language Agents with Verbal Reinforcement Learning* — [arXiv:2303.11366](https://arxiv.org/abs/2303.11366)
- [Google AI Studio](https://aistudio.google.com/) — free Gemini API access
- [Ollama](https://ollama.com/) — run LLMs locally
- [Microsoft AutoGen](https://microsoft.github.io/autogen/) — multi-agent framework

---

*Boston Institute of Analytics — Lecture 11*
