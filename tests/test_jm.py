"""jm 하네스 시험 — 표준 라이브러리 unittest 만 쓴다.
   python3 -m unittest discover -s tests -v   (윈도: py -3 -m unittest discover -s tests -v)
모든 시험은 임시 폴더에서만 돈다(실제 작업 폴더 · ~/.codex 와 무관)."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import hub  # noqa: E402
import jmlib  # noqa: E402

JM = [sys.executable, os.path.join(ROOT, "jm.py")]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, ".git"))  # find_root 이 여기를 작업 폴더로 보게
        self.env = dict(os.environ, JM_ROOT=self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def jm(self, *args):
        return subprocess.run(JM + list(args), cwd=self.root, env=self.env, capture_output=True, text=True,
                              encoding="utf-8")


class BoardTest(Base):
    def test_init_and_template_todos(self):
        r = self.jm("init")
        self.assertEqual(r.returncode, 0, r.stderr)
        b = jmlib.load(self.root)
        self.assertEqual(len(b["todo"]), 10)
        self.assertEqual(len(b["essay"]), 12)
        self.assertTrue(os.path.exists(os.path.join(self.root, "docs", "jm", "BOARD.md")))

    def test_add_set_done_numbers(self):
        self.jm("init")
        self.assertEqual(self.jm("add", "question", "text=키는 누구에게?", "stage=1").stdout.strip(), "Q1")
        self.assertEqual(self.jm("add", "question", "text=하루 경계는?").stdout.strip(), "Q2")
        self.jm("set", "Q2", "status=answered", "answer=자정 기준")
        q2 = jmlib.get(jmlib.load(self.root), "question", "Q2")
        self.assertEqual((q2["status"], q2["answer"]), ("answered", "자정 기준"))
        self.assertEqual(self.jm("done", "T1").returncode, 0)
        self.assertEqual(jmlib.get(jmlib.load(self.root), "todo", "T1")["status"], "done")

    def test_bad_status_and_unknown_id_are_errors(self):
        self.jm("init")
        self.assertEqual(self.jm("set", "T1", "status=finished").returncode, 2)
        self.assertEqual(self.jm("set", "Q99", "answer=x").returncode, 2)
        self.assertEqual(self.jm("done", "Q1").returncode, 2)  # 질문은 done 대상 아님

    def test_import_replace_renumbers(self):
        self.jm("init")
        data = {"title": "알람 현황판", "todo": [{"title": "가"}, {"title": "나"}],
                "auto": [{"title": "health", "cmd": "exit 0", "todo": "T2"}]}
        path = os.path.join(self.root, "a.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        r = self.jm("import", path, "--replace")
        self.assertEqual(r.returncode, 0, r.stderr)
        b = jmlib.load(self.root)
        self.assertEqual([t["id"] for t in b["todo"]], ["T1", "T2"])
        self.assertEqual(b["title"], "알람 현황판")
        self.assertEqual(len(b["essay"]), 12)  # 가져오지 않은 칸은 그대로


class CheckTest(Base):
    def test_pass_marks_todo_done_and_fail_reverts(self):
        self.jm("init")
        self.jm("add", "auto", "title=통과", "cmd=echo ready", "expect_text=ready", "todo=T5")
        r = self.jm("run", "all")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        b = jmlib.load(self.root)
        self.assertTrue(b["auto"][0]["last"]["ok"])
        self.assertEqual(jmlib.get(b, "todo", "T5")["status"], "done")
        # 같은 검증이 이제 실패하면 자동으로 완료됐던 할 일은 진행 중으로 돌아간다
        self.jm("set", "A1", "cmd=exit 3")
        self.assertEqual(self.jm("run", "A1").returncode, 1)
        b = jmlib.load(self.root)
        self.assertFalse(b["auto"][0]["last"]["ok"])
        self.assertEqual(b["auto"][0]["last"]["code"], 3)
        self.assertEqual(jmlib.get(b, "todo", "T5")["status"], "doing")

    def test_expect_text_missing_is_fail(self):
        self.jm("init")
        self.jm("add", "auto", "title=글자", "cmd=echo 500", "expect_text=200")
        self.assertEqual(self.jm("run").returncode, 1)


class DeliverTest(Base):
    def write_cfg(self, cfg):
        p = os.path.join(self.root, "docs", "jm", "deliver.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)

    def read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def test_auto_sections_follow_board_and_manual_text_survives(self):
        self.jm("init")
        self.write_cfg({"files": [{"path": "DECISIONS.md", "title": "판단 기록", "sections": [
            {"title": "담당자와 확인한 기준", "source": "answers"},
            {"title": "AI 제안과 내 판단", "source": "ai_judgments"},
            {"title": "내가 직접 쓴 회고", "mode": "manual", "hint": "직접 작성"},
            {"title": "남은 확인 사항", "source": "open_items"}]}]})
        self.jm("add", "question", "text=하루 경계는?")
        text = self.read("DECISIONS.md")
        self.assertIn("## 담당자와 확인한 기준", text)
        self.assertIn("하루 경계는?", text)  # 아직 답이 없으니 남은 확인 사항에
        # 직접 칸과 표시 밖에 사람이 쓴 글
        text = text.replace("<!-- 직접 작성 칸: 직접 작성 -->", "내가 쓴 회고 문장")
        with open(os.path.join(self.root, "DECISIONS.md"), "w", encoding="utf-8") as f:
            f.write(text + "\n맨 끝 메모\n")
        self.jm("set", "Q1", "status=answered", "answer=자정 기준")
        self.jm("add", "decision", "title=수집 주기", "recommend=5분", "chosen=5분", "reason=서버 부담")
        text = self.read("DECISIONS.md")
        self.assertIn("자정 기준", text)
        self.assertIn("| D1 | 수집 주기 | 5분 | 5분 | 채택 |", text)
        self.assertIn("내가 쓴 회고 문장", text)
        self.assertIn("맨 끝 메모", text)

    def test_note_source_and_unchanged_file_not_rewritten(self):
        self.jm("init")
        self.write_cfg({"files": [{"path": "docs/AI_COLLAB.md", "sections": [{"title": "협업 요약", "source": "note:ai"}]}]})
        self.jm("note", "ai", "분석은 Codex, 결정은 내가")
        self.assertIn("분석은 Codex, 결정은 내가", self.read("docs/AI_COLLAB.md"))
        mtime = os.path.getmtime(os.path.join(self.root, "docs", "AI_COLLAB.md"))
        self.jm("deliver")
        self.assertEqual(mtime, os.path.getmtime(os.path.join(self.root, "docs", "AI_COLLAB.md")))

    def test_bad_paths_and_sources_rejected(self):
        self.jm("init")
        self.write_cfg({"files": [{"path": "../outside.md", "sections": []}]})
        self.assertRaises(ValueError, jmlib.load_deliver, self.root)
        self.write_cfg({"files": [{"path": "kit/x.md", "sections": []}]})
        self.assertRaises(ValueError, jmlib.load_deliver, self.root)
        self.write_cfg({"files": [{"path": "A.md", "sections": [{"title": "x", "source": "rm -rf"}]}]})
        self.assertRaises(ValueError, jmlib.load_deliver, self.root)


class CodexLogTest(Base):
    def test_parse_skips_injected_and_filters_cwd(self):
        home = os.path.join(self.root, "codexhome")
        d = os.path.join(home, "sessions", "2026", "11", "05")
        os.makedirs(d)
        lines = [
            {"type": "session_meta", "payload": {"id": "abc12345xyz", "cwd": self.root}},
            {"type": "response_item", "payload": {"type": "message", "role": "user",
                                                  "content": [{"type": "input_text", "text": "<environment_context>…"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "user",
                                                  "content": [{"type": "input_text", "text": "$jm 분석"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "developer",
                                                  "content": [{"type": "input_text", "text": "비밀 지시"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                                                  "content": [{"type": "output_text", "text": "분석 끝"}]}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": 1234}}}},
        ]
        with open(os.path.join(d, "rollout-1.jsonl"), "w", encoding="utf-8") as f:
            for o in lines:
                f.write(json.dumps(o, ensure_ascii=False) + "\n")
        other = os.path.join(d, "rollout-2.jsonl")
        with open(other, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "session_meta", "payload": {"id": "zzz", "cwd": "/somewhere/else"}}) + "\n")
        out = jmlib.codex_sessions(self.root, codex_home=home)
        self.assertEqual(len(out), 1)
        self.assertEqual([m["text"] for m in out[0]["msgs"]], ["$jm 분석", "분석 끝"])
        self.assertEqual(out[0]["tokens"], 1234)


class GitTest(Base):
    def test_risky_files_flagged(self):
        os.rmdir(os.path.join(self.root, ".git"))
        subprocess.run(["git", "init", "-q", self.root], check=True)
        for name in (".env", "app.py", "data.db"):
            with open(os.path.join(self.root, name), "w") as f:
                f.write("x")
        g = jmlib.git_info(self.root)
        warn = {f["path"]: f["warn"] for f in g["files"]}
        self.assertTrue(warn[".env"])
        self.assertTrue(warn["data.db"])
        self.assertEqual(warn["app.py"], [])


class HubTest(Base):
    def setUp(self):
        super().setUp()
        self.jm("init")
        self.srv = hub.make_server(self.root, "127.0.0.1", 0, codex_home=os.path.join(self.root, "nohome"))
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def req(self, path, body=None, header=True):
        data = None if body is None else json.dumps(body).encode("utf-8")
        r = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), data=data)
        if data is not None:
            r.add_header("Content-Type", "application/json")
            if header:
                r.add_header("X-JM", "1")
        try:
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")

    def test_state_and_index(self):
        code, s = self.req("/api/state")
        self.assertEqual(code, 200)
        self.assertEqual(len(s["board"]["todo"]), 10)
        with urllib.request.urlopen("http://127.0.0.1:%d/" % self.port, timeout=5) as resp:
            self.assertIn("jm 허브", resp.read().decode("utf-8"))

    def test_update_allowed_field(self):
        code, _ = self.req("/api/item", {"section": "todo", "id": "T1", "fields": {"status": "done"}})
        self.assertEqual(code, 200)
        self.assertEqual(jmlib.get(jmlib.load(self.root), "todo", "T1")["status"], "done")

    def test_write_needs_header(self):
        code, _ = self.req("/api/item", {"section": "todo", "id": "T1", "fields": {"status": "done"}}, header=False)
        self.assertEqual(code, 403)

    def test_cannot_touch_commands_or_unknown_fields(self):
        self.jm("add", "auto", "title=x", "cmd=echo hi")
        self.assertEqual(self.req("/api/item", {"section": "auto", "id": "A1", "fields": {"cmd": "rm -rf /"}})[0], 400)
        self.assertEqual(self.req("/api/item", {"section": "todo", "id": "T1", "fields": {"cmd": "x"}})[0], 400)
        self.assertEqual(jmlib.get(jmlib.load(self.root), "auto", "A1")["cmd"], "echo hi")

    def test_no_command_endpoint_and_no_path_escape(self):
        self.assertEqual(self.req("/api/run", {})[0], 404)
        code, _ = self.req("/..%2F..%2Fjmlib.py")
        self.assertEqual(code, 404)


class SendTest(Base):
    UUID = "019a0000-1111-7222-8333-444455556666"

    def setUp(self):
        super().setUp()
        self.jm("init")
        self.home = os.path.join(self.root, "codexhome")
        d = os.path.join(self.home, "sessions", "2026", "11", "05")
        os.makedirs(d)
        with open(os.path.join(d, "rollout-a.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "session_meta", "payload": {"id": self.UUID, "cwd": self.root}}) + "\n")
        with open(os.path.join(self.home, "session_index.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"id": self.UUID, "thread_name": "MAIN"}) + "\n")
        self.srv = hub.make_server(self.root, "127.0.0.1", 0, codex_home=self.home, key="k3y12345")
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.sent = []
        self.orig = jmlib.send_to_codex
        jmlib.send_to_codex = lambda t, m: (self.sent.append((t, m)), {"ok": True, "code": 0, "out": ""})[1]

    def tearDown(self):
        jmlib.send_to_codex = self.orig
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def post(self, body, key="k3y12345"):
        r = urllib.request.Request("http://127.0.0.1:%d/api/send" % self.port, data=json.dumps(body).encode("utf-8"))
        r.add_header("Content-Type", "application/json")
        r.add_header("X-JM", "1")
        if key is not None:
            r.add_header("X-JM-Key", key)
        try:
            with urllib.request.urlopen(r, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_session_name_shown(self):
        s = jmlib.codex_sessions(self.root, codex_home=self.home)
        self.assertEqual((s[0]["uuid"], s[0]["name"]), (self.UUID, "MAIN"))

    def test_send_needs_right_key(self):
        self.assertEqual(self.post({"threads": [self.UUID], "message": "hi"}, key=None)[0], 401)
        self.assertEqual(self.post({"threads": [self.UUID], "message": "hi"}, key="wrong")[0], 401)
        self.assertEqual(self.sent, [])

    def test_send_only_to_this_workspace_sessions(self):
        code, j = self.post({"threads": [self.UUID, "019a0000-0000-7000-8000-000000000000"], "message": "$jm 진행"})
        self.assertEqual(code, 200)
        self.assertEqual(self.sent, [(self.UUID, "$jm 진행")])
        self.assertFalse(j["ok"])  # 다른 세션은 거부되어 일부 실패

    def test_lockout_after_many_wrong_keys(self):
        for _ in range(hub.MAX_KEY_FAILS):
            self.post({"threads": [self.UUID], "message": "x"}, key="bad")
        self.assertEqual(self.post({"threads": [self.UUID], "message": "x"})[0], 429)

    def test_send_validation(self):
        self.assertRaises(ValueError, self.orig, "not-a-uuid", "hi")
        self.assertRaises(ValueError, self.orig, self.UUID, "")
        r = self.orig(self.UUID, "hi", codex_bin="no-such-codex-binary-xyz")
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()
