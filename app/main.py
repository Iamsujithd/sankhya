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

    # Prompt to write code
    code_prompt = f"""You are Sankhya — a world-class AI data scientist and mathematician. The user uploaded a dataset and you must write Python code that fully and correctly answers their query.

=== DATASET CONTEXT ===
Preloaded variable: `df` (pandas DataFrame — DO NOT reload from file)
Shape: {df.shape[0]} rows × {df.shape[1]} columns
Columns & dtypes: {cols_info}
Sample values (first 3 per column): {sample_vals}
scikit-learn available: {sklearn_available}

=== USER QUERY ===
{message}

=== RULES ===
1. **DataFrame**: Use the existing `df` variable. Never read from a file.
2. **Tabular output**: Assign a DataFrame or Series to `answer`.
   - Stats: `answer = df.describe()` or `answer = df.groupby(...).agg(...)`
   - Filter: `answer = df[df['col'] > value]`
   - Correlation: `answer = df.corr(numeric_only=True)` then plot it
   - Missing: `answer = df.isnull().sum().reset_index(name='missing_count')`
3. **Charts**: Assign a Plotly figure to `fig`.
   - Use `import plotly.express as px` or `import plotly.graph_objects as go`
   - NEVER use `px.dataframe`, `px.table`, `go.Table` as primary output — assign tables to `answer` instead
   - For heatmaps: `fig = px.imshow(df.corr(numeric_only=True), ...)` 
   - For histograms: use `px.histogram(df, x='col')`
   - For scatter: use `px.scatter(df, x='col1', y='col2')`
   - For bar: use `px.bar(df, x='col', y='val')`
4. **Machine learning** (if sklearn available): Use sklearn for regression, classification, or clustering. Always assign results to `answer`.
5. **Text analytics**: If the query involves text columns, use basic string operations or sklearn's TfidfVectorizer.
6. **Handle errors gracefully**: If a column doesn't exist, select the closest matching one. If numeric operations are requested on text columns, convert or skip gracefully.
7. **One answer at a time**: If the user asks for both a table and chart, produce both `answer` AND `fig`.
8. Do NOT use `print()` — assign results to `answer` or `fig`.
9. Do NOT include any explanation. Return ONLY the Python code block:

```python
# code here
```"""

    try:
        # Call Groq API
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": code_prompt}],
            temperature=0
        )
        llm_response = response.choices[0].message.content
        
        # Parse python code block
        code_match = re.search(r"```python\n(.*?)\n```", llm_response, re.DOTALL)
        code_str = code_match.group(1) if code_match else llm_response
        
        # Prepare namespace for execution
        namespace = {"df": df, "pd": pd, "np": np}
        exec("import plotly.express as px\nimport plotly.graph_objects as go\nimport matplotlib.pyplot as plt\nimport seaborn as sns", namespace)
        
        # Reset Matplotlib state before execution
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plt.clf()
        plt.close('all')
        
        # Execute code with stdout capturing
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
            
        fig = namespace.get("fig", None)
        answer = namespace.get("answer", None)
        
        # Fallback to stdout if answer is not set
        if answer is None and printed_output:
            answer = printed_output
            
        # Capture Matplotlib figure if generated
        matplotlib_img = None
        if plt.get_fignums():
            try:
                fig_plt = plt.gcf()
                buf = io.BytesIO()
                fig_plt.savefig(buf, format="png", bbox_inches="tight", dpi=150)
                buf.seek(0)
                import base64
                matplotlib_img = base64.b64encode(buf.read()).decode("utf-8")
                plt.close(fig_plt)
            except Exception as plot_err:
                print(f"Error capturing matplotlib plot: {plot_err}")
        
        # Convert chart to JSON
        fig_json = json.loads(pio.to_json(fig)) if fig else None
        
        # Parse answer output
        answer_data = None
        if isinstance(answer, (pd.DataFrame, pd.Series)):
            df_answer = pd.DataFrame(answer)
            # Map elements to be JSON safe
            df_json = df_answer.map(make_json_safe) if hasattr(df_answer, "map") else df_answer.applymap(make_json_safe)
            answer_data = {
                "type": "table",
                "columns": list(df_json.columns),
                "records": df_json.to_dict(orient="records")
            }
        elif answer is not None:
            answer_data = {
                "type": "text",
                "value": str(answer)
            }
            
        # Explanatory prompt
        if exec_success:
            has_chart = fig is not None
            has_table = answer_data is not None and answer_data.get("type") == "table"
            has_image = matplotlib_img is not None
            result_preview = str(answer)[:1500] if answer is not None else "(chart/visualization generated)"

            summary_prompt = f"""You are Sankhya — a brilliant AI data scientist known for clear, insightful explanations.

User Query: "{message}"

What was produced:
- Chart/Plot: {"Yes" if has_chart or has_image else "No"}
- Data Table: {"Yes" if has_table else "No"}
- Result preview: {result_preview}

Write a concise, insightful explanation (2-4 sentences) that:
1. Directly answers the user's query — don't say "I have processed"; say what the result actually tells us
2. Highlights key findings or notable numbers if applicable
3. Suggests a smart follow-up question the user might want to ask
Use **bold** for important numbers or column names. Be professional yet warm. No bullet points — flowing sentences only."""
        else:
            summary_prompt = f"""You are Sankhya — an expert AI data scientist.

User Query: "{message}"
Execution error: {exec_error[:600] if exec_error else "Unknown error"}

Explain in 2-3 sentences:
1. What likely went wrong (in plain English, not technical jargon)
2. A specific, actionable suggestion to reformulate the query (e.g. "Try asking: 'What is the average MEDV by CHAS?'")
Be warm and helpful. No apologies needed — just guide them forward."""

        summary_response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.2
        ).choices[0].message.content
        
        return make_json_safe({
            "status": "success" if exec_success else "error",
            "code": code_str,
            "explanation": summary_response,
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
