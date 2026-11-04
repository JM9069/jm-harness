#!/usr/bin/env python3
"""jm 허브 — 진행판 · 검증 결과 · 커밋 · 서술형 · Codex 대화를 한 화면에(기본 포트 3156).

  python3 jmkit/hub.py [--root 작업폴더] [--host 0.0.0.0] [--port 3156]

표준 라이브러리 서버 하나. 화면은 static/ (외부 CDN 없음).
- GET  /api/state   진행판 + git + Codex 대화 (읽기만)
- POST /api/item    화면에서 고칠 수 있는 칸만: 상태 · 받은 답 · 결정 · 메모 · 서술형 연습 기록

- POST /api/send    {threads: [UUID...], message} — 열린 Codex 세션에 글 넣기(codex queue). 열쇠 필요

안전: 이 서버는 셸 명령을 실행하지 않는다. 자동 검증(명령)은 터미널의 `jm.py run` · `jm.py watch` 만 돌리고,
명령(cmd)을 만들거나 바꾸는 것도 jm.py 로만 한다. 화면에서 바꿀 수 있는 칸은 아래 EDITABLE 뿐이다.
쓰기 요청은 X-JM: 1 머리글이 있어야 받는다(다른 포트의 페이지가 몰래 보내는 요청 차단).
Codex 로 글 보내기는 서버를 켤 때 터미널에만 찍히는 열쇠(X-JM-Key)가 맞아야 하고,
이 작업 폴더에서 띄운 세션(대화 기록으로 확인)에만 보낸다 — 미리보기 주소가 밖에 알려져도 남이 Codex 를 부리지 못하게.
"""
import argparse
import hmac
import json
import os
import secrets
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jmlib  # noqa: E402

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8"}

# 화면에서 고칠 수 있는 칸 · 필드 (명령이 들어가는 auto 칸은 없음)
EDITABLE = {
    "todo": {"status", "note"},
    "question": {"status", "answer", "note"},
    "feature": {"status", "note"},
    "decision": {"status", "chosen", "reason"},
    "manual": {"status", "note"},
    "commit": {"status"},
    "essay": {"answer", "practice"},
}
MAX_TEXT = 4000


def clean_fields(section, fields):
    allowed = EDITABLE.get(section)
    if allowed is None:
        raise ValueError("화면에서 고칠 수 없는 칸: %s" % section)
    out = {}
    for k, v in (fields or {}).items():
        if k not in allowed:
            raise ValueError("화면에서 고칠 수 없는 항목: %s.%s" % (section, k))
        if k == "practice":
            if not isinstance(v, list) or len(v) > 50:
                raise ValueError("practice 는 50개 이하 목록")
            v = [{"at": str(p.get("at", ""))[:40], "text": str(p.get("text", ""))[:MAX_TEXT]}
                 for p in v if isinstance(p, dict)]
        elif not isinstance(v, str) or len(v) > MAX_TEXT:
            raise ValueError("%s 는 %d자 이하 글자" % (k, MAX_TEXT))
        out[k] = v
    return out


MAX_KEY_FAILS = 20  # 열쇠를 이만큼 틀리면 서버를 다시 켤 때까지 보내기를 막는다(찍어 맞히기 방지)


