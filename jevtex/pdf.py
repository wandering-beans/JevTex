"""Compile a local TeX document and map source lines through SyncTeX."""
import math
import gzip
import os
from pathlib import Path
import re
import shutil
import subprocess

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Highlight
from pypdf.generic import (
    ArrayObject, FloatObject, NameObject, DictionaryObject,
    DecodedStreamObject, TextStringObject, NumberObject,
)

ROOT = Path(__file__).resolve().parent.parent


def executable(name):
    candidates = [ROOT / ".tools/texlive/bin/universal-darwin" / name, Path("/Library/TeX/texbin") / name]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


def tex_environment():
    # Explicit allowlist: API keys and unrelated credentials never reach TeX.
    env = {k: os.environ[k] for k in ("HOME", "PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT") if k in os.environ}
    env.update({"openin_any": "p", "openout_any": "p", "shell_escape": "f",
                "TEXMFVAR": str(ROOT / ".cache/texmf-var"), "TEXMFCONFIG": str(ROOT / ".cache/texmf-config")})
    return env


def compile_tex(directory):
    compiler = executable("lualatex")
    if not compiler:
        raise ValueError("LuaLaTeXが見つかりません。READMEのTeXセットアップを実行してください。")
    args = [compiler, "-no-shell-escape", "-synctex=1", "-interaction=nonstopmode", "-halt-on-error", "document.tex"]
    for _ in range(2):
        try:
            result = subprocess.run(args, cwd=directory, env=tex_environment(), capture_output=True, timeout=90)
        except subprocess.TimeoutExpired:
            raise ValueError("TeXコンパイルが90秒を超えました。文書を確認してください。") from None
        if result.returncode:
            # The complete diagnostic stays local; no environment or raw TeX in HTTP errors.
            raise ValueError("TeXコンパイルに失敗しました。文書の構文・必要パッケージを確認してください（作業フォルダのdocument.log）。")
    if not (directory / "document.pdf").is_file():
        raise ValueError("TeXからPDFが生成されませんでした。")


def parse_synctex(text, pages):
    boxes, record = [], {}
    for line in text.splitlines() + ["Page:"]:
        if line.startswith("Page:"):
            if record:
                try:
                    page = int(record["Page"]) - 1
                    p = pages[page]
                    x, baseline, width, height = (float(record[k]) for k in ("h", "v", "W", "H"))
                    # synctex CLI uses top-left PDF points. v is the bottom of the visible box.
                    rect = [x, float(p.mediabox.top) - baseline, x + width, float(p.mediabox.top) - baseline + height]
                    if (page < 0 or width <= 0 or height <= 0 or not all(map(math.isfinite, rect))
                            or rect[0] < -1 or rect[1] < -1 or rect[2] > float(p.mediabox.right) + 1
                            or rect[3] > float(p.mediabox.top) + 1):
                        raise ValueError()
                    boxes.append({"page": page + 1, "rect": [round(v, 3) for v in rect]})
                except (KeyError, ValueError, IndexError):
                    pass
            record = {}
        if ":" in line:
            key, value = line.split(":", 1)
            if key in {"Page", "h", "v", "W", "H"}:
                record[key] = value.strip()
    return boxes


def locate_equations(directory, equations):
    synctex = executable("synctex")
    if not synctex:
        return ["SyncTeXが見つかりません。数式のPDF位置は未取得です。"]
    reader = PdfReader(directory / "document.pdf")
    sync_path = directory / "document.synctex.gz"
    if not sync_path.is_file():
        return ["SyncTeXファイルが生成されていません。位置未取得です。"]
    sync_text = gzip.decompress(sync_path.read_bytes()).decode("utf-8", errors="replace")
    tags = [m.group(1) for m in re.finditer(r"^Input:(\d+):(.+)$", sync_text, re.M)
            if Path(m.group(2)).resolve() == (directory / "document.tex").resolve()]
    recorded_lines = set()
    for tag in tags:
        recorded_lines.update(int(n) for n in re.findall(r"^[([]" + tag + r",(\d+)[:,]", sync_text, re.M))
    missing = []
    groups = {}
    for equation in equations:
        equation["locations"] = []
        groups.setdefault(equation["block"], []).append(equation)
    for group in groups.values():
        line = group[0]["block_end_line"]
        boxes = []
        # amsmath collects align's body: all rows are attributed to the environment's
        # closing line. Query that exact recorded line, never SyncTeX's nearest-line guess.
        if line in recorded_lines:
            try:
                result = subprocess.run([synctex, "view", "-i", f"{line}:0:{directory / 'document.tex'}",
                                         "-o", str(directory / "document.pdf")],
                                        capture_output=True, text=True, timeout=5, env=tex_environment())
                if result.returncode == 0:
                    boxes.extend(parse_synctex(result.stdout, reader.pages))
            except subprocess.TimeoutExpired:
                pass
        # ponytail: standard display boxes only; custom layouts need explicit TeX anchors.
        # The outer display boxes are the widest boxes; fragments (fractions, glyphs)
        # must not be mistaken for independent rows. Require an exact row-count match.
        width = max((b["rect"][2]-b["rect"][0] for b in boxes), default=0)
        outer = {(b["page"], tuple(b["rect"])) for b in boxes
                 if abs(b["rect"][2]-b["rect"][0]-width) < 0.1}
        ordered = sorted(outer, key=lambda b: (b[0], -b[1][3]))
        if len(ordered) == len(group):
            for equation, (page, rect) in zip(group, ordered):
                equation["locations"] = [{"page": page, "rect": list(rect)}]
        else:
            missing.extend(e["id"] for e in group)
    return ["位置未取得: " + ", ".join(missing)] if missing else []


def annotate(source, destination, results):
    writer = PdfWriter(clone_from=source)
    seen = set()
    # Red wins when multiple pairs point to the same equation.
    for result in sorted(results, key=lambda r: r.get("verdict") != "incorrect"):
        verdict = result.get("verdict")
        if result.get("status") != "ok" or verdict not in ("incorrect", "uncertain"):
            continue
        color, rgb = ("ff0000", "1 0 0") if verdict == "incorrect" else ("ffff00", "1 1 0")
        for location in result.get("locations", []):
            rect, page = location["rect"], location["page"] - 1
            key = (page, tuple(rect))
            if key in seen:
                continue
            seen.add(key)
            x0, y0, x1, y1 = rect
            annotation = Highlight(rect=rect, quad_points=ArrayObject([FloatObject(v) for v in
                [x0, y1, x1, y1, x0, y0, x1, y0]]), highlight_color=color)
            annotation[NameObject("/CA")] = FloatObject(0.22)
            annotation[NameObject("/F")] = NumberObject(4)
            annotation[NameObject("/Contents")] = TextStringObject(f"{result.get('model', 'Jev')}: {result['before']} -> {result['after']} ({verdict})")
            # Explicit appearance ensures saved highlights render in PDF.js and desktop readers.
            appearance = DecodedStreamObject()
            w, h = x1 - x0, y1 - y0
            appearance.set_data(f"q /GS gs {rgb} rg 0 0 {w} {h} re f Q".encode())
            appearance.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Form"),
                NameObject("/BBox"): ArrayObject([FloatObject(v) for v in [0, 0, w, h]]),
                NameObject("/Resources"): DictionaryObject({NameObject("/ExtGState"): DictionaryObject({
                    NameObject("/GS"): DictionaryObject({NameObject("/ca"): FloatObject(0.22)})})})})
            annotation[NameObject("/AP")] = DictionaryObject({NameObject("/N"): writer._add_object(appearance)})
            writer.add_annotation(page_number=page, annotation=annotation)
    writer.write(destination)
