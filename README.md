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
- Quality-first sliding context with adjustable dialogue groups
- Previous accepted translations and upcoming source lines as context
- Optional second pass for consistent tone, pronouns, terminology, and idioms
- Validated subtitle IDs with automatic smaller-group and individual fallback
- Preserves formatting, line breaks, segmentation, and timing

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
git clone https://github.com/romainbjl/subtitlesforge.git
cd subtitlesforge
uv sync
uv run python main.py
```

### Alternative (using pip)

```bash
git clone https://github.com/romainbjl/subtitlesforge.git
cd subtitlesforge
python -m pip install .
python main.py
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
   - Keep **Contextual sliding window** selected for the best dialogue quality
   - Optionally describe the movie, genre, tone, and character names
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
    path_a='english.srt',
    path_b='french.srt',
    output_path='merged.srt',
    threshold_ms=1000,
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

Repair output is parsed and validated before being saved. A successful repair
therefore always contains at least one non-empty subtitle entry.

Context-aware translation is also available as a library generator:

```python
import pysubs2
from sub_engine import translate_subs

subs = pysubs2.load("episode.srt", encoding="utf-8")
for progress, source, translated in translate_subs(
    subs,
    "http://localhost:1234/v1",
    "typhoon-translate1.5-4b@q8_0",
    "English",
    "French",
    context_info="A dry comedy; keep character names unchanged.",
    group_size=4,
    previous_context=8,
    next_context=8,
    temperature=0.4,
    review_temperature=0.3,
    consistency_pass=True,
):
    print(f"{progress:.0%}", source, translated)

subs.save("translated.srt", encoding="utf-8")
```

### Running tests

```bash
uv sync --group dev
uv run pytest
```

## AI Translation Setup

### Recommended quality settings

The default contextual mode translates four subtitle events at a time. It gives
the model eight earlier events (including accepted translations) and eight future
source events as read-only context. The optional consistency pass then reviews
eight translations inside a window of up to 24 dialogue events.

The initial translation uses temperature `0.4` by default for more natural,
idiomatic dialogue. The consistency review uses a more conservative `0.3` to
keep corrections focused and structurally reliable. Both values are adjustable
in the interface.

Every translated event uses a stable ID. If the model omits or changes an ID, the
request is automatically retried with smaller groups and finally as an individual
subtitle. A malformed consistency review is discarded, leaving the validated
first-pass translation unchanged.

Individual mode remains available for narrowly fine-tuned models that cannot
follow structured prompts. It is faster but provides no dialogue context or
consistency review.

### LM Studio
1. Download from [lmstudio.ai](https://lmstudio.ai)
2. Load a model (openai/gpt-oss-20b, Mistral 7B, Llama 3, etc.)
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