def make_handler(root, codex_home=None, key=None):
    fails = {"n": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # 터미널을 조용히
            pass

        def send_json(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path.endswith("/api/state"):
                return self.send_json(200, {
                    "root": root, "now": time.strftime("%H:%M:%S"), "board": jmlib.load(root),
                    "git": jmlib.git_info(root), "codex": jmlib.codex_sessions(root, codex_home),
                    "deliver": jmlib.deliver_state(root),
                })
            if path.endswith("/api/health"):
                return self.send_json(200, {"status": "ok"})
            name = "index.html" if path.endswith("/") else path.rsplit("/", 1)[-1]
            full = os.path.join(STATIC, os.path.basename(name))  # static/ 밖은 못 나감
            if not os.path.isfile(full):
                return self.send_json(404, {"error": "없음"})
            with open(full, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", TYPES.get(os.path.splitext(full)[1], "text/plain; charset=utf-8"))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.headers.get("X-JM") != "1":
                return self.send_json(403, {"error": "X-JM 머리글 없음"})
            path = self.path.split("?", 1)[0]
            if path.endswith("/api/send"):
                return self.send_codex()
            if not path.endswith("/api/item"):
                return self.send_json(404, {"error": "없음"})
            try:
                data = self.read_json()
                sec, item_id = data.get("section"), data.get("id")
                fields = clean_fields(sec, data.get("fields"))
                jmlib.mutate(root, lambda b: jmlib.update(b, sec, item_id, fields))
                jmlib.write_export(root)
                return self.send_json(200, {"ok": True, "id": item_id})
            except (ValueError, KeyError) as e:
                return self.send_json(400, {"error": str(e.args[0] if e.args else e)})

        def read_json(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 200000:
                raise ValueError("요청이 너무 큼")
            return json.loads(self.rfile.read(n).decode("utf-8") or "{}")

        def send_codex(self):
            if fails["n"] >= MAX_KEY_FAILS:
                return self.send_json(429, {"error": "열쇠를 너무 많이 틀림 — 허브를 다시 켜세요(start.sh stop → start)"})
            if not key or not hmac.compare_digest(self.headers.get("X-JM-Key", ""), key):
                fails["n"] += 1
                return self.send_json(401, {"error": "열쇠가 맞지 않음 — 허브를 켠 터미널에 찍힌 열쇠를 넣으세요"})
            try:
                data = self.read_json()
                threads = data.get("threads") or []
                if not isinstance(threads, list) or not threads or len(threads) > 10:
                    raise ValueError("보낼 세션을 1 ~ 10개 고르세요")
                mine = {s.get("uuid") for s in jmlib.codex_sessions(root, codex_home, limit=10)}
                results = {}
                for t in threads:
                    if t not in mine:
                        results[t] = {"ok": False, "code": None, "out": "이 작업 폴더의 최근 세션이 아님"}
                    else:
                        results[t] = jmlib.send_to_codex(t, data.get("message", ""))
                return self.send_json(200, {"ok": all(r["ok"] for r in results.values()), "results": results})
            except ValueError as e:
                return self.send_json(400, {"error": str(e.args[0] if e.args else e)})
    return Handler


def make_server(root, host="0.0.0.0", port=3156, codex_home=None, key=None):
    return ThreadingHTTPServer((host, port), make_handler(root, codex_home, key))


def save_key(port, key):
    """열쇠를 ~/.jm/hub-<포트>.key 에(본인만 읽기) — start.sh 가 터미널에 보여 준다."""
    d = os.path.join(os.path.expanduser("~"), ".jm")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "hub-%d.key" % port)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key + "\n")
    return p


def main():
    for stream in (sys.stdout, sys.stderr):  # 로캘이 UTF-8 이 아니어도 한글 출력에서 죽지 않게
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower() not in ("utf-8", "utf8"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="jm 허브")
    ap.add_argument("--root", default=None, help="작업 폴더(기본: .git 이 있는 위쪽 폴더)")
    ap.add_argument("--host", default="0.0.0.0", help="0.0.0.0 이어야 IDE 미리보기가 열린다")
    ap.add_argument("--port", type=int, default=3156)
    a = ap.parse_args()
    root = os.path.abspath(a.root) if a.root else jmlib.find_root()
    if not os.path.exists(jmlib.board_path(root)):
        b = jmlib.new_board()
        with jmlib.locked(root):
            jmlib.save(root, b)
        jmlib.write_export(root, b)
    key = secrets.token_hex(4)  # 화면에서 Codex 로 글 보낼 때 필요한 열쇠 8자리(켤 때마다 새로)
    save_key(a.port, key)
    srv = make_server(root, a.host, a.port, key=key)
    print("jm 허브 — 작업 폴더 %s · IDE 미리보기 PORT %d · Codex 보내기 열쇠 %s" % (root, a.port, key), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
