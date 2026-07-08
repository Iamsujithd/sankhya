from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import numpy as np
import os
import re
import json
import traceback
import plotly.io as pio
from openai import OpenAI

app = FastAPI(title="Sankhya: AI Data Analyst Backend")

# Enable CORS for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global store for active DataFrame and metadata
store = {}

# Initialize Groq client with the environment variable
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    # We will log a warning or raise an exception when a query is made, 
    # but let's initialize OpenAI client to avoid failure on startup.
    # We'll set a placeholder if env is missing so server still boots, but fails gracefully on chat requests.
    GROQ_API_KEY = "missing_key"

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

def make_json_safe(val):
    if val is None:
        return None
    if isinstance(val, pd.DataFrame):
        return make_json_safe(val.to_dict(orient="records"))
    if isinstance(val, pd.Series):
        return make_json_safe(val.to_list())
    if isinstance(val, (str, bool)):
        return val
    if isinstance(val, (int, np.integer, np.signedinteger)):
        return int(val)
    if isinstance(val, (float, np.floating)):
        if np.isnan(val) or np.isinf(val):
            return None
        return float(val)
    if isinstance(val, (list, np.ndarray, tuple, set)):
        return [make_json_safe(x) for x in val]
    if isinstance(val, dict):
        return {str(k): make_json_safe(v) for k, v in val.items()}
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        # Determine file type
        ext = os.path.splitext(file.filename)[1].lower()
        if ext == ".csv":
            df = pd.read_csv(file.file)
        elif ext in [".xls", ".xlsx"]:
            df = pd.read_excel(file.file)
        elif ext == ".json":
            df = pd.read_json(file.file)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format! Please upload CSV, Excel, or JSON.")
        
        # Store df and metadata
        store["df"] = df
        store["filename"] = file.filename
        
        # Calculate summary statistics for columns
        columns_info = []
        for col in df.columns:
            dtype = df[col].dtype
            nulls = int(df[col].isnull().sum())
            nunique = int(df[col].nunique())
            columns_info.append({
                "name": col,
                "type": str(dtype),
                "nulls": nulls,
                "nunique": nunique
            })
            
        return make_json_safe({
            "status": "success",
            "filename": file.filename,
            "shape": df.shape,
            "columns": columns_info,
            "head": df.head(5).to_dict(orient="records")
        })
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Error reading dataset: {str(e)}")

