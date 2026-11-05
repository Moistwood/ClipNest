"""SQLite 存储层。没有 ORM，语句都写在这里，便于后面换实现。"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from core.models import ClipItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT    NOT NULL,
    content_hash  TEXT    NOT NULL UNIQUE,
    preview       TEXT    NOT NULL DEFAULT '',
    text_body     TEXT    NOT NULL DEFAULT '',
    html_body     TEXT    NOT NULL DEFAULT '',
    rtf_body      TEXT    NOT NULL DEFAULT '',
    image_path    TEXT    NOT NULL DEFAULT '',
    width         INTEGER NOT NULL DEFAULT 0,
    height        INTEGER NOT NULL DEFAULT 0,
    files_json    TEXT    NOT NULL DEFAULT '',
    source_app    TEXT    NOT NULL DEFAULT '',
    size          INTEGER NOT NULL DEFAULT 0,
    pinned        INTEGER NOT NULL DEFAULT 0,
    use_count     INTEGER NOT NULL DEFAULT 0,
    created_at    REAL    NOT NULL,
    last_used_at  REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_recent ON items(pinned DESC, last_used_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_kind   ON items(kind, last_used_at DESC);
"""

UPSERT = """
INSERT INTO items (kind, content_hash, preview, text_body, html_body, rtf_body,
                   image_path, width, height,
                   files_json, source_app, size, pinned, use_count, created_at, last_used_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
ON CONFLICT(content_hash) DO UPDATE SET
    last_used_at = excluded.last_used_at,
    use_count    = use_count + 1,
    preview      = excluded.preview
RETURNING id
"""

INSERT_IF_ABSENT = """
INSERT INTO items (kind, content_hash, preview, text_body, html_body, rtf_body,
                   image_path, width, height,
                   files_json, source_app, size, pinned, use_count, created_at, last_used_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(content_hash) DO NOTHING
RETURNING id
"""

# trigram 把文本按三个字符滑窗切，中文不需要额外分词器。
# 但它对少于三个字符的查询永远返回 0 条，所以短词必须走 LIKE。
# 老版本 SQLite 没有 trigram 时整段跳过，程序退化成纯 LIKE，一样能用。
FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(body, tokenize='trigram');

CREATE TRIGGER IF NOT EXISTS items_fts_insert AFTER INSERT ON items BEGIN
    INSERT INTO items_fts(rowid, body)
    VALUES (new.id, new.text_body || char(10) || new.preview);
END;

CREATE TRIGGER IF NOT EXISTS items_fts_update AFTER UPDATE ON items BEGIN
    DELETE FROM items_fts WHERE rowid = old.id;
    INSERT INTO items_fts(rowid, body)
    VALUES (new.id, new.text_body || char(10) || new.preview);
END;

CREATE TRIGGER IF NOT EXISTS items_fts_delete AFTER DELETE ON items BEGIN
    DELETE FROM items_fts WHERE rowid = old.id;
