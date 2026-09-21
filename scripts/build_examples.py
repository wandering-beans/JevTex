"""Compile both fixtures; an optional overlay is explicitly an oracle demo."""
import json
from jevtex.pdf import ROOT, compile_tex, locate_equations, annotate
from jevtex.tex import extract


def main():
    truth = json.loads((ROOT/"examples/expected.json").read_text())
    for variant in ("correct", "mistake"):
        directory = ROOT / "output/pdf" / variant
        directory.mkdir(parents=True, exist_ok=True)
        source = (ROOT / f"examples/laplacian_{variant}.tex").read_text()
        (directory / "document.tex").write_text(source)
        compile_tex(directory)
        parsed = extract(source)
        parsed["warnings"] += locate_equations(directory, parsed["equations"])
        (directory/"extracted.json").write_text(json.dumps(parsed,ensure_ascii=False,indent=2))
        if variant == "mistake":
            by_id = {e["id"]:e for e in parsed["equations"]}
            results = [{**p, "status":"ok", "verdict":p["expected"], "model":"oracle-demo-NOT-Jev",
                        "locations":by_id[p["after"]]["locations"]} for p in truth["variants"][variant]]
            annotate(directory/"document.pdf", directory/"overlay-demo.pdf", results)
            (directory/"overlay-demo.json").write_text(json.dumps({"kind":"oracle-demo-NOT-Jev", "results":results},ensure_ascii=False,indent=2))
        print(directory/"document.pdf", parsed["warnings"])


if __name__ == "__main__":
    main()
