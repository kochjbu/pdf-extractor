"""
PDF Form Extractor
-------------------
A simple desktop app: drag in one or many fillable PDF forms,
it reads every form field, and saves the results to a CSV file.

No internet connection needed once built into an .exe / .app.
"""

import csv
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime

from pypdf import PdfReader

# Optional drag-and-drop support (tkinterdnd2). Falls back gracefully
# to "click to browse" if it isn't installed/bundled.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False


# ── Core extraction logic ────────────────────────────────────────────────

def extract_fields_from_pdf(path):
    """Return a dict of {field_name: value} for one fillable PDF."""
    reader = PdfReader(path)
    fields = reader.get_fields() or {}
    result = {}
    for name, field in fields.items():
        raw = field.get("/V", "")
        # Checkboxes / radio buttons come back as NameObjects like '/Yes'
        if hasattr(raw, "startswith") and raw.startswith("/"):
            raw = raw[1:]
        result[name] = str(raw).strip() if raw else ""
    return result


def extract_many(paths, progress_callback=None):
    """
    Run extraction across multiple PDFs.
    Returns (rows, fieldnames, errors)
      rows       -> list of dicts, one per PDF (always includes 'source_file')
      fieldnames -> ordered list of all column names seen, for the CSV header
      errors     -> list of (filename, error_message) for files that failed
    """
    rows = []
    errors = []
    fieldnames = ["source_file"]

    for i, path in enumerate(paths):
        name = os.path.basename(path)
        if progress_callback:
            progress_callback(i + 1, len(paths), name)
        try:
            fields = extract_fields_from_pdf(path)
            row = {"source_file": name}
            row.update(fields)
            rows.append(row)
            for key in fields:
                if key not in fieldnames:
                    fieldnames.append(key)
        except Exception as e:
            errors.append((name, str(e)))

    return rows, fieldnames, errors


def write_csv(rows, fieldnames, out_path):
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ── GUI ───────────────────────────────────────────────────────────────────

class PDFExtractorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Form Extractor")
        self.root.geometry("560x460")
        self.root.minsize(480, 400)
        self.root.configure(bg="#F7F8FA")

        self.selected_files = []

        self._build_ui()

    # -- UI construction --
    def _build_ui(self):
        PRIMARY = "#4F6EF7"
        DARK = "#1A1D23"
        GRAY = "#6B7280"

        # Header
        header = tk.Frame(self.root, bg=DARK, height=56)
        header.pack(fill="x", side="top")
        tk.Label(
            header, text="📋  PDF Form Extractor",
            bg=DARK, fg="white", font=("Segoe UI", 13, "bold"),
            padx=18, pady=14
        ).pack(side="left")

        body = tk.Frame(self.root, bg="#F7F8FA", padx=24, pady=20)
        body.pack(fill="both", expand=True)

        # Drop zone
        self.drop_frame = tk.Frame(
            body, bg="white", highlightbackground="#D1D5DB",
            highlightthickness=2, bd=0
        )
        self.drop_frame.pack(fill="both", expand=True, pady=(0, 14))

        inner = tk.Frame(self.drop_frame, bg="white")
        inner.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(inner, text="📂", bg="white", font=("Segoe UI", 28)).pack(pady=(0, 8))
        self.drop_label = tk.Label(
            inner,
            text="Drag PDF forms here" if DND_AVAILABLE else "Click below to choose PDF forms",
            bg="white", fg=DARK, font=("Segoe UI", 12, "bold")
        )
        self.drop_label.pack()
        tk.Label(
            inner, text="or click the button to browse — select one or many files",
            bg="white", fg=GRAY, font=("Segoe UI", 9)
        ).pack(pady=(2, 14))

        browse_btn = tk.Button(
            inner, text="Choose Files", command=self.browse_files,
            bg=PRIMARY, fg="white", font=("Segoe UI", 10, "bold"),
            relief="flat", padx=18, pady=6, cursor="hand2",
            activebackground="#3B57D6", activeforeground="white"
        )
        browse_btn.pack()

        # Enable drag-and-drop if available
        if DND_AVAILABLE:
            self.drop_frame.drop_target_register(DND_FILES)
            self.drop_frame.dnd_bind("<<Drop>>", self.on_drop)

        # Status label
        self.status_var = tk.StringVar(value="No files selected yet.")
        self.status_label = tk.Label(
            body, textvariable=self.status_var, bg="#F7F8FA", fg=GRAY,
            font=("Segoe UI", 9), anchor="w", justify="left"
        )
        self.status_label.pack(fill="x", pady=(0, 10))

        # Run button
        self.run_btn = tk.Button(
            body, text="Extract & Save CSV", command=self.run_extraction,
            bg=DARK, fg="white", font=("Segoe UI", 11, "bold"),
            relief="flat", padx=16, pady=10, cursor="hand2",
            activebackground="#2D3139", activeforeground="white",
            state="disabled"
        )
        self.run_btn.pack(fill="x")

    # -- File selection --
    def browse_files(self):
        paths = filedialog.askopenfilenames(
            title="Select PDF form(s)",
            filetypes=[("PDF files", "*.pdf")]
        )
        if paths:
            self.set_files(list(paths))

    def on_drop(self, event):
        # event.data is a string with paths, space-separated, braces around
        # paths that contain spaces. tkinterdnd2 gives us splitlist for this.
        paths = self.root.tk.splitlist(event.data)
        pdfs = [p for p in paths if p.lower().endswith(".pdf")]
        if not pdfs:
            messagebox.showwarning("No PDFs found", "Please drop PDF files only.")
            return
        self.set_files(pdfs)

    def set_files(self, paths):
        self.selected_files = paths
        n = len(paths)
        self.status_var.set(f"{n} file{'s' if n != 1 else ''} selected — ready to extract.")
        self.run_btn.config(state="normal")

    # -- Extraction --
    def run_extraction(self):
        if not self.selected_files:
            return
        self.run_btn.config(state="disabled", text="Processing…")
        self.status_var.set("Starting extraction…")
        thread = threading.Thread(target=self._extraction_worker, daemon=True)
        thread.start()

    def _extraction_worker(self):
        def progress(i, total, name):
            self.root.after(0, lambda: self.status_var.set(f"Processing {i}/{total}: {name}"))

        rows, fieldnames, errors = extract_many(self.selected_files, progress)

        if not rows:
            self.root.after(0, lambda: self._extraction_failed(errors))
            return

        # Ask where to save
        default_name = f"form_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.root.after(0, lambda: self._prompt_save(rows, fieldnames, errors, default_name))

    def _prompt_save(self, rows, fieldnames, errors, default_name):
        out_path = filedialog.asksaveasfilename(
            title="Save CSV as…",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv")]
        )
        if not out_path:
            self.status_var.set("Save cancelled.")
            self._reset_run_button()
            return

        try:
            write_csv(rows, fieldnames, out_path)
        except Exception as e:
            messagebox.showerror("Error saving CSV", str(e))
            self._reset_run_button()
            return

        msg = f"✓ Saved {len(rows)} record(s) to:\n{out_path}"
        if errors:
            msg += f"\n\n⚠ {len(errors)} file(s) failed:\n" + "\n".join(
                f"- {name}: {err}" for name, err in errors
            )
        self.status_var.set(f"Done — {len(rows)} record(s) saved.")
        messagebox.showinfo("Extraction complete", msg)
        self._reset_run_button()

    def _extraction_failed(self, errors):
        msg = "No data could be extracted."
        if errors:
            msg += "\n\n" + "\n".join(f"- {name}: {err}" for name, err in errors)
        messagebox.showerror("Extraction failed", msg)
        self.status_var.set("Extraction failed.")
        self._reset_run_button()

    def _reset_run_button(self):
        self.run_btn.config(state="normal", text="Extract & Save CSV")


def main():
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    app = PDFExtractorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
