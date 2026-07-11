from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import numpy as np
import os
import re
import ast
import json
import traceback
import threading
import plotly.io as pio
from openai import OpenAI

# ── Safe builtins: only math/data-safe functions allowed in exec() ──────────
_SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool,
    "dict": dict, "enumerate": enumerate, "filter": filter,
    "float": float, "frozenset": frozenset, "getattr": getattr,
    "hasattr": hasattr, "int": int, "isinstance": isinstance,
    "issubclass": issubclass, "iter": iter, "len": len,
    "list": list, "map": map, "max": max, "min": min,
    "next": next, "print": print, "range": range, "repr": repr,
    "reversed": reversed, "round": round, "set": set,
    "slice": slice, "sorted": sorted, "str": str, "sum": sum,
    "tuple": tuple, "type": type, "zip": zip,
    "True": True, "False": False, "None": None,
}

# ── Blocked AST nodes and import names ──────────────────────────────────────
_BLOCKED_IMPORTS = {
    "os", "sys", "subprocess", "shutil", "pathlib", "socket",
    "urllib", "http", "requests", "httpx", "ftplib", "smtplib",
    "pickle", "shelve", "dbm", "sqlite3", "multiprocessing",
    "threading", "concurrent", "asyncio", "signal", "ctypes",
    "importlib", "builtins", "inspect", "gc", "resource",
    "tempfile", "glob", "fnmatch", "io",
}
_BLOCKED_ATTRS = {
    "__import__", "__builtins__", "__subclasses__", "__globals__",
    "__code__", "__closure__", "mro", "__bases__",
}