@app.post("/chat")
async def chat_with_data(message: str = Form(...)):

    if GROQ_API_KEY == "missing_key":
        raise HTTPException(status_code=400, detail="GROQ_API_KEY environment variable is not configured.")
    if "df" not in store:
        raise HTTPException(status_code=400, detail="No dataset uploaded yet. Please upload a dataset first.")

    df       = store["df"]
    filename = store.get("filename", "uploaded file")
    cols_info = ", ".join([f"{col} ({dtype})" for col, dtype in zip(df.columns, df.dtypes)])

    try:
        import sklearn  # noqa
        sklearn_available = True
    except ImportError:
        sklearn_available = False

    sample_vals = {}
    for col in df.columns[:10]:
        sample_vals[col] = df[col].dropna().head(3).tolist()

    # ── SINGLE LLM CALL — model decides everything ────────────────────────
    # Give the model full context + two clear output modes.
    # It naturally decides based on what the user is asking for.
    # No classifier, no rules list, no JSON overhead — just reasoning.
    # ──────────────────────────────────────────────────────────────────────
    system_prompt = f"""You are Sankhya — a brilliant AI data scientist and data companion.

The user has uploaded: "{filename}"
Shape: {df.shape[0]} rows × {df.shape[1]} columns
Columns & types: {cols_info}
Sample values (first 3 per column): {sample_vals}
scikit-learn available: {sklearn_available}

You have two modes — choose naturally based on what the user needs:

MODE A — CONVERSATIONAL:
Use this for: greetings, capability questions, dataset explanations, column meanings, concept definitions, strategic advice, opinions, "what should I analyze", "what is X", "who are you", etc.
Just reply naturally in plain text. Keep it to 2-5 sentences. Use **bold** for key terms.

MODE B — CODE EXECUTION:
Use this when the user wants actual data: statistics, computations, filters, aggregations, charts, predictions, "show me", "find", "calculate", "plot", "what is the average/min/max/top/cheapest/highest/lowest/most/least", comparisons, correlations, ML models, etc.
Write a Python code block. Rules:
- `df` is already loaded — never reload from file
- For data results, assign to `answer` (DataFrame, Series, scalar)
- For charts, assign a Plotly figure to `fig` (use px or go)
- Never use `px.dataframe`, `px.table`, or `go.Table`
- Never use `print()`
- You may produce both `answer` and `fig`

Output the code block like this:
```python
# your code
```

No explanations inside the code block. Code only."""

    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": message}
            ],
            temperature=0.1,
            max_tokens=1500
        )
        llm_output = resp.choices[0].message.content.strip()

        # ── Detect which mode was used ────────────────────────────────────
        code_match = re.search(r"```python\n(.*?)\n```", llm_output, re.DOTALL)

        # ── MODE A: Conversational reply ──────────────────────────────────
        if not code_match:
            return make_json_safe({
                "status":      "success",
                "intent":      "chat",
                "code":        None,
                "explanation": llm_output,
                "answer":      None,
                "chart":       None,
                "image":       None,
                "error":       None
            })

        # ── MODE B: Execute the generated code ────────────────────────────
        code_str = code_match.group(1)

        import io, sys, base64, matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plt.clf(); plt.close('all')

        namespace = {"df": df, "pd": pd, "np": np}
        exec("import plotly.express as px\nimport plotly.graph_objects as go"
             "\nimport matplotlib.pyplot as plt\nimport seaborn as sns", namespace)

        stdout_buf = io.StringIO()
        old_stdout, sys.stdout = sys.stdout, stdout_buf
        exec_error = None
        try:
            exec(code_str, namespace)
            exec_success = True
        except Exception:
            exec_success = False
            exec_error = traceback.format_exc()
        finally:
            sys.stdout = old_stdout

        printed = stdout_buf.getvalue().strip()
        fig      = namespace.get("fig",    None)
        answer   = namespace.get("answer", None)
        if answer is None and printed:
            answer = printed

        # Capture matplotlib
        matplotlib_img = None
        if plt.get_fignums():
            try:
                buf = io.BytesIO()
                plt.gcf().savefig(buf, format="png", bbox_inches="tight", dpi=150)
                buf.seek(0)
                matplotlib_img = base64.b64encode(buf.read()).decode()
                plt.close('all')
            except Exception:
                pass

        fig_json = json.loads(pio.to_json(fig)) if fig else None

        # Serialize answer
        answer_data = None
        if isinstance(answer, (pd.DataFrame, pd.Series)):
            df_a = pd.DataFrame(answer)
            df_s = df_a.map(make_json_safe) if hasattr(df_a, "map") else df_a.applymap(make_json_safe)
            answer_data = {
                "type":    "table",
                "columns": list(df_s.columns),
                "records": df_s.to_dict(orient="records")
            }
        elif answer is not None:
            answer_data = {"type": "text", "value": str(answer)}

        # Generate natural explanation of the result
        if exec_success:
            result_preview = str(answer)[:1500] if answer is not None else "(chart generated)"
            ex_prompt = f"""You are Sankhya — a data scientist giving a clear, insightful result summary.

User asked: "{message}"
Result: {result_preview}
Has chart: {"Yes" if fig or matplotlib_img else "No"}
Has table: {"Yes" if answer_data and answer_data.get("type") == "table" else "No"}

Write 2-4 flowing sentences that:
1. State what the result actually shows (numbers, patterns, findings — not "I processed")
2. Highlight the most interesting or important finding in **bold**
3. Suggest one smart follow-up the user might want to explore

No bullet points. No preamble."""
        else:
            ex_prompt = f"""You are Sankhya — a helpful data scientist.

User asked: "{message}"
Error encountered: {exec_error[:500] if exec_error else "unknown"}

In 2-3 plain-English sentences: say what went wrong (without jargon) and give one concrete rephrasing suggestion the user can try."""

        ex_resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": ex_prompt}],
            temperature=0.3,
            max_tokens=300
        )
        explanation = ex_resp.choices[0].message.content

        return make_json_safe({
            "status":      "success" if exec_success else "error",
            "intent":      "code",
            "code":        code_str,
            "explanation": explanation,
            "answer":      answer_data,
            "chart":       fig_json,
            "image":       matplotlib_img,
            "error":       exec_error
        })

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"AI query failed: {str(e)}")

# Mount static files
app.mount("/", StaticFiles(directory="static", html=True), name="static")


