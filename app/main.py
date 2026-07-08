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
        raise HTTPException(status_code=400, detail="GROQ_API_KEY environment variable is not configured! Please set it before running queries.")
    if "df" not in store:
        raise HTTPException(status_code=400, detail="No dataset uploaded yet. Please upload a dataset first!")
    
    df = store["df"]
    filename = store.get("filename", "uploaded file")
    cols_info = ", ".join([f"{col} ({dtype})" for col, dtype in zip(df.columns, df.dtypes)])
    
    # Detect available sklearn for ML queries
    try:
        import sklearn  # noqa
        sklearn_available = True
    except ImportError:
        sklearn_available = False

    # Build column sample values for richer context
    sample_vals = {}
    for col in df.columns[:8]:
        vals = df[col].dropna().head(3).tolist()
        sample_vals[col] = vals

    try:
        # ══════════════════════════════════════════════════════════════════
        # STEP 1: COMBINED CLASSIFIER + CHAT RESPONSE (single LLM call)
        # The model classifies the intent AND generates the reply in one
        # shot — eliminating the extra round-trip for CHAT queries.
        # ══════════════════════════════════════════════════════════════════
        combined_prompt = f"""You are Sankhya — an expert AI data companion.
The user has loaded a dataset: "{filename}" with {df.shape[0]} rows × {df.shape[1]} columns.
Columns & types: {cols_info}
Sample values (first 3 per column): {sample_vals}

TASK: Decide whether the user's message needs Python code execution on the data, or can be answered conversationally.

=== INTENT RULES ===
Reply with intent=CODE if the user wants: computation, calculation, filtering, aggregation, statistics, plotting, visualization, ML, prediction, groupby, correlation, missing values, sorting — anything that runs on the actual data rows.

Reply with intent=CHAT for everything else: greetings, general questions, advisory/opinion, concept explanations, column descriptions, capability questions, "what KPI", "what should I analyze", "who are you", "explain X", "is this good for ML?", etc.
When in doubt → CHAT.

=== OUTPUT FORMAT (strict JSON, no markdown) ===
If CHAT: {{"intent":"CHAT","reply":"<your answer here>"}}
If CODE: {{"intent":"CODE"}}

=== CHAT GUIDELINES (only used when intent=CHAT) ===
- Greetings: warm intro, mention what you can do with this specific dataset
- Advisory ("what KPI?", "what to analyze?"): give expert data science advice, name actual columns
- Column questions: describe based on dtype and sample values  
- Concept questions: explain clearly, relate to this dataset
- Keep reply to 2-5 sentences. Use **bold** for key terms/column names.
- Never say you can't answer.

User message: "{message}"

Respond with JSON only:"""

        combined_resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": combined_prompt}],
            temperature=0,
            max_tokens=512
        )
        raw = combined_resp.choices[0].message.content.strip()

        # Parse JSON response — strip any accidental markdown wrapping
        json_str = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw, flags=re.MULTILINE).strip()
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            # Fallback: if JSON is malformed, try to detect intent from raw text
            is_code_fallback = '"intent":"CODE"' in raw or raw.upper().startswith('CODE')
            parsed = {"intent": "CODE" if is_code_fallback else "CHAT", "reply": raw}

        is_code = parsed.get("intent", "CHAT").upper() == "CODE"

        # ══════════════════════════════════════════════════════════════════
        # STEP 2A: CHAT PATH — reply already generated above, just return it
        # ══════════════════════════════════════════════════════════════════
        if not is_code:
            reply = parsed.get("reply", "I'm ready to help — ask me anything about your dataset!")
            return make_json_safe({
                "status": "success",
                "intent": "chat",
                "code": None,
                "explanation": reply,
                "answer": None,
                "chart": None,
                "image": None,
                "error": None
            })


        # ══════════════════════════════════════════════════════════════════
        # STEP 2B: CODE PATH — generate & execute Python, then explain
        # ══════════════════════════════════════════════════════════════════
        code_prompt = f"""You are Sankhya — a world-class AI data scientist. The user uploaded a dataset and you must write Python code that fully and correctly answers their query.

=== DATASET CONTEXT ===
Preloaded variable: `df` (pandas DataFrame — DO NOT reload from file)
Shape: {df.shape[0]} rows × {df.shape[1]} columns
Columns & dtypes: {cols_info}
Sample values (first 3 per column): {sample_vals}
scikit-learn available: {sklearn_available}

=== USER QUERY ===
{message}

=== RULES ===
1. Use the existing `df` variable. Never read from a file.
2. For tabular output (stats, filters, groupby, aggregations), assign a DataFrame or Series to `answer`.
3. For charts, assign a Plotly figure to `fig` using `px` or `go`.
   - NEVER use `px.dataframe`, `px.table`, or `go.Table` — assign data to `answer` instead.
   - Heatmap: `fig = px.imshow(df.corr(numeric_only=True), text_auto=True)`
   - Histogram: `px.histogram(df, x='col')`
   - Scatter: `px.scatter(df, x='col1', y='col2')`
4. For ML queries, use sklearn — assign predictions/metrics to `answer`.
5. If a column doesn't exist, pick the closest matching one gracefully.
6. You may produce both `answer` AND `fig` if appropriate.
7. Do NOT use `print()`. Do NOT include explanations.
8. Return ONLY a Python code block:

```python
# code here
```"""

        code_resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": code_prompt}],
            temperature=0
        )
        llm_response = code_resp.choices[0].message.content
        
        # Extract code block
        code_match = re.search(r"```python\n(.*?)\n```", llm_response, re.DOTALL)
        code_str = code_match.group(1) if code_match else llm_response
        
        # Build execution namespace
        namespace = {"df": df, "pd": pd, "np": np}
        exec("import plotly.express as px\nimport plotly.graph_objects as go\nimport matplotlib.pyplot as plt\nimport seaborn as sns", namespace)
        
        # Reset Matplotlib
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plt.clf()
        plt.close('all')
        
        # Capture stdout
        import io
        import sys
        stdout_capture = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = stdout_capture
        
        try:
            exec(code_str, namespace)
            exec_success = True
            exec_error = None
        except Exception as err:
            exec_success = False
            exec_error = traceback.format_exc()
        finally:
            sys.stdout = old_stdout
            
        printed_output = stdout_capture.getvalue().strip()
        fig    = namespace.get("fig", None)
        answer = namespace.get("answer", None)
        
        # Fallback: use stdout if answer not explicitly set
        if answer is None and printed_output:
            answer = printed_output
            
        # Capture Matplotlib figure
        matplotlib_img = None
        if plt.get_fignums():
            try:
                import base64
                fig_plt = plt.gcf()
                buf = io.BytesIO()
                fig_plt.savefig(buf, format="png", bbox_inches="tight", dpi=150)
                buf.seek(0)
                matplotlib_img = base64.b64encode(buf.read()).decode("utf-8")
                plt.close(fig_plt)
            except Exception as plot_err:
                print(f"Matplotlib capture error: {plot_err}")
        
        # Convert Plotly chart to JSON
        fig_json = json.loads(pio.to_json(fig)) if fig else None
        
        # Serialize answer
        answer_data = None
        if isinstance(answer, (pd.DataFrame, pd.Series)):
            df_answer = pd.DataFrame(answer)
            df_safe = df_answer.map(make_json_safe) if hasattr(df_answer, "map") else df_answer.applymap(make_json_safe)
            answer_data = {
                "type": "table",
                "columns": list(df_safe.columns),
                "records": df_safe.to_dict(orient="records")
            }
        elif answer is not None:
            answer_data = {"type": "text", "value": str(answer)}
            
        # Generate explanation
        if exec_success:
            has_chart = fig is not None or matplotlib_img is not None
            has_table = answer_data is not None and answer_data.get("type") == "table"
            result_preview = str(answer)[:1500] if answer is not None else "(visualization generated)"

            explanation_prompt = f"""You are Sankhya — a brilliant AI data scientist known for clear, insightful explanations.

User Query: "{message}"

Produced:
- Visualization: {"Yes" if has_chart else "No"}
- Data Table: {"Yes" if has_table else "No"}
- Result preview: {result_preview}

Write a concise, insightful response (2-4 sentences):
1. State what the result shows — don't say "I have processed", say what the data tells us
2. Call out key numbers or patterns if visible
3. Suggest one smart follow-up question
Use **bold** for key numbers or column names. Flowing sentences, no bullet points."""
        else:
            explanation_prompt = f"""You are Sankhya — an expert AI data scientist.

User Query: "{message}"
Error: {exec_error[:600] if exec_error else "Unknown error"}

In 2-3 sentences: explain in plain English what went wrong and give one specific, actionable suggestion to rephrase the query. Be helpful and direct."""

        explanation_resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": explanation_prompt}],
            temperature=0.2
        )
        explanation = explanation_resp.choices[0].message.content
        
        return make_json_safe({
            "status": "success" if exec_success else "error",
            "intent": "code",
            "code": code_str,
            "explanation": explanation,
            "answer": answer_data,
            "chart": fig_json,
            "image": matplotlib_img,
            "error": exec_error
        })
        
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to query AI: {str(e)}")

# Mount static files (will be loaded at /)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
