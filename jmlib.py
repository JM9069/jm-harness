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
import sys
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
    b.setdefault("notes", {})
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
                info["uuid"] = str(p.get("id", ""))
                info["id"] = info["uuid"][:8]
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
    names = {}  # /rename 으로 붙인 세션 이름 — 나중 줄이 최신
    idx = os.path.join(home, "session_index.jsonl")
    if os.path.exists(idx):
        with open(idx, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    o = json.loads(line)
                    names[o["id"]] = o.get("thread_name") or ""
                except (ValueError, KeyError, TypeError):
                    pass
    out = []
    rootn = os.path.normcase(os.path.abspath(root))
    for f in files[:30]:
        try:
            s = parse_session(f)
        except OSError:
            continue
        cwd = os.path.normcase(os.path.abspath(s["cwd"])) if s["cwd"] else ""
        if cwd and not (cwd.startswith(rootn) or rootn.startswith(cwd)):
            continue
        name = names.get(s.get("uuid", ""), "")
        if name == "Guardian review":  # 승인 자동 검토용 내부 세션은 뺀다
            continue
        s = dict(s, name=name, msgs=s["msgs"][-30:])
        out.append(s)
        if len(out) >= limit:
            break
    return out


UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def send_to_codex(thread, message, codex_bin=None, timeout=30):
    """열려 있는 Codex 세션에 글을 넣는다 — `codex queue --thread <UUID> --message <글>` (셸 없이 인자 목록으로).
    받는 세션이 일하는 중이면 그 턴이 끝난 뒤 들어간다. 성공 = «큐 등록» 까지(읽었다는 뜻 아님)."""
    if not UUID_RE.fullmatch(thread or ""):
        raise ValueError("세션 번호(UUID) 모양이 아님")
    message = (message or "").strip()
    if not message or len(message) > 4000:
        raise ValueError("글은 1 ~ 4000자")
    exe = codex_bin or os.environ.get("JM_CODEX_BIN") or "codex"
    try:
        p = subprocess.run([exe, "queue", "--thread", thread, "--message", message], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return {"ok": p.returncode == 0, "code": p.returncode, "out": ((p.stdout or "") + (p.stderr or ""))[-800:]}
    except FileNotFoundError:
        return {"ok": False, "code": None, "out": "codex 명령을 찾을 수 없음"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": None, "out": "시간 초과(%d초)" % timeout}


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
    """진행판이 바뀔 때마다 부른다 — BOARD.md 와 제출 문서(deliver.json 이 있으면)를 다시 쓴다."""
    board = board or load(root)
    path = os.path.join(root, "docs", "jm", "BOARD.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(export_md(board))
    try:
        render_deliverables(root, board)
    except ValueError as e:  # 설정이 틀려도 진행판 저장은 막지 않는다
        print("제출 문서 설정 오류: %s" % e, file=sys.stderr)
    return path


# ======= 제출 문서 자동 갱신 =======
# 시험장 README 가 요구하는 md 파일(예: DECISIONS.md · AI 협업 기록)을 docs/jm/deliver.json 에 적어 두면
# 진행판이 바뀔 때마다 «자동 칸» 만 다시 쓴다. «직접 칸»(mode=manual)과 표시 밖의 글은 건드리지 않는다.
DELIVER = os.path.join("docs", "jm", "deliver.json")
SOURCES = ("summary", "deliverables", "requirements", "answers", "questions_open", "decisions", "ai_judgments",
           "features", "unfinished", "checks", "auto_checks", "manual_checks", "todos", "commits", "prompts",
           "open_items")


def deliver_path(root):
    return os.path.join(root, DELIVER)


def load_deliver(root):
    p = deliver_path(root)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        cfg = json.load(f)
    rootn = os.path.normcase(os.path.abspath(root))
    for fi in cfg.get("files", []):
        rel = fi.get("path", "")
        full = os.path.normcase(os.path.abspath(os.path.join(root, rel)))
        if (not rel.endswith(".md") or not full.startswith(rootn + os.sep)
                or re.match(r"(\.git|jmkit|kit)([\\/]|$)", rel)):
            raise ValueError("제출 문서 경로는 작업 폴더 안의 .md 만: %s" % rel)
        for s in fi.get("sections", []):
            src = s.get("source", "")
            if s.get("mode") != "manual" and not (src in SOURCES or src.startswith("note:") or src.startswith("text:")):
                raise ValueError("%s 의 «%s» 칸: 모르는 source %s" % (rel, s.get("title"), src))
    return cfg


def _rows(header, rows):
    if not rows:
        return "(아직 없음)"
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for r in rows:
        out.append("| " + " | ".join(str(c if c not in (None, "") else "-").replace("|", "\\|").replace("\n", " ")
                                      for c in r) + " |")
    return "\n".join(out)


def render_source(root, board, src, git=None):
    b = board
    if src.startswith("text:"):
        return src[5:]
    if src.startswith("note:"):
        return b.get("notes", {}).get(src[5:]) or "(아직 없음 — `jm.py note %s \"...\"`)" % src[5:]
    if src == "summary":
        return b.get("summary") or "(아직 없음)"
    if src == "deliverables":
        return "\n".join("- " + d for d in b.get("deliverables") or []) or "(아직 없음)"
    if src == "requirements":
        return _rows(["번호", "README 요구", "반영"], [(x["id"], x.get("text"), x.get("where")) for x in b["req"]])
    if src == "answers":
        rows = [(x["id"], x.get("text"), x.get("answer"), x.get("why")) for x in b["question"] if x.get("status") == "answered"]
        return _rows(["번호", "확인한 것", "담당자 답", "반영"], rows)
    if src == "questions_open":
        return _rows(["번호", "아직 확인 못 한 것", "답에 따라 바뀌는 것"],
                     [(x["id"], x.get("text"), x.get("why")) for x in b["question"] if x.get("status") != "answered"])
    if src == "decisions":
        rows = [(x["id"], x.get("title"), x.get("chosen") or "(미정)", x.get("reason"),
                 " / ".join(x["options"]) if isinstance(x.get("options"), list) else x.get("options"),
                 x.get("rejected")) for x in b["decision"]]
        return _rows(["번호", "정한 것", "결정", "이유", "검토한 선택지", "버린 안과 이유"], rows)
    if src == "ai_judgments":
        rows = [(x["id"], x.get("title"), x.get("recommend"), x.get("chosen") or "(미정)",
                 "채택" if x.get("chosen") and x.get("recommend") and x["chosen"] in x["recommend"] else
                 ("다르게 정함" if x.get("chosen") else "-"), x.get("reason")) for x in b["decision"]]
        return _rows(["번호", "판단할 것", "AI 제안", "내 결정", "채택 여부", "이유"], rows)
    if src == "features":
        return _rows(["번호", "기능", "중요도", "상태", "메모"],
                     [(x["id"], x.get("title"), x.get("priority"), x.get("status"), x.get("note")) for x in b["feature"]])
    if src == "unfinished":
        rows = [(x["id"], x.get("title"), x.get("status"), x.get("note")) for x in b["feature"] if x.get("status") != "done"]
        return _rows(["번호", "구현 안 됨 · 안 함", "상태", "이유"], rows)
    if src in ("checks", "auto_checks"):
        rows = [(x["id"], x.get("title"), "`%s`" % x.get("cmd", ""),
                 ("통과" if x["last"]["ok"] else "실패 (종료코드 %s)" % x["last"]["code"]) + " · " + x["last"]["at"]
                 if x.get("last") else "안 돌림") for x in b["auto"]]
        out = "**자동 검증**\n\n" + _rows(["번호", "확인", "명령", "결과"], rows)
        if src == "auto_checks":
            return out
        return out + "\n\n" + render_source(root, b, "manual_checks")
    if src == "manual_checks":
        return "**직접 확인**\n\n" + _rows(["번호", "확인", "방법", "결과", "메모"],
                                         [(x["id"], x.get("title"), x.get("how"), x.get("status"), x.get("note")) for x in b["manual"]])
    if src == "todos":
        return "\n".join("- [%s] %s %s" % ("x" if x.get("status") == "done" else " ", x["id"], x.get("title", ""))
                         for x in b["todo"]) or "(아직 없음)"
    if src == "commits":
        g = git if git is not None else git_info(root)
        return "\n".join("- `%s` %s" % (c["hash"], c["msg"]) for c in g.get("log", [])) or "(아직 없음)"
    if src == "prompts":
        lines = []
        for s in codex_sessions(root, limit=5):
            for m in s["msgs"]:
                if m["role"] == "user":
                    lines.append("- %s · %s" % ((m.get("ts") or "")[11:16], m["text"].replace("\n", " ")[:160]))
        return "\n".join(lines[-40:]) or "(아직 없음)"
    if src == "open_items":
        parts = [render_source(root, b, "questions_open"),
                 _rows(["번호", "아직 정하지 못한 것"], [(x["id"], x.get("title")) for x in b["decision"] if x.get("status") != "decided"]),
                 _rows(["번호", "남은 할 일"], [(x["id"], x.get("title")) for x in b["todo"] if x.get("status") != "done"])]
        return "\n\n".join(parts)
    raise ValueError("모르는 source: %s" % src)


def deliver_state(root):
    """허브 «제출 문서» 탭용 — 설정과 파일 내용(앞 20000자)."""
    try:
        cfg = load_deliver(root)
    except (ValueError, OSError) as e:
        return {"config": None, "error": str(e), "files": []}
    if not cfg:
        return {"config": None, "error": "", "files": []}
    files = []
    for fi in cfg.get("files", []):
        full = os.path.join(root, fi["path"])
        content = ""
        if os.path.exists(full):
            with open(full, encoding="utf-8", errors="replace") as f:
                content = f.read(20000)
        files.append({"path": fi["path"], "exists": os.path.exists(full), "content": content,
                      "sections": [{"title": s.get("title"), "mode": s.get("mode", "auto"), "source": s.get("source", "")}
                                   for s in fi.get("sections", [])]})
    return {"config": True, "error": "", "files": files}


def _block(sid, body):
    return "<!-- jm:begin %s -->\n%s\n<!-- jm:end %s -->" % (sid, body.strip(), sid)


def render_deliverables(root, board=None):
    """설정된 제출 문서를 만들거나 «자동 칸» 만 바꾼다. 돌려주는 값: [(경로, 바뀐 칸 수, 경고 목록)]."""
    cfg = load_deliver(root)
    if not cfg:
        return []
    board = board or load(root)
    git = git_info(root)
    report = []
    for fi in cfg.get("files", []):
        full = os.path.join(root, fi["path"])
        text = None
        if os.path.exists(full):
            with open(full, encoding="utf-8") as f:
                text = f.read()
        before = text
        warns, changed = [], 0
        if text is None:  # 처음: 제목 + 칸을 차례로
            parts = ["# " + (fi.get("title") or os.path.splitext(os.path.basename(fi["path"]))[0])]
            if fi.get("intro"):
                parts.append(fi["intro"])
            for i, s in enumerate(fi.get("sections", [])):
                parts.append("## " + s["title"])
                if s.get("mode") == "manual":
                    parts.append("<!-- 직접 작성 칸: %s -->\n" % (s.get("hint") or "이 칸은 내가 직접 쓴다"))
                else:
                    parts.append(_block(s.get("id") or "s%d" % (i + 1), render_source(root, board, s["source"], git)))
                changed += 1
            text = "\n\n".join(parts) + "\n"
        else:
            for i, s in enumerate(fi.get("sections", [])):
                sid = s.get("id") or "s%d" % (i + 1)
                if s.get("mode") == "manual":
                    if not re.search(r"^#{1,6} +%s *$" % re.escape(s["title"].strip()), text, re.M):
                        text = text.rstrip("\n") + "\n\n## %s\n\n<!-- 직접 작성 칸: %s -->\n" % (s["title"], s.get("hint") or "")
                        changed += 1
                    continue
                pat = re.compile(r"<!-- jm:begin %s -->.*?<!-- jm:end %s -->" % (re.escape(sid), re.escape(sid)), re.S)
                new = _block(sid, render_source(root, board, s["source"], git))
                head = re.compile(r"^(#{1,6}) +%s *$" % re.escape(s["title"].strip()), re.M)
                hm = head.search(text)
                if pat.search(text):
                    text2 = pat.sub(lambda m: new, text, count=1)
                    changed += text2 != text
                    text = text2
                elif hm:
                    # 시험이 준 양식(제목이 이미 있음): 제목 바로 아래에 자동 칸을 넣는다 · 바로 뒤 «(답변)» 자리 글은 걷어 낸다
                    after = re.sub(r"^\s*\n\s*\((답변|answer)\)[ \t]*(?=\n|$)", "", text[hm.end():], count=1)
                    rest = after.lstrip("\n")
                    text = text[:hm.end()] + "\n\n" + new + ("\n\n" + rest if rest else "\n")
                    changed += 1
                else:
                    text = text.rstrip("\n") + "\n\n## %s\n\n%s\n" % (s["title"], new)
                    changed += 1
        if text != before:  # 바뀐 게 없으면 쓰지 않는다(편집기의 «외부 변경» 알림을 줄인다)
            os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
            with open(full, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        report.append((fi["path"], changed, warns))
    return report


def snapshot(board):
    return copy.deepcopy(board)
