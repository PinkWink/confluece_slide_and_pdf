#!/usr/bin/env python3
"""Flask web GUI for Confluence PDF Exporter."""

import io
import os
import re
import sys
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

import confluence_export as ce

app = Flask(__name__)

# Store export job status
jobs = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/defaults", methods=["GET"])
def get_defaults():
    """Return default settings for the UI."""
    logo_path = Path(__file__).parent / "pinklab_logo_text.png"
    return jsonify({
        "logo_exists": logo_path.exists(),
        "default_output_dir": str(Path.home() / "Downloads"),
    })


@app.route("/api/children", methods=["POST"])
def list_children():
    """Return the descendant page tree for a Confluence URL.

    Body: { "url": "...", "depth": 0|1|2|3 }   (0 = all)
    """
    data = request.json or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Page URL is required"}), 400
    try:
        depth = int(data.get("depth", 0))
    except (TypeError, ValueError):
        depth = 0
    if depth < 0:
        depth = 0

    try:
        ce.load_token_file()
        if not ce.CONFLUENCE_URL or not ce.CONFLUENCE_EMAIL or not ce.CONFLUENCE_API_TOKEN:
            return jsonify({"error": "confluence_token.txt is missing required keys"}), 500
        page_id = ce.extract_page_id(url)

        # Fetch parent page metadata for title (lightweight v1 call)
        try:
            parent = ce.fetch_page_v1(page_id)
            parent_title = parent.get("title", "Untitled")
        except Exception:
            parent_title = "Untitled"

        tree = ce.fetch_child_tree(page_id, max_depth=depth)
        flat = ce.flatten_tree(tree)
        return jsonify({
            "parent": {"id": page_id, "title": parent_title},
            "children": flat,
            "count": len(flat),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/export", methods=["POST"])
def start_export():
    """Start an export job in background thread."""
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "Page URL is required"}), 400

    output_dir = data.get("output_dir", "").strip() or str(Path.home() / "Downloads")
    logo_file = data.get("logo_path", "").strip() or ""
    doc_pdf_name = data.get("doc_pdf_name", "").strip()
    present_html_name = data.get("present_html_name", "").strip()
    present_pdf_name = data.get("present_pdf_name", "").strip()
    enable_doc_pdf = data.get("enable_doc_pdf", True)
    enable_present_html = data.get("enable_present_html", True)
    enable_present_pdf = data.get("enable_present_pdf", True)

    include_children = bool(data.get("include_children", False))
    selected_child_ids = data.get("selected_child_ids") or []
    # Normalize to list of strings
    selected_child_ids = [str(x) for x in selected_child_ids if str(x).strip()]
    merge_mode = (data.get("merge_mode") or "merged").strip().lower()
    if merge_mode not in ("merged", "separate"):
        merge_mode = "merged"

    if not enable_doc_pdf and not enable_present_html and not enable_present_pdf:
        return jsonify({"error": "At least one output must be enabled"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {"status": "running", "progress": [], "files": []}

    def log(msg):
        jobs[job_id]["progress"].append(msg)

    def run_export():
        try:
            # Load credentials
            log("Loading credentials...")
            ce.load_token_file()
            if not ce.CONFLUENCE_URL or not ce.CONFLUENCE_EMAIL or not ce.CONFLUENCE_API_TOKEN:
                raise ValueError("confluence_token.txt is missing required keys")

            # Handle custom logo
            original_load_logo = ce.load_logo_base64
            if logo_file and Path(logo_file).exists():
                def custom_logo():
                    import base64
                    with open(logo_file, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    ext = Path(logo_file).suffix.lower()
                    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                            "gif": "image/gif", "svg": "image/svg+xml", "webp": "image/webp"
                            }.get(ext.lstrip("."), "image/png")
                    return f"data:{mime};base64,{b64}"
                ce.load_logo_base64 = custom_logo

            # Extract page ID
            log("Parsing URL...")
            page_id = ce.extract_page_id(url)
            log(f"Page ID: {page_id}")

            # Helper: fetch one page (v2, fallback v1)
            def fetch_one(pid):
                try:
                    return ce.fetch_page(pid)
                except Exception:
                    return ce.fetch_page_v1(pid)

            # Fetch parent page
            log("Fetching page from Confluence API...")
            page_data = fetch_one(page_id)

            # Create output directory
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)

            # Process parent content
            log("Processing page content...")
            title, processed_soup = ce.process_page_content(page_data, page_id, str(out))
            log(f"Page title: {title}")

            # Collect pages: list of (page_id, page_data, title, processed_soup)
            pages = [(page_id, page_data, title, processed_soup)]

            if include_children and selected_child_ids:
                log(f"Fetching {len(selected_child_ids)} child page(s)...")
                # Parent page id is a useful fallback when children reference
                # images stored on the parent (or sibling) page.
                sibling_ids = [pid for pid in selected_child_ids if pid != page_id]
                for cid in selected_child_ids:
                    try:
                        cdata = fetch_one(cid)
                        fb = [page_id] + [s for s in sibling_ids if s != cid]
                        ctitle, csoup = ce.process_page_content(cdata, cid, str(out), fallback_page_ids=fb)
                        log(f"  + {ctitle}")
                        pages.append((cid, cdata, ctitle, csoup))
                    except Exception as ex:
                        log(f"  ! Failed to fetch child {cid}: {ex}")

            # Sanitize title for default filenames
            def make_safe(t):
                s = re.sub(r'[^\w\s가-힣-]', '', t).strip()
                s = re.sub(r'\s+', '_', s)
                return s or f"page_{page_id}"

            safe_title = make_safe(title)

            # Determine filenames
            fn_doc_pdf = doc_pdf_name if doc_pdf_name else f"{safe_title}.pdf"
            fn_present_html = present_html_name if present_html_name else f"present_{safe_title}.html"
            fn_present_pdf = present_pdf_name if present_pdf_name else f"present_{safe_title}.pdf"

            # Ensure extensions
            if not fn_doc_pdf.endswith(".pdf"):
                fn_doc_pdf += ".pdf"
            if not fn_present_html.endswith(".html"):
                fn_present_html += ".html"
            if not fn_present_pdf.endswith(".pdf"):
                fn_present_pdf += ".pdf"

            from bs4 import BeautifulSoup
            generated_files = []

            # Decide build groups based on merge_mode
            # Each group: (group_title, group_page_id, group_page_data, group_soup, fn_suffix)
            # fn_suffix is "" for the canonical/parent file and "_<safe>" for separate-mode children.
            groups = []
            if len(pages) == 1 or merge_mode == "merged":
                if len(pages) > 1:
                    log(f"Merging {len(pages)} pages into one document...")
                    merged_soup = ce.merge_pages([(t, s) for (_, _, t, s) in pages])
                else:
                    merged_soup = processed_soup
                groups.append((title, page_id, page_data, merged_soup, ""))
            else:
                # separate mode
                for idx, (pid, pdata, ptitle, psoup) in enumerate(pages):
                    suffix = "" if idx == 0 else f"_{make_safe(ptitle)}"
                    groups.append((ptitle, pid, pdata, psoup, suffix))

            def with_suffix(base_name: str, suffix: str, ext: str) -> str:
                if not suffix:
                    return base_name
                stem = base_name[: -len(ext)] if base_name.endswith(ext) else base_name
                return f"{stem}{suffix}{ext}"

            for g_title, g_pid, g_pdata, g_soup, g_suffix in groups:
                g_safe = make_safe(g_title)

                # --- Document PDF ---
                if enable_doc_pdf:
                    name = with_suffix(fn_doc_pdf, g_suffix, ".pdf")
                    log(f"Building Document PDF: {name}")
                    doc_soup = BeautifulSoup(str(g_soup), "html.parser")
                    doc_html_content = ce.build_html(g_title, doc_soup)
                    tmp_doc_html = out / f"_tmp_{g_safe}{g_suffix}.html"
                    tmp_doc_html.write_text(doc_html_content, encoding="utf-8")
                    pdf_path = out / name
                    ce.generate_pdf(str(tmp_doc_html), str(pdf_path))
                    tmp_doc_html.unlink(missing_ok=True)
                    log(f"Document PDF saved: {pdf_path.name}")
                    generated_files.append({"name": name, "path": str(pdf_path), "type": "Document PDF"})

                # --- Presentation HTML ---
                present_html_path = None
                if enable_present_html or enable_present_pdf:
                    name = with_suffix(fn_present_html, g_suffix, ".html")
                    log(f"Building Presentation HTML: {name}")
                    present_soup = BeautifulSoup(str(g_soup), "html.parser")
                    present_html = ce.build_presentation_html(g_pdata, g_pid, present_soup)
                    present_html_path = out / name
                    present_html_path.write_text(present_html, encoding="utf-8")
                    if enable_present_html:
                        log(f"Presentation HTML saved: {present_html_path.name}")
                        generated_files.append({"name": name, "path": str(present_html_path), "type": "Presentation HTML"})

                # --- Presentation PDF ---
                if enable_present_pdf:
                    name = with_suffix(fn_present_pdf, g_suffix, ".pdf")
                    log(f"Building Presentation PDF: {name}")
                    present_pdf_path = out / name
                    if not present_html_path:
                        present_soup = BeautifulSoup(str(g_soup), "html.parser")
                        present_html = ce.build_presentation_html(g_pdata, g_pid, present_soup)
                        present_html_path = out / f"_tmp_present_{g_safe}{g_suffix}.html"
                        present_html_path.write_text(present_html, encoding="utf-8")
                    ce.generate_pdf(str(present_html_path), str(present_pdf_path), presentation=True)
                    log(f"Presentation PDF saved: {present_pdf_path.name}")
                    generated_files.append({"name": name, "path": str(present_pdf_path), "type": "Presentation PDF"})
                    if not enable_present_html:
                        present_html_path.unlink(missing_ok=True)

            # Restore original logo loader
            ce.load_logo_base64 = original_load_logo

            jobs[job_id]["status"] = "done"
            jobs[job_id]["files"] = generated_files
            jobs[job_id]["output_dir"] = str(out)
            log("Export complete!")

        except Exception as e:
            # Restore logo loader on error too
            if 'original_load_logo' in dir():
                ce.load_logo_base64 = original_load_logo
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)
            log(f"Error: {e}")

    thread = threading.Thread(target=run_export, daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>", methods=["GET"])
def job_status(job_id):
    """Get export job status."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/api/logo/upload", methods=["POST"])
def upload_logo():
    """Upload a custom logo file and return its temp path."""
    if "logo" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files["logo"]
    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    upload_dir = Path(__file__).parent / "uploads"
    upload_dir.mkdir(exist_ok=True)
    ext = Path(file.filename).suffix
    save_path = upload_dir / f"custom_logo{ext}"
    file.save(str(save_path))
    return jsonify({"path": str(save_path), "filename": file.filename})


@app.route("/api/logo/reset", methods=["POST"])
def reset_logo():
    """Reset to default PinkLAB logo."""
    return jsonify({"path": "", "filename": "pinklab_logo_text.png (default)"})


@app.route("/api/files/<path:filepath>")
def serve_output_file(filepath):
    """Serve an output file for in-browser viewing."""
    # filepath comes URL-decoded by Flask; ensure it starts with /
    if not filepath.startswith("/"):
        filepath = "/" + filepath
    file_path = Path(filepath)
    if not file_path.exists():
        return "File not found", 404
    return send_from_directory(str(file_path.parent), file_path.name)


if __name__ == "__main__":
    print("Confluence PDF Exporter — Web GUI")
    print("Open http://localhost:5001 in your browser")
    app.run(host="0.0.0.0", port=5001, debug=True)
