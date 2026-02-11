# 🎬 SubtitlesForge

**SubtitlesForge** is a comprehensive, modular Python-based subtitle toolkit. It is a full-featured suite for translating, syncing, and "cleaning" subtitle files with a clean, responsive Streamlit web interface.

## ✨ Features

### 🔗 1. Batch Merger (Dual-Language)
Automatically pairs files using episode patterns and combines two tracks into one with custom coloring.
![Batch Merger Interface](https://github.com/user-attachments/assets/39eec33c-0ec5-405e-b7b6-227e6b050a65)

### 🤖 2. AI Translator
Translates subtitles via local LLMs (LM Studio) with a live side-by-side quality preview.
![AI Translator Interface](https://github.com/user-attachments/assets/db84b9e4-fb5a-4157-8285-6b0f7c9af6a3)

### ⏱️ 3. Quick Sync & Drift Fix
Apply global shifts or use the Drift Calculator to fix subtitles that desync over time.
![Quick Sync Interface](https://github.com/user-attachments/assets/8e4133d2-4371-4a15-96d1-50b3ac23746d)

### 🧼 4. Subtitle Sanitizer
Standardize encodings to UTF-8, strip ads, and remove hearing-impaired tags in bulk.
![Subtitle Sanitizer Interface](https://github.com/user-attachments/assets/401da32e-2815-48d7-9cae-e6bd4e5e100a)

## 🛠️ Tech Stack

**Language:** Python 3.12+

**Package Manager:** [uv](https://github.com/astral-sh/uv)

**Subtitle Logic:** `pysubs2`

**Encoding Detection:** `charset-normalizer`

**Frontend:** `Streamlit`

## 🚀 Getting Started
### 1. Prerequisites

Ensure you have uv installed:

    #### Windows
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

    #### macOS/Linux
    curl -LsSf https://astral.sh/uv/install.sh | sh

### 2. Installation

Clone the repository and sync the environment:

    uv sync

### 3. Running the App

    uv run streamlit run app.py

## 📖 Module Breakdown
### The Tabs

**Merger:** Upload two sets of subtitles. Enter a "Track B Keyword" (e.g., FR) so the app knows which language to color and place on the bottom.

**AI Translator:** Ensure your LM Studio server is running. Paste your local URL (default: http://localhost:1234/v1) and choose your model.

**Quick Sync:** If a movie starts fine but ends 2 seconds late, use the Drift Calculator to find your new Speed Factor.

**Sanitizer:** Use this as a "pre-processor" to ensure all your files are clean UTF-8 before merging or translating.

### File Structure

    ├── app.py              # Streamlit UI & Session State management
    ├── sub_engine.py       # Core logic (Merging, AI translation, Sanitization)
    ├── pyproject.toml      # Dependencies (pysubs2, requests, streamlit, etc.)
    └── README.md           # Documentation

### 🔧 Modular Logic

The `sub_engine.py` is designed to be headless. You can import its functions into your own CLI scripts:

- `normalize_subtitle()`: Standardizes encoding to UTF-8.

- `translate_subs()`: A generator function for AI-based batch translation.

- `merge_subtitles()`: Handles the heavy lifting of timestamp matching and color injection.