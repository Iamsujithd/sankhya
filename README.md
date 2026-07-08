# Sankhya (सांख्य) 🔮
### The AI-Powered Data Analyst & Machine Learning Companion

**Sankhya** (Sanskrit: सांख्य, meaning *Numbers*, *Calculation*, or *Intellect*) is a state-of-the-art, open-source AI Data Scientist. It streamlines and automates the entire lifecycle of data analysis—from preprocessing and missing value imputation to predictive modeling and conversational insights.

Developed by **[Sujith D](https://github.com/Iamsujithd)**.

---

## 🕉️ Philosophy & Concept

In ancient Sanskrit, **Sankhya** represents the systematic enumeration of the universe's elements to attain knowledge. In modern context, this application functions as a digital philosopher of data, analyzing numbers and translating complex statistics into plain English using advanced Large Language Models.

It supports ultra-fast inference via **Groq** (`llama-3.3-70b-versatile`) and **OpenAI** (`GPT-4o`).

---

## 🌟 Key Capabilities

### 1. Conversational Query Assistant (Chat with Data)
*   Upload any tabular file (`.csv`, `.xlsx`, `.xls`, `.json`).
*   Ask questions in plain English (e.g., *"Show me the correlation between prices and area"* or *"Identify the top 5 highest-performing segments"*).
*   Sankhya translates your questions into Python/Pandas execution scripts, runs them, and displays:
    *   **Tabular result data**
    *   **Interactive Plotly visualizations** (scatter plots, line charts, heatmaps, bar charts)
    *   **AI-generated observations** explaining what the numbers and charts actually denote.

### 2. End-to-End Automated Machine Learning
Choose an analytical mode and let Sankhya guide you through automated model building:
*   **Predictive Classification:** Automatically encodes categoricals, fills missing values, splits data, balances minority classes (SMOTE/ADASYN), and trains models like Random Forest, XGBoost, and SVM. Evaluates with confusion matrices and ROC curves.
*   **Regression Modeling:** Scales data, performs PCA, trains regression algorithms (Linear, Ridge, Lasso, RandomForest), and visualizes predictions vs. actuals alongside Q-Q plots.
*   **Clustering Discovery:** Runs silhouette and Calinski-Harabasz score analysis to identify natural groupings, trains KMeans/DBSCAN/GMM, and plots 3D/2D cluster graphs.

### 3. Automated Preprocessing & Data Imputation
*   **Missing Value Resolution:** AI analyzes columns to select the optimal fill method (Mean, Median, Mode, Interpolation, or New Category).
*   **Categorical Encoding:** AI determines whether columns should be Integer-Mapped or One-Hot Encoded, and drops long-text fields.
*   **Target Class Balancing:** Applies balancing strategies for highly skewed classification targets.

### 4. Custom Dark-Mode UI/UX
*   A premium, responsive UI styled with glassmorphic cards, deep navy/slate backgrounds (`#0A0E1A`), and neon blue/gold accents.

---

## 🛠️ Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/Iamsujithd/sankhya.git
cd sankhya
```

### 2. Initialize Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Your API Key (Optional)
To preload your API key without entering it in the web UI, set it as an environment variable:
```bash
# Mac / Linux
export GROQ_API_KEY="your_groq_api_key_here"

# Windows (Command Prompt)
set GROQ_API_KEY="your_groq_api_key_here"
```

### 5. Run the Application
```bash
streamlit run app/app.py
```

---

## 🌐 Cloud Deployment

Sankhya is pre-configured with a `Procfile` for one-click hosting on **Render** or **Hugging Face Spaces**. For detailed cloud deployment steps, please read the [Deployment Guide](deployment_guide.md).

---

## 📝 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
