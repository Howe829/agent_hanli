from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parent
RESOURCES_ROOT = REPO_ROOT / "resources"
VAULT_ROOT = REPO_ROOT / "fanren-obsidian-vault"
PROGRESS_MD_PATH = VAULT_ROOT / "progress.md"
INDEX_MD_PATH = VAULT_ROOT / "index.md"
LOG_MD_PATH = VAULT_ROOT / "log.md"
HOME_MD_PATH = VAULT_ROOT / "Home.md"
CHAPTER_DIR = VAULT_ROOT / "08-章节"
RELATION_DIR = VAULT_ROOT / "09-关系"

SOURCE_FILE_RE = re.compile(r"^(?P<index>\d{4})(?P<chapter_mark>第.+?章)(?: (?P<title>.+))?$")
PROGRESS_ROW_RE = re.compile(
    r"^\|\s*第(?P<label>\d+)章\s*\|\s*`(?P<source>[^`]+)`\s*\|\s*(?P<chapter_page>[^|]+)\|\s*(?P<relation_page>[^|]+)\|\s*(?P<status>[^|]+)\|$"
)
LOG_RANGE_RE = re.compile(r"`[^`]*?(?P<start>\d{4})[^`]*`\s*~\s*`[^`]*?(?P<end>\d{4})[^`]*`")
LOG_CHAPTER_RANGE_RE = re.compile(r"第(?P<start>\d+)-(?P<end>\d+)章")


@dataclass(frozen=True)
class SourceChapter:
    chapter_number: int
    volume_name: str
    volume_prefix: str
    source_path: Path
    chapter_mark: str
    chapter_title: str | None

    @property
    def chapter_label(self) -> str:
        return f"第{self.chapter_number:02d}章" if self.chapter_number < 100 else f"第{self.chapter_number}章"

    @property
    def display_name(self) -> str:
        if self.chapter_title:
            return f"{self.volume_prefix}{self.chapter_mark} {self.chapter_title}"
        return f"{self.volume_prefix}{self.chapter_mark}"

    @property
    def source_rel(self) -> str:
        return repo_rel(self.source_path)


@dataclass(frozen=True)
class ProgressRow:
    chapter_label: str
    source_name: str
    status_label: str
    chapter_page_label: str
    relation_page_label: str

    @property
    def is_complete(self) -> bool:
        return self.status_label == "已完成"


@dataclass(frozen=True)
class ChapterStatus:
    chapter: SourceChapter
    chapter_page_exists: bool
    relation_page_exists: bool
    log_marked_complete: bool = False

    @property
    def is_complete(self) -> bool:
        return self.log_marked_complete or (self.chapter_page_exists and self.relation_page_exists)

    @property
    def status_label(self) -> str:
        if self.is_complete:
            return "已完成"
        if self.chapter_page_exists or self.relation_page_exists:
            return "部分完成"
        return "未开始"


def repo_rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def parse_source_chapter(path: Path) -> SourceChapter:
    match = SOURCE_FILE_RE.match(path.stem)
    if not match:
        raise ValueError(f"Unrecognized chapter source name: {path.name}")

    return SourceChapter(
        chapter_number=int(match.group("index")),
        volume_name=path.parent.name,
        volume_prefix=path.parent.name.split(" ", 1)[0],
        source_path=path,
        chapter_mark=match.group("chapter_mark"),
        chapter_title=match.group("title"),
    )


def discover_all_source_chapters(resources_root: Path = RESOURCES_ROOT) -> list[SourceChapter]:
    chapters: list[SourceChapter] = []
    for source_path in resources_root.glob("*/*.txt"):
        try:
            chapter = parse_source_chapter(source_path)
        except ValueError:
            continue
        chapters.append(chapter)
    chapters.sort(key=lambda item: item.chapter_number)
    return chapters


def parse_progress_rows(path: Path = PROGRESS_MD_PATH) -> list[ProgressRow]:
    if not path.exists():
        return []

    rows: list[ProgressRow] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = PROGRESS_ROW_RE.match(line.strip())
        if not match:
            continue

        rows.append(
            ProgressRow(
                chapter_label=f"第{match.group('label')}章",
                source_name=match.group("source"),
                chapter_page_label=match.group("chapter_page").strip(),
                relation_page_label=match.group("relation_page").strip(),
                status_label=match.group("status").strip(),
            )
        )
    return rows


