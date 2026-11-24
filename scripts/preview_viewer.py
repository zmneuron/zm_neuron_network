"""Prepare one project-bound localhost viewer; the host opens the returned URL.

Only generated HTML and service metadata in docs/viewer are updated. The server
serves that HTML alone, never project files or a directory listing. It does not
run a model, watch research files, or open an external system browser.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import uuid

from build_viewer import build_viewer, inside

CONTRACT = "zm-neuron-preview/1"
IDLE_SECONDS = 7200


def location(project):
    root = Path(project).resolve(strict=True)
    folder = root / "docs" / "viewer"
    if not folder.resolve().is_relative_to(root) or folder.is_symlink():
        raise ValueError("Viewer directory must stay within this project")
    for name in ("index.html", "viewer.json", "update.lock"):
        if (folder / name).is_symlink():
            raise ValueError("Viewer files cannot be symbolic links")
    key = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
    return root, folder, key


def read_state(folder, key):
    file = folder / "viewer.json"
    if not file.exists():
        if (folder / "index.html").exists():
            raise ValueError("Existing index.html is not owned by this viewer; it was not overwritten")
        return None
    value = json.loads(file.read_text(encoding="utf-8"))
    if value.get("contract") != CONTRACT or value.get("project_key") != key:
        raise ValueError("Viewer state belongs to another project or format")
    return value


def write_state(folder, value):
    temp = folder / (".state-" + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, folder / "viewer.json")
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def update_lock(folder):
    lock = folder / "update.lock"
    with lock.open("x", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def request(state, path, payload=None):
    url = urlsplit(state.get("url") or "")
    if (url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port
            or url.username or url.password or url.path != "/index.html" or url.query or url.fragment):
        raise ValueError("Only this viewer's loopback URL is accepted")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{url.port}{path}", data=data)
    # A configured system proxy must not receive project preview requests.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=1) as response:
        return json.loads(response.read(8192))


def alive(state):
    if not state or not state.get("url"):
        return False
    try:
        reply = request(state, "/_identity")
        return all(reply.get(k) == state.get(k) for k in ("contract", "project_key", "instance_id"))
    except (OSError, ValueError):
        return False


def prepare_preview(project, plan_ref="docs/task_plan.json", checkpoint="transition"):
    root, folder, key = location(project)
    plan_ref = inside(root, plan_ref).relative_to(root).as_posix()
    if not (root / plan_ref).is_file():
        raise ValueError("Save this project's task plan before opening its viewer")
    plan = json.loads((root / plan_ref).read_text(encoding="utf-8-sig"))
    enabled = plan.get("review", {}).get("viewer", {}).get("auto_open", True)
    if type(enabled) is not bool:
        raise ValueError("viewer.auto_open must be a boolean")
    if not enabled:
        return dict(status="disabled", project=str(root), browser_opened=False)
    folder.mkdir(parents=True, exist_ok=True)
    with update_lock(folder):
        state = read_state(folder, key)
        if state and state.get("plan_ref") != plan_ref:
            raise ValueError("This viewer is bound to a different task plan")
        temporary = folder / (".page-" + uuid.uuid4().hex + ".html")
        try:
            built = build_viewer(root, temporary, plan_ref, checkpoint)
            os.replace(temporary, folder / "index.html")
        finally:
            temporary.unlink(missing_ok=True)
        reused = alive(state)
        if not reused:
            state = dict(contract=CONTRACT, project_key=key, plan_ref=plan_ref,
                         instance_id=uuid.uuid4().hex, url=None)
            write_state(folder, state)
            options = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.name == "nt":
                options["creationflags"] = subprocess.CREATE_NO_WINDOW
            else:
                options["start_new_session"] = True
            child = subprocess.Popen([sys.executable, "-B", "-X", "utf8", str(Path(__file__).resolve()),
                                      "--project", str(root), "--serve"], **options)
            # Retain/reap this intentional background child without leaking a
            # Popen handle when the caller stays alive (for example, tests).
            threading.Thread(target=child.wait, daemon=True).start()
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                current = read_state(folder, key)
                if current and current.get("instance_id") == state["instance_id"] and alive(current):
                    state = current
                    break
                if child.poll() is not None:
                    raise RuntimeError("Local viewer service exited before becoming ready; HTML remains available")
                time.sleep(0.1)
            else:
                child.terminate()
                child.wait(timeout=3)
                raise RuntimeError("Local viewer service did not become ready; HTML remains available")
        return dict(status="ready", url=state["url"], html=str(folder / "index.html"),
                    project=str(root), plan_id=built["plan_id"], model_version=built["model_version"],
                    checkpoint=checkpoint, reused_server=reused, browser_opened=False,
                    open_request={"target": {"type": "browser", "url": state["url"]},
                                  "placement": "right"},
                    next_action="Call the host open_in_codex with open_request in this chat, then verify the project shown. Reuse the existing tab at this URL; ready does not mean opened.")


def stop_preview(project):
    _, folder, key = location(project)
    state = read_state(folder, key)
    if not alive(state):
        return dict(status="not_running")
    request(state, "/_stop", {"instance_id": state["instance_id"]})
    return dict(status="stop_requested")


def serve(project):
    _, folder, key = location(project)
    state = read_state(folder, key)
    if not state:
        raise ValueError("Prepare the viewer before starting its service")
    active = {"stop": False, "last_request": time.monotonic()}
    identity = {k: state[k] for k in ("contract", "project_key", "instance_id")}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_data(self, body, content_type="application/json", head=False):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def do_GET(self, head=False):
            active["last_request"] = time.monotonic()
            route = urlsplit(self.path).path
            if route in ("/", "/index.html"):
                self.send_data((folder / "index.html").read_bytes(), "text/html; charset=utf-8", head)
            elif route == "/_identity":
                self.send_data(json.dumps(identity).encode(), head=head)
            else:
                self.send_error(404)

        def do_HEAD(self):
            self.do_GET(head=True)

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if self.path != "/_stop" or not 0 < length <= 512:
                    raise ValueError("Invalid stop request")
                body = json.loads(self.rfile.read(length))
                if body.get("instance_id") != identity["instance_id"]:
                    raise ValueError("Wrong viewer instance")
            except (ValueError, TypeError, AttributeError):
                self.send_error(400)
                return
            active["stop"] = True
            self.send_data(b'{"status":"stopping"}')

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        server.timeout = 1
        state.update(url=f"http://127.0.0.1:{server.server_port}/index.html", pid=os.getpid())
        write_state(folder, state)
        while not active["stop"] and time.monotonic() - active["last_request"] < IDLE_SECONDS:
            server.handle_request()


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--plan", default="docs/task_plan.json")
    parser.add_argument("--checkpoint", choices=("start", "transition", "resume", "delivery"), default="transition")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    modes.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    try:
        if args.serve:
            serve(args.project)
            return 0
        result = stop_preview(args.project) if args.stop else prepare_preview(args.project, args.plan, args.checkpoint)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, RuntimeError) as error:
        print(json.dumps(dict(status="failed", reason=str(error)), ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
