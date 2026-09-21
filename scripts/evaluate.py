"""Run the real Jev API against the held-out fixture labels (never sent)."""
import json
import os
from pathlib import Path
import sys

from jevtex import judge
from jevtex.pdf import ROOT
from jevtex.tex import extract


def main():
    if not os.environ.get("TYPESAFE_API_KEY", "").strip():
        print("実API評価は未実施: TYPESAFE_API_KEYを環境変数に設定してください。", file=sys.stderr)
        return 2
    truth = json.loads((ROOT / "examples/expected.json").read_text())
    model = os.environ.get("JEV_MODEL", judge.DEFAULT_MODEL)
    rows = []
    for variant, expected_pairs in truth["variants"].items():
        equations = extract((ROOT / f"examples/laplacian_{variant}.tex").read_text())["equations"]
        for expected in expected_pairs:
            pair = {k: expected[k] for k in ("before", "after", "context_ids")}
            row = {"variant": variant, **pair, "expected": expected["expected"]}
            try:
                payload = judge.payload_for(equations, pair, truth["assumptions"], model)
                row.update(judge.call_jev(payload))
            except judge.JudgeError as exc:
                row.update({"status": "error", "error": str(exc)})
            rows.append(row)
            print(f"{variant}: {pair['before']} -> {pair['after']}: {row.get('verdict', 'error')}")
    incorrect = [r for r in rows if r["expected"] == "incorrect"]
    correct = [r for r in rows if r["expected"] == "correct"]
    report = {"kind": "live-api-evaluation", "requested_model": model, "threshold": judge.THRESHOLD,
              "total": len(rows), "matched": sum(r.get("verdict") == r["expected"] for r in rows),
              "error_detection_rate": sum(r.get("verdict") == "incorrect" for r in incorrect) / len(incorrect),
              "false_positive_count": sum(r.get("verdict") == "incorrect" for r in correct),
              "uncertain_count": sum(r.get("verdict") == "uncertain" for r in rows),
              "api_error_count": sum(r["status"] == "error" for r in rows), "results": rows}
    output = ROOT / "output/evaluation.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k:v for k,v in report.items() if k != "results"},ensure_ascii=False,indent=2))
    print(f"保存先: {output}")
    return 0 if report["matched"] == report["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