def parse_logged_completed_chapter_numbers(path: Path = LOG_MD_PATH) -> set[int]:
    if not path.exists():
        return set()

    completed: set[int] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = LOG_RANGE_RE.search(line)
        if match:
            start = int(match.group("start"))
            end = int(match.group("end"))
            completed.update(range(start, end + 1))

        for chapter_match in LOG_CHAPTER_RANGE_RE.finditer(line):
            start = int(chapter_match.group("start"))
            end = int(chapter_match.group("end"))
            if start <= end:
                completed.update(range(start, end + 1))
    return completed


def _chapter_page_exists(chapter: SourceChapter) -> bool:
    candidate_names = [
        f"{chapter.volume_prefix}{chapter.chapter_mark}",
        f"{chapter.volume_prefix}{chapter.chapter_label}",
    ]
    if chapter.chapter_title:
        candidate_names = [
            f"{name} {chapter.chapter_title}" for name in candidate_names
        ] + candidate_names

    for name in candidate_names:
        if (CHAPTER_DIR / f"{name}.md").exists():
            return True

    patterns = [
        f"{chapter.volume_prefix}{chapter.chapter_mark}*.md",
        f"{chapter.volume_prefix}{chapter.chapter_label}*.md",
    ]
    return any(CHAPTER_DIR.glob(patterns[0])) or any(CHAPTER_DIR.glob(patterns[1]))


def _relation_page_exists(chapter: SourceChapter, batch: list[SourceChapter]) -> bool:
    if any(RELATION_DIR.glob(f"{chapter.volume_prefix}{chapter.chapter_mark}*关系总览.md")):
        return True

    if not batch:
        return False

    batch_start = batch[0]
    batch_end = batch[-1]
    if batch_start.volume_name != batch_end.volume_name:
        return False

    range_path = RELATION_DIR / (
        f"{chapter.volume_prefix}{batch_start.chapter_mark}至{batch_end.chapter_mark}关系总览.md"
    )
    return range_path.exists()


def build_batch_map(chapters: list[SourceChapter], batch_size: int = 10) -> dict[int, list[SourceChapter]]:
    batch_map: dict[int, list[SourceChapter]] = {}
    cursor = 0
    while cursor < len(chapters):
        start = cursor
        end = min(start + batch_size, len(chapters))
        while end < len(chapters) and chapters[end - 1].volume_name != chapters[start].volume_name:
            end -= 1
        batch = chapters[start:end]
        if not batch:
            batch = [chapters[cursor]]
            end = cursor + 1
        for item in batch:
            batch_map[item.chapter_number] = batch
        cursor = end
    return batch_map


def compute_chapter_statuses(chapters: Iterable[SourceChapter], batch_size: int = 10) -> list[ChapterStatus]:
    chapter_list = list(chapters)
    batch_map = build_batch_map(chapter_list, batch_size=batch_size)
    logged_complete = parse_logged_completed_chapter_numbers()
    results: list[ChapterStatus] = []
    for chapter in chapter_list:
        batch = batch_map.get(chapter.chapter_number, [])
        results.append(
            ChapterStatus(
                chapter=chapter,
                chapter_page_exists=_chapter_page_exists(chapter),
                relation_page_exists=_relation_page_exists(chapter, batch),
                log_marked_complete=chapter.chapter_number in logged_complete,
            )
        )
    return results


def infer_tracked_chapters(
    all_chapters: list[SourceChapter],
    *,
    batch_size: int = 10,
) -> list[ChapterStatus]:
    if not all_chapters:
        return []

    statuses = compute_chapter_statuses(all_chapters, batch_size=batch_size)
    touched = [
        status
        for status in statuses
        if status.chapter_page_exists or status.relation_page_exists or status.log_marked_complete
    ]
    if not touched:
        return []

    frontier = max(status.chapter.chapter_number for status in touched)
    return [status for status in statuses if status.chapter.chapter_number <= frontier]


