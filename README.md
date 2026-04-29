# Confluence PDF Exporter

A Python tool that converts Confluence Cloud pages into **document PDFs** and **presentations (slides)**. Available as both a **web GUI** and a **CLI**.

It addresses the limitations of Confluence's built-in PDF exporter (e.g., missing line numbers in code blocks, poor styling) and allows pages to be used directly as presentation materials.

## Features

- **Web GUI** — Browser-based interface (Flask) with real-time progress bar
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

- Confluence Cloud account + API Token
- **Python 3.10+** (venv 사용 시) 또는 **Conda** (Miniconda / Anaconda)
- macOS / Windows 모두 지원, conda와 venv 모두 지원

> 런처 스크립트가 conda 설치 여부를 **자동으로 감지**합니다.
> conda가 있으면 conda를, 없으면 venv를 자동으로 사용합니다.

## Setup

### 1. Clone

```bash
git clone https://github.com/PinkWink/confluece_slide_and_pdf
cd confluece_slide_and_pdf
```

### 2. 초기 설정 (최초 1회)

| OS | 실행 파일 | 방법 |
|----|-----------|------|
| macOS | `setup.sh` | 터미널에서 `chmod +x setup.sh && ./setup.sh` |
| Windows | `setup.bat` | 더블클릭 |

실행하면 conda / venv를 자동 감지하여:
- 가상환경 생성 (`confluence` 또는 `venv/`)
- 패키지 설치 (`requirements.txt`)
- Playwright Chromium 설치

### 3. 인증 설정

프로젝트 루트에 `confluence_token.txt` 파일 생성:

```
CONFLUENCE_URL=https://your-domain.atlassian.net
CONFLUENCE_EMAIL=your-email@example.com
CONFLUENCE_API_TOKEN=your-api-token-here
```

> API Token 발급: [Atlassian API Token Management](https://id.atlassian.com/manage-profile/security/api-tokens)

### 4. 실행

| OS | 실행 파일 | 방법 |
|----|-----------|------|
| macOS | `start.sh` 또는 `Conf. Exporter.command` | 터미널 또는 Finder에서 더블클릭 |
| Windows | `start.bat` | 더블클릭 |

브라우저에서 **http://localhost:5001** 자동으로 열립니다.

---

## 환경별 동작 방식

### macOS

```
conda 설치됨?
  ├── YES → conda activate confluence → python app.py
  └── NO  → source venv/bin/activate  → python app.py
```

### Windows

```
conda 설치됨?
  ├── YES → conda activate confluence → python app.py
  └── NO  → venv\Scripts\activate    → python app.py
```

---

## Usage

### Web GUI (Recommended)

Open **http://localhost:5001** in your browser. The GUI provides:

- Confluence page URL input + Export 버튼 (URL 바로 아래)
- 실시간 프로그레스 바 (단계별 % 표시)
- "자세히 보기" 클릭 시 상세 로그 확인
- Logo selection (default PinkLAB logo, or upload custom)
- Output directory configuration (default: `~/Downloads`)
- Per-file generation toggle (Document PDF / Presentation HTML / PDF)
- Custom filenames for all 3 output files
- Direct "Open" links to view generated files in browser

### CLI

```bash
# macOS (conda)
conda activate confluence
python confluence_export.py "PAGE_URL"

# macOS (venv)
source venv/bin/activate
python confluence_export.py "PAGE_URL"

# Windows (conda)
conda activate confluence
python confluence_export.py "PAGE_URL"

# Windows (venv)
venv\Scripts\activate
python confluence_export.py "PAGE_URL"

# 출력 디렉토리 지정
python confluence_export.py "PAGE_URL" --output-dir ./my_output
```

### Output

Three files are generated in the output directory:

| File | Description |
|------|-------------|
| `Page_Title.pdf` | A4 document PDF (cover + TOC + body + back page) |
| `present_Page_Title.html` | Presentation HTML (browser slideshow) |
| `present_Page_Title.pdf` | Presentation PDF (16:9 slides) |

### Presentation Controls

| Action | Key |
|--------|-----|
| Next slide | `Space`, `→`, `↓`, `PageDown` |
| Previous slide | `←`, `↑`, `PageUp` |
| Go to first slide | `Home` |
| Go to last slide | `End` |
| Mouse wheel | Scroll up/down |
| Open TOC | `T` |

## Dependencies

| Package | Version | Role |
|---------|---------|------|
| `requests` | >= 2.28 | Confluence REST API calls |
| `beautifulsoup4` | >= 4.12 | HTML parsing and macro conversion |
| `playwright` | >= 1.40 | Headless Chromium PDF rendering |
| `flask` | >= 3.0 | Web GUI server |

## File Structure

```
confluece_slide_and_pdf/
├── Conf. Exporter.command    # macOS one-click launcher (→ start.sh 위임)
├── start.sh                  # macOS launcher (conda/venv 자동 감지)
├── setup.sh                  # macOS 초기 설정 (conda/venv 자동 감지)
├── start.bat                 # Windows launcher (conda/venv 자동 감지)
├── setup.bat                 # Windows 초기 설정 (conda/venv 자동 감지)
├── requirements.txt          # Python package list
├── app.py                    # Flask web GUI server
├── confluence_export.py      # Core export engine + CLI entry point
├── templates/
│   └── index.html            # Web GUI template
├── static/
│   └── pinklab_logo_text.png # Logo (symlink)
├── pinklab_logo_text.png     # PinkLAB logo
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

## Changelog

### conda/venv 자동 감지 지원 (macOS + Windows)

`setup.sh` / `start.sh` (macOS 신규), `setup.bat` / `start.bat` (Windows 업데이트):
conda가 설치되어 있으면 conda를, 없으면 venv를 자동으로 감지하여 실행합니다.

### Windows File Open Bug Fix (`app.py` + `templates/index.html`)

파일 서빙 URL을 경로 기반 → `job_id + 파일명` 기반으로 변경하여 Windows 경로(`C:\...`)가 URL에 포함되던 문제를 해결했습니다.

---

## VIDEO
[![YOUTUBE](https://img.youtube.com/vi/VcSHt-2HNkY/0.jpg)](https://www.youtube.com/watch?v=VcSHt-2HNkY)