END;
"""

FTS_BACKFILL = """
INSERT INTO items_fts(rowid, body)
SELECT i.id, i.text_body || char(10) || i.preview
FROM items i
WHERE i.id NOT IN (SELECT rowid FROM items_fts)
"""


class Repository:
    def __init__(self, db_path: Path, setup_index: bool = True) -> None:
        """写入线程传 setup_index=False，索引结构由主线程那一个连接建立。

        触发器是数据库对象，不属于某个连接，工作线程往 items 写的
        时候照样会同步到全文索引，没必要两个连接抢着建表。
        """
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        # 写入线程和主线程偶尔会同时抢写锁，等一下而不是直接抛 busy
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()
        self._fts_ready = self._setup_fts() if setup_index else False

    def _migrate(self) -> None:
        """给老数据库补列。CREATE TABLE IF NOT EXISTS 不会改已经存在的表结构。"""
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(items)")}
        for column in ("html_body", "rtf_body"):
            if column not in columns:
                self._conn.execute(
                    f"ALTER TABLE items ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
                )

    def _setup_fts(self) -> bool:
        try:
            self._conn.executescript(FTS_SCHEMA)
            indexed = self._conn.execute("SELECT count(*) FROM items_fts").fetchone()[0]
            total = self._conn.execute("SELECT count(*) FROM items").fetchone()[0]
            if indexed != total:
                self._conn.execute(FTS_BACKFILL)
            self._conn.commit()
            return True
        except sqlite3.Error:
            self._conn.rollback()
            return False

    def close(self) -> None:
        self._conn.close()

    def add(self, item: ClipItem) -> int:
        now = time.time()
        cursor = self._conn.execute(
            UPSERT,
            (
                item.kind,
                item.content_hash,
                item.preview,
                item.text,
                item.html,
                item.rtf,
                item.image_path,
                item.width,
                item.height,
                "\n".join(item.files),
                item.source_app,
                item.size,
                1 if item.pinned else 0,
                item.created_at or now,
                now,
            ),
        )
        row = cursor.fetchone()
        self._conn.commit()
        return int(row[0]) if row else 0

    def insert_if_absent(self, item: ClipItem) -> int:
        """导入用。已存在的哈希原样跳过，不涨 use_count。"""
        cursor = self._conn.execute(
            INSERT_IF_ABSENT,
            (
                item.kind,
                item.content_hash,
                item.preview,
                item.text,
                item.html,
                item.rtf,
                item.image_path,
                item.width,
                item.height,
                "\n".join(item.files),
                item.source_app,
                item.size,
                1 if item.pinned else 0,
                item.use_count,
                item.created_at,
                item.created_at,
            ),
        )
        row = cursor.fetchone()
        self._conn.commit()
        return int(row[0]) if row else 0

    def all_items(self, limit: int = 0) -> list[ClipItem]:
        sql = "SELECT * FROM items ORDER BY created_at"
        if limit > 0:
            sql += " LIMIT ?"
            rows = self._conn.execute(sql, (limit,))
        else:
            rows = self._conn.execute(sql)
        return [self._to_item(row) for row in rows]

    def _to_item(self, row: sqlite3.Row) -> ClipItem:
        return ClipItem(
            kind=row["kind"],
            content_hash=row["content_hash"],
            preview=row["preview"],
            text=row["text_body"],
            html=row["html_body"],
            rtf=row["rtf_body"],
            files=[p for p in row["files_json"].split("\n") if p],
            image_path=row["image_path"],
            width=row["width"],
            height=row["height"],
            source_app=row["source_app"],
            size=row["size"],
            created_at=row["created_at"],
            id=row["id"],
            pinned=bool(row["pinned"]),
            use_count=row["use_count"],
        )

    def list(self, query: str = "", kind: str = "", limit: int = 100) -> list[ClipItem]:
        term = query.strip()
        if term and self._fts_ready and len(term) >= 3:
            try:
                hits = self._search_fts(term, kind, limit)
            except sqlite3.Error:
                hits = []
            # 索引没命中时再用 LIKE 兜一次，宁可多查一次也别让用户以为没这条
            if hits:
                return hits
        return self._search_like(term, kind, limit)

    def _search_fts(self, term: str, kind: str, limit: int) -> list[ClipItem]:
        # 整串加引号当短语，输入里的 * OR - 之类不会被当成 FTS5 语法
        phrase = '"' + term.replace('"', '""') + '"'
        sql = (
            "SELECT i.* FROM items_fts JOIN items i ON i.id = items_fts.rowid "
            "WHERE items_fts MATCH ?"
        )
        params: list[object] = [phrase]
        if kind:
            sql += " AND i.kind = ?"
            params.append(kind)
        sql += " ORDER BY i.pinned DESC, i.last_used_at DESC LIMIT ?"
        params.append(limit)
        return [self._to_item(row) for row in self._conn.execute(sql, params)]

    def _search_like(self, term: str, kind: str, limit: int) -> list[ClipItem]:
        sql = "SELECT * FROM items WHERE 1=1"
        params: list[object] = []
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        if term:
            escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            sql += " AND (text_body LIKE ? ESCAPE '\\' OR preview LIKE ? ESCAPE '\\')"
            params.extend([f"%{escaped}%", f"%{escaped}%"])
        sql += " ORDER BY pinned DESC, last_used_at DESC LIMIT ?"
        params.append(limit)
        return [self._to_item(row) for row in self._conn.execute(sql, params)]

    def get(self, item_id: int) -> ClipItem | None:
        row = self._conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return self._to_item(row) if row else None

    def touch(self, item_id: int) -> None:
        self._conn.execute(
            "UPDATE items SET last_used_at = ?, use_count = use_count + 1 WHERE id = ?",
            (time.time(), item_id),
        )
        self._conn.commit()

    def toggle_pin(self, item_id: int) -> bool:
        self._conn.execute("UPDATE items SET pinned = 1 - pinned WHERE id = ?", (item_id,))
        self._conn.commit()
        row = self._conn.execute("SELECT pinned FROM items WHERE id = ?", (item_id,)).fetchone()
        return bool(row and row["pinned"])

    def delete(self, item_id: int) -> str:
        row = self._conn.execute("SELECT image_path FROM items WHERE id = ?", (item_id,)).fetchone()
        self._conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        self._conn.commit()
        return row["image_path"] if row else ""

    def clear(self, keep_pinned: bool = True) -> list[str]:
        condition = "WHERE pinned = 0" if keep_pinned else ""
        rows = self._conn.execute(f"SELECT image_path FROM items {condition}").fetchall()
        self._conn.execute(f"DELETE FROM items {condition}")
        self._conn.commit()
        return [r["image_path"] for r in rows if r["image_path"]]

    def prune(self, max_items: int, max_days: int) -> list[str]:
        doomed: set[str] = set()
        if max_days > 0:
            cutoff = time.time() - max_days * 86400
            rows = self._conn.execute(
                "SELECT image_path FROM items WHERE pinned = 0 AND last_used_at < ?", (cutoff,)
            ).fetchall()
            doomed.update(r["image_path"] for r in rows if r["image_path"])
            self._conn.execute(
                "DELETE FROM items WHERE pinned = 0 AND last_used_at < ?", (cutoff,)
            )
        if max_items > 0:
            rows = self._conn.execute(
                """SELECT image_path FROM items WHERE pinned = 0 AND id NOT IN (
                       SELECT id FROM items WHERE pinned = 0
                       ORDER BY last_used_at DESC LIMIT ?)""",
                (max_items,),
            ).fetchall()
            doomed.update(r["image_path"] for r in rows if r["image_path"])
            self._conn.execute(
                """DELETE FROM items WHERE pinned = 0 AND id NOT IN (
                       SELECT id FROM items WHERE pinned = 0
                       ORDER BY last_used_at DESC LIMIT ?)""",
                (max_items,),
            )
        self._conn.commit()
        return list(doomed)

    def count(self) -> int:
        return int(self._conn.execute("SELECT count(*) FROM items").fetchone()[0])

    def summary(self) -> dict[str, object]:
        """统计用的一次性聚合，别在循环里调用。"""
        row = self._conn.execute(
            """SELECT count(*)               AS total,
                      coalesce(sum(size), 0)  AS bytes_total,
                      coalesce(sum(use_count), 0) AS uses,
                      min(created_at)         AS first_at,
                      max(last_used_at)       AS last_at,
                      sum(pinned)             AS pinned
               FROM items"""
        ).fetchone()

        kinds = {
            r["kind"]: r["n"]
            for r in self._conn.execute(
                "SELECT kind, count(*) AS n FROM items GROUP BY kind"
            )
        }
        sources = [
            (r["source_app"], r["n"])
            for r in self._conn.execute(
                """SELECT source_app, count(*) AS n FROM items
                   WHERE source_app <> ''
                   GROUP BY source_app ORDER BY n DESC LIMIT 5"""
            )
        ]
        return {
            "total": int(row["total"] or 0),
            "bytes_total": int(row["bytes_total"] or 0),
            "uses": int(row["uses"] or 0),
            "first_at": float(row["first_at"] or 0),
            "last_at": float(row["last_at"] or 0),
            "pinned": int(row["pinned"] or 0),
            "kinds": kinds,
            "sources": sources,
        }