def select_next_batch(
    all_chapters: list[SourceChapter],
    *,
    batch_size: int = 10,
) -> list[SourceChapter]:
    if not all_chapters:
        return []

    statuses = compute_chapter_statuses(all_chapters, batch_size=batch_size)
    touched = [
        status
        for status in statuses
        if status.chapter_page_exists or status.relation_page_exists or status.log_marked_complete
    ]
    frontier = max((status.chapter.chapter_number for status in touched), default=0)

    start_chapter_number = None
    for status in statuses:
        if status.chapter.chapter_number > frontier:
            break
        if not status.is_complete:
            start_chapter_number = status.chapter.chapter_number
            break

    if start_chapter_number is None:
        if frontier == 0:
            start_chapter_number = all_chapters[0].chapter_number
        else:
            start_chapter_number = frontier + 1

    start_idx = next(
        (idx for idx, chapter in enumerate(all_chapters) if chapter.chapter_number >= start_chapter_number),
        len(all_chapters),
    )
    if start_idx >= len(all_chapters):
        return []

    volume_name = all_chapters[start_idx].volume_name
    end_idx = start_idx
    while end_idx < len(all_chapters) and end_idx - start_idx < batch_size:
        if all_chapters[end_idx].volume_name != volume_name:
            break
        end_idx += 1
    return all_chapters[start_idx:end_idx]


def build_scope_label(chapters: list[SourceChapter]) -> str:
    if not chapters:
        return "当前未纳入任何章节"
    first = chapters[0]
    last = chapters[-1]
    return f"当前纳入：第{first.chapter_number}章至第{last.chapter_number}章"


def render_progress_markdown(
    chapters: Iterable[SourceChapter],
    *,
    generated_at: datetime | None = None,
    batch_size: int = 10,
) -> str:
    chapter_list = list(chapters)
    generated_at = generated_at or datetime.now()
    statuses = compute_chapter_statuses(chapter_list, batch_size=batch_size)

    completed = [item for item in statuses if item.is_complete]
    partial = [item for item in statuses if not item.is_complete and (item.chapter_page_exists or item.relation_page_exists)]
    pending = [item for item in statuses if not item.chapter_page_exists and not item.relation_page_exists]

    lines = [
        "# 章节整理进度",
        "",
        f"- 范围：{build_scope_label(chapter_list)}",
        f"- 生成时间：{generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 目标章节数：{len(chapter_list)}",
        f"- 已完成：{len(completed)}",
        f"- 部分完成：{len(partial)}",
        f"- 未开始：{len(pending)}",
        "",
        "## 进度表",
        "",
        "| 章次 | 原文章节 | 章节页 | 关系页 | 状态 |",
        "| --- | --- | --- | --- | --- |",
    ]

    for item in statuses:
        chapter_page = "已建" if item.chapter_page_exists else "未建"
        relation_page = "已建" if item.relation_page_exists else "未建"
        lines.append(
            f"| {item.chapter.chapter_label} | `{item.chapter.source_path.name}` | {chapter_page} | {relation_page} | {item.status_label} |"
        )

    lines.extend(["", "## 待整理章节", ""])

    if partial or pending:
        for item in [*partial, *pending]:
            lines.append(f"- {item.chapter.display_name}：{item.status_label}")
    else:
        lines.append(f"- 无，当前已纳入的 {len(chapter_list)} 章均已整理完成")

    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- `已完成`：章节页与关系页均已存在",
            "- `部分完成`：章节页或关系页存在其一，但尚未齐全",
            "- `未开始`：章节页与关系页均不存在",
            "",
            "- 本文件由批量整理脚本自动刷新",
        ]
    )
    return "\n".join(lines) + "\n"


def write_progress_markdown(
    chapters: Iterable[SourceChapter],
    *,
    path: Path = PROGRESS_MD_PATH,
    batch_size: int = 10,
) -> Path:
    content = render_progress_markdown(chapters, batch_size=batch_size)
    path.write_text(content, encoding="utf-8")
    return path
