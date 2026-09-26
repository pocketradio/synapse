from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

from pypdf import PdfReader


@dataclass
class NormalizedChunk:
    content: str
    locator: dict[str, Any]


def _markdown_chunks(content: str) -> list[NormalizedChunk]:
    chunks: list[NormalizedChunk] = []
    heading = "document"
    lines = content.splitlines()
    current: list[str] = []
    start = 1
    for number, line in enumerate(lines, start=1):
        if line.startswith("#"):
            if current:
                chunks.append(NormalizedChunk(
                    "\n".join(current).strip(),
                    {
                        "kind": "heading",
                        "heading": heading,
                        "line_start": start,
                        "line_end": number - 1,
                    },
                ))
            heading = line.lstrip("#").strip() or "document"
            current = [line]
            start = number
        else:
            current.append(line)
    if current and "\n".join(current).strip():
        chunks.append(NormalizedChunk("\n".join(current).strip(), {
            "kind": "heading", "heading": heading, "line_start": start, "line_end": len(lines),
        }))
    return chunks


def _code_chunks(content: str) -> list[NormalizedChunk]:
    lines = content.splitlines()
    symbols = list(re.finditer(r"(?m)^(?:class|def|function)\s+([A-Za-z_]\w*)", content))
    if not symbols:
        return [NormalizedChunk(
            content.strip(), {"kind": "code_file", "line_start": 1, "line_end": len(lines)}
        )]
    chunks: list[NormalizedChunk] = []
    for index, match in enumerate(symbols):
        start = content.count("\n", 0, match.start()) + 1
        end = (
            content.count("\n", 0, symbols[index + 1].start())
            if index + 1 < len(symbols)
            else len(lines)
        )
        chunks.append(NormalizedChunk("\n".join(lines[start - 1:end]).strip(), {
            "kind": "code_symbol", "symbol": match.group(1), "line_start": start, "line_end": end,
        }))
    return chunks


def _json_chunks(content: str) -> list[NormalizedChunk]:
    value = json.loads(content)
    chunks: list[NormalizedChunk] = []

    def visit(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                visit(child, f"{path}.{key}")
        elif isinstance(node, list):
            for index, child in enumerate(node):
                visit(child, f"{path}[{index}]")
        else:
            chunks.append(NormalizedChunk(f"{path} = {json.dumps(node)}", {
                "kind": "json_path", "path": path,
            }))

    visit(value, "$")
    return chunks or [NormalizedChunk(content, {"kind": "json_document", "path": "$"})]


def _html_chunks(content: str) -> list[NormalizedChunk]:
    text_content = re.sub(r"<[^>]+>", " ", content)
    text_content = re.sub(r"\s+", " ", text_content).strip()
    return [NormalizedChunk(text_content, {"kind": "html_document", "section": "body"})]


def _pdf_chunks(content: bytes) -> list[NormalizedChunk]:
    reader = PdfReader(__import__("io").BytesIO(content))
    return [
        NormalizedChunk(page.extract_text() or "", {"kind": "pdf", "page": number})
        for number, page in enumerate(reader.pages, start=1)
        if (page.extract_text() or "").strip()
    ]


def normalize_file(filename: str, content: bytes) -> list[NormalizedChunk]:
    suffix = PurePath(filename).suffix.lower()
    if suffix in {".md", ".markdown"}:
        return _markdown_chunks(content.decode("utf-8"))
    if suffix in {".py", ".js", ".ts", ".java", ".go"}:
        return _code_chunks(content.decode("utf-8"))
    if suffix == ".json":
        return _json_chunks(content.decode("utf-8"))
    if suffix in {".html", ".htm"}:
        return _html_chunks(content.decode("utf-8"))
    if suffix == ".pdf":
        return _pdf_chunks(content)
    return [NormalizedChunk(content.decode("utf-8"), {"kind": "text", "line_start": 1})]

