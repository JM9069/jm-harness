"""jm-harness 공용 부품 — 보드(board.json) 읽기·쓰기, 검증 실행, git·Codex 기록 읽기.

표준 라이브러리만 쓴다(시험 환경에서 설치 없이 돌게). hub.py(화면 서버)와 jm.py(명령줄)가 같이 쓴다.
보드 위치: <작업 폴더>/docs/jm/board.json  — 사람이 읽는 판은 docs/jm/BOARD.md (export 가 만든다)
"""
import contextlib
import copy
import glob
import json
import os
import re
import subprocess
import time

try:
    import fcntl  # 리눅스(시험 환경)
except ImportError:  # 윈도(개발 PC)
    fcntl = None
    import msvcrt

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "templates", "board.json")

# 칸 이름 → 번호 앞글자
SECTIONS = {
    "req": "R",       # README 요구 문장
    "question": "Q",  # 담당자에게 물을 것
    "feature": "F",   # 만들 기능
    "decision": "D",  # 정해야 할 것
    "auto": "A",      # 자동 검증(명령으로 확인)
    "manual": "M",    # 직접 확인(사람 눈)
    "todo": "T",      # 순서대로 할 일
    "commit": "C",    # 커밋 계획
    "essay": "E",     # 서술형 대비
}

# 칸마다 허용하는 상태 값(처음 값이 기본)
STATUS = {
    "question": ["draft", "asked", "answered"],
    "feature": ["todo", "doing", "done", "wont"],
    "decision": ["open", "decided"],
    "manual": ["todo", "done", "fail"],
    "todo": ["todo", "doing", "done"],
    "commit": ["todo", "done"],
}

# 커밋하면 안 되거나 확인이 필요한 파일 모양
RISKY = [
    (r"(^|/)\.env($|\.(?!example))", "비밀값 파일(.env)"),
    (r"(^|/)(\.venv|venv|node_modules|__pycache__|\.pytest_cache)(/|$)", "가상환경·캐시"),
    (r"\.(db|sqlite3?|log)$", "DB·로그 파일"),
    (r"(^|/)\.(bash_history|literacy|profile|bashrc)", "플랫폼 기록 파일"),
    (r"(^|/)(kit|jmkit)/", "키트·하네스 폴더"),
]


# ======= 경로 =======
def find_root(start=None):
    """작업 폴더 찾기: JM_ROOT → 위로 올라가며 .git 이 있는 곳 → 지금 폴더."""
    env = os.environ.get("JM_ROOT")
    if env:
        return os.path.abspath(env)
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def board_path(root):
    return os.path.join(root, "docs", "jm", "board.json")


# ======= 잠금 · 읽기 · 쓰기 =======
@contextlib.contextmanager
def locked(root):
    """hub(화면)와 jm.py(Codex)가 동시에 쓰지 않게 잠금 파일로 순서를 정한다."""
    gitdir = os.path.join(root, ".git")
    # 잠금 파일은 .git 안에 둔다 — 작업 폴더에 두면 «커밋 안 된 파일» 로 보인다
    path = os.path.join(gitdir, "jm-board.lock") if os.path.isdir(gitdir) else board_path(root) + ".lock"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    f = open(path, "a+")
    try:
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_EX)
        else:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        yield
    finally:
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_UN)
        else:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        f.close()


def new_board():
    with open(TEMPLATE, encoding="utf-8") as f:
        return json.load(f)


def load(root):
    path = board_path(root)
    if not os.path.exists(path):
        return new_board()
    with open(path, encoding="utf-8") as f:
        b = json.load(f)
    for sec in SECTIONS:  # 옛 판에 칸이 없으면 채운다
        b.setdefault(sec, [])
    return b


