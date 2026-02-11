🎬 SubtitlesForge

SubtitlesForge is a comprehensive, modular Python-based subtitle toolkit. It is a full-featured suite for translating, syncing, and "cleaning" subtitle files with a clean, responsive Streamlit web interface.

✨ Features
🔗 1. Batch Merger (Dual-Language)

    Smart Matching: Automatically pairs files using episode patterns (e.g., S01E01, 1x05).

    Dual-Track Logic: Combines two languages into one file, matching cues based on a configurable millisecond threshold.

    HTML Coloring: Applies <font> tags to specific tracks to distinguish languages (ideal for VLC, Plex, and MPC-HC).

🤖 2. AI Translator

    Local LLM Integration: Connects to LM Studio (or any OpenAI-compatible API) to translate subtitles using models like Llama 3 or Mistral.

    Context-Aware: Provide IMDB summaries or plot descriptions to help the AI maintain tone and gender-correct translations.

    Live Preview: Watch the translation happen line-by-line with a side-by-side comparison.

⏱️ 3. Quick Sync & Drift Fix

    Global Shifting: Apply millisecond offsets (positive or negative) to fix static delays.

    Linear Drift Calculator: Fix subtitles that start synced but slowly drift out of time by calculating the exact speed factor (FPS ratio) between two points.

🧼 4. Subtitle Sanitizer

    Encoding Fixer: Automatically detects and converts "corrupt" encodings (like Western Windows-1252) into standard UTF-8.

    Ad-Stripping: Removes common promotional spam from groups like YIFY or OpenSubtitles.

    HI Tag Removal: Strips Hearing Impaired descriptions like [Banging on door] or (Sighs).

    Bulk Regex: Use custom Find/Replace logic across multiple files simultaneously.

🛠️ Tech Stack

    Language: Python 3.12+

    Package Manager: uv

    Subtitle Logic: pysubs2

    Encoding Detection: charset-normalizer

    Frontend: Streamlit

🚀 Getting Started
1. Prerequisites

Ensure you have uv installed:
Bash

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

2. Installation

Clone the repository and sync the environment:
Bash

uv sync

3. Running the App
Bash

uv run streamlit run app.py

📖 Module Breakdown
The Tabs

    Merger: Upload two sets of subtitles. Enter a "Track B Keyword" (e.g., FR) so the app knows which language to color and place on the bottom.

    AI Translator: Ensure your LM Studio server is running. Paste your local URL (default: http://localhost:1234/v1) and choose your model.

    Quick Sync: If a movie starts fine but ends 2 seconds late, use the Drift Calculator to find your new Speed Factor.

    Sanitizer: Use this as a "pre-processor" to ensure all your files are clean UTF-8 before merging or translating.

File Structure
Plaintext

├── app.py              # Streamlit UI & Session State management
├── sub_engine.py       # Core logic (Merging, AI translation, Sanitization)
├── pyproject.toml      # Dependencies (pysubs2, requests, streamlit, etc.)
└── README.md           # Documentation

🔧 Modular Logic

The sub_engine.py is designed to be headless. You can import its functions into your own CLI scripts:

    normalize_subtitle(): Standardizes encoding to UTF-8.

    translate_subs(): A generator function for AI-based batch translation.

    merge_subtitles(): Handles the heavy lifting of timestamp matching and color injection.