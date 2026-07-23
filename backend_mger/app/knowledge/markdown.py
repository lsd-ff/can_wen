from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from app.knowledge.types import DocumentChunk


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
ASCII_WORD_RE = re.compile(r"[A-Za-z0-9_]+(?:[-./][A-Za-z0-9_]+)*")


@dataclass
class MarkdownSection:
    level: int
    title: str
    start_line: int
    heading_line: str = ""
    body_lines: list[tuple[int, str]] = field(default_factory=list)
    children: list["MarkdownSection"] = field(default_factory=list)
    parent: "MarkdownSection | None" = field(default=None, repr=False)

    @property
    def heading_path(self) -> list[str]:
        path: list[str] = []
        current: MarkdownSection | None = self
        while current and current.level:
            if current.title:
                path.append(current.title)
            current = current.parent
        return list(reversed(path))

    @property
    def end_line(self) -> int:
        lines = [self.start_line, *(number for number, _ in self.body_lines)]
        for child in self.children:
            lines.append(child.end_line)
        return max(lines)

    def direct_text(self, include_heading: bool = True) -> str:
        parts: list[str] = []
        if include_heading and self.heading_line:
            parts.append(self.heading_line)
        body = "\n".join(line for _, line in self.body_lines).strip()
        if body:
            parts.append(body)
        return "\n\n".join(parts).strip()

    def render(self) -> str:
        parts = [self.direct_text()]
        parts.extend(child.render() for child in self.children)
        return "\n\n".join(part for part in parts if part).strip()


SemanticSplitter = Callable[[str, int], list[str]]


def normalize_markdown(text: str) -> str:
    normalized = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    output: list[str] = []
    blank_count = 0
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and not line.strip():
            blank_count += 1
            if blank_count > 2:
                continue
        else:
            blank_count = 0
        output.append(line)
    return "\n".join(output).strip() + "\n"


def estimate_tokens(text: str) -> int:
    cjk = len(CJK_RE.findall(text))
    ascii_words = len(ASCII_WORD_RE.findall(text))
    remaining = max(0, len(text) - cjk - sum(len(word) for word in ASCII_WORD_RE.findall(text)))
    return max(1, round(cjk * 0.68 + ascii_words * 1.15 + remaining * 0.22))


def parse_heading_tree(markdown: str) -> MarkdownSection:
    root = MarkdownSection(level=0, title="", start_line=1)
    stack: list[MarkdownSection] = [root]
    in_fence = False
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        match = None if in_fence else HEADING_RE.match(line)
        if not match:
            stack[-1].body_lines.append((line_number, line))
            continue
        level = len(match.group(1))
        title = re.sub(r"\s+", " ", match.group(2)).strip()
        while stack[-1].level >= level:
            stack.pop()
        parent = stack[-1]
        section = MarkdownSection(
            level=level,
            title=title,
            start_line=line_number,
            heading_line=f"{'#' * level} {title}",
            parent=parent,
        )
        parent.children.append(section)
        stack.append(section)
    return root


def _walk(section: MarkdownSection) -> Iterable[MarkdownSection]:
    for child in section.children:
        yield child
        yield from _walk(child)


def _paragraph_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and not line.strip() and current:
            blocks.append("\n".join(current).strip())
            current = []
        elif line.strip() or current:
            current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return [block for block in blocks if block]


def _split_oversized_block(block: str, target_tokens: int) -> list[str]:
    if estimate_tokens(block) <= target_tokens:
        return [block]
    sentences = [part.strip() for part in re.split(r"(?<=[。！？；!?;])", block) if part.strip()]
    if len(sentences) <= 1:
        sentences = [line.strip() for line in block.splitlines() if line.strip()]
    if len(sentences) <= 1:
        width = max(200, int(target_tokens / 0.68))
        return [block[index : index + width] for index in range(0, len(block), width)]
    return _pack_blocks(sentences, target_tokens)


def _pack_blocks(blocks: list[str], target_tokens: int) -> list[str]:
    packed: list[str] = []
    current: list[str] = []
    for block in blocks:
        pieces = _split_oversized_block(block, target_tokens) if estimate_tokens(block) > target_tokens else [block]
        for piece in pieces:
            candidate = "\n\n".join([*current, piece])
            if current and estimate_tokens(candidate) > target_tokens:
                packed.append("\n\n".join(current))
                current = [piece]
            else:
                current.append(piece)
    if current:
        packed.append("\n\n".join(current))
    return packed


def fallback_semantic_split(text: str, target_tokens: int) -> list[str]:
    """Deterministic last-resort split used only when the semantic model is unavailable."""
    return _pack_blocks(_paragraph_blocks(text), target_tokens)