def save(root, board):
    path = board_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    board["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(board, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)  # 반쯤 쓴 파일이 남지 않게 한 번에 바꾼다


def mutate(root, fn):
    """잠금 → 읽기 → fn(board) → 쓰기. fn 이 돌려준 값을 돌려준다."""
    with locked(root):
        b = load(root)
        out = fn(b)
        save(root, b)
        return out


# ======= 항목 다루기 =======
def next_id(board, section):
    pre = SECTIONS[section]
    nums = [int(x["id"][len(pre):]) for x in board[section] if re.fullmatch(pre + r"\d+", str(x.get("id", "")))]
    return "%s%d" % (pre, (max(nums) + 1) if nums else 1)


def check_section(section):
    if section not in SECTIONS:
        raise ValueError("모르는 칸: %s (가능: %s)" % (section, ", ".join(SECTIONS)))


def check_status(section, fields):
    if "status" in fields and section in STATUS and fields["status"] not in STATUS[section]:
        raise ValueError("%s 상태는 %s 중 하나" % (section, "/".join(STATUS[section])))


def add(board, section, fields):
    check_section(section)
    check_status(section, fields)
    item = {"id": next_id(board, section)}
    if section in STATUS:
        item["status"] = STATUS[section][0]
    item.update({k: v for k, v in fields.items() if k != "id"})
    board[section].append(item)
    return item["id"]


def get(board, section, item_id):
    check_section(section)
    for x in board[section]:
        if x.get("id") == item_id:
            return x
    raise KeyError("%s 에 %s 없음" % (section, item_id))


def update(board, section, item_id, fields):
    check_status(section, fields)
    x = get(board, section, item_id)
    x.update({k: v for k, v in fields.items() if k != "id"})
    return x


def remove(board, section, item_id):
    x = get(board, section, item_id)
    board[section].remove(x)


def import_data(board, data, replace=False):
    """Codex 가 만든 분석 JSON 을 합친다. replace=True 면 그 칸을 통째로 바꾼다(번호 새로)."""
    for key in ("title", "summary", "deliverables", "stack"):
        if key in data:
            board[key] = data[key]
    counts = {}
    for sec in SECTIONS:
        items = data.get(sec)
        if not items:
            continue
        if replace:
            board[sec] = []
        for it in items:
            if not isinstance(it, dict):
                raise ValueError("%s 칸의 항목은 객체여야 함" % sec)
            add(board, sec, it)
        counts[sec] = len(items)
    return counts


def find_section(item_id):
    """'Q3' → 'question'"""
    m = re.fullmatch(r"([A-Z])\d+", item_id or "")
    if not m:
        raise ValueError("번호 모양이 아님: %s" % item_id)
    for sec, pre in SECTIONS.items():
        if pre == m.group(1):
            return sec
    raise ValueError("모르는 번호 앞글자: %s" % item_id)


# ======= 자동 검증 =======
def run_check(root, item, timeout=None):
    """item = {"cmd", "expect_code"(기본 0), "expect_text"(선택), "timeout"(초)} → 결과 dict.
    판정은 종료코드 + (있으면) 출력에 기대 글자가 있는지. 걸린 시간으로 판정하지 않는다."""
    cmd = item.get("cmd", "").strip()
    if not cmd:
        return {"ok": False, "code": None, "out": "명령 없음", "at": time.strftime("%H:%M:%S"), "sec": 0}
    limit = timeout or int(item.get("timeout", 60))
    start = time.time()
    try:
        if os.name == "nt":
            p = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=limit)
        else:
            p = subprocess.run(["bash", "-lc", cmd], cwd=root, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=limit)
        out = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr else "")
        ok = p.returncode == int(item.get("expect_code", 0))
        if ok and item.get("expect_text"):
            ok = item["expect_text"] in (p.stdout or "")
        code = p.returncode
    except subprocess.TimeoutExpired:
        ok, code, out = False, None, "시간 초과(%d초) — 멈춘 명령인지 확인" % limit
    return {"ok": ok, "code": code, "out": out[-1500:], "at": time.strftime("%H:%M:%S"),
            "sec": round(time.time() - start, 1)}


def apply_check_result(board, check_id, result):
    """결과를 기록하고, 연결된 할 일(todo)을 통과면 done · 실패면 doing 으로 맞춘다."""
    a = get(board, "auto", check_id)
    a["last"] = result
    tid = a.get("todo")
    if tid:
        try:
            t = get(board, "todo", tid)
        except KeyError:
            return
        if result["ok"]:
            t["status"] = "done"
            t["by"] = "auto:" + check_id
        elif t.get("by") == "auto:" + check_id:
            t["status"] = "doing"
            t.pop("by", None)


def run_checks(root, ids=None, only_watch=False):
    """검증 실행은 잠금 밖에서(오래 걸릴 수 있음), 결과 기록만 잠금 안에서."""
    board = load(root)
    targets = [a for a in board["auto"]
               if (ids is None or a["id"] in ids) and (not only_watch or a.get("watch"))]
    results = {a["id"]: run_check(root, a) for a in targets}

    def write(b):
        for cid, res in results.items():
            try:
                apply_check_result(b, cid, res)
            except KeyError:
                pass
    if results:
        mutate(root, write)
    return results


# ======= git =======
def _git(root, *args):
    try:
        p = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10,
                           env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
        return p.stdout if p.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def git_info(root):
    """커밋 안 된 파일(위험 표시 포함) · 최근 커밋."""
    if not os.path.isdir(os.path.join(root, ".git")):
        return {"repo": False}
    files = []
    for line in _git(root, "status", "--porcelain=v1", "-uall").splitlines():
        if len(line) < 4:
            continue
        st, path = line[:2], line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        warn = [why for pat, why in RISKY if re.search(pat, path)]
        files.append({"st": st.strip() or "?", "path": path, "warn": warn})
    log = [l.split(" ", 1) for l in _git(root, "log", "--oneline", "-12").splitlines() if l]
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    return {"repo": True, "branch": branch, "files": files,
            "log": [{"hash": h, "msg": m} for h, m in log]}


# ======= Codex 대화 기록 =======
_cache = {}


def _text_of(content):
    if isinstance(content, str):
        return content
    parts = []
    for c in content or []:
        if isinstance(c, dict) and isinstance(c.get("text"), str):
            parts.append(c["text"])
    return "\n".join(parts)


