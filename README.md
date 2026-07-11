# Sankhya — AI Data Intelligence

> Upload any CSV, Excel, or JSON dataset and ask anything about it in plain English. Sankhya uses a large language model to reason about your data, run Python analysis, generate charts, and answer questions — all in a clean, dark-themed UI.

![Built with FastAPI](https://img.shields.io/badge/backend-FastAPI-009688?style=flat-square)
![Powered by Groq](https://img.shields.io/badge/AI-Groq%20%7C%20LLaMA%203.3-orange?style=flat-square)
![Frontend](https://img.shields.io/badge/frontend-Vanilla%20JS-yellow?style=flat-square)

---

## Features

- **Natural language queries** — ask "cheapest entry", "plot a histogram of AGE", "train a regression model"
- **Smart routing** — the LLM decides whether to respond conversationally or write & execute Python code
- **Interactive charts** — Plotly charts rendered inline
- **Data tables** — filterable results displayed directly in chat
- **Security hardened** — AST scanner, restricted builtins, 30s timeout, sanitized errors
- **File support** — CSV, Excel (.xlsx / .xls), JSON

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Uvicorn |
| AI | Groq API (LLaMA 3.3 70B) |
| Frontend | Vanilla JS + CSS (glassmorphic dark UI) |
| Charts | Plotly |
| Data | Pandas, NumPy, Scikit-learn |

---

## Local Setup

```bash
# 1. Clone
git clone https://github.com/Iamsujithd/sankhya.git
cd sankhya_ai

# 2. Create venv & install
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Set your Groq API key
export GROQ_API_KEY=your_key_here

# 4. Run
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open [https://sankhya.onrender.com]

---

## Security

- **Input cap:** Messages > 2000 characters are rejected
- **AST scan:** Generated code is parsed before execution — blocks `os`, `sys`, `subprocess`, `eval`, `while True`, dunder access
- **Safe builtins:** exec runs with an allowlist — filesystem and network calls are inaccessible
- **Timeout:** Code execution is killed after 30 seconds
- **Error sanitization:** Only the last line of a traceback is returned — no internal paths exposed
