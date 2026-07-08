import streamlit as st
import pandas as pd
import re
import traceback
from src.llm_service import get_chat_model
from langchain.schema import HumanMessage

def execute_analysis_code(df, code_str):
    """
    Safely executes python code on the dataframe and captures outputs (answer, fig).
    """
    # Create isolated namespace with df preloaded
    namespace = {"df": df, "pd": pd}
    try:
        # Import plotting libraries inside namespace just in case
        exec("import plotly.express as px\nimport plotly.graph_objects as go", namespace)
        exec(code_str, namespace)
        return {
            "success": True,
            "answer": namespace.get("answer", None),
            "fig": namespace.get("fig", None),
            "error": None
        }
    except Exception as e:
        error_msg = traceback.format_exc()
        return {
            "success": False,
            "answer": None,
            "fig": None,
            "error": error_msg
        }

def run_copilot(df, api_key, model_choice):
    st.markdown("### 🤖 Sankhya AI Assistant")
    st.write("Talk directly to your dataset in plain English. Ask questions, request calculations, or generate custom charts.")

    # Initialize chat history
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "assistant", "content": "Namaste! I am Sankhya, your AI Data Companion. Upload your data and ask me anything!"}
        ]

    # Quick suggestion chips
    st.markdown("**Suggestions:**")
    s_col1, s_col2, s_col3 = st.columns(3)
    with s_col1:
        if st.button("📊 Show data overview"):
            st.session_state.suggestions_input = "Show me the general columns, shape, and a brief description of the dataset."
    with s_col2:
        if st.button("📈 Check for missing values"):
            st.session_state.suggestions_input = "List columns with missing values and the percentage of nulls in each."
    with s_col3:
        if st.button("🔍 Find correlation matrix"):
            st.session_state.suggestions_input = "Identify correlation between numeric columns and plot a heatmap."

    # Display chat history
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "fig" in message and message["fig"] is not None:
                st.plotly_chart(message["fig"], use_container_width=True)
            if "df_result" in message and message["df_result"] is not None:
                st.dataframe(message["df_result"], use_container_width=True)

    # Get input (from suggestions or user input)
    user_input = st.chat_input("Ask a question about the dataset...")
    
    if "suggestions_input" in st.session_state and st.session_state.suggestions_input:
        user_input = st.session_state.suggestions_input
        st.session_state.suggestions_input = None

    if user_input:
        # User message
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Assistant response container
        with st.chat_message("assistant"):
            status_placeholder = st.empty()
            status_placeholder.markdown("*AI is thinking...*")

            try:
                llm = get_chat_model(model_choice, api_key)
                
                # Context prep
                cols_info = ", ".join([f"{col} ({dtype})" for col, dtype in zip(df.columns, df.dtypes)])
                df_head = df.head(3).to_string()
                
                # Code generation prompt
                code_prompt = f"""You are an expert AI Data Analyst. The user has uploaded a dataset.
Here is the context of the dataset `df`:
- Columns & Types: {cols_info}
- Shape: {df.shape}
- Sample head (first 3 rows):
{df_head}

User Query: "{user_input}"

Write a Python code block to answer the user's request. Follow these rules:
1. The preloaded DataFrame is named `df`.
2. To show tabular data, filters, or calculations, assign it to a variable named `answer` (e.g. `answer = df.groupby('col').mean()`).
3. To display a plot, build a Plotly chart (Express `px` or Graph Objects `go`) and assign it to a variable named `fig`.
4. Return ONLY the python code block wrapped in standard markdown syntax:
```python
# python code here
```
Do not include any explanation or extra text. Only return the code block."""

                llm_response = llm([HumanMessage(content=code_prompt)]).content
                
                # Parse python code block
                code_match = re.search(r"```python\n(.*?)\n```", llm_response, re.DOTALL)
                if code_match:
                    code_str = code_match.group(1)
                else:
                    code_str = llm_response

                status_placeholder.markdown("*Executing data query...*")
                
                # Execute the generated python code
                execution = execute_analysis_code(df, code_str)
                
                if execution["success"]:
                    fig_to_show = execution["fig"]
                    answer_to_show = execution["answer"]
                    
                    # Generate natural language summary using the results
                    summary_prompt = f"""You are an expert AI Data Analyst.
User Question: {user_input}
Python Code Executed:
```python
{code_str}
```
Result Object (answer):
{str(answer_to_show)[:2000]}

Explain this result to the user in a professional, concise business tone. If a plot (fig) was created, mention that you have plotted the chart below. Keep your explanation under 4 sentences."""
                    
                    summary_response = llm([HumanMessage(content=summary_prompt)]).content
                    
                    # Display response
                    status_placeholder.empty()
                    st.markdown(summary_response)
                    
                    df_to_save = None
                    if isinstance(answer_to_show, (pd.DataFrame, pd.Series)):
                        df_to_save = pd.DataFrame(answer_to_show)
                        st.dataframe(df_to_save, use_container_width=True)
                    elif answer_to_show is not None:
                        st.info(f"**Value:** {answer_to_show}")
                        
                    if fig_to_show is not None:
                        st.plotly_chart(fig_to_show, use_container_width=True)
                        
                    # Save to chat history
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": summary_response,
                        "fig": fig_to_show,
                        "df_result": df_to_save
                    })
                    
                else:
                    status_placeholder.empty()
                    st.error("Error executing the analysis. Let me try a simpler explanation.")
                    fallback_prompt = f"The user asked: '{user_input}'. The dataset columns are: {cols_info}. Explain how they could answer this question using pandas or visualization."
                    fallback_response = llm([HumanMessage(content=fallback_prompt)]).content
                    st.markdown(fallback_response)
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": fallback_response
                    })

            except Exception as e:
                status_placeholder.empty()
                st.error(f"Cannot complete request. Details: {e}")
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": f"Sorry, I encountered an error: {e}"
                })
            
            # Rerender to preserve state
            st.rerun()
