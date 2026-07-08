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
    
    # Prompt to write code
    code_prompt = f"""You are Sankhya, a wise data mathematician and expert data scientist. The user has uploaded a dataset.
Dataset context `df`:
- Columns & Types: {cols_info}
- Shape: {df.shape}

User query: "{message}"

Write a Python code block to answer this query. Follow these rules:
1. The preloaded DataFrame is named `df`. Do not load it again from a file.
2. To output tabular results, descriptive statistics, filters, calculations, or groupings, assign it to the `answer` variable (e.g. `answer = df.describe()`, `answer = df.head()`, or `answer = df.dtypes`).
3. To plot a chart, build a Plotly chart (Express `px` or Graph Objects `go`) and assign it to a variable named `fig`. 
   - CRITICAL: `plotly.express` (`px`) does NOT have a `.dataframe()` or `.table()` function. Never use `px.dataframe` or `px.table`. If the user asks for tables or raw data, assign the DataFrame directly to `answer` instead of plotting.
4. Return ONLY the python code block wrapped in standard markdown syntax:
```python
# python code here
```
Do not include any explanation or extra text. Only return the code block."""

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
            summary_prompt = f"""You are Sankhya, the divine data companion.
User Query: {message}
Executed Code:
```python
{code_str}
```
Result Object (answer):
{str(answer)[:1000]}

Explain this result to the user in a professional, warm, and concise tone. Mention that you have processed the calculations or plotted the chart as requested. Keep the summary under 4 sentences."""
        else:
            summary_prompt = f"""You are Sankhya, the divine data companion.
User Query: {message}
The code generated failed to execute with this error:
{exec_error}

Provide a helpful, polite explanation to the user about what went wrong and guide them on how to reformulate the query. Keep it brief."""

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
