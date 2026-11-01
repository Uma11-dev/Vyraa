from __future__ import annotations

import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from knowledge.ingestion_manager import KnowledgeBaseManager


class KnowledgeBaseEventHandler(FileSystemEventHandler):
    """
    Watches the knowledge_base/ directory and keeps the Chroma
    knowledge base synchronized with PDF files.
    """

    def __init__(self, manager: KnowledgeBaseManager):
        super().__init__()

        self.manager = manager

        # Prevent two ingestion operations from running simultaneously.
        self._ingestion_lock = threading.Lock()

        # Prevent duplicate watchdog events for the same file.
        self._pending: set[str] = set()

        # Protect access to _pending from multiple watchdog threads.
        self._pending_lock = threading.Lock()

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    @staticmethod
    def _is_pdf(path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def _mark_pending(self, path: Path) -> bool:
        """
        Mark a file as currently being processed.

        Returns False if the file is already being processed.
        """
        path_key = str(path.resolve())

        with self._pending_lock:
            if path_key in self._pending:
                return False

            self._pending.add(path_key)
            return True

    def _unmark_pending(self, path: Path) -> None:
        path_key = str(path.resolve())

        with self._pending_lock:
            self._pending.discard(path_key)

    def _process_pdf(self, path_string: str) -> None:
        """
        Wait until a PDF has finished copying/writing, then ingest it.
        """

        path = Path(path_string).resolve()

        if not self._is_pdf(path):
            return

        if not path.exists():
            return

        if not self._mark_pending(path):
            print(f"[WATCHER] Already processing: {path.name}")
            return

        try:
            print()
            print("=" * 70)
            print(f"[WATCHER] PDF DETECTED: {path.name}")
            print("=" * 70)

            # A PDF may trigger several filesystem events while it is
            # still being copied. Wait until its size/mtime stabilizes.
            self.manager.wait_until_stable(path)

            if not path.exists():
                print(f"[WATCHER] File disappeared: {path.name}")
                return

            # Only one ingestion operation at a time.
            with self._ingestion_lock:
                print(f"[WATCHER] Processing: {path.name}")

                self.manager.ingest_pdf(path)

            print(f"[WATCHER] Finished: {path.name}")

        except Exception as exc:
            print()
            print("=" * 70)
            print(f"[WATCHER] INGESTION FAILED: {path.name}")
            print("=" * 70)
            print(f"[WATCHER] Error: {exc}")

        finally:
            self._unmark_pending(path)

    # ---------------------------------------------------------
    # Watchdog events
    # ---------------------------------------------------------

    def on_created(self, event):
        if event.is_directory:
            return

        self._process_pdf(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return

        self._process_pdf(event.src_path)

    def on_deleted(self, event):
        if event.is_directory:
            return

        path = Path(event.src_path).resolve()

        if not self._is_pdf(path):
            return

        try:
            print()
            print("=" * 70)
            print(f"[WATCHER] PDF DELETED: {path.name}")
            print("=" * 70)

            with self._ingestion_lock:
                self.manager.delete_pdf(path)

            print(f"[WATCHER] Deletion synchronized: {path.name}")

        except Exception as exc:
            print()
            print("=" * 70)
            print(f"[WATCHER] DELETION SYNC FAILED: {path.name}")
            print("=" * 70)
            print(f"[WATCHER] Error: {exc}")


# -------------------------------------------------------------
# Watcher startup
# -------------------------------------------------------------

def start_watcher():
    """
    Start the VYRA knowledge-base watcher.

    On startup:
        1. Create knowledge_base/ if necessary.
        2. Create the ingestion manager.
        3. Scan existing PDFs.
        4. Start watching for new/modified/deleted PDFs.
    """

    project_root = Path(__file__).resolve().parents[1]

    knowledge_base = project_root / "knowledge_base"

    knowledge_base.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print("=" * 70)
    print("VYRA KNOWLEDGE BASE")
    print("=" * 70)
    print(f"Knowledge base:\n{knowledge_base}")
    print("=" * 70)

    # ---------------------------------------------------------
    # Initialize manager
    # ---------------------------------------------------------

    manager = KnowledgeBaseManager(
        knowledge_base_dir=knowledge_base,
        registry_path=knowledge_base / ".ingestion_registry.json",
    )

    # ---------------------------------------------------------
    # Initial synchronization
    # ---------------------------------------------------------

    print()
    print("[WATCHER] Performing initial knowledge-base scan...")

    manager.scan()

    print()
    print("[WATCHER] Initial scan complete.")

    # ---------------------------------------------------------
    # Start filesystem watcher
    # ---------------------------------------------------------

    handler = KnowledgeBaseEventHandler(manager)

    observer = Observer()

    observer.schedule(
        handler,
        str(knowledge_base),
        recursive=False,
    )

    observer.start()

    print()
    print("=" * 70)
    print("VYRA KNOWLEDGE BASE WATCHER RUNNING")
    print("=" * 70)
    print(f"Watching:\n{knowledge_base}")
    print()
    print("Automatic synchronization enabled.")
    print()
    print("Add PDF      → ingest")
    print("Modify PDF   → re-ingest")
    print("Delete PDF   → remove from Chroma")
    print("Duplicate    → skip")
    print("Unchanged    → skip")
    print()
    print("Press Ctrl+C to stop.")
    print("=" * 70)

    # ---------------------------------------------------------
    # Keep process alive
    # ---------------------------------------------------------

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print()
        print("[WATCHER] Shutdown requested...")

    finally:
        observer.stop()
        observer.join()

        print("[WATCHER] Stopped.")
        print("=" * 70)


if __name__ == "__main__":
    start_watcher()