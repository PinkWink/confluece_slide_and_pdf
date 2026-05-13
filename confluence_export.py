#!/usr/bin/env python3
"""Confluence Cloud page exporter with styled HTML and PDF output.

Usage:
    python confluence_export.py <page_url>
    python confluence_export.py <page_url> --output-dir ./my_output
"""

import argparse
import base64
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup, NavigableString

# ---------------------------------------------------------------------------
# Token file loading
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
TOKEN_FILE = SCRIPT_DIR / "confluence_token.txt"

CONFLUENCE_URL = ""
CONFLUENCE_EMAIL = ""
CONFLUENCE_API_TOKEN = ""


def load_token_file() -> None:
    """Read confluence_token.txt (key=value) and set module-level credentials."""
    global CONFLUENCE_URL, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN
    if not TOKEN_FILE.exists():
        print(f"Error: Token file not found: {TOKEN_FILE}", file=sys.stderr)
        print("Create confluence_token.txt with the following format:", file=sys.stderr)
        print("  CONFLUENCE_URL=https://your-domain.atlassian.net", file=sys.stderr)
        print("  CONFLUENCE_EMAIL=your@email.com", file=sys.stderr)
        print("  CONFLUENCE_API_TOKEN=your_api_token", file=sys.stderr)
        sys.exit(1)
    for line in TOKEN_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key == "CONFLUENCE_URL":
            CONFLUENCE_URL = value.rstrip("/")
        elif key == "CONFLUENCE_EMAIL":
            CONFLUENCE_EMAIL = value
        elif key == "CONFLUENCE_API_TOKEN":
            CONFLUENCE_API_TOKEN = value


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CUSTOM_CSS = """
@page {
    size: A4;
    margin: 20mm 15mm 20mm 15mm;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    font-size: 14px;
    line-height: 1.6;
    color: #172B4D;
    max-width: 900px;
    margin: 0 auto;
    padding: 20px 40px;
}

h1 { font-size: 28px; margin-top: 32px; margin-bottom: 16px; color: #172B4D; border-bottom: 2px solid #DFE1E6; padding-bottom: 8px; }
h2 { font-size: 22px; margin-top: 28px; margin-bottom: 12px; color: #172B4D; border-bottom: 1px solid #DFE1E6; padding-bottom: 6px; }
h3 { font-size: 18px; margin-top: 24px; margin-bottom: 10px; color: #172B4D; }
h4, h5, h6 { font-size: 15px; margin-top: 20px; margin-bottom: 8px; color: #172B4D; }

p { margin: 8px 0; }

a { color: #0052CC; text-decoration: none; }
a:hover { text-decoration: underline; }

/* Tables */
table {
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
    font-size: 13px;
}
th, td {
    border: 1px solid #DFE1E6;
    padding: 8px 12px;
    text-align: left;
    vertical-align: top;
}
th {
    background-color: #F4F5F7;
    font-weight: 600;
    color: #172B4D;
}
tr:nth-child(even) {
    background-color: #FAFBFC;
}

/* Code blocks with line numbers */
.code-block-wrapper {
    background-color: #F4F5F7;
    border: 1px solid #DFE1E6;
    border-radius: 4px;
    margin: 16px 0;
    overflow: hidden;
    page-break-inside: avoid;
}
.code-block-header {
    background-color: #EBECF0;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 600;
    color: #6B778C;
    border-bottom: 1px solid #DFE1E6;
}
.code-block-body {
    font-size: 12.5px;
    line-height: 1.5;
}
.code-line {
    display: flex;
    align-items: flex-start;
}
.code-line:first-child { padding-top: 10px; }
.code-line:last-child { padding-bottom: 10px; }
.code-line-num {
    flex-shrink: 0;
    width: 40px;
    text-align: right;
    padding-right: 10px;
    user-select: none;
    background-color: #EBECF0;
    color: #999;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 12px;
    line-height: 1.5;
    border-right: 1px solid #DFE1E6;
    box-sizing: border-box;
}
.code-line:first-child .code-line-num { padding-top: 10px; }
.code-line:last-child .code-line-num { padding-bottom: 10px; }
.code-line-text {
    flex-grow: 1;
    padding: 0 14px;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 12px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-all;
}
.code-line:first-child .code-line-text { padding-top: 10px; }
.code-line:last-child .code-line-text { padding-bottom: 10px; }

/* Inline code */
code {
    background-color: #F4F5F7;
    border-radius: 3px;
    padding: 2px 6px;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 0.9em;
    color: #e74c3c;
}

/* Info/Note/Warning panels */
.confluence-panel {
    border-radius: 4px;
    padding: 16px;
    margin: 16px 0;
    page-break-inside: avoid;
}
.confluence-panel-info {
    background-color: #DEEBFF;
    border-left: 4px solid #0052CC;
}
.confluence-panel-note {
    background-color: #EAE6FF;
    border-left: 4px solid #6554C0;
}
.confluence-panel-warning {
    background-color: #FFFAE6;
    border-left: 4px solid #FF8B00;
}
.confluence-panel-error {
    background-color: #FFEBE6;
    border-left: 4px solid #DE350B;
}
.confluence-panel-success {
    background-color: #E3FCEF;
    border-left: 4px solid #00875A;
}

/* Custom panel (with title bar) */
.confluence-custom-panel {
    border: 1px solid #DFE1E6;
    border-radius: 4px;
    margin: 16px 0;
    page-break-inside: avoid;
    overflow: hidden;
}
.confluence-custom-panel-title {
    padding: 10px 16px;
    font-weight: bold;
    font-size: 1em;
}
.confluence-custom-panel-body {
    padding: 16px;
}

/* Images */
img {
    max-width: 100%;
    height: auto;
}

/* Blockquote */
blockquote {
    border-left: 4px solid #DFE1E6;
    margin: 16px 0;
    padding: 8px 16px;
    color: #6B778C;
}

/* Lists */
ul, ol {
    padding-left: 24px;
    margin: 8px 0;
}
li {
    margin: 4px 0;
}

/* Expand/Collapse sections */
.expand-section {
    border: 1px solid #DFE1E6;
    border-radius: 4px;
    margin: 12px 0;
    page-break-inside: avoid;
}
.expand-title {
    background-color: #F4F5F7;
    padding: 8px 12px;
    font-weight: 600;
    cursor: pointer;
}
.expand-content {
    padding: 12px;
}

/* Title */
.page-title {
    font-size: 32px;
    font-weight: 700;
    color: #172B4D;
    margin-bottom: 8px;
    border-bottom: 3px solid #0052CC;
    padding-bottom: 12px;
}
.page-meta {
    font-size: 12px;
    color: #6B778C;
    margin-bottom: 24px;
}

/* Horizontal rule */
hr {
    border: none;
    border-top: 1px solid #DFE1E6;
    margin: 24px 0;
}

/* Status lozenge */
.status-lozenge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
}

/* Cover page */
.cover-page {
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    align-items: center;
    min-height: 100vh;
    text-align: center;
    page-break-after: always;
    padding: 0;
    position: relative;
}
.cover-top-area {
    flex-grow: 3;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    width: 100%;
}
.cover-title {
    font-size: 36px;
    font-weight: 700;
    color: #172B4D;
    line-height: 1.3;
    max-width: 700px;
    margin-bottom: 40px;
}
.cover-divider {
    width: 120px;
    height: 4px;
    background: linear-gradient(135deg, #E8A0BF, #7B8EC8);
    border: none;
    border-radius: 2px;
    margin-bottom: 40px;
}
.cover-meta {
    font-size: 14px;
    color: #6B778C;
    line-height: 1.8;
}
.cover-bottom-area {
    flex-grow: 1;
    display: flex;
    align-items: flex-end;
    justify-content: center;
    padding-bottom: 60px;
    width: 100%;
}
.cover-logo {
    width: 300px;
}

/* YouTube embeds */
.youtube-embed {
    display: block;
    position: relative;
    width: 100%;
    max-width: 720px;
    aspect-ratio: 16 / 9;
    margin: 16px auto;
    border-radius: 8px;
    overflow: hidden;
    background: #000;
    cursor: pointer;
    text-decoration: none;
}
.youtube-embed .youtube-thumb {
    position: absolute;
    top: 0; left: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
}
.youtube-embed .youtube-play-btn {
    position: absolute;
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    width: 68px; height: 48px;
    background: rgba(255, 0, 0, 0.85);
    border-radius: 14px;
    pointer-events: none;
}
.youtube-play-btn::after {
    content: "";
    position: absolute;
    top: 50%; left: 54%;
    transform: translate(-50%, -50%);
    border-style: solid;
    border-width: 10px 0 10px 18px;
    border-color: transparent transparent transparent #fff;
}
.youtube-embed .youtube-url-label {
    position: absolute;
    bottom: 8px; left: 12px;
    color: #fff;
    font-size: 11px;
    background: rgba(0,0,0,0.6);
    padding: 2px 8px;
    border-radius: 4px;
}
.youtube-embed:hover .youtube-play-btn {
    background: rgba(255, 0, 0, 1);
}

/* Back page (YouTube promo) */
.back-page {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    text-align: center;
    page-break-before: always;
    padding: 0;
    background: linear-gradient(160deg, #FFF5F9 0%, #F0F0FF 50%, #F5F5FF 100%);
}
.back-logo {
    width: 240px;
    margin-bottom: 48px;
}
.back-message {
    font-size: 20px;
    font-weight: 600;
    color: #172B4D;
    margin-bottom: 12px;
}
.back-sub {
    font-size: 15px;
    color: #6B778C;
    margin-bottom: 40px;
    line-height: 1.6;
}
.back-yt-btn {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    background: #FF0000;
    color: #fff;
    font-size: 16px;
    font-weight: 700;
    padding: 14px 32px;
    border-radius: 8px;
    text-decoration: none;
    margin-bottom: 16px;
}
.back-yt-btn:hover {
    opacity: 0.9;
}
.back-yt-url {
    font-size: 13px;
    color: #999;
    word-break: break-all;
}
.back-footer {
    margin-top: 60px;
    font-size: 12px;
    color: #B0B0B0;
}

/* TOC page */
.toc-page {
    page-break-after: always;
    min-height: 100vh;
    padding-top: 60px;
}
.toc-heading {
    font-size: 28px;
    font-weight: 700;
    color: #172B4D;
    border-bottom: 3px solid #0052CC;
    padding-bottom: 12px;
    margin-bottom: 32px;
}
.toc-list {
    list-style: none;
    padding: 0;
    margin: 0;
}
.toc-list li {
    margin: 0;
    padding: 0;
}
.toc-list a {
    display: block;
    padding: 8px 0;
    color: #172B4D;
    text-decoration: none;
    border-bottom: 1px solid #F4F5F7;
    transition: background 0.15s;
}
.toc-list a:hover {
    background-color: #F4F5F7;
}
.toc-h1 { padding-left: 0; font-size: 16px; font-weight: 600; }
.toc-h2 { padding-left: 20px; font-size: 15px; font-weight: 500; }
.toc-h3 { padding-left: 40px; font-size: 14px; font-weight: 400; color: #6B778C; }
.toc-h4 { padding-left: 60px; font-size: 13px; font-weight: 400; color: #8993A4; }
.toc-number {
    display: inline-block;
    min-width: 36px;
    color: #0052CC;
    font-weight: 600;
}

/* Print styles */
@media print {
    body { padding: 0; }
    .code-block-wrapper { break-inside: avoid; }
    a { color: #0052CC; }
    a[href^="http"]::after { content: " (" attr(href) ")"; font-size: 0.8em; color: #999; }
    .toc-list a::after { content: none !important; }
    .cover-page { min-height: 0; height: 100vh; }
    .toc-page { min-height: 0; }
    .back-page { min-height: 0; height: 100vh; }
    .back-yt-btn { color: #fff !important; }
    .back-yt-btn::after { content: none !important; }
    .back-yt-url::after { content: none !important; }
}
"""


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def get_auth():
    return (CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)


