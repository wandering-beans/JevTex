import json
import os
from pathlib import Path
import re
import threading
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from pylatexenc.latexwalker import LatexWalkerParseError

from . import judge
from .pdf import ROOT, annotate, compile_tex, executable, locate_equations
from .tex import extract

DATA = ROOT / ".jevtex"
app = FastAPI(title="JevTex", docs_url=None, redoc_url=None, openapi_url=None)
# ponytail: one active check per local process; per-document locks if multiuser use becomes necessary.
check_lock = threading.Lock()


class Upload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=1_000_000)


class Pair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    before: str
    after: str
    context_ids: list[str] = Field(default_factory=list, max_length=30)


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pairs: list[Pair] = Field(min_length=1, max_length=50)
    assumptions: str = Field(default="", max_length=8000)


@app.middleware("http")
async def local_only(request: Request, call_next):
    host = request.url.hostname
    if host not in {"localhost", "127.0.0.1", "::1"}:
        return JSONResponse({"detail": "localhostからのみ利用できます。"}, status_code=403)
    origin = request.headers.get("origin")
    if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
        return JSONResponse({"detail": "外部サイトからのリクエストは拒否しました。"}, status_code=403)
    if request.method == "POST":
        if request.headers.get("x-jevtex-client") != "1":
            return JSONResponse({"detail": "アプリ画面から操作してください。"}, status_code=403)
        try:
            length = int(request.headers.get("content-length", "-1"))
        except ValueError:
            length = -1
        if length < 0 or length > 4_000_000:
            return JSONResponse({"detail": "入力サイズが上限を超えています。"}, status_code=413)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; worker-src 'self' blob:; img-src 'self' data: blob:; font-src 'self' data:; frame-ancestors 'none'"
    return response


def document_dir(doc_id):
    if not re.fullmatch(r"[a-f0-9]{32}", doc_id):
        raise HTTPException(404, "文書が見つかりません。")
    directory = DATA / doc_id
    if not (directory / "metadata.json").is_file():
        raise HTTPException(404, "文書が見つかりません。")
    return directory


def save_json(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


@app.get("/api/status")
def status():
    return {"api_key_configured": bool(os.environ.get("TYPESAFE_API_KEY", "").strip()),
            "model": os.environ.get("JEV_MODEL", judge.DEFAULT_MODEL), "threshold": judge.THRESHOLD,
            "lualatex": bool(executable("lualatex")), "synctex": bool(executable("synctex"))}


@app.get("/api/samples/{variant}")
def sample(variant: str):
    if variant not in {"correct", "mistake"}:
        raise HTTPException(404)
    return {"name": f"laplacian_{variant}.tex", "source": (ROOT / "examples" / f"laplacian_{variant}.tex").read_text()}


@app.post("/api/documents")
def upload(body: Upload):
    if not body.name.lower().endswith(".tex"):
        raise HTTPException(422, "UTF-8の.texファイルを選んでください。")
    try:
        parsed = extract(body.source)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except (LatexWalkerParseError, RecursionError):
        raise HTTPException(422, "TeXを解析できません。単一の完全な文書、対応数式環境、括弧の対応を確認してください。") from None
    doc_id = uuid.uuid4().hex
    directory = DATA / doc_id
    directory.mkdir(parents=True, mode=0o700)
    (directory / "document.tex").write_text(body.source, encoding="utf-8")
    metadata = {"id": doc_id, "name": Path(body.name).name, **parsed, "pdf_available": False, "results": []}
    try:
        compile_tex(directory)
        metadata["pdf_available"] = True
        metadata["warnings"] += locate_equations(directory, metadata["equations"])
    except ValueError as exc:
        metadata["warnings"].append(str(exc))
    save_json(directory / "metadata.json", metadata)
    return metadata


@app.post("/api/documents/{doc_id}/check")
def check(doc_id: str, body: Check):
    directory = document_dir(doc_id)
    if not os.environ.get("TYPESAFE_API_KEY", "").strip():
        raise HTTPException(503, "TYPESAFE_API_KEYが未設定です。")
    metadata = json.loads((directory / "metadata.json").read_text())
    by_id = {e["id"]: e for e in metadata["equations"]}
    pairs = [p.model_dump() for p in body.pairs]
    seen = set()
    for p in pairs:
        if any(eid not in by_id for eid in [p["before"], p["after"], *p["context_ids"]]):
            raise HTTPException(422, "比較ペアに存在しない式IDがあります。")
        if p["before"] == p["after"] or (p["before"], p["after"]) in seen:
            raise HTTPException(422, "同じ式同士・重複するペアは指定できません。")
        if any(by_id[eid]["start"] >= by_id[p["after"]]["start"] for eid in p["context_ids"]):
            raise HTTPException(422, "参照式は比較先より前にある式を選んでください。")
        seen.add((p["before"], p["after"]))
    if not check_lock.acquire(blocking=False):
        raise HTTPException(409, "判定が実行中です。完了後に再実行してください。")
    try:
        model = os.environ.get("JEV_MODEL", judge.DEFAULT_MODEL)
        results = []
        for pair in pairs:
            result = {**pair, "locations": by_id[pair["after"]]["locations"]}
            try:
                payload = judge.payload_for(metadata["equations"], pair, body.assumptions, model)
                result.update(judge.call_jev(payload))
            except judge.JudgeError as exc:
                result.update({"status": "error", "error": str(exc)})
            results.append(result)
        metadata.update({"results": results, "pairs": pairs, "assumptions": body.assumptions})
        save_json(directory / "metadata.json", metadata)
        if metadata["pdf_available"]:
            annotate(directory / "document.pdf", directory / "annotated.pdf", results)
        return metadata
    finally:
        check_lock.release()


@app.get("/api/documents/{doc_id}/results")
def results(doc_id: str):
    directory = document_dir(doc_id)
    return FileResponse(directory / "metadata.json", filename="jevtex-results.json", media_type="application/json")


@app.get("/api/documents/{doc_id}/pdf")
def pdf(doc_id: str, annotated: bool = False):
    directory = document_dir(doc_id)
    path = directory / ("annotated.pdf" if annotated else "document.pdf")
    if not path.is_file():
        raise HTTPException(404, "PDFはまだ生成されていません。")
    return FileResponse(path, media_type="application/pdf", filename="jevtex-annotated.pdf" if annotated else None)


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
app.mount("/vendor", StaticFiles(directory=ROOT / "node_modules/pdfjs-dist", check_dir=False), name="vendor")


@app.get("/")
def index():
    return FileResponse(ROOT / "static/index.html")