def _is_injected(text):
    t = text.lstrip()
    return (t.startswith("<") or t.startswith("# AGENTS.md") or "<environment_context>" in t[:200]
            or t.startswith("<user_instructions>"))


def parse_session(path):
    """rollout-*.jsonl → {id, cwd, msgs:[{role, text, ts}], tokens}. 바뀌지 않았으면 캐시."""
    st = os.stat(path)
    key = (path, st.st_mtime, st.st_size)
    if _cache.get(path, (None,))[0] == key:
        return _cache[path][1]
    info = {"file": os.path.basename(path), "cwd": "", "msgs": [], "tokens": None, "mtime": st.st_mtime}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            p = o.get("payload") if isinstance(o.get("payload"), dict) else {}
            typ = o.get("type")
            if typ == "session_meta":
                info["cwd"] = p.get("cwd", "")
                info["id"] = str(p.get("id", ""))[:8]
            elif typ == "response_item" and p.get("type") == "message" and p.get("role") in ("user", "assistant"):
                text = _text_of(p.get("content")).strip()
                if not text or (p["role"] == "user" and _is_injected(text)):
                    continue
                info["msgs"].append({"role": p["role"], "text": text[:1200], "ts": o.get("timestamp", "")})
            elif typ == "event_msg" and p.get("type") == "token_count":
                tot = ((p.get("info") or {}).get("total_token_usage") or {}).get("total_tokens")
                if tot:
                    info["tokens"] = tot
    _cache[path] = (key, info)
    return info


def codex_sessions(root, codex_home=None, limit=3, hours=12):
    """작업 폴더 안에서 띄운 최근 Codex 세션의 대화(사용자 · 최종 답변만)."""
    home = codex_home or os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    files = glob.glob(os.path.join(home, "sessions", "**", "rollout-*.jsonl"), recursive=True)
    cutoff = time.time() - hours * 3600
    files = sorted((f for f in files if os.path.getmtime(f) >= cutoff), key=os.path.getmtime, reverse=True)
    out = []
    rootn = os.path.normcase(os.path.abspath(root))
    for f in files[:20]:
        try:
            s = parse_session(f)
        except OSError:
            continue
        cwd = os.path.normcase(os.path.abspath(s["cwd"])) if s["cwd"] else ""
        if cwd and not (cwd.startswith(rootn) or rootn.startswith(cwd)):
            continue
        s = dict(s, msgs=s["msgs"][-30:])
        out.append(s)
        if len(out) >= limit:
            break
    return out


# ======= 사람이 읽는 판 =======
MARK = {"done": "✅", "doing": "🔄", "todo": "⬜", "wont": "🚫", "draft": "📝", "asked": "📨",
        "answered": "✅", "open": "🔴", "decided": "🟢", "fail": "❌"}


def export_md(board):
    L = ["# %s — 진행판" % (board.get("title") or "과제"), "",
         "> jm-harness 가 docs/jm/board.json 에서 만든 파일 · 갱신 %s" % board.get("updated", ""), ""]
    if board.get("summary"):
        L += ["## 문제 요약", board["summary"], ""]
    if board.get("deliverables"):
        L += ["## 제출물"] + ["- " + d for d in board["deliverables"]] + [""]

    def table(title, sec, cols):
        items = board.get(sec) or []
        if not items:
            return
        L.append("## " + title)
        L.append("| 번호 | 상태 | " + " | ".join(c[1] for c in cols) + " |")
        L.append("|---|---|" + "---|" * len(cols))
        for x in items:
            st = x.get("status", "")
            if sec == "auto":
                last = x.get("last") or {}
                st = "✅" if last.get("ok") else ("❌" if last else "⬜")
            cells = [str(x.get(k, "")).replace("|", "\\|").replace("\n", " ") for k, _ in cols]
            L.append("| %s | %s | %s |" % (x["id"], MARK.get(st, st), " | ".join(cells)))
        L.append("")

    table("할 일(순서)", "todo", [("title", "할 일"), ("check", "끝 확인")])
    table("README 요구", "req", [("text", "원문"), ("where", "어디에")])
    table("담당자 질문", "question", [("text", "질문"), ("why", "답에 따라 바뀌는 것"), ("answer", "받은 답")])
    table("기능", "feature", [("title", "기능"), ("priority", "중요도"), ("note", "메모")])
    table("결정", "decision", [("title", "정할 것"), ("options", "선택지"), ("chosen", "결정"), ("reason", "이유")])
    table("자동 검증", "auto", [("title", "확인"), ("cmd", "명령")])
    table("직접 검증", "manual", [("title", "확인"), ("how", "방법")])
    table("커밋 계획", "commit", [("when", "언제"), ("files", "파일"), ("message", "메시지")])
    table("서술형 대비", "essay", [("q", "예상 질문"), ("answer", "답 메모"), ("evidence", "근거")])
    return "\n".join(L) + "\n"


def write_export(root, board=None):
    board = board or load(root)
    path = os.path.join(root, "docs", "jm", "BOARD.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(export_md(board))
    return path


def snapshot(board):
    return copy.deepcopy(board)