def get_session() -> requests.Session:
    """Create a requests session with retry logic for transient failures."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def extract_page_id(url: str) -> str:
    """Extract page ID from various Confluence URL formats."""
    parsed = urlparse(url)
    path = parsed.path

    # Format: /wiki/spaces/SPACE/pages/PAGE_ID/title
    m = re.search(r"/pages/(\d+)", path)
    if m:
        return m.group(1)

    # Format: /wiki/x/ENCODED or other short links — try query param
    # Some URLs use pageId query parameter
    from urllib.parse import parse_qs
    qs = parse_qs(parsed.query)
    if "pageId" in qs:
        return qs["pageId"][0]

    raise ValueError(
        f"Could not extract page ID from URL: {url}\n"
        "Expected format: .../pages/PAGE_ID/... or ?pageId=PAGE_ID"
    )


def fetch_page(page_id: str) -> dict:
    """Fetch page content using Confluence REST API v2."""
    api_url = f"{CONFLUENCE_URL}/wiki/api/v2/pages/{page_id}"
    params = {"body-format": "storage"}
    session = get_session()
    resp = session.get(api_url, auth=get_auth(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_page_v1(page_id: str) -> dict:
    """Fallback: fetch page using v1 API with expand."""
    api_url = f"{CONFLUENCE_URL}/wiki/rest/api/content/{page_id}"
    params = {"expand": "body.storage,version,space"}
    session = get_session()
    resp = session.get(api_url, auth=get_auth(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_child_page_ids(page_id: str) -> list:
    """Return immediate child page metadata: [{"id": ..., "title": ...}, ...]."""
    api_url = f"{CONFLUENCE_URL}/wiki/rest/api/content/{page_id}/child/page"
    session = get_session()
    children = []
    start = 0
    limit = 100
    while True:
        params = {"limit": limit, "start": start}
        resp = session.get(api_url, auth=get_auth(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("results", []):
            children.append({"id": str(item.get("id")), "title": item.get("title", "Untitled")})
        size = data.get("size", len(data.get("results", [])))
        if size < limit:
            break
        start += limit
    return children


def fetch_child_tree(page_id: str, max_depth: int = 0, _current_depth: int = 1) -> list:
    """Return nested tree of descendants.

    max_depth=0 means unlimited (all descendants). max_depth=1 means immediate
    children only. Each node: {"id", "title", "depth", "children": [...]}.
    """
    nodes = []
    for c in fetch_child_page_ids(page_id):
        node = {"id": c["id"], "title": c["title"], "depth": _current_depth, "children": []}
        if max_depth == 0 or _current_depth < max_depth:
            node["children"] = fetch_child_tree(c["id"], max_depth, _current_depth + 1)
        nodes.append(node)
    return nodes


def flatten_tree(tree: list) -> list:
    """Flatten nested tree to ordered list of {"id","title","depth"}."""
    out = []
    for node in tree:
        out.append({"id": node["id"], "title": node["title"], "depth": node["depth"]})
        if node.get("children"):
            out.extend(flatten_tree(node["children"]))
    return out


def download_image(url: str) -> str | None:
    """Download an image and return it as a base64 data URI."""
    try:
        if url.startswith("/"):
            # Confluence Cloud download paths need /wiki prefix
            url = CONFLUENCE_URL + "/wiki" + url
        session = get_session()
        resp = session.get(url, auth=get_auth(), timeout=30)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "image/png")
        b64 = base64.b64encode(resp.content).decode("utf-8")
        return f"data:{content_type};base64,{b64}"
    except Exception as e:
        print(f"  Warning: Failed to download image {url}: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# HTML processing
# ---------------------------------------------------------------------------

def process_code_blocks(soup: BeautifulSoup) -> None:
    """Convert Confluence code macros to styled code blocks with line numbers."""
    # Handle <ac:structured-macro ac:name="code"> elements
    for macro in soup.find_all("ac:structured-macro", attrs={"ac:name": "code"}):
        language = ""
        title = ""
        code_text = ""

        # Extract language parameter
        for param in macro.find_all("ac:parameter"):
            name = param.get("ac:name", "")
            if name == "language":
                language = param.get_text(strip=True)
            elif name == "title":
                title = param.get_text(strip=True)

        # Extract code body
        body = macro.find("ac:plain-text-body")
        if body:
            code_text = body.get_text()
            # Remove leading/trailing newlines but preserve internal structure
            code_text = code_text.strip("\n")

        # Build styled code block
        wrapper = soup.new_tag("div", attrs={"class": "code-block-wrapper"})

        # Header with language
        header_text = title or language or "Code"
        header = soup.new_tag("div", attrs={"class": "code-block-header"})
        header.string = header_text
        wrapper.append(header)

        # Body container — one row per line for proper wrap with line numbers
        body_div = soup.new_tag("div", attrs={"class": "code-block-body"})

        lines = code_text.split("\n")
        for i, line in enumerate(lines, 1):
            row = soup.new_tag("div", attrs={"class": "code-line"})
            num_span = soup.new_tag("span", attrs={"class": "code-line-num"})
            num_span.string = str(i)
            row.append(num_span)
            code_span = soup.new_tag("span", attrs={"class": "code-line-text"})
            code_span.string = line or "\n"
            row.append(code_span)
            body_div.append(row)

        wrapper.append(body_div)
        macro.replace_with(wrapper)


def process_panels(soup: BeautifulSoup) -> None:
    """Convert Confluence info/note/warning panels."""
    panel_types = {
        "info": "info",
        "note": "note",
        "warning": "warning",
        "tip": "success",
        "error": "error",
    }
    for panel_name, css_class in panel_types.items():
        for macro in soup.find_all("ac:structured-macro", attrs={"ac:name": panel_name}):
            panel_div = soup.new_tag("div", attrs={
                "class": f"confluence-panel confluence-panel-{css_class}"
            })
            body = macro.find("ac:rich-text-body")
            if body:
                for child in list(body.children):
                    panel_div.append(child.extract())
            macro.replace_with(panel_div)


def process_custom_panel(soup: BeautifulSoup) -> None:
    """Convert Confluence panel macro (with optional title bar and colors)."""
    for macro in soup.find_all("ac:structured-macro", attrs={"ac:name": "panel"}):
        params = {}
        for param in macro.find_all("ac:parameter"):
            params[param.get("ac:name", "")] = param.get_text(strip=True)

        title = params.get("title", "")
        title_bg = params.get("titleBGColor", "#4C9AFF")
        title_color = params.get("titleColor", "#FFFFFF")
        bg_color = params.get("bgColor", "#FFFFFF")
        border_color = params.get("borderColor", title_bg)

        panel_div = soup.new_tag("div", attrs={
            "class": "confluence-custom-panel",
            "style": f"border-color: {border_color}; background-color: {bg_color};"
        })

        if title:
            title_div = soup.new_tag("div", attrs={
                "class": "confluence-custom-panel-title",
                "style": f"background-color: {title_bg}; color: {title_color};"
            })
            title_div.string = title
            panel_div.append(title_div)

        body_div = soup.new_tag("div", attrs={
            "class": "confluence-custom-panel-body"
        })
        body = macro.find("ac:rich-text-body")
        if body:
            for child in list(body.children):
                body_div.append(child.extract())
        panel_div.append(body_div)

        macro.replace_with(panel_div)


def process_expand(soup: BeautifulSoup) -> None:
    """Convert Confluence expand macros."""
    for macro in soup.find_all("ac:structured-macro", attrs={"ac:name": "expand"}):
        section = soup.new_tag("div", attrs={"class": "expand-section"})

        title_text = "Details"
        for param in macro.find_all("ac:parameter"):
            if param.get("ac:name") == "title":
                title_text = param.get_text(strip=True)

        title_div = soup.new_tag("div", attrs={"class": "expand-title"})
        title_div.string = f"▼ {title_text}"
        section.append(title_div)

        content_div = soup.new_tag("div", attrs={"class": "expand-content"})
        body = macro.find("ac:rich-text-body")
        if body:
            for child in list(body.children):
                content_div.append(child.extract())
        section.append(content_div)

        macro.replace_with(section)


def process_status(soup: BeautifulSoup) -> None:
    """Convert Confluence status macros."""
    color_map = {
        "Green": "#00875A",
        "Yellow": "#FF8B00",
        "Red": "#DE350B",
        "Blue": "#0052CC",
        "Grey": "#6B778C",
    }
    for macro in soup.find_all("ac:structured-macro", attrs={"ac:name": "status"}):
        title = ""
        colour = "Grey"
        for param in macro.find_all("ac:parameter"):
            name = param.get("ac:name", "")
            if name == "title":
                title = param.get_text(strip=True)
            elif name == "colour":
                colour = param.get_text(strip=True)

        bg = color_map.get(colour, "#6B778C")
        span = soup.new_tag("span", attrs={
            "class": "status-lozenge",
            "style": f"background-color: {bg}20; color: {bg}; border: 1px solid {bg};"
        })
        span.string = title
        macro.replace_with(span)


VIDEO_EXTENSIONS = {'.mov', '.mp4', '.webm', '.avi', '.mkv', '.m4v', '.ogv'}

def _is_video_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in VIDEO_EXTENSIONS

def process_images(soup: BeautifulSoup) -> None:
    """Convert Confluence image tags and embed images/videos as base64."""
    # Handle <ac:image> tags
    for img_tag in soup.find_all("ac:image"):
        attachment = img_tag.find("ri:attachment")
        url_tag = img_tag.find("ri:url")

        if attachment:
            filename = attachment.get("ri:filename", "")
            # Fallback: if filename is UNKNOWN_ATTACHMENT, use ac:alt attribute
            if filename == "UNKNOWN_ATTACHMENT":
                alt_name = img_tag.get("ac:alt", "")
                if alt_name:
                    filename = alt_name
            # Capture optional <ri:page> reference (image hosted on another page)
            page_ref = attachment.find("ri:page")
            ref_title = page_ref.get("ri:content-title", "") if page_ref else ""
            ref_space = page_ref.get("ri:space-key", "") if page_ref else ""
            if _is_video_file(filename):
                video = soup.new_tag("video", attrs={
                    "controls": "",
                    "data-attachment-video": filename,
                    "style": "max-width:100%; max-height:100%;",
                })
                if ref_title:
                    video["data-attachment-page-title"] = ref_title
                if ref_space:
                    video["data-attachment-space-key"] = ref_space
                video.string = filename
                img_tag.replace_with(video)
                continue
            img = soup.new_tag("img")
            img["data-attachment"] = filename
            if ref_title:
                img["data-attachment-page-title"] = ref_title
            if ref_space:
                img["data-attachment-space-key"] = ref_space
            img["alt"] = filename
        elif url_tag:
            img = soup.new_tag("img")
            img["src"] = url_tag.get("ri:value", "")
            img["alt"] = "image"
        else:
            img = soup.new_tag("img")

        # Copy width/height if present
        for attr in ["ac:width", "ac:height"]:
            val = img_tag.get(attr)
            if val:
                img[attr.split(":")[1]] = val

        img_tag.replace_with(img)


_page_id_cache: dict = {}


def _lookup_page_id_by_title(title: str, space_key: str = "") -> str | None:
    """Resolve a page id from its title (and optional space key) via v1 search."""
    if not title:
        return None
    cache_key = f"{space_key}::{title}"
    if cache_key in _page_id_cache:
        return _page_id_cache[cache_key]
    try:
        session = get_session()
        params = {"title": title, "type": "page", "limit": 1}
        if space_key:
            params["spaceKey"] = space_key
        api_url = f"{CONFLUENCE_URL}/wiki/rest/api/content"
        resp = session.get(api_url, auth=get_auth(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        pid = str(results[0]["id"]) if results else None
    except Exception:
        pid = None
    _page_id_cache[cache_key] = pid
    return pid


def _fetch_attachment_download_path(page_id: str, filename: str) -> str | None:
    """Return an authenticated download URL for a named attachment, or None.

    Uses /rest/api/content/{pageId}/child/attachment/{attachmentId}/download,
    which authenticates with Basic auth and 302-redirects to the Atlassian
    media CDN with a signed URL. The legacy /download/attachments/... path
    on Confluence Cloud returns 401 with Basic auth.
    """
    if not page_id:
        return None
    att_url = (
        f"{CONFLUENCE_URL}/wiki/rest/api/content/{page_id}"
        f"/child/attachment?filename={quote(filename)}"
    )
    try:
        session = get_session()
        resp = session.get(att_url, auth=get_auth(), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None
        att_id = results[0].get("id")
        if not att_id:
            return None
        # download_image() prepends CONFLUENCE_URL + "/wiki" for paths starting
        # with "/", so we return the path without the /wiki prefix.
        return f"/rest/api/content/{page_id}/child/attachment/{att_id}/download"
    except Exception:
        return None


def resolve_attachment_images(soup: BeautifulSoup, page_id: str, fallback_page_ids: list | None = None) -> None:
    """Download attachment images and embed as base64.

    Honors optional <ri:page> reference captured during process_images. Also
    tries any fallback_page_ids (e.g. the parent page) when the primary lookup
    yields no result — useful when a child page references an attachment that
    actually lives on the parent.
    """
    fallback_page_ids = fallback_page_ids or []
    for img in soup.find_all("img", attrs={"data-attachment": True}):
        filename = img["data-attachment"]
        ref_title = img.get("data-attachment-page-title", "")
        ref_space = img.get("data-attachment-space-key", "")

        # Build ordered list of page ids to try
        candidate_ids = []
        if ref_title:
            other_id = _lookup_page_id_by_title(ref_title, ref_space)
            if other_id:
                candidate_ids.append(other_id)
        if page_id not in candidate_ids:
            candidate_ids.append(page_id)
        for fid in fallback_page_ids:
            if fid and fid not in candidate_ids:
                candidate_ids.append(fid)

        download_path = None
        for pid in candidate_ids:
            download_path = _fetch_attachment_download_path(pid, filename)
            if download_path:
                break

        if download_path:
            data_uri = download_image(download_path)
            if data_uri:
                img["src"] = data_uri
        else:
            print(f"  Warning: Failed to resolve attachment '{filename}' "
                  f"(tried pages: {candidate_ids})", file=sys.stderr)

        for attr in ("data-attachment", "data-attachment-page-title", "data-attachment-space-key"):
            if img.has_attr(attr):
                del img[attr]


def resolve_attachment_videos(soup: BeautifulSoup, page_id: str, output_dir: str = "output", fallback_page_ids: list | None = None) -> None:
    """Download attachment videos and save as files next to HTML."""
    session = get_session()
    fallback_page_ids = fallback_page_ids or []
    for video in soup.find_all("video", attrs={"data-attachment-video": True}):
        filename = video["data-attachment-video"]
        ref_title = video.get("data-attachment-page-title", "")
        ref_space = video.get("data-attachment-space-key", "")

        candidate_ids = []
        if ref_title:
            other_id = _lookup_page_id_by_title(ref_title, ref_space)
            if other_id:
                candidate_ids.append(other_id)
        if page_id not in candidate_ids:
            candidate_ids.append(page_id)
        for fid in fallback_page_ids:
            if fid and fid not in candidate_ids:
                candidate_ids.append(fid)

        download_path = None
        for pid in candidate_ids:
            download_path = _fetch_attachment_download_path(pid, filename)
            if download_path:
                break

        if download_path:
            try:
                dl_url = download_path
                if dl_url.startswith("/"):
                    dl_url = CONFLUENCE_URL + "/wiki" + dl_url
                dl_resp = session.get(dl_url, auth=get_auth(), timeout=300)
                dl_resp.raise_for_status()
                safe_name = re.sub(r'[^\w\s\-.]', '_', filename)
                video_path = Path(output_dir) / safe_name
                video_path.parent.mkdir(parents=True, exist_ok=True)
                video_path.write_bytes(dl_resp.content)
                video["src"] = safe_name
                video.string = ""
                print(f"  Saved video: {safe_name} ({len(dl_resp.content) / 1024 / 1024:.1f} MB)")
            except Exception as e:
                print(f"  Warning: Failed to download video '{filename}': {e}", file=sys.stderr)
        else:
            print(f"  Warning: Failed to resolve video '{filename}' "
                  f"(tried pages: {candidate_ids})", file=sys.stderr)

        for attr in ("data-attachment-video", "data-attachment-page-title", "data-attachment-space-key"):
            if video.has_attr(attr):
                del video[attr]


def process_toc(soup: BeautifulSoup) -> None:
    """Remove TOC macros (we don't generate a TOC)."""
    for macro in soup.find_all("ac:structured-macro", attrs={"ac:name": "toc"}):
        macro.decompose()


def process_emoticons(soup: BeautifulSoup) -> None:
    """Convert Confluence emoticons."""
    emoticon_map = {
        "smile": "😊", "sad": "😢", "cheeky": "😜", "laugh": "😄",
        "wink": "😉", "thumbs-up": "👍", "thumbs-down": "👎",
        "information": "ℹ️", "tick": "✅", "cross": "❌",
        "warning": "⚠️", "plus": "➕", "minus": "➖",
        "question": "❓", "light-on": "💡", "light-off": "💡",
        "yellow-star": "⭐", "red-star": "⭐", "green-star": "⭐",
        "blue-star": "⭐", "heart": "❤️", "broken-heart": "💔",
    }
    for emoticon in soup.find_all("ac:emoticon"):
        name = emoticon.get("ac:name", "")
        emoji = emoticon_map.get(name, f"[{name}]")
        emoticon.replace_with(emoji)


def process_links(soup: BeautifulSoup) -> None:
    """Convert Confluence link macros to standard HTML links."""
    for link in soup.find_all("ac:link"):
        page_ref = link.find("ri:page")
        attachment_ref = link.find("ri:attachment")
        link_body = link.find("ac:link-body") or link.find("ac:plain-text-link-body")

        a_tag = soup.new_tag("a")

        if page_ref:
            title = page_ref.get("ri:content-title", "")
            space = page_ref.get("ri:space-key", "")
            a_tag["href"] = f"{CONFLUENCE_URL}/wiki/spaces/{space}/pages?title={title}"
            a_tag.string = link_body.get_text() if link_body else title
        elif attachment_ref:
            filename = attachment_ref.get("ri:filename", "")
            a_tag["href"] = "#"
            a_tag.string = link_body.get_text() if link_body else filename
        else:
            anchor = link.get("ac:anchor", "")
            a_tag["href"] = f"#{anchor}" if anchor else "#"
            a_tag.string = link_body.get_text() if link_body else anchor

        link.replace_with(a_tag)


def _extract_youtube_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    if not url:
        return None
    patterns = [
        r'(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def _build_youtube_embed(soup: BeautifulSoup, vid: str):
    """Build a YouTube thumbnail with play button, linked to YouTube in new tab."""
    link = soup.new_tag("a", attrs={
        "class": "youtube-embed",
        "href": f"https://youtu.be/{vid}",
        "target": "_blank",
        "rel": "noopener noreferrer",
    })
    thumb = soup.new_tag("img", attrs={
        "class": "youtube-thumb",
        "src": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
        "alt": "YouTube video",
    })
    link.append(thumb)
    play_btn = soup.new_tag("div", attrs={"class": "youtube-play-btn"})
    link.append(play_btn)
    url_label = soup.new_tag("div", attrs={"class": "youtube-url-label"})
    url_label.string = f"https://youtu.be/{vid}"
    link.append(url_label)
    return link


def process_youtube_links(soup: BeautifulSoup) -> None:
    """Convert YouTube links and widget macros into thumbnail embeds."""
    # 1. Handle Confluence widget macros (ac:structured-macro name="widget")
    for macro in soup.find_all("ac:structured-macro", attrs={"ac:name": "widget"}):
        url_param = macro.find("ac:parameter", attrs={"ac:name": "url"})
        if url_param:
            url = url_param.get_text(strip=True)
            vid = _extract_youtube_id(url)
            if vid:
                macro.replace_with(_build_youtube_embed(soup, vid))
                continue
        # If not a YouTube widget, leave for process_remaining_macros

    # 2. Handle plain <a> tags with YouTube URLs
    for a_tag in list(soup.find_all("a", href=True)):
        href = a_tag["href"]
        vid = _extract_youtube_id(href)
        if vid:
            a_tag.replace_with(_build_youtube_embed(soup, vid))


def process_remaining_macros(soup: BeautifulSoup) -> None:
    """Handle remaining unprocessed macros gracefully."""
    for macro in soup.find_all("ac:structured-macro"):
        name = macro.get("ac:name", "unknown")
        body = macro.find("ac:rich-text-body")
        if body:
            # Keep the body content
            div = soup.new_tag("div", attrs={
                "style": "border: 1px dashed #DFE1E6; padding: 8px; margin: 8px 0;",
                "title": f"Macro: {name}"
            })
            for child in list(body.children):
                div.append(child.extract())
            macro.replace_with(div)
        else:
            # Remove macros without body
            macro.decompose()


def load_logo_base64() -> str:
    """Load PinkLAB logo and return as base64 data URI."""
    logo_path = Path(__file__).parent / "pinklab_logo_text.png"
    if not logo_path.exists():
        print("  Warning: Logo file not found, skipping cover logo", file=sys.stderr)
        return ""
    with open(logo_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def build_cover_page(title: str, logo_b64: str) -> str:
    """Build a cover page with title at center-upper area and logo at bottom quarter."""
    logo_html = ""
    if logo_b64:
        logo_html = f'<img class="cover-logo" src="{logo_b64}" alt="PinkLAB">'

    return f"""
    <div class="cover-page">
        <div class="cover-top-area">
            <div class="cover-title">{title}</div>
            <div class="cover-divider"></div>
        </div>
        <div class="cover-bottom-area">
            {logo_html}
        </div>
    </div>
"""


def build_back_page(logo_b64: str) -> str:
    """Build a back page promoting PinkLAB YouTube channel."""
    logo_html = ""
    if logo_b64:
        logo_html = f'<img class="back-logo" src="{logo_b64}" alt="PinkLAB">'

    yt_icon_svg = (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="white">'
        '<path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 '
        '3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 '
        '0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 '
        '9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 '
        '2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 '
        '15.568V8.432L15.818 12l-6.273 3.568z"/></svg>'
    )

    return f"""
    <div class="back-page">
        {logo_html}
        <div class="back-message">PinkLAB YouTube Channel</div>
        <div class="back-sub">
            PinkLAB Studio &mdash; Robotics, AI, ROS2 and more!
        </div>
        <a class="back-yt-btn" href="https://www.youtube.com/@pinklab_studio">
            {yt_icon_svg}
            Subscribe on YouTube
        </a>
        <div class="back-yt-url">https://www.youtube.com/@pinklab_studio</div>
        <div class="back-footer">
            &copy; PinkLAB &middot; Exported with Confluence PDF Exporter
        </div>
    </div>
"""


def build_toc_page(soup: BeautifulSoup) -> str:
    """Build a table of contents from headings in the content."""
    headings = soup.find_all(re.compile(r"^h[1-4]$"))
    if not headings:
        return ""

    # Assign IDs to headings and build TOC entries
    toc_items = []
    counters = [0, 0, 0, 0]  # h1, h2, h3, h4

    for heading in headings:
        level = int(heading.name[1])  # 1-4
        idx = level - 1

        # Update counters
        counters[idx] += 1
        for i in range(idx + 1, 4):
            counters[i] = 0

        # Build section number
        parts = []
        for i in range(idx + 1):
            if counters[i] > 0:
                parts.append(str(counters[i]))
        number = ".".join(parts)

        # Set anchor ID on the heading
        text = heading.get_text(strip=True)
        anchor_id = f"section-{number.replace('.', '-')}"
        heading["id"] = anchor_id

        toc_items.append(
            f'<li><a class="toc-h{level}" href="#{anchor_id}">'
            f'<span class="toc-number">{number}</span> {text}</a></li>'
        )

    toc_html = "\n".join(toc_items)
    return f"""
    <div class="toc-page">
        <div class="toc-heading">Contents</div>
        <ul class="toc-list">
            {toc_html}
        </ul>
    </div>
"""


def process_page_content(page_data: dict, page_id: str, output_dir: str = "output", fallback_page_ids: list | None = None) -> tuple:
    """Process Confluence page data and return (title, processed_soup).

    fallback_page_ids: additional page ids to try when resolving attachments,
    used when a child page references an image that actually lives on the
    parent.
    """
    title = page_data.get("title", "Untitled")

    body_html = ""
    if "body" in page_data:
        body_obj = page_data["body"]
        if isinstance(body_obj, dict):
            if "storage" in body_obj:
                storage = body_obj["storage"]
                if isinstance(storage, dict):
                    body_html = storage.get("value", "")
                else:
                    body_html = str(storage)

    if not body_html:
        print("Warning: No body content found in page data", file=sys.stderr)

    soup = BeautifulSoup(body_html, "html.parser")

    print("  Processing code blocks...")
    process_code_blocks(soup)
    print("  Processing panels...")
    process_panels(soup)
    print("  Processing custom panels...")
    process_custom_panel(soup)
    print("  Processing expand sections...")
    process_expand(soup)
    print("  Processing status macros...")
    process_status(soup)
    print("  Processing images...")
    process_images(soup)
    print("  Processing emoticons...")
    process_emoticons(soup)
    print("  Processing links...")
    process_links(soup)
    print("  Processing TOC...")
    process_toc(soup)
    print("  Processing YouTube links...")
    process_youtube_links(soup)
    print("  Processing remaining macros...")
    process_remaining_macros(soup)
    print("  Resolving attachment images...")
    resolve_attachment_images(soup, page_id, fallback_page_ids=fallback_page_ids)
    print("  Resolving attachment videos...")
    resolve_attachment_videos(soup, page_id, output_dir, fallback_page_ids=fallback_page_ids)

    return title, soup


def merge_pages(pages: list) -> BeautifulSoup:
    """Combine multiple (title, soup) pairs into one soup.

    The first page is treated as the parent and emitted as-is. Each subsequent
    page is prefixed with an <h1> containing the page title, so it becomes a
    top-level section in the merged document and a section slide in the
    presentation pipeline.
    """
    parts = []
    for i, (title, soup) in enumerate(pages):
        if i > 0:
            safe = re.sub(r"<[^>]+>", "", str(title)).strip() or "Untitled"
            parts.append(f'<h1 class="page-section-title">{safe}</h1>')
        parts.append(str(soup))
    return BeautifulSoup("\n".join(parts), "html.parser")


def build_html(title: str, soup: BeautifulSoup) -> str:
    """Build a complete styled HTML document from processed soup."""
    # Build cover page
    print("  Building cover page...")
    logo_b64 = load_logo_base64()
    cover_html = build_cover_page(title, logo_b64)

    # Build TOC page (must be after processing, so headings are clean)
    print("  Building table of contents...")
    toc_html = build_toc_page(soup)

    # Build back page (YouTube promo)
    print("  Building back page...")
    back_html = build_back_page(logo_b64)

    # Build full HTML document
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
{CUSTOM_CSS}
    </style>
</head>
<body>
    {cover_html}
    {toc_html}
    <div class="page-title">{title}</div>
    <div class="page-meta">
        Exported from Confluence &middot; {CONFLUENCE_URL}
    </div>
    <hr>
    {soup}
    {back_html}
<script>
document.querySelectorAll('a:not([target])').forEach(function(a) {{
    if (a.getAttribute('href') && !a.getAttribute('href').startsWith('#')) {{
        a.setAttribute('target', '_blank');
        a.setAttribute('rel', 'noopener noreferrer');
    }}
}});
</script>
</body>
</html>"""

    return html


# ---------------------------------------------------------------------------
# Presentation mode
# ---------------------------------------------------------------------------

PRESENT_CSS = """
@page {
    size: 1280px 720px;
    margin: 0;
}
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    margin: 0; padding: 0; color: #1a202c; background: #fff;
}

/* ===== Slide base ===== */
.slide {
    width: 100%;
    height: 100vh;
    min-height: 100vh;
    max-height: 100vh;
    page-break-after: always;
    break-after: page;
    display: flex;
    flex-direction: column;
    position: relative;
    overflow: hidden;
    box-sizing: border-box;
}
.slide:last-child { page-break-after: avoid; break-after: avoid; }

/* ===== Print page break support ===== */
@media print {
    .slide {
        height: 100vh;
        page-break-after: always;
        break-after: page;
        page-break-inside: avoid;
        break-inside: avoid;
    }
    .slide:last-child {
        page-break-after: avoid;
        break-after: avoid;
    }
}

/* ===== Slide header bar ===== */
.slide-topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 40px;
    border-bottom: 1px solid #E2E8F0;
    flex-shrink: 0;
    overflow: hidden;
    max-height: 52px;
}
.topbar-section-name {
    font-size: 13px;
    font-weight: 600;
    color: #0052CC;
}
.topbar-title {
    font-size: 14px;
    font-weight: 500;
    color: #2d3748;
}
.topbar-logo {
    height: 28px;
    max-width: 140px;
    object-fit: contain;
}

/* ===== Slide footer ===== */
.slide-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 40px;
    flex-shrink: 0;
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    border-top: 3px solid;
    border-image: linear-gradient(90deg, #0052CC 40%, transparent 40%) 1;
}
.footer-author {
    font-size: 11px;
    color: #718096;
}
.footer-page-num {
    font-size: 11px;
    color: #A0AEC0;
    font-weight: 600;
}

/* ===== Cover slide ===== */
.slide-cover {
    justify-content: flex-start;
    align-items: center;
    text-align: center;
}
.slide-cover .cover-top-area {
    flex-grow: 3;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
}
.slide-cover .cover-title {
    font-size: 42px;
    font-weight: 800;
    color: #1a202c;
    line-height: 1.3;
    max-width: 850px;
    margin-bottom: 28px;
}
.slide-cover .cover-divider {
    width: 100px; height: 4px;
    background: linear-gradient(135deg, #E8A0BF, #7B8EC8);
    border: none; border-radius: 2px;
    margin-bottom: 28px;
}
.slide-cover .cover-meta {
    font-size: 16px; color: #718096; line-height: 1.8;
}
.slide-cover .cover-bottom-area {
    flex-grow: 1;
    display: flex;
    align-items: flex-end;
    justify-content: center;
    padding-bottom: 48px;
}
.slide-cover .cover-logo { width: 260px; }

/* ===== H1/H2 title-only slide ===== */
.slide-heading {
    padding: 0;
}
.slide-heading .heading-body {
    flex: 1;
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 40px 80px;
}
.slide-heading .heading-text {
    font-size: 38px;
    font-weight: 700;
    color: #1a202c;
    text-align: center;
    line-height: 1.4;
}

/* ===== H3 content slide ===== */
.slide-content {
    padding: 0;
}
.slide-content .content-body {
    flex: 1;
    padding: 24px 56px;
    padding-bottom: 48px;
    overflow: hidden;
    max-width: 100%;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    justify-content: center;
}
.slide-content .content-title {
    font-size: 28px;
    font-weight: 700;
    color: #1a202c;
    text-align: center;
    margin-bottom: 24px;
    flex-shrink: 0;
}
.slide-content .content-inner {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    min-height: 0;
    gap: 12px;
    flex: 1;
    width: 100%;
}
.slide-content p { font-size: 16px; line-height: 1.7; margin: 4px 0; }
.slide-content ul, .slide-content ol { padding-left: 28px; margin: 8px 0; }
.slide-content li { font-size: 16px; line-height: 1.7; margin: 4px 0; }
.slide-content .content-inner > img {
    max-width: calc(100% - 20px);
    max-height: 100%;
    width: auto;
    height: 100%;
    margin: 8px auto;
    display: block;
    object-fit: contain;
    flex: 1;
    min-height: 200px;
}
.slide-content .content-inner > p:has(img) {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 0;
    margin: 8px 0;
    width: 100%;
}
.slide-content .content-inner > p:has(img) img {
    max-width: calc(100% - 20px);
    max-height: 100%;
    width: auto;
    height: 100%;
    object-fit: contain;
    display: block;
    margin: 0 auto;
    min-height: 200px;
}
.slide-content .content-inner img {
    max-width: calc(100% - 20px);
    object-fit: contain;
    display: block;
    margin: 8px auto;
}
.slide-content .content-inner > video {
    max-width: calc(100% - 20px);
    max-height: 100%;
    width: auto;
    height: auto;
    margin: 8px auto;
    display: block;
    flex: 1;
    min-height: 0;
    border-radius: 8px;
    background: #000;
}
/* YouTube embeds */
.youtube-embed {
    position: relative;
    width: 100%;
    max-width: 720px;
    aspect-ratio: 16 / 9;
    margin: 12px auto;
    border-radius: 8px;
    overflow: hidden;
    background: #000;
    cursor: pointer;
}
.youtube-embed .youtube-thumb {
    position: absolute;
    top: 0; left: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
}
.youtube-embed .youtube-play-btn {
    position: absolute;
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    width: 68px; height: 48px;
    background: rgba(255, 0, 0, 0.85);
    border-radius: 14px;
    pointer-events: none;
}
.youtube-embed .youtube-play-btn::after {
    content: "";
    position: absolute;
    top: 50%; left: 54%;
    transform: translate(-50%, -50%);
    border-style: solid;
    border-width: 10px 0 10px 18px;
    border-color: transparent transparent transparent #fff;
}
.youtube-embed .youtube-url-label {
    position: absolute;
    bottom: 8px; left: 12px;
    color: #fff;
    font-size: 11px;
    background: rgba(0,0,0,0.6);
    padding: 2px 8px;
    border-radius: 4px;
}
.youtube-embed:hover .youtube-play-btn {
    background: rgba(255, 0, 0, 1);
}
.slide-content .content-inner > .youtube-embed {
    flex: 1;
    min-height: 0;
    max-height: 100%;
}
.slide-heading .heading-body .youtube-embed {
    max-width: 640px;
}

.slide-content a { color: #0052CC; text-decoration: none; }

/* Code blocks — light theme */
.slide-content .code-block-wrapper {
    background: #F8F9FA;
    border-radius: 6px;
    margin: 8px 0;
    overflow: hidden;
    width: 100%;
    border: 1px solid #E2E8F0;
}
.slide-content .code-block-header {
    background: #EDF2F7;
    padding: 5px 14px;
    font-size: 16.5px;
    font-weight: 600;
    color: #4A5568;
    border-bottom: 1px solid #E2E8F0;
}
.slide-content .code-block-body {
    max-height: 340px;
    overflow-y: auto;
}
.slide-content .code-line {
    display: flex;
    align-items: flex-start;
}
.slide-content .code-line:first-child { padding-top: 8px; }
.slide-content .code-line:last-child { padding-bottom: 8px; }
.slide-content .code-line-num {
    flex-shrink: 0;
    width: 36px;
    text-align: right;
    padding-right: 8px;
    user-select: none;
    background: #EDF2F7;
    color: #A0AEC0;
    border-right: 1px solid #E2E8F0;
    font-family: "SFMono-Regular", Consolas, monospace;
    font-size: 18px; line-height: 1.5;
    box-sizing: border-box;
}
.slide-content .code-line:first-child .code-line-num { padding-top: 8px; }
.slide-content .code-line:last-child .code-line-num { padding-bottom: 8px; }
.slide-content .code-line-text {
    flex-grow: 1;
    padding: 0 14px;
    font-family: "SFMono-Regular", Consolas, monospace;
    font-size: 18px; line-height: 1.2;
    white-space: pre-wrap;
    word-break: break-all;
    color: #2D3748;
}
.slide-content .code-line:first-child .code-line-text { padding-top: 8px; }
.slide-content .code-line:last-child .code-line-text { padding-bottom: 8px; }
.slide-content code {
    background: #F0ECF9; padding: 2px 5px; border-radius: 3px;
    font-size: 0.88em; color: #6D28D9;
}

/* Panels */
.slide-content .confluence-panel {
    border-radius: 6px; padding: 20px 28px; margin: 10px 0; font-size: 18px;
    width: 100%; box-sizing: border-box;
}
.slide-content .confluence-panel-info { background: #EBF5FF; border-left: 5px solid #3182CE; }
.slide-content .confluence-panel-note { background: #F3EEFF; border-left: 5px solid #805AD5; }
.slide-content .confluence-panel-warning { background: #FFFBEB; border-left: 5px solid #D69E2E; }
.slide-content .confluence-panel-error { background: #FFF5F5; border-left: 5px solid #E53E3E; }
.slide-content .confluence-panel-success { background: #F0FFF4; border-left: 5px solid #38A169; }
.slide-content .confluence-panel p,
.slide-content .confluence-custom-panel-body p { font-size: 18px; line-height: 1.8; }
.slide-content .confluence-panel li,
.slide-content .confluence-custom-panel-body li { font-size: 18px; line-height: 1.8; }

/* Custom panels (with title bar) */
.slide-content .confluence-custom-panel {
    border-radius: 6px; margin: 10px 0; font-size: 18px; overflow: hidden;
    width: 100%; box-sizing: border-box;
    display: flex; flex-direction: column;
}
.slide-content .confluence-custom-panel-title {
    padding: 10px 18px; font-size: 16px; flex-shrink: 0;
}
.slide-content .confluence-custom-panel-body {
    padding: 20px 28px;
}

/* Tables */
.slide-content table {
    width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 14px;
}
.slide-content th, .slide-content td {
    border: 1px solid #E2E8F0; padding: 8px 12px; text-align: left;
}
.slide-content th { background: #F7FAFC; font-weight: 600; }

/* Expand */
.slide-content .expand-section {
    border: 1px solid #E2E8F0; border-radius: 6px; margin: 8px 0;
}
.slide-content .expand-title { background: #F7FAFC; padding: 6px 10px; font-weight: 600; font-size: 14px; }
.slide-content .expand-content { padding: 10px; }

/* Status lozenge */
.slide-content .status-lozenge {
    display: inline-block; padding: 2px 8px; border-radius: 3px;
    font-size: 11px; font-weight: 700; text-transform: uppercase;
}

/* ===== Back slide ===== */
.slide-back {
    justify-content: center; align-items: center; text-align: center;
    background: linear-gradient(160deg, #FFF5F9 0%, #F0F0FF 50%, #F5F5FF 100%);
}
.slide-back .back-logo { width: 200px; margin-bottom: 36px; }
.slide-back .back-message { font-size: 24px; font-weight: 700; color: #1a202c; margin-bottom: 10px; }
.slide-back .back-sub { font-size: 16px; color: #718096; margin-bottom: 32px; line-height: 1.6; }
.slide-back .back-yt-btn {
    display: inline-flex; align-items: center; gap: 10px;
    background: #FF0000; color: #fff; font-size: 18px; font-weight: 700;
    padding: 16px 36px; border-radius: 10px; text-decoration: none; margin-bottom: 14px;
}
.slide-back .back-yt-url { font-size: 14px; color: #999; }
.slide-back .back-footer { margin-top: 48px; font-size: 12px; color: #B0B0B0; }

/* ===== TOC Navigation Overlay ===== */
.toc-overlay {
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.45);
    z-index: 9999;
    justify-content: center;
    align-items: center;
}
.toc-overlay.active { display: flex; }
.toc-panel {
    background: #fff;
    border-radius: 14px;
    box-shadow: 0 12px 48px rgba(0,0,0,0.2);
    width: 520px;
    max-height: 75vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    animation: tocFadeIn 0.15s ease-out;
}
@keyframes tocFadeIn {
    from { opacity: 0; transform: scale(0.95) translateY(-10px); }
    to { opacity: 1; transform: scale(1) translateY(0); }
}
.toc-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 18px 24px 14px;
    border-bottom: 1px solid #EDF2F7;
}
.toc-header h3 {
    font-size: 17px;
    font-weight: 700;
    color: #1a202c;
    margin: 0;
}
.toc-header .toc-hint {
    font-size: 12px;
    color: #A0AEC0;
}
.toc-list {
    overflow-y: auto;
    padding: 10px 0;
    list-style: none;
    margin: 0;
}
.toc-item {
    padding: 8px 24px;
    cursor: pointer;
    font-size: 14px;
    color: #2d3748;
    display: flex;
    align-items: center;
    gap: 10px;
    transition: background 0.1s;
    border-left: 3px solid transparent;
}
.toc-item:hover, .toc-item.selected {
    background: #F0F4FF;
    border-left-color: #0052CC;
}
.toc-item.selected {
    font-weight: 600;
    color: #0052CC;
}
.toc-item .toc-page {
    font-size: 11px;
    color: #A0AEC0;
    margin-left: auto;
    flex-shrink: 0;
}
.toc-item.toc-h1 { padding-left: 24px; font-weight: 700; font-size: 15px; }
.toc-item.toc-h2 { padding-left: 40px; font-weight: 600; }
.toc-item.toc-h3 { padding-left: 56px; }

@media print {
    .slide { min-height: 0; height: 100vh; }
    .slide-back .back-yt-btn { color: #fff !important; }
    .slide-back .back-yt-btn::after, .slide-back .back-yt-url::after { content: none !important; }
    a[href^="http"]::after { content: none !important; }
    .toc-overlay { display: none !important; }
}
"""


def build_presentation_html(page_data: dict, page_id: str, processed_soup: BeautifulSoup) -> str:
    """Build a presentation (slide) version of the page.

    Layout rules:
    - H1, H2: Title-only slide (heading centered)
    - H3: Title at top + following content until next heading
    - Cover page first, YouTube back page last
    - No TOC page
    - Each slide has a top bar (section name | title | logo) and footer
    """
    title = page_data.get("title", "Untitled")
    logo_b64 = load_logo_base64()

    logo_topbar = f'<img class="topbar-logo" src="{logo_b64}" alt="PinkLAB">' if logo_b64 else ""

    # --- Helper: build topbar ---
    def topbar(section_name: str) -> str:
        return f"""<div class="slide-topbar">
            <span class="topbar-section-name">{section_name}</span>
            <span class="topbar-title">{title}</span>
            {logo_topbar}
        </div>"""

    # --- Helper: build footer ---
    def footer(page_num: int, total: int) -> str:
        return f"""<div class="slide-footer">
            <span class="footer-author">PinkWink in PinkLAB</span>
            <span class="footer-page-num">{page_num} / {total}</span>
        </div>"""

    # --- Cover slide ---
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    cover_logo = f'<img class="cover-logo" src="{logo_b64}" alt="PinkLAB">' if logo_b64 else ""

    cover_slide_html = f"""
    <div class="slide slide-cover">
        <div class="cover-top-area">
            <div class="cover-title">{title}</div>
            <div class="cover-divider"></div>
        </div>
        <div class="cover-bottom-area">
            {cover_logo}
        </div>
    </div>"""

    # --- Remove inline width/height from images so CSS can scale them up ---
    for img in processed_soup.find_all("img"):
        if img.has_attr("width"):
            del img["width"]
        if img.has_attr("height"):
            del img["height"]

    # --- Parse content into slides ---
    slides_data = []  # list of (type, section_name, heading_text, content_html, h_level)
    current_section = title  # H1/H2 section name for topbar

    children = list(processed_soup.children)
    i = 0
    while i < len(children):
        child = children[i]
        if hasattr(child, 'name') and child.name in ('h1', 'h2'):
            heading_text = child.get_text(strip=True)
            current_section = heading_text
            slides_data.append(('heading', current_section, heading_text, '', 'h1'))
            i += 1
        elif hasattr(child, 'name') and child.name == 'h3':
            heading_text = child.get_text(strip=True)
            # Collect content until next h1/h2/h3
            content_parts = []
            i += 1
            while i < len(children):
                c = children[i]
                if hasattr(c, 'name') and c.name in ('h1', 'h2', 'h3'):
                    break
                content_parts.append(str(c))
                i += 1
            body = '\n'.join(content_parts).strip()
            if body:
                slides_data.append(('content', current_section, heading_text, body, 'h3'))
            else:
                # H3 with no content → treat as heading slide (same visual as H2)
                slides_data.append(('heading', current_section, heading_text, '', 'h3'))
        else:
            # Content before any heading or between headings — collect as content slide
            content_parts = [str(child)]
            i += 1
            while i < len(children):
                c = children[i]
                if hasattr(c, 'name') and c.name in ('h1', 'h2', 'h3'):
                    break
                content_parts.append(str(c))
                i += 1
            body = '\n'.join(content_parts).strip()
            if body:
                slides_data.append(('content', current_section, '', body, ''))

    total_pages = len(slides_data) + 2  # +cover +back

    # --- Build slide HTML ---
    content_slides = []
    for idx, (stype, section_name, heading_text, body, h_level) in enumerate(slides_data):
        pnum = idx + 2  # cover is page 1

        if stype == 'heading':
            content_slides.append(f"""
    <div class="slide slide-heading" data-toc-level="{h_level}" data-toc-title="{heading_text}">
        {topbar(section_name)}
        <div class="heading-body">
            <div class="heading-text">{heading_text}</div>
        </div>
        {footer(pnum, total_pages)}
    </div>""")
        else:
            title_html = f'<div class="content-title">{heading_text}</div>' if heading_text else ''
            toc_attr = f' data-toc-level="h3" data-toc-title="{heading_text}"' if heading_text else ''
            content_slides.append(f"""
    <div class="slide slide-content"{toc_attr}>
        {topbar(section_name)}
        <div class="content-body">
            {title_html}
            <div class="content-inner">
                {body}
            </div>
        </div>
        {footer(pnum, total_pages)}
    </div>""")

    # --- Back slide ---
    back_logo = f'<img class="back-logo" src="{logo_b64}" alt="PinkLAB">' if logo_b64 else ""
    yt_svg = (
        '<svg width="24" height="24" viewBox="0 0 24 24" fill="white">'
        '<path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 '
        '3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 '
        '0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 '
        '9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 '
        '2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 '
        '15.568V8.432L15.818 12l-6.273 3.568z"/></svg>'
    )
    back_slide_html = f"""
    <div class="slide slide-back">
        {back_logo}
        <div class="back-message">PinkLAB YouTube Channel</div>
        <div class="back-sub">PinkLAB Studio &mdash; Robotics, AI, ROS2 and more!</div>
        <a class="back-yt-btn" href="https://www.youtube.com/@pinklab_studio">
            {yt_svg} Subscribe on YouTube
        </a>
        <div class="back-yt-url">https://www.youtube.com/@pinklab_studio</div>
        <div class="back-footer">&copy; PinkLAB &middot; Exported with Confluence PDF Exporter</div>
    </div>"""

    all_slides = [cover_slide_html] + content_slides + [back_slide_html]

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} (Presentation)</title>
    <style>
{PRESENT_CSS}
html {{ scroll-behavior: auto; overflow: hidden; }}
body {{ overflow: hidden; }}
    </style>
</head>
<body>
    {"".join(all_slides)}

    <!-- TOC Navigation Overlay -->
    <div class="toc-overlay" id="tocOverlay">
        <div class="toc-panel">
            <div class="toc-header">
                <h3>Table of Contents</h3>
                <span class="toc-hint">T to close &middot; Enter to jump &middot; Arrow keys to navigate</span>
            </div>
            <ul class="toc-list" id="tocList"></ul>
        </div>
    </div>

<script>
(function() {{
    const slides = document.querySelectorAll('.slide');
    let current = 0;
    let scrolling = false;

    function goTo(idx) {{
        if (idx < 0 || idx >= slides.length || scrolling) return;
        scrolling = true;
        current = idx;
        slides[current].scrollIntoView({{ behavior: 'smooth' }});
        setTimeout(() => {{ scrolling = false; }}, 400);
    }}

    /* --- TOC Navigation --- */
    const tocOverlay = document.getElementById('tocOverlay');
    const tocList = document.getElementById('tocList');
    let tocOpen = false;
    let tocItems = [];
    let tocSelected = 0;

    function buildToc() {{
        tocList.innerHTML = '';
        tocItems = [];
        slides.forEach((slide, idx) => {{
            const level = slide.getAttribute('data-toc-level');
            const title = slide.getAttribute('data-toc-title');
            if (!title) return;
            const li = document.createElement('li');
            li.className = 'toc-item toc-' + level;
            li.innerHTML = '<span class="toc-label">' + title + '</span><span class="toc-page">' + (idx + 1) + ' / ' + slides.length + '</span>';
            li.setAttribute('data-slide-idx', idx);
            li.addEventListener('click', function() {{
                closeToc();
                goTo(idx);
            }});
            tocList.appendChild(li);
            tocItems.push({{ el: li, idx: idx }});
        }});
    }}

    function updateTocSelection() {{
        tocItems.forEach((item, i) => {{
            item.el.classList.toggle('selected', i === tocSelected);
        }});
        if (tocItems[tocSelected]) {{
            tocItems[tocSelected].el.scrollIntoView({{ block: 'nearest' }});
        }}
    }}

    function openToc() {{
        buildToc();
        if (tocItems.length === 0) return;
        tocOpen = true;
        tocOverlay.classList.add('active');
        // Select the closest TOC item to current slide
        tocSelected = 0;
        for (let i = tocItems.length - 1; i >= 0; i--) {{
            if (tocItems[i].idx <= current) {{ tocSelected = i; break; }}
        }}
        updateTocSelection();
    }}

    function closeToc() {{
        tocOpen = false;
        tocOverlay.classList.remove('active');
    }}

    tocOverlay.addEventListener('click', function(e) {{
        if (e.target === tocOverlay) closeToc();
    }});

    document.addEventListener('keydown', function(e) {{
        if (tocOpen) {{
            if (e.key === 't' || e.key === 'T' || e.key === 'Escape') {{
                e.preventDefault();
                closeToc();
            }} else if (e.key === 'ArrowDown') {{
                e.preventDefault();
                tocSelected = Math.min(tocSelected + 1, tocItems.length - 1);
                updateTocSelection();
            }} else if (e.key === 'ArrowUp') {{
                e.preventDefault();
                tocSelected = Math.max(tocSelected - 1, 0);
                updateTocSelection();
            }} else if (e.key === 'Enter') {{
                e.preventDefault();
                if (tocItems[tocSelected]) {{
                    closeToc();
                    goTo(tocItems[tocSelected].idx);
                }}
            }}
            return;
        }}

        if (e.key === 't' || e.key === 'T') {{
            e.preventDefault();
            openToc();
        }} else if (e.key === 'ArrowDown' || e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') {{
            e.preventDefault();
            goTo(current + 1);
        }} else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft' || e.key === 'PageUp') {{
            e.preventDefault();
            goTo(current - 1);
        }} else if (e.key === 'Home') {{
            e.preventDefault();
            goTo(0);
        }} else if (e.key === 'End') {{
            e.preventDefault();
            goTo(slides.length - 1);
        }}
    }});

    document.addEventListener('wheel', function(e) {{
        if (tocOpen) return;
        e.preventDefault();
        if (e.deltaY > 0) goTo(current + 1);
        else if (e.deltaY < 0) goTo(current - 1);
    }}, {{ passive: false }});
}})();

/* Open all links in new tab */
document.querySelectorAll('a:not([target])').forEach(function(a) {{
    if (a.getAttribute('href') && !a.getAttribute('href').startsWith('#')) {{
        a.setAttribute('target', '_blank');
        a.setAttribute('rel', 'noopener noreferrer');
    }}
}});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def generate_pdf(html_path: str, pdf_path: str, presentation: bool = False) -> None:
    """Generate PDF from HTML using Playwright."""
    from playwright.sync_api import sync_playwright

    print("  Launching browser for PDF generation...")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        file_url = f"file://{os.path.abspath(html_path)}"
        page.goto(file_url, wait_until="load")

        if presentation:
            # Use CSS @page size (1280x720 = 16:9)
            page.pdf(
                path=pdf_path,
                prefer_css_page_size=True,
                margin={"top": "0mm", "right": "0mm", "bottom": "0mm", "left": "0mm"},
                print_background=True,
            )
        else:
            page.pdf(
                path=pdf_path,
                format="A4",
                margin={"top": "20mm", "right": "15mm", "bottom": "20mm", "left": "15mm"},
                print_background=True,
            )
        browser.close()
    print(f"  PDF saved: {pdf_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Export Confluence Cloud page to styled HTML and PDF"
    )
    parser.add_argument("url", help="Confluence page URL")
    parser.add_argument(
        "--output-dir", "-o", default="output",
        help="Output directory (default: output)"
    )
    args = parser.parse_args()

    # Load credentials from token file
    load_token_file()
    if not CONFLUENCE_URL or not CONFLUENCE_EMAIL or not CONFLUENCE_API_TOKEN:
        print("Error: confluence_token.txt is missing required keys "
              "(CONFLUENCE_URL, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)",
              file=sys.stderr)
        sys.exit(1)

    # Extract page ID
    print(f"Parsing URL: {args.url}")
    page_id = extract_page_id(args.url)
    print(f"Page ID: {page_id}")

    # Fetch page
    print("Fetching page from Confluence API...")
    try:
        page_data = fetch_page(page_id)
    except requests.exceptions.HTTPError:
        print("  v2 API failed, trying v1 API...")
        page_data = fetch_page_v1(page_id)

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Process page content (shared between document and presentation)
    print("Processing page content...")
    title, processed_soup = process_page_content(page_data, page_id, str(output_dir))
    print(f"Page title: {title}")

    # Sanitize title for filename
    safe_title = re.sub(r'[^\w\s가-힣-]', '', title).strip()
    safe_title = re.sub(r'\s+', '_', safe_title)
    if not safe_title:
        safe_title = f"page_{page_id}"

    # --- Document PDF ---
    print("\n[Document] Building PDF...")
    doc_soup = BeautifulSoup(str(processed_soup), "html.parser")
    doc_html_content = build_html(title, doc_soup)
    # Write temporary HTML for PDF generation, then remove it
    tmp_doc_html = output_dir / f"_tmp_{safe_title}.html"
    tmp_doc_html.write_text(doc_html_content, encoding="utf-8")
    pdf_path = output_dir / f"{safe_title}.pdf"
    generate_pdf(str(tmp_doc_html), str(pdf_path))
    tmp_doc_html.unlink(missing_ok=True)

    # --- Presentation HTML & PDF ---
    print("\n[Presentation] Building slide HTML...")
    present_soup = BeautifulSoup(str(processed_soup), "html.parser")
    present_html = build_presentation_html(page_data, page_id, present_soup)

    present_html_path = output_dir / f"present_{safe_title}.html"
    present_html_path.write_text(present_html, encoding="utf-8")
    print(f"HTML saved: {present_html_path}")

    print("[Presentation] Generating PDF...")
    present_pdf_path = output_dir / f"present_{safe_title}.pdf"
    generate_pdf(str(present_html_path), str(present_pdf_path), presentation=True)

    print(f"\nDone! Files saved in '{output_dir}/':")
    print(f"  1. {pdf_path}  (Document PDF)")
    print(f"  2. {present_html_path}  (Presentation HTML)")
    print(f"  3. {present_pdf_path}  (Presentation PDF)")


if __name__ == "__main__":
    main()