class AdaptiveMarkdownChunker:
    def __init__(
        self,
        target_tokens: int = 1200,
        semantic_splitter: SemanticSplitter | None = None,
        defer_semantic: bool = False,
    ) -> None:
        if target_tokens < 200:
            raise ValueError("target_tokens must be at least 200")
        self.target_tokens = target_tokens
        self.semantic_splitter = semantic_splitter
        self.defer_semantic = defer_semantic

    def split(self, markdown: str) -> list[DocumentChunk]:
        normalized = normalize_markdown(markdown)
        root = parse_heading_tree(normalized)
        all_sections = list(_walk(root))
        base_level = 3 if any(section.level == 3 for section in all_sections) else 2
        if not any(section.level == base_level for section in all_sections):
            base_level = 1 if any(section.level == 1 for section in all_sections) else 0

        candidates = [section for section in all_sections if section.level == base_level]
        chunks: list[tuple[MarkdownSection, str, str]] = []

        root_text = root.direct_text(include_heading=False)
        if root_text:
            chunks.extend(self._split_text(root, root_text, "root_fallback"))

        # Preserve meaningful parent introductions that are not part of a chosen
        # H3/H2 subtree. A complete short introduction is not treated as noise.
        for section in all_sections:
            if section.level >= base_level:
                continue
            direct = section.direct_text()
            body = "\n".join(line for _, line in section.body_lines).strip()
            if body:
                chunks.extend(self._split_text(section, direct, "parent_intro"))

        for section in candidates:
            chunks.extend(self._split_section(section))

        if not chunks:
            chunks.extend(self._split_text(root, normalized.strip(), "document_fallback"))

        result: list[DocumentChunk] = []
        seen_hashes: set[str] = set()
        for section, content, strategy in chunks:
            cleaned = content.strip()
            if not cleaned:
                continue
            content_sha = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
            if content_sha in seen_hashes:
                continue
            seen_hashes.add(content_sha)
            token_count = estimate_tokens(cleaned)
            quality_score, flags = self._quality(cleaned, token_count, bool(section.title))
            stable_material = "\x1f".join([*section.heading_path, content_sha])
            stable_key = hashlib.sha256(stable_material.encode("utf-8")).hexdigest()
            result.append(
                DocumentChunk(
                    stable_key=stable_key,
                    ordinal=len(result),
                    start_line=section.start_line,
                    end_line=section.end_line,
                    heading_path=section.heading_path,
                    heading_level=section.level or None,
                    content=cleaned,
                    content_sha256=content_sha,
                    token_count=token_count,
                    quality_score=quality_score,
                    quality_flags=flags,
                    split_strategy=strategy,
                )
            )
        return result

    def _split_section(self, section: MarkdownSection) -> list[tuple[MarkdownSection, str, str]]:
        rendered = section.render()
        if estimate_tokens(rendered) <= self.target_tokens:
            return [(section, rendered, f"h{section.level}_complete")]

        if section.level < 5 and section.children:
            chunks: list[tuple[MarkdownSection, str, str]] = []
            direct = section.direct_text()
            body = "\n".join(line for _, line in section.body_lines).strip()
            if body:
                chunks.extend(self._split_text(section, direct, f"h{section.level}_intro"))
            for child in section.children:
                chunks.extend(self._split_section(child))
            return chunks

        return self._split_text(section, rendered, "semantic_llm" if self.semantic_splitter else "semantic_fallback")

    def _split_text(self, section: MarkdownSection, text: str, strategy: str) -> list[tuple[MarkdownSection, str, str]]:
        if estimate_tokens(text) <= self.target_tokens:
            return [(section, text, strategy)]
        if self.defer_semantic and self.semantic_splitter is None:
            return [(section, text, "semantic_pending")]
        pieces: list[str] = []
        if self.semantic_splitter:
            pieces = [piece.strip() for piece in self.semantic_splitter(text, self.target_tokens) if piece.strip()]
        if not pieces or any(estimate_tokens(piece) > self.target_tokens * 1.2 for piece in pieces):
            pieces = fallback_semantic_split(text, self.target_tokens)
            strategy = "semantic_fallback"
        return [(section, piece, strategy) for piece in pieces]

    @staticmethod
    def _quality(content: str, token_count: int, has_heading: bool) -> tuple[float, list[str]]:
        flags: list[str] = []
        score = 1.0
        body_lines = [line for line in content.splitlines() if line.strip() and not line.startswith("#")]
        if not body_lines:
            flags.append("heading_only")
            score -= 0.65
        if token_count < 18 and not has_heading:
            flags.append("short_fragment")
            score -= 0.45
        elif token_count < 40 and has_heading and body_lines:
            flags.append("short_but_complete")
            score -= 0.05
        if content.count("|") >= 6 and len(body_lines) >= 2:
            flags.append("contains_table")
        if re.search(r"(?:^|\n)\s*(?:问|答|Q|A)[：:]", content, flags=re.IGNORECASE):
            flags.append("qa_style")
        return max(0.0, round(score, 3)), flags
