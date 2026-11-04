"""历史记录导入导出。导出文件里只有内容本身，不带本机路径。"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

from core.models import KIND_IMAGE, ClipItem
from core.repository import Repository

FORMAT_NAME = "ClipNest"
FORMAT_VERSION = 1


class ExportError(Exception):
    """格式不对或者文件读不了，调用方只需要知道失败原因。"""


def _encode_item(item: ClipItem, include_images: bool) -> dict[str, object]:
    data: dict[str, object] = {
        "kind": item.kind,
        "hash": item.content_hash,
        "preview": item.preview,
        "text": item.text,
        "files": item.files,
        "width": item.width,
        "height": item.height,
        "source": item.source_app,
        "size": item.size,
        "created_at": item.created_at,
        "pinned": item.pinned,
        "use_count": item.use_count,
    }
    # 图片单独转 base64，导出文件可以搬到别的机器上去
    if include_images and item.kind == KIND_IMAGE and item.image_path:
        path = Path(item.image_path)
        if path.exists():
            data["image"] = base64.b64encode(path.read_bytes()).decode("ascii")
    return data


def _decode_item(data: dict[str, object]) -> ClipItem:
    kind = str(data.get("kind") or "")
    if kind not in ("text", "image", "files"):
        raise ExportError(f"未知条目类型：{kind}")

    files = data.get("files") or []
    return ClipItem(
        kind=kind,
        content_hash=str(data.get("hash") or ""),
        preview=str(data.get("preview") or ""),
        text=str(data.get("text") or ""),
        files=[str(p) for p in files],
        width=int(data.get("width") or 0),
        height=int(data.get("height") or 0),
        source_app=str(data.get("source") or ""),
        size=int(data.get("size") or 0),
        created_at=float(data.get("created_at") or time.time()),
        pinned=bool(data.get("pinned")),
        use_count=int(data.get("use_count") or 0),
    )


def export_to_file(
    repo: Repository, target: Path, include_images: bool = True, limit: int = 0
) -> int:
    items = repo.all_items(limit)
    payload = {
        "app": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "exported_at": time.time(),
        "count": len(items),
        "items": [_encode_item(item, include_images) for item in items],
    }
    try:
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except OSError as exc:
        raise ExportError(f"写入失败：{exc}") from exc
    return len(items)


def _read_payload(source: Path) -> list[dict[str, object]]:
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ExportError(f"读取失败：{exc}") from exc
    except ValueError as exc:
        raise ExportError("文件不是有效的 JSON") from exc

    if not isinstance(raw, dict) or raw.get("app") != FORMAT_NAME:
        raise ExportError("不是本程序导出的文件")
    if int(raw.get("version") or 0) > FORMAT_VERSION:
        raise ExportError("导出文件版本比当前程序新，请升级后再导入")

    items = raw.get("items")
    if not isinstance(items, list):
        raise ExportError("文件里没有条目列表")
    return [entry for entry in items if isinstance(entry, dict)]


def import_from_file(repo: Repository, source: Path) -> tuple[int, int]:
    """返回（新增条数, 跳过条数）。图片会重新落到本机缓存目录。"""
    from app import paths  # 延迟导入，避免 core 依赖 app 的顶层

    added = 0
    skipped = 0
    for entry in _read_payload(source):
        item = _decode_item(entry)
        if not item.content_hash:
            item.content_hash = f"import-{item.created_at:.6f}-{added + skipped}"

        encoded = entry.get("image")
        if item.kind == KIND_IMAGE and isinstance(encoded, str) and encoded:
            try:
                blob = base64.b64decode(encoded.encode("ascii"))
            except ValueError:
                blob = b""
            if blob:
                item.image_path = str(paths.save_blob(blob, item.content_hash))

        row_id = repo.insert_if_absent(item)
        if row_id:
            added += 1
        else:
            skipped += 1
    return added, skipped
