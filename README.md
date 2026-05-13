# Confluence PDF Exporter

A Python tool that converts Confluence Cloud pages into **document PDFs** and **presentations (slides)**. Available as both a **web GUI** and a **CLI**.

It addresses the limitations of Confluence's built-in PDF exporter (e.g., missing line numbers in code blocks, poor styling) and allows pages to be used directly as presentation materials.

## Features

- **Web GUI** — Browser-based interface (Flask) with real-time progress
- **Document PDF** — Cover page + auto-generated TOC + body + back page
- **Presentation HTML** — Slide-based presentation (keyboard/mouse navigation)
- **Presentation PDF** — 16:9 slide PDF
- Custom logo support (default: PinkLAB logo)
- Configurable output directory and filenames
- Line numbers in code blocks
- Base64 inline image embedding (standalone)
- Automatic video attachment download & playback support
- Confluence macro conversion (panels, expand, status, emoticon, links, etc.)

## Prerequisites

- [Conda](https://docs.conda.io/) (Miniconda or Anaconda)
- Confluence Cloud account + API Token

## Setup

### 1. Create Conda Environment

```bash
conda create -n confluence python=3.11 -y
conda activate confluence
```

### 2. Install Packages

```bash
pip install requests beautifulsoup4 playwright flask
playwright install chromium
```

### 3. Configure Authentication

Create a `confluence_token.txt` file in the project root:

```
CONFLUENCE_URL=https://your-domain.atlassian.net
CONFLUENCE_EMAIL=your-email@example.com
CONFLUENCE_API_TOKEN=your-api-token-here
```

> You can generate an API Token at [Atlassian API Token Management](https://id.atlassian.com/manage-profile/security/api-tokens).

## Usage

### Web GUI (Recommended)

**One-click launch** — double-click `start.command` in Finder. It activates conda, starts the server, and opens your browser automatically.

Or manually:

```bash
conda activate confluence
python app.py
```

Open **http://localhost:5001** in your browser. The GUI provides:

- Confluence page URL input
- Logo selection (default PinkLAB logo, or upload a custom logo)
- Output directory configuration (default: `~/Downloads`)
- Per-file generation toggle (checkbox to enable/disable each output)
- Custom filenames for all 3 output files
- Real-time export progress log
- Direct "Open" links to view generated files in browser

### CLI

```bash
conda activate confluence

# Basic usage
python confluence_export.py "https://your-domain.atlassian.net/wiki/spaces/SPACE/pages/PAGE_ID/Page+Title"

# Specify output directory
python confluence_export.py "PAGE_URL" --output-dir ./my_output
```

### Output

Three files are generated in the `output/` directory:

| File | Description |
|------|-------------|
| `Page_Title.pdf` | A4 document PDF (cover + TOC + body + back page) |
| `present_Page_Title.html` | Presentation HTML (can be presented directly in a browser) |
| `present_Page_Title.pdf` | Presentation PDF (16:9 slides) |

### Presentation Controls

Open the presentation HTML in a browser to use it as a slideshow:

| Action | Key |
|--------|-----|
| Next slide | `Space`, `→`, `↓`, `PageDown` |
| Previous slide | `←`, `↑`, `PageUp` |
| Go to first slide | `Home` |
| Go to last slide | `End` |
| Mouse wheel | Scroll up/down to navigate slides |
| Open TOC | `T` |

## Dependencies

| Package | Version | Role |
|---------|---------|------|
| `requests` | >= 2.28 | Confluence REST API calls |
| `beautifulsoup4` | >= 4.12 | HTML parsing and Confluence macro conversion |
| `playwright` | >= 1.40 | Headless Chromium PDF rendering |
| `flask` | >= 3.0 | Web GUI server |

## File Structure

```
confluence_print/
├── start.command             # macOS one-click launcher (double-click)
├── app.py                    # Flask web GUI server
├── confluence_export.py      # Core export engine + CLI entry point
├── templates/
│   └── index.html            # Web GUI template
├── static/
│   └── pinklab_logo_text.png # Logo (symlink)
├── pinklab_logo_text.png     # PinkLAB logo (cover/back pages)
├── confluence_token.txt      # Auth config (not in git)
├── .gitignore
├── README.md
├── history.md / history.html
├── architecture.md / architecture.html
├── uploads/                  # Temp uploaded logos (not in git)
└── output/                   # Generated files
```

## Supported Confluence Macros

| Macro | Conversion |
|-------|-----------|
| `code` | Styled code block with line numbers |
| `info` / `note` / `warning` / `tip` / `error` | Colored panels |
| `expand` | Expand/Collapse sections (shown expanded) |
| `status` | Colored status lozenges |
| `toc` | Removed (custom TOC page generated) |
| `ac:image` | Base64 inline embedded images |
| `ac:image` (video) | Video file download & `<video>` tag embedding |
| `ac:link` | Standard HTML `<a>` tags |
| `ac:emoticon` | Unicode emoji |
| Others | Graceful fallback (body content preserved) |
