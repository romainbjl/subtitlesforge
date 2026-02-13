# 🎬 SubtitlesForge

A powerful, all-in-one subtitle toolkit built with Python and Streamlit. Merge dual-language subs, translate with local AI, fix timing issues, and repair encoding corruption — all through a clean web interface.

![Python](https://img.shields.io/badge/python-3.12+-blue.svg)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
![Streamlit](https://img.shields.io/badge/streamlit-1.30+-red.svg)

## Features

### 🔗 Batch Merger
Merge dual-language subtitle files with smart episode detection and custom color coding.

- Auto-pairs files by episode code (S01E01, E05, etc.)
- Independent timing adjustments for each track
- Customizable color coding for language distinction
- Configurable alignment threshold (0-5000ms)

![Batch Merger Interface](https://github.com/user-attachments/assets/810b39d0-0e3f-4fbd-ba3d-5fba69f75ed7)

### 🤖 AI Translator
Translate subtitles using local LLMs (LM Studio, Ollama) or any OpenAI-compatible API.

- Real-time side-by-side preview
- Batch processing with adjustable sizes
- Context-aware translation
- Preserves formatting and timing

![AI Translator Interface](https://github.com/user-attachments/assets/1d50491d-0397-4369-9859-189fa7516cbf)

### ⏱️ Quick Sync
Fix subtitle timing with global shifts or drift correction for progressive desync.

- Simple time shift (ms precision)
- Drift calculator for frame rate issues
- Batch processing support

![Quick Sync Interface](https://github.com/user-attachments/assets/1bac3a5e-0698-4b1e-91f8-2309961a262a)

### 🧼 Sanitizer
Clean and standardize subtitle files in bulk.

- Auto UTF-8 normalization with smart encoding detection
- Strip advertising and hearing-impaired tags
- Batch processing with preview

![Subtitle Sanitizer Interface](https://github.com/user-attachments/assets/746138c1-ffa5-4bb5-a143-ae7b3ef488a6)

### 🔧 Encoding Repair Lab
Analyze and repair corrupted subtitle files (mojibake, double-encoding, wrong codepage).

- Detects Thai, French, Chinese, and Western European corruption
- Multi-strategy repair algorithms
- Detailed analysis reports with confidence scores

**Fixes common issues like:**
- Thai: `à¸œà¸¡` → `ผม`
- French: `Ã©` → `é`, `¶` → `ô`
- Chinese: Garbled characters → proper Unicode

## Installation

### Quick Start

1. Install [uv](https://github.com/astral-sh/uv) (recommended):

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

2. Clone and run:

```bash
git clone https://github.com/yourusername/SubtitlesForge.git
cd SubtitlesForge
uv sync
uv run streamlit run app.py
```

### Alternative (using pip)

```bash
git clone https://github.com/yourusername/SubtitlesForge.git
cd SubtitlesForge
pip install -r requirements.txt  # if you generate one from pyproject.toml
streamlit run app.py
```

## Usage

### Basic Workflow

1. **Merger**: Upload paired subtitle files (e.g., `episode01.en.srt` + `episode01.fr.srt`)
   - Set Track B keyword to identify which language to colorize
   - Adjust timing if needed
   - Download merged files

2. **Translator**: 
   - Start LM Studio or Ollama
   - Enter API endpoint (default: `http://localhost:1234/v1`)
   - Upload subs and translate

3. **Quick Sync**:
   - Simple delay: enter shift in ms
   - Drift issue: use drift calculator with start/end reference points

4. **Sanitizer**: Upload files → enable cleaning options → download

5. **Repair Lab**: Upload corrupted files → analyze → repair if needed

### Using as a Library

`sub_engine.py` can be imported and used standalone:

```python
from sub_engine import normalize_subtitle, merge_subtitles, repair_corrupted_encoding

# Fix encoding
normalize_subtitle('input.srt', 'output.srt')

# Merge dual-language subs
merge_subtitles(
    track_a='english.srt',
    track_b='french.srt', 
    output='merged.srt',
    threshold=1000,
    color_hex='#FFFF54',
    color_track='Track B'
)

# Repair corrupted file
success, corruption_type, method = repair_corrupted_encoding(
    'corrupted.srt',
    'repaired.srt',
    target_script='french'
)
```

## AI Translation Setup

### LM Studio
1. Download from [lmstudio.ai](https://lmstudio.ai)
2. Load a model (Mistral 7B, Llama 3, etc.)
3. Start local server → use `http://localhost:1234/v1`

### Ollama
```bash
ollama serve
# Use http://localhost:11434/v1
```

### Other APIs
Any OpenAI-compatible endpoint works (OpenAI, Azure, custom deployments).

## Tech Stack

- **Python 3.12+**
- **[uv](https://github.com/astral-sh/uv)** - Fast package management
- **[Streamlit](https://streamlit.io)** - Web interface
- **[pysubs2](https://github.com/tkarabela/pysubs2)** - Subtitle parsing
- **[charset-normalizer](https://github.com/Ousret/charset_normalizer)** - Encoding detection

## Troubleshooting

**Garbled characters (Ã©, ¶, Ķ)?**
→ Use Repair Lab or Sanitizer with "Fix encoding issues"

**Subtitles won't merge?**
→ Increase threshold to 2000-3000ms, verify episode codes match

**AI translation fails?**
→ Check LM Studio is running, verify API URL and model is loaded

**Subs drift over time?**
→ Use Drift Calculator instead of simple shift (likely frame rate mismatch)

## Contributing

Pull requests welcome! For major changes, please open an issue first.