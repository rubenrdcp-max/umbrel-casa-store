"""Soma o espaco do disco interno do Umbrel com todos os discos USB/rede montados."""
import html
import http.server
import json
import os

ROOT = os.environ.get("UMBREL_ROOT_MOUNT", "/umbrel")
PORT = int(os.environ.get("PORT", "8000"))


def candidates(root):
    yield "Interno", root
    for base in ("external", "network"):
        folder = os.path.join(root, base)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if os.path.ismount(path):
                yield name, path


def disks(root=ROOT):
    seen, out = set(), []
    for name, path in candidates(root):
        try:
            st, dev = os.statvfs(path), os.stat(path).st_dev
        except OSError:
            continue  # disco tirado a meio da leitura
        if dev in seen:
            continue
        seen.add(dev)
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        out.append({"name": name, "total": total, "used": total - free, "free": free})
    return out


def fmt(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1000:
            return f"{n:.0f} {unit}"
        n /= 1000
    return f"{n:.1f} TB".replace(".", ",")


def widget(ds):
    total = sum(d["total"] for d in ds)
    used = sum(d["used"] for d in ds)
    extra = len(ds) - 1
    title = "Armazenamento total" + (f" · {extra} USB" if extra > 0 else "")
    return {
        "type": "text-with-progress",
        "link": "",
        "title": title,
        "text": fmt(used),
        "progressLabel": f"{fmt(total - used)} livres de {fmt(total)}",
        "progress": round(used / total, 3) if total else 0,
    }


def page(ds):
    rows = "".join(
        f"<tr><td>{html.escape(d['name'])}</td><td>{fmt(d['used'])}</td>"
        f"<td>{fmt(d['free'])}</td><td>{fmt(d['total'])}</td></tr>"
        for d in ds
    )
    w = widget(ds)
    return (
        "<!doctype html><meta charset=utf-8><title>Armazenamento</title>"
        "<style>body{font:16px system-ui;background:#111;color:#eee;padding:24px}"
        "table{border-collapse:collapse}td,th{padding:6px 14px;border-bottom:1px solid #333;text-align:left}</style>"
        f"<h1>{w['text']} usados</h1><p>{w['progressLabel']}</p>"
        f"<table><tr><th>Disco</th><th>Usado</th><th>Livre</th><th>Total</th></tr>{rows}</table>"
    )


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        ds = disks()
        if self.path.startswith("/api/widget"):
            body, ctype = json.dumps(widget(ds)).encode(), "application/json"
        elif self.path.startswith("/api/disks"):
            body, ctype = json.dumps(ds).encode(), "application/json"
        else:
            body, ctype = page(ds).encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def selftest():
    assert fmt(999) == "999 B" and fmt(227_000_000_000) == "227 GB"
    assert fmt(2_485_000_000_000) == "2,5 TB"
    ds = [{"name": "a", "total": 100, "used": 25, "free": 75}, {"name": "b", "total": 100, "used": 25, "free": 75}]
    w = widget(ds)
    assert w["progress"] == 0.25 and w["title"].endswith("1 USB"), w
    assert widget([])["progress"] == 0


if __name__ == "__main__":
    selftest()
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