def _check_code_safety(code: str) -> tuple[bool, str]:
    """
    Static AST scan. Returns (is_safe, reason).
    Runs BEFORE exec() — blocks obvious attack vectors.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

    for node in ast.walk(tree):
        # Block dangerous imports
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [alias.name.split(".")[0] for alias in node.names]
                if isinstance(node, ast.Import)
                else ([node.module.split(".")[0]] if node.module else [])
            )
            for name in names:
                if name in _BLOCKED_IMPORTS:
                    return False, f"Import of '{name}' is not allowed."

        # Block dangerous attribute access
        if isinstance(node, ast.Attribute) and node.attr in _BLOCKED_ATTRS:
            return False, f"Access to '{node.attr}' is not allowed."

        # Block dangerous builtin calls by name
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in {
                "eval", "exec", "compile", "open", "__import__",
                "breakpoint", "input", "memoryview",
            }:
                return False, f"Call to '{func.id}' is not allowed."

        # Block infinite loops: while True / while 1
        if isinstance(node, ast.While):
            test = node.test
            is_true_const = (
                (isinstance(test, ast.Constant) and test.value in (True, 1))
                or (isinstance(test, ast.Name) and test.id == "True")
            )
            if is_true_const:
                return False, "Infinite loops (while True) are not allowed."

    return True, ""


def _exec_with_timeout(code: str, namespace: dict, timeout: int = 30) -> tuple[bool, str | None]:
    """
    Run exec() in a daemon thread with a hard timeout.
    Returns (completed_before_timeout, error_or_None).
    """
    result = {"error": None, "done": False}

    def _run():
        try:
            exec(code, namespace)  # noqa: S102
        except Exception:
            result["error"] = traceback.format_exc()
        finally:
            result["done"] = True

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    if not result["done"]:
        return False, "Execution timed out (30 s limit). Try a simpler query."
    return True, result["error"]


# ── Pre-execution import stripper ────────────────────────────────────────────
_SAFE_IMPORT_PATTERN = re.compile(
    r'^\s*import\s+(pandas|numpy|plotly|matplotlib|seaborn|sklearn|scipy)'
    r'(\s+as\s+\w+)?\s*$|'
    r'^\s*from\s+(pandas|numpy|plotly|matplotlib|seaborn|sklearn|scipy)\b.*$',
    re.MULTILINE
)

def _strip_known_imports(code: str) -> str:
    """Remove lines that import already-injected libraries so exec() doesn't
    hit the missing __import__ builtin."""
    cleaned = []
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith('import ') or stripped.startswith('from '):
            # Keep the line only if it is NOT a known-safe library import
            # (unknown imports will fail naturally in exec and be caught)
            module = stripped.split()[1].split('.')[0]
            if module not in {
                'pandas', 'numpy', 'plotly', 'matplotlib',
                'seaborn', 'sklearn', 'scipy'
            }:
                cleaned.append(line)
            # else: silently drop — already in namespace
        else:
            cleaned.append(line)
    return '\n'.join(cleaned)

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

    # ── Input guard ────────────────────────────────────────────────────────
    if len(message) > 2000:
        raise HTTPException(status_code=400, detail="Message too long (max 2000 characters).")
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
- NEVER write any import statements — pd, np, px, go, plt, sns, sklearn are ALL pre-imported
- For data results, assign to `answer` (DataFrame, Series, scalar, or string)
- For a dataset summary use: answer = df.describe(include='all').to_string()
- For charts, assign a Plotly figure to `fig` (use px or go)
- Never use `px.dataframe`, `px.table`, or `go.Table`
- Never use `print()` or `df.info()` — they do not return values
- You may produce both `answer` and `fig`

Output the code block like this:
```python
# your code
```

No explanations inside the code block. Code only."""

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": message}
        ]
        
        max_retries = 3
        printed = ""
        for attempt in range(max_retries):
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.1,
                max_tokens=1500
            )
            llm_output = resp.choices[0].message.content.strip()
            messages.append({"role": "assistant", "content": llm_output})

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

            # ── MODE B: Security scan → Execute the generated code ───────────
            code_str = code_match.group(1)

            # 0. Strip known-safe library imports
            code_str = _strip_known_imports(code_str)

            # 1. Static AST safety check — runs BEFORE any execution
            is_safe, reason = _check_code_safety(code_str)
            if not is_safe:
                exec_success = False
                exec_error = f"Blocked by security filter: {reason}"
                if attempt < max_retries - 1:
                    messages.append({
                        "role": "user",
                        "content": f"The code was blocked: {reason}. Please analyze and provide the corrected python code block."
                    })
                    continue
                else:
                    break

            import io, sys, base64, matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            plt.clf(); plt.close('all')

            # 2. Restricted namespace
            _seed = {}
            exec(
                "import plotly.express as px\nimport plotly.graph_objects as go"
                "\nimport matplotlib.pyplot as plt\nimport seaborn as sns",
                _seed
            )
            namespace = {
                "__builtins__": _SAFE_BUILTINS,
                "df": df, "pd": pd, "np": np,
                "px": _seed["px"], "go": _seed["go"],
                "plt": _seed["plt"], "sns": _seed["sns"],
            }

            # 3. Captured stdout + 30-second execution timeout
            stdout_buf = io.StringIO()
            old_stdout, sys.stdout = sys.stdout, stdout_buf
            exec_error = None
            try:
                completed, raw_error = _exec_with_timeout(code_str, namespace, timeout=30)
                if not completed:
                    exec_success = False
                    exec_error = raw_error  # timeout message
                elif raw_error:
                    exec_success = False
                    # Sanitize: return only last traceback line, never full stack
                    exec_error = raw_error.strip().splitlines()[-1]
                else:
                    exec_success = True
            finally:
                sys.stdout = old_stdout
            
            printed = stdout_buf.getvalue().strip()
            
            if exec_success:
                break
            else:
                if attempt < max_retries - 1:
                    messages.append({
                        "role": "user",
                        "content": f"The code execution failed with this error:\n{exec_error}\n\nPlease analyze the error and provide the corrected python code block."
                    })
                    continue
                else:
                    break


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


