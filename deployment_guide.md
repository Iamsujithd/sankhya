# Deployment Guide — Sankhya (AI Data Analyst)

You can deploy this AI Data Agent **for free** on either **Render** or **Hugging Face Spaces**. Both platforms support Python/Streamlit natively and will auto-redeploy every time you push code to GitHub.

---

## Option 1: Deploy for Free on **Render** (Recommended)

Render is the simplest way to deploy. The repository is already pre-configured with a `Procfile`.

### Step 1: Push the Code to GitHub
1. Create a new, blank repository named `sankhya` on GitHub.
2. Open your terminal in the `sankhya` folder and run:
   ```bash
   git init
   git add .
   git commit -m "Initial commit of Sankhya"
   git branch -M main
   git remote add origin https://github.com/Iamsujithd/sankhya.git
   git push -u origin main --force
   ```

### Step 2: Deploy to Render
1. Go to [Render](https://render.com) and log in with your GitHub account.
2. Click **New +** (top right) and select **Web Service**.
3. Select your `sankhya` repository.
4. Fill in the configuration:
   *   **Name:** `sankhya`
   *   **Environment:** `Python 3`
   *   **Region:** Select the closest region (e.g., Oregon or Frankfurt).
   *   **Branch:** `main`
   *   **Build Command:** `pip install -r requirements.txt`
   *   **Start Command:** `streamlit run app/app.py --server.port $PORT --server.address 0.0.0.0`
   *   **Instance Type:** `Free`

### Step 3: Configure the Groq Key (Crucial!)
To avoid having to type your API key in the web interface every time:
1. Go to the **Environment** tab inside your Render Web Service dashboard.
2. Add a new **Environment Variable**:
   *   **Key:** `GROQ_API_KEY`
   *   **Value:** `your_groq_api_key_here`
3. Click **Save Changes**. Render will automatically rebuild and deploy your app with the key preloaded!

---

## Option 2: Deploy for Free on **Hugging Face Spaces**

Hugging Face Spaces provides permanent free hosting with zero sleep/timeout limitations for basic apps, making it a stellar addition to a developer portfolio.

### Step 1: Create a Space on Hugging Face
1. Go to [Hugging Face](https://huggingface.co) and sign in.
2. Click on your profile icon (top right) and select **New Space**.
3. Configure the Space:
   *   **Space Name:** `sankhya`
   *   **SDK:** Select **Streamlit**.
   *   **Space Hardware:** `CPU basic (Free)`
   *   **Visibility:** `Public`
4. Click **Create Space**.

### Step 2: Push your Files
Hugging Face will give you a Git URL. You can push your files directly to it:
1. In your `sankhya` folder, add the Hugging Face remote:
   ```bash
   git remote add hf HTTPS_LINK_GIVEN_BY_HUGGING_FACE
   ```
2. Push the files:
   ```bash
   git push -f hf main
   ```

### Step 3: Add the Groq Key as a Space Secret
1. Go to your Space settings.
2. Under **Variables and Secrets**, add a new Secret:
   *   **Name:** `GROQ_API_KEY`
   *   **Value:** `your_groq_api_key_here`
3. Your app will automatically build and start running.
