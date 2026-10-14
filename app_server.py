"""Local SQLite web server for Seky Barcode APP."""
from __future__ import annotations

import json
import mimetypes
import math
import os
import secrets
import socket
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
import webbrowser


ROOT = Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", ROOT))
WEB_FILE = Path(os.environ.get("SEKY_APP_WEB_FILE", RESOURCE_DIR / "index.html"))
DATA_DIR = Path(os.environ.get("SEKY_APP_DATA_DIR", ROOT))
DB_FILE = DATA_DIR / "SekyBarcode.sqlite3"
BACKUP_DIR = DATA_DIR / "database_backups"
SEED_DB_FILE = Path(os.environ.get("SEKY_APP_SEED_DB", RESOURCE_DIR / "initial-database.sqlite3"))
LEGACY_DB_FILE = Path(os.environ.get("SEKY_APP_LEGACY_DB", ROOT / "SekyBarcode.sqlite3"))
PORT = int(os.environ.get("SEKY_APP_PORT", "8765"))
HOST = os.environ.get("SEKY_APP_HOST", "0.0.0.0")
DELETE_PASSWORD = "123"
BACKUP_PASSWORD = "Admin"
MAX_BODY = 15 * 1024 * 1024
SHUTDOWN_TOKEN = os.environ.get("SEKY_APP_SHUTDOWN_TOKEN", "")

