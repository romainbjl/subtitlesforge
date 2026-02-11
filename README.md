🎬 SubMerge Pro

SubMerge Pro is a modular Python-based subtitle processor with a clean web interface. It allows you to batch-merge subtitle tracks (perfect for language learning or dual-language households), apply custom colors to specific tracks for better readability, and globally shift timestamps.
✨ Features

    Smart Batch Matching: Automatically pairs files using episode patterns (e.g., S01E01, 1x05) so you can upload an entire season at once.

    Dual-Language Merging: Combines two tracks into one file, matching cues based on a configurable millisecond threshold.

    HTML Coloring: Applies <font> tags to the secondary track, ensuring compatibility with most modern players (VLC, Plex, MPC-HC).

    Global Time Shifter: Shift all timestamps forward or backward to fix sync issues before merging.

    Web Interface: Drag-and-drop UI powered by Streamlit.

    Zip Export: Process dozens of files and download them all in a single compressed archive.

🛠️ Tech Stack

    Language: Python 3.12+

    Package Manager: uv (Extremely fast Rust-based manager)

    Logic Engine: pysubs2

    Frontend: Streamlit

🚀 Getting Started
1. Prerequisites

Ensure you have uv installed. If not, run:
Bash

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

2. Installation

Clone this repository or move into your project folder and sync the environment:
Bash

uv sync

3. Running the App

Launch the web interface using:
Bash

uv run streamlit run app.py

📖 How to Use

    Adjust Settings: Use the sidebar to set your merge threshold (default 1000ms) and choose which track to color.

    Pick Color: Select your preferred highlight color (e.g., Yellow #FFFF54).

    Identify Track B: Enter a keyword found in your secondary subtitle filenames (e.g., FR, French, SDH).

    Upload: Drag and drop all .srt or .ass files for the season into the upload box.

    Process: Click Process & Merge.

    Download: Download individual files or the complete ZIP archive.

📁 Project Structure
Plaintext

├── .venv/               # Virtual environment (managed by uv)
├── app.py               # Streamlit web interface
├── sub_engine.py        # Modular logic (merging, shifting, matching)
├── pyproject.toml       # Project dependencies and metadata
└── README.md            # You are here!

🔧 Modular Logic

The sub_engine.py is designed to be imported into other scripts. You can use the shift_subtitles or merge_subtitles functions independently for command-line automation.