#!/usr/bin/env python3
"""jm — 진행판(docs/jm/board.json) 명령줄 도구. Codex 와 사람이 같이 쓴다.

  python3 jmkit/jm.py init                         진행판 만들기(있으면 그대로)
  python3 jmkit/jm.py show [칸]                     요약 보기
  python3 jmkit/jm.py add <칸> 키=값 ...            항목 추가(번호 자동) → 번호 출력
  python3 jmkit/jm.py set <번호> 키=값 ...           항목 고치기 (예: set Q2 status=answered answer="...")
  python3 jmkit/jm.py done <번호>                    할 일 · 기능 · 커밋 · 직접 검증을 완료로
  python3 jmkit/jm.py rm <번호>                      항목 지우기
  python3 jmkit/jm.py import <파일.json> [--replace] 분석 결과 한꺼번에 넣기
  python3 jmkit/jm.py run [번호 ... | all]           자동 검증 실행 → 결과 기록 · 연결된 할 일 갱신
  python3 jmkit/jm.py watch [초=30]                  watch=true 검증을 주기적으로 실행(화면 실시간 갱신용 · Ctrl+C 로 끝)
  python3 jmkit/jm.py export                         docs/jm/BOARD.md 다시 쓰기

칸: req question feature decision auto manual todo commit essay
값은 따옴표로 감싼다. 숫자 · true/false 는 그대로 들어간다(예: watch=true timeout=30).
종료코드: 0 정상 · 1 검증 실패 있음 · 2 사용법 · 입력 오류
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jmlib  # noqa: E402


def parse_fields(args):
    out = {}
    for a in args:
        if "=" not in a:
            raise ValueError("키=값 모양이 아님: %s" % a)
        k, v = a.split("=", 1)
        if v in ("true", "false"):
            v = v == "true"
        elif v.lstrip("-").isdigit():
            v = int(v)
        out[k.strip()] = v
    return out


def cmd_show(root, args):
    b = jmlib.load(root)
    secs = args or ["todo", "question", "decision", "feature", "auto", "manual", "commit"]
    print("과제: %s · 갱신 %s" % (b.get("title") or "(제목 없음)", b.get("updated") or "-"))
    for sec in secs:
        items = b.get(sec) or []
        if not items:
            continue
        print("\n[%s]" % sec)
        for x in items:
            st = x.get("status", "")
            if sec == "auto":
                last = x.get("last") or {}
                st = "pass" if last.get("ok") else ("FAIL" if last else "-")
            label = x.get("title") or x.get("text") or x.get("q") or x.get("message") or ""
            print("  %-4s %-9s %s" % (x["id"], st, str(label)[:90]))


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    root = jmlib.find_root()
    cmd, args = argv[0], argv[1:]

    if cmd == "init":
        path = jmlib.board_path(root)
        if os.path.exists(path):
            print("이미 있음: %s" % path)
            return 0
        b = jmlib.new_board()
        readme = os.path.join(root, "README.md")
        if os.path.exists(readme):
            with open(readme, encoding="utf-8", errors="replace") as f:
                first = f.readline().strip().lstrip("#").strip()
            b["title"] = first
        with jmlib.locked(root):
            jmlib.save(root, b)
        jmlib.write_export(root, b)
        print("진행판 만듦: %s" % path)
        return 0

    if cmd == "show":
        cmd_show(root, args)
        return 0

    if cmd == "add":
        if not args:
            raise ValueError("칸 이름이 필요함")
        sec, fields = args[0], parse_fields(args[1:])
        new_id = jmlib.mutate(root, lambda b: jmlib.add(b, sec, fields))
        jmlib.write_export(root)
        print(new_id)
        return 0

    if cmd in ("set", "done", "rm"):
        if not args:
            raise ValueError("번호가 필요함 (예: Q2)")
        item_id = args[0]
        sec = jmlib.find_section(item_id)
        if cmd == "set":
            fields = parse_fields(args[1:])
            jmlib.mutate(root, lambda b: jmlib.update(b, sec, item_id, fields))
        elif cmd == "done":
            if sec not in ("todo", "feature", "commit", "manual"):
                raise ValueError("done 은 할 일 · 기능 · 커밋 · 직접 검증만")
            jmlib.mutate(root, lambda b: jmlib.update(b, sec, item_id, {"status": "done"}))
        else:
            jmlib.mutate(root, lambda b: jmlib.remove(b, sec, item_id))
        jmlib.write_export(root)
        print("%s %s" % (item_id, cmd))
        return 0

    if cmd == "import":
        if not args:
            raise ValueError("JSON 파일 경로가 필요함")
        with open(args[0], encoding="utf-8") as f:
            data = json.load(f)
        replace = "--replace" in args[1:]
        counts = jmlib.mutate(root, lambda b: jmlib.import_data(b, data, replace=replace))
        jmlib.write_export(root)
        print("넣음: " + (", ".join("%s %d" % kv for kv in counts.items()) or "없음"))
        return 0

    if cmd == "run":
        ids = None if (not args or args == ["all"]) else args
        results = jmlib.run_checks(root, ids)
        jmlib.write_export(root)
        if not results:
            print("실행할 자동 검증이 없음")
            return 0
        bad = 0
        for cid, r in results.items():
            print("%s %s (종료코드 %s · %.1f초)" % (cid, "통과" if r["ok"] else "실패", r["code"], r["sec"]))
            if not r["ok"]:
                bad += 1
                print("   " + r["out"].strip().replace("\n", "\n   ")[-600:])
        return 1 if bad else 0

    if cmd == "watch":
        every = int(args[0]) if args else 30
        print("watch 검증을 %d초마다 실행 — 끝내려면 Ctrl+C" % every, flush=True)
        try:
            while True:
                results = jmlib.run_checks(root, only_watch=True)
                if results:
                    jmlib.write_export(root)
                    print(time.strftime("%H:%M:%S"), " · ".join(
                        "%s %s" % (k, "통과" if v["ok"] else "실패") for k, v in results.items()), flush=True)
                time.sleep(every)
        except KeyboardInterrupt:
            return 0

    if cmd == "export":
        print(jmlib.write_export(root))
        return 0

    raise ValueError("모르는 명령: %s (help 로 사용법)" % cmd)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # 윈도 콘솔에서도 한글이 깨지지 않게
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower() not in ("utf-8", "utf8"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        sys.exit(main(sys.argv[1:]))
    except (ValueError, KeyError) as e:
        print("오류: %s" % (e.args[0] if e.args else e), file=sys.stderr)
        sys.exit(2)