FIELDS = (
    "id", "company", "product", "code", "barcode", "price", "quantity",
    "category", "expiry", "width", "height", "showCompany", "showCategory", "createdAt"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_code(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def normalize_product(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def connect_db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 20000")
    return conn


def initialize_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    migrate_database_once()
    with connect_db() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                company TEXT NOT NULL DEFAULT '',
                product TEXT NOT NULL,
                product_key TEXT NOT NULL UNIQUE,
                code TEXT NOT NULL,
                code_key TEXT NOT NULL UNIQUE,
                barcode TEXT NOT NULL,
                price REAL NOT NULL CHECK (price >= 0),
                quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 500),
                category TEXT NOT NULL DEFAULT '',
                expiry TEXT NOT NULL DEFAULT '',
                width REAL NOT NULL DEFAULT 55,
                height REAL NOT NULL DEFAULT 40,
                showCompany INTEGER NOT NULL DEFAULT 1,
                showCategory INTEGER NOT NULL DEFAULT 1,
                createdAt TEXT NOT NULL
            )
        """)


def migrate_database_once() -> None:
    """Seed the writable database once, using SQLite backup so committed WAL data is included."""
    if DB_FILE.exists():
        return
    candidates = (LEGACY_DB_FILE, SEED_DB_FILE, ROOT / "SekyBarcode.sqlite3")
    source_path = next((path for path in candidates if path.exists() and path.resolve() != DB_FILE.resolve()), None)
    if source_path is None:
        return
    if source_path != SEED_DB_FILE:
        try:
            with socket.create_connection(("127.0.0.1", 8765), timeout=0.2):
                raise RuntimeError("Close the old Seky Barcode app before migrating its database.")
        except OSError:
            pass
    temporary = DB_FILE.with_name(DB_FILE.name + ".migrating")
    if temporary.exists():
        temporary.unlink()
    source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
    destination = sqlite3.connect(temporary)
    try:
        source.backup(destination)
        destination.execute("PRAGMA journal_mode = DELETE")
        destination.commit()
    finally:
        destination.close()
        source.close()
    os.replace(temporary, DB_FILE)


def row_to_item(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "company": row["company"], "product": row["product"],
        "code": row["code"], "barcode": row["barcode"], "price": row["price"],
        "quantity": row["quantity"], "category": row["category"], "expiry": row["expiry"],
        "width": row["width"], "height": row["height"],
        "showCompany": bool(row["showCompany"]), "showCategory": bool(row["showCategory"]),
        "createdAt": row["createdAt"],
    }


def list_items() -> list[dict]:
    with connect_db() as conn:
        return [row_to_item(row) for row in conn.execute("SELECT * FROM items ORDER BY rowid")]


def validate_item(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Each item must be an object.")
    product = " ".join(str(raw.get("product", "")).split())
    code = " ".join(str(raw.get("code", "")).split())
    if not product:
        raise ValueError("Product name is required.")
    if not code:
        raise ValueError("Item code is required.")
    if len(product) > 300 or len(code) > 120:
        raise ValueError("Product name or item code is too long.")
    try:
        price = float(raw.get("price", 0))
        quantity = int(raw.get("quantity", 1))
        width = float(raw.get("width", 55))
        height = float(raw.get("height", 40))
    except (TypeError, ValueError):
        raise ValueError("Price, quantity, and label size must be valid numbers.")
    if not math.isfinite(price) or price < 0:
        raise ValueError("Price must be a valid non-negative number.")
    if quantity < 1 or quantity > 500:
        raise ValueError("Quantity must be between 1 and 500.")
    if not math.isfinite(width) or not 20 <= width <= 100:
        raise ValueError("Label width must be between 20 and 100 mm.")
    if not math.isfinite(height) or not 15 <= height <= 100:
        raise ValueError("Label height must be between 15 and 100 mm.")
    item_id = str(raw.get("id") or uuid.uuid4())
    created = str(raw.get("createdAt") or now_iso())
    return {
        "id": item_id, "company": str(raw.get("company") or "").strip(),
        "product": product, "product_key": normalize_product(product),
        "code": code, "code_key": normalize_code(code), "barcode": code,
        "price": price, "quantity": quantity,
        "category": str(raw.get("category") or "").strip(),
        "expiry": str(raw.get("expiry") or ""), "width": width, "height": height,
        "showCompany": int(bool(raw.get("showCompany", True))),
        "showCategory": int(bool(raw.get("showCategory", True))), "createdAt": created,
    }


def insert_values(item: dict) -> tuple:
    return tuple(item[name] for name in FIELDS[:3]) + (
        item["product_key"], item["code"], item["code_key"], item["barcode"], item["price"],
        item["quantity"], item["category"], item["expiry"], item["width"], item["height"],
        item["showCompany"], item["showCategory"], item["createdAt"]
    )


INSERT_SQL = """INSERT INTO items
    (id, company, product, product_key, code, code_key, barcode, price, quantity,
     category, expiry, width, height, showCompany, showCategory, createdAt)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""


def make_snapshot() -> Path | None:
    BACKUP_DIR.mkdir(exist_ok=True)
    with connect_db() as source:
        if source.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0:
            return None
        name = datetime.now().strftime("before-change-%Y%m%d-%H%M%S-%f.sqlite3")
        target = BACKUP_DIR / name
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    snapshots = sorted(BACKUP_DIR.glob("before-change-*.sqlite3"), key=lambda path: path.stat().st_mtime, reverse=True)
    for old in snapshots[30:]:
        old.unlink(missing_ok=True)
    return target


def lan_addresses() -> list[str]:
    found = set()
    try:
        for entry in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = entry[4][0]
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                found.add(ip)
    except OSError:
        pass
    return sorted(found)


class Handler(BaseHTTPRequestHandler):
    server_version = "SekyBarcode/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Invalid request size.")
        if length <= 0 or length > MAX_BODY:
            raise ValueError("Request is empty or too large.")
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("Request must contain valid JSON.")
        if not isinstance(value, dict):
            raise ValueError("Request must contain a JSON object.")
        return value

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/items":
            self.send_json(200, {"items": list_items()})
        elif path == "/api/server-info":
            self.send_json(200, {"port": self.server.server_port, "addresses": lan_addresses()})
        elif path in ("/", "/index.html"):
            try:
                body = WEB_FILE.read_bytes()
            except OSError:
                self.send_error(500, "Web app file is missing.")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif path.startswith("/assets/vendor/"):
            asset_root = (RESOURCE_DIR / "assets" / "vendor").resolve()
            asset_path = (asset_root / path.removeprefix("/assets/vendor/")).resolve()
            if not asset_path.is_relative_to(asset_root) or not asset_path.is_file():
                self.send_error(404)
                return
            body = asset_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/shutdown":
            try:
                body = self.read_json()
            except ValueError as error:
                self.send_json(400, {"error": str(error)})
                return
            if not SHUTDOWN_TOKEN or not secrets.compare_digest(str(body.get("token", "")), SHUTDOWN_TOKEN):
                self.send_json(403, {"error": "Invalid shutdown token."})
                return
            self.send_json(200, {"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        try:
            body = self.read_json()
            if path == "/api/backup":
                if body.get("password") != BACKUP_PASSWORD:
                    self.send_json(403, {"error": "Incorrect password."})
                    return
                self.send_json(200, {"format": "seky-barcode-items", "version": 1, "exportedAt": now_iso(), "items": list_items()})
                return
            if path == "/api/items":
                item = validate_item(body)
                with connect_db() as conn:
                    try:
                        conn.execute("BEGIN IMMEDIATE")
                        conn.execute(INSERT_SQL, insert_values(item))
                        conn.commit()
                    except sqlite3.IntegrityError:
                        conn.rollback()
                        self.send_duplicate_error(item)
                        return
                item.pop("product_key", None)
                item.pop("code_key", None)
                item["showCompany"] = bool(item["showCompany"])
                item["showCategory"] = bool(item["showCategory"])
                self.send_json(201, {"item": item})
                return
            if path == "/api/restore":
                if body.get("password") != BACKUP_PASSWORD:
                    self.send_json(403, {"error": "Incorrect password."})
                    return
                raw_items = body.get("items")
                if not isinstance(raw_items, list):
                    self.send_json(400, {"code": "invalid_backup", "error": "Backup does not contain an item list."})
                    return
                prepared = [validate_item(raw) for raw in raw_items]
                product_keys, code_keys, ids = set(), set(), set()
                for item in prepared:
                    if item["product_key"] in product_keys:
                        self.send_json(409, {"code": "duplicate_product", "error": "Backup repeats a product name."})
                        return
                    if item["code_key"] in code_keys:
                        self.send_json(409, {"code": "duplicate_code", "error": "Backup repeats an item code."})
                        return
                    if item["id"] in ids:
                        item["id"] = str(uuid.uuid4())
                    product_keys.add(item["product_key"])
                    code_keys.add(item["code_key"])
                    ids.add(item["id"])
                make_snapshot()
                with connect_db() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("DELETE FROM items")
                    for item in prepared:
                        conn.execute(INSERT_SQL, insert_values(item))
                    conn.commit()
                self.send_json(200, {"items": list_items()})
                return
            self.send_error(404)
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except sqlite3.Error as error:
            print("Database error:", error)
            self.send_json(500, {"error": "The database could not complete this request."})

    def send_duplicate_error(self, item: dict) -> None:
        with connect_db() as conn:
            product = conn.execute("SELECT 1 FROM items WHERE product_key = ?", (item["product_key"],)).fetchone()
            code = conn.execute("SELECT 1 FROM items WHERE code_key = ?", (item["code_key"],)).fetchone()
        if code:
            self.send_json(409, {"code": "duplicate_code", "error": "This item code already exists."})
        elif product:
            self.send_json(409, {"code": "duplicate_product", "error": "This product name already exists."})
        else:
            self.send_json(409, {"error": "The item could not be saved because a unique value already exists."})

    def do_DELETE(self) -> None:
        path = urlsplit(self.path).path
        try:
            body = self.read_json()
            if body.get("password") != DELETE_PASSWORD:
                self.send_json(403, {"error": "Incorrect password."})
                return
            if path == "/api/items":
                make_snapshot()
                with connect_db() as conn:
                    conn.execute("DELETE FROM items")
                self.send_json(200, {"ok": True})
                return
            prefix = "/api/items/"
            if path.startswith(prefix):
                item_id = unquote(path[len(prefix):])
                make_snapshot()
                with connect_db() as conn:
                    cursor = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
                    if cursor.rowcount == 0:
                        self.send_json(404, {"error": "Item was not found."})
                        return
                self.send_json(200, {"ok": True})
                return
            self.send_error(404)
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except sqlite3.Error as error:
            print("Database error:", error)
            self.send_json(500, {"error": "The database could not complete this request."})


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> None:
    initialize_db()
    try:
        server = Server((HOST, PORT), Handler)
    except OSError as error:
        print(f"Could not start the app on port {PORT}: {error}")
        print("Close another copy of the app or set SEKY_APP_PORT to a free port.")
        input("Press Enter to close…")
        return
    print("Seky Barcode database app is running.")
    print(f"On this computer: http://localhost:{PORT}/")
    addresses = lan_addresses() if HOST == "0.0.0.0" else []
    if addresses:
        print("On the same Wi-Fi/LAN, use one of these addresses on another device:")
        for address in addresses:
            print(f"  http://{address}:{PORT}/")
    else:
        print("No local network address was found yet. Connect this computer to Wi-Fi and restart the app.")
    print(f"Database file: {DB_FILE}")
    if os.environ.get("SEKY_APP_NO_BROWSER") != "1":
        print("Keep this window open while using the app. Press Ctrl+C to stop it.")
        threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}/")).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nStopping the app…")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
