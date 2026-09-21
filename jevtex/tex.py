"""Extract supported display math without expanding or executing TeX."""
from pylatexenc.latexwalker import (
    LatexWalker, LatexEnvironmentNode, LatexMathNode, LatexMacroNode,
    LatexCommentNode, LatexCharsNode, LatexSpecialsNode,
)

SUPPORTED = {"equation", "equation*", "align", "align*"}
SECTIONS = {"section", "subsection", "subsubsection", "chapter"}


def children(node):
    yield from getattr(node, "nodelist", None) or []
    args = getattr(getattr(node, "nodeargd", None), "argnlist", [])
    yield from (arg for arg in args if arg is not None)


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(children(node))


def clean_math(source, nodes):
    """Remove presentation metadata, preserving nested alignment markers."""
    if not nodes:
        return "", []
    start, end = nodes[0].pos, nodes[-1].pos + nodes[-1].len
    cuts, labels = [], []
    for node in walk(nodes):
        if isinstance(node, LatexCommentNode):
            cuts.append((node.pos, node.pos + node.len))
        elif isinstance(node, LatexMacroNode) and node.macroname in {"label", "tag", "notag", "nonumber"}:
            cuts.append((node.pos, node.pos + node.len))
            if node.macroname == "label":
                labels.append(source[node.pos:node.pos + node.len].split("{", 1)[1].rsplit("}", 1)[0])
    for node in nodes:
        if isinstance(node, LatexSpecialsNode) and node.specials_chars == "&":
            cuts.append((node.pos, node.pos + node.len))
    text = source[start:end]
    for a, b in sorted(set(cuts), reverse=True):
        text = text[:a-start] + text[b-start:]
    return text.strip(), labels


def extract(source):
    nodes = LatexWalker(source, tolerant_parsing=False).get_latex_nodes()[0]
    warnings = []
    for node in walk(nodes):
        if isinstance(node, LatexMacroNode) and node.macroname in {"input", "include", "includegraphics"}:
            raise ValueError("初版は外部ファイルを参照しない単一TeXに対応しています。")
        if isinstance(node, LatexMacroNode) and node.macroname in {"newcommand", "renewcommand", "def", "DeclareMathOperator"}:
            warnings.append("独自マクロの展開には未対応です。判定前に数式を標準コマンドへ書き換えてください。")
        if isinstance(node, LatexEnvironmentNode) and node.environmentname in {"gather", "gather*", "multline", "multline*", "eqnarray", "eqnarray*", "displaymath"}:
            warnings.append(f"{node.environmentname}環境は抽出対象外です。equationまたはalignを使用してください。")
        if isinstance(node, LatexMathNode) and node.delimiters[0] == "$$":
            warnings.append("$$数式は抽出対象外です。\\[...\\]を使用してください。")
    documents = [n for n in nodes if isinstance(n, LatexEnvironmentNode) and n.environmentname == "document"]
    if len(documents) != 1:
        raise ValueError("\\begin{document}を含む単一の完全なTeX文書が必要です。")
    equations, section, prose, block = [], 0, "", 0
    for node in documents[0].nodelist:
        if isinstance(node, LatexMacroNode) and node.macroname in SECTIONS:
            section += 1
            prose = ""
            continue
        display = isinstance(node, LatexEnvironmentNode) and node.environmentname in SUPPORTED
        display = display or (isinstance(node, LatexMathNode) and node.delimiters[0] == "\\[")
        if not display:
            if isinstance(node, (LatexCharsNode, LatexMathNode)):
                prose += source[node.pos:node.pos + node.len]
            elif isinstance(node, LatexMacroNode) and node.macroname in {"textbf", "emph", "textit", "ref", "eqref"}:
                prose += source[node.pos:node.pos + node.len]
            elif isinstance(node, LatexEnvironmentNode):
                warnings.append(f"{node.environmentname}内部の数式は未対応です。文書直下に置いてください。")
            continue
        block += 1
        rows, row = [], []
        is_align = isinstance(node, LatexEnvironmentNode) and node.environmentname.startswith("align")
        for part in node.nodelist:
            if is_align and isinstance(part, LatexMacroNode) and part.macroname == "\\":
                rows.append(row)
                row = []
            elif is_align and isinstance(part, LatexMacroNode) and part.macroname == "intertext":
                warnings.append("align内のintertextは比較文脈に含めません。ペアと前提を確認してください。")
            else:
                row.append(part)
        rows.append(row)
        lhs = ""
        for parts in rows:
            latex, labels = clean_math(source, parts)
            if not latex:
                continue
            raw = source[parts[0].pos:parts[-1].pos + parts[-1].len]
            start = parts[0].pos + len(raw) - len(raw.lstrip())
            end = parts[0].pos + len(raw.rstrip())
            if latex.startswith("=") and lhs:
                latex = lhs + " " + latex
            elif "=" in latex:
                lhs = latex.split("=", 1)[0].strip()
            equations.append({
                "id": f"e{len(equations)+1}", "latex": latex, "labels": labels,
                "start": start, "end": end,
                "line_start": source.count("\n", 0, start) + 1,
                "line_end": source.count("\n", 0, max(start, end - 1)) + 1,
                "section": section, "block": block, "context": prose.strip()[-3000:],
                "block_end_line": source.count("\n", 0, node.pos + node.len - 1) + 1,
                "environment": getattr(node, "environmentname", "display"),
                "locations": [],
            })
        prose = ""
    pairs = [{"before": a["id"], "after": b["id"], "context_ids": []}
             for a, b in zip(equations, equations[1:]) if a["section"] == b["section"]]
    if not equations:
        warnings.append("対応する独立数式が見つかりませんでした。")
    return {"equations": equations, "pairs": pairs, "warnings": list(dict.fromkeys(warnings))}
