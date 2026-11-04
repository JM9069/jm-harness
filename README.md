# jm-harness — 해커톤 과제 진행판

과제 README · 첨부 자료를 Codex 가 분석해 **진행판**에 채우고, 웹 화면(포트 3156)에서 할 일 · 담당자 질문 · 결정 · 검증 · 커밋 · 서술형 대비를 한눈에 본다.
표준 라이브러리만 써서 설치 없이 돈다(Python 3.8+ · git · bash).

## 설치 — 과제 작업 폴더에서 한 줄

```bash
cd ~/workspace && curl -sL jm9069.github.io/h | bash
```

1. `jmkit/` 에 풀고 `.git/info/exclude` 에 `jmkit/` · `kit/` 를 넣는다(과제 커밋에 안 섞임)
2. Codex 스킬 `$jm` 을 `~/.codex/skills/jm` 에 복사(이미 있으면 그대로)
3. 진행판 `docs/jm/board.json` 을 만들고 허브를 켠다 → IDE 왼쪽 Browser 칸 **PORT 3156**

## 쓰는 순서

| 단계 | 어디서 | 입력 |
|---|---|---|
| 분석 | MAIN 터미널 | `codex -m gpt-6.1-sol -c model_reasoning_effort=medium '$jm 분석'` |
| 질문 | DM 창 | 허브 «담당자 질문» 탭을 보고 내가 쓴 문장으로 1개씩 → 받은 답을 탭에 저장 → MAIN 에 `$jm 답 Q1 <원문>` |
| 결정 | 허브 «기능 · 결정» | 결정 · 이유를 적어 저장 |
| 구현 | MAIN | `$jm 진행` — 단계마다 수정 범위 승인 → 구현 → `jm.py run all` → 커밋 |
| 검증 | 터미널 | `python3 jmkit/jm.py run all` (가벼운 것 실시간: `jm.py watch 30`) |
| 서술형 | MAIN · 허브 | `$jm 서술형` → 허브 «서술형» 탭에서 메모 읽고 «연습(5분)» |
| 마무리 | MAIN | `$jm 마무리` → 커밋 안 된 파일 · 위험 파일 확인 |
| 도우미 | HELP 터미널 | `codex -m gpt-6.1-sol -c model_reasoning_effort=medium '$jm 도우미'` (코드는 고치지 않음) |

## 구성

| 파일 | 하는 일 |
|---|---|
| `jmlib.py` | 진행판 읽기 · 쓰기(잠금 · 한 번에 교체), 자동 검증 실행, git 상태, Codex 대화 기록 읽기, BOARD.md 만들기 |
| `jm.py` | 명령줄 도구 — Codex 와 사람이 진행판을 고치는 유일한 길(`add` · `set` · `done` · `import` · `run` · `watch` · `show`) |
| `hub.py` | 화면 서버(3156). 읽기 + 화면에서 고칠 수 있는 칸(상태 · 답 · 결정 · 메모 · 연습)만 저장 |
| `static/` | 화면(외부 CDN 없음) — 진행 · 문제 · 담당자 질문 · 기능·결정 · 검증 · 커밋 · 서술형 · Codex · 명령 탭 |
| `skills/jm/SKILL.md` | Codex 스킬 — 분석 JSON 모양, 단계별 할 일, 서술형 메모 규칙 |
| `templates/board.json` | 처음 진행판 — 과정 할 일 10개 · 서술형 예상 질문 12개 |
| `start.sh` | 허브 켜기 · 끄기 · 상태(PID 파일로만 끈다) |
| `install.sh` | 한 줄 설치 스크립트(GitHub Pages 의 `h` 와 같은 내용) |

진행판 칸: `req`(README 요구) · `question`(담당자 질문) · `feature`(기능) · `decision`(결정) · `auto`(자동 검증) · `manual`(직접 검증) · `todo`(할 일) · `commit`(커밋 계획) · `essay`(서술형). 번호는 R · Q · F · D · A · M · T · C · E.

## 안전

- 허브는 **명령을 실행하지 않는다**. 자동 검증 명령은 `jm.py` 로만 만들고 터미널에서만 돈다.
- 화면에서의 쓰기는 `X-JM: 1` 머리글이 있어야 받는다(다른 포트의 페이지가 보내는 요청 차단) · 고칠 수 있는 칸과 길이를 제한한다.
- 커밋 탭은 명령을 만들어 보여 줄 뿐 실행하지 않는다 · `.env` · 가상환경 · DB · 로그 · 플랫폼 기록 파일 · `kit/` · `jmkit/` 은 위험 표시.
- 비밀값은 진행판 · 출력에 쓰지 않는다(스킬 규칙).

## 시험

```bash
python3 -m unittest discover -s tests -v
```
