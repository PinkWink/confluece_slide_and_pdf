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

            # Fetch page
            log("Fetching page from Confluence API...")
            try:
                page_data = ce.fetch_page(page_id)
            except Exception:
                log("v2 API failed, trying v1...")
                page_data = ce.fetch_page_v1(page_id)

            # Create output directory
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)

            # Process content
            log("Processing page content...")
            title, processed_soup = ce.process_page_content(page_data, page_id, str(out))
            log(f"Page title: {title}")

            # Sanitize title for default filenames
            safe_title = re.sub(r'[^\w\s가-힣-]', '', title).strip()
            safe_title = re.sub(r'\s+', '_', safe_title)
            if not safe_title:
                safe_title = f"page_{page_id}"

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

            # --- Document PDF ---
            if enable_doc_pdf:
                log("Building Document PDF...")
                doc_soup = BeautifulSoup(str(processed_soup), "html.parser")
                doc_html_content = ce.build_html(title, doc_soup)
                tmp_doc_html = out / f"_tmp_{safe_title}.html"
                tmp_doc_html.write_text(doc_html_content, encoding="utf-8")
                pdf_path = out / fn_doc_pdf
                ce.generate_pdf(str(tmp_doc_html), str(pdf_path))
                tmp_doc_html.unlink(missing_ok=True)
                log(f"Document PDF saved: {pdf_path.name}")
                generated_files.append({"name": fn_doc_pdf, "path": str(pdf_path), "type": "Document PDF"})

            # --- Presentation HTML ---
            # Build presentation HTML if either HTML or PDF is enabled (PDF needs the HTML)
            present_html_path = None
            if enable_present_html or enable_present_pdf:
                log("Building Presentation HTML...")
                present_soup = BeautifulSoup(str(processed_soup), "html.parser")
                present_html = ce.build_presentation_html(page_data, page_id, present_soup)
                present_html_path = out / fn_present_html
                present_html_path.write_text(present_html, encoding="utf-8")
                if enable_present_html:
                    log(f"Presentation HTML saved: {present_html_path.name}")
                    generated_files.append({"name": fn_present_html, "path": str(present_html_path), "type": "Presentation HTML"})

            # --- Presentation PDF ---
            if enable_present_pdf:
                log("Building Presentation PDF...")
                present_pdf_path = out / fn_present_pdf
                # If HTML wasn't enabled, we still generated it as temp; build PDF then clean up
                if not present_html_path:
                    present_soup = BeautifulSoup(str(processed_soup), "html.parser")
                    present_html = ce.build_presentation_html(page_data, page_id, present_soup)
                    present_html_path = out / f"_tmp_present_{safe_title}.html"
                    present_html_path.write_text(present_html, encoding="utf-8")
                ce.generate_pdf(str(present_html_path), str(present_pdf_path), presentation=True)
                log(f"Presentation PDF saved: {present_pdf_path.name}")
                generated_files.append({"name": fn_present_pdf, "path": str(present_pdf_path), "type": "Presentation PDF"})
                # Clean up temp HTML if it was only for PDF generation
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


@app.route("/api/files/<job_id>/<filename>")
def serve_output_file(job_id, filename):
    """Serve an output file for in-browser viewing.

    Uses job_id to look up the output directory, avoiding Windows path
    encoding issues (C: in URL etc).
    """
    job = jobs.get(job_id)
    if not job:
        return "Job not found", 404
    output_dir = job.get("output_dir", "")
    if not output_dir:
        return "Output directory not found", 404
    file_path = Path(output_dir) / filename
    if not file_path.exists():
        return "File not found", 404
    return send_from_directory(str(file_path.parent), file_path.name)


if __name__ == "__main__":
    print("Confluence PDF Exporter — Web GUI")
    print("Open http://localhost:5001 in your browser")
    app.run(host="0.0.0.0", port=5001, debug=True)
