---
name: jm
description: jm 하네스 — 과제 README · 첨부 자료를 분석해 진행판(docs/jm/board.json)을 채우고(요구 · 담당자 질문 · 기능 · 결정 · 자동/직접 검증 · 커밋 계획 · 할 일), 제출 md 를 진행판에서 자동 갱신하게 등록하며, 끝에는 서술형 대비 메모를 실제 코드 근거로 쓴다. "$jm 분석" · "$jm 제출문서 <지시>" · "$jm 답 Q번호 <원문>" · "$jm 진행" · "$jm 서술형" · "$jm 마무리" · "$jm 도우미" 로 부른다.
---

# jm — 진행판으로 과제 풀기

- 진행판은 `docs/jm/board.json`, 사람이 읽는 판은 `docs/jm/BOARD.md`(자동). 화면은 허브(포트 3156)가 2초마다 보여 준다.
- **진행판은 반드시 도구로만 고친다**: `python3 jmkit/jm.py ...` (JSON 을 손으로 고치지 않는다 · 잠금 · 번호를 도구가 맡는다)
  - `add <칸> 키=값 ...` → 번호 출력 · `set <번호> 키=값 ...` · `done <번호>` · `import <파일> [--replace]` · `run all` · `show`
- 하네스 폴더(`jmkit/`)와 다른 키트(`kit/`)는 과제 커밋에 넣지 않는다. 서버는 내가 띄우지 않고 유저 터미널 명령 한 줄을 준다(Codex 샌드박스는 소켓을 막는다).
- 비밀값(키 · 토큰)은 진행판 · 코드 · 출력 · 커밋에 쓰지 않는다. 확인은 «있음/없음»만.
- 담당자(업무 페르소나) 답을 **지어내지 않는다**. 모르면 질문(Q)으로 남긴다. 질문은 초안만 쓰고, 보내는 문장은 유저가 직접 고쳐 쓴다.

## $jm 분석 — 과제를 받은 직후 (코드는 쓰지 않는다)
1. 읽기: 루트 README 전체 · 첨부(uploads 등) 파일 목록 · 크기 · 형식 · 앞부분. CSV 는 열 · 빈칸 · 값 종류를 **세어서** 확인(눈으로 훑지 않는다). API 명세가 있으면 경로 · 인증 · 오류 코드.
2. 아래 모양의 JSON 을 `docs/jm/analysis.json` 에 쓰고 `python3 jmkit/jm.py import docs/jm/analysis.json` (처음이면 `--replace` 로 todo 를 과제용으로 바꾼다 — 기본 todo 의 과정 단계도 포함해 다시 쓴다)
3. 채팅 보고는 짧게: 문제 한 줄 · 담당자에게 먼저 물을 것 3개 · 유저가 정할 것 · 다음 할 일. 자세한 건 «허브 PORT 3156 의 각 탭» 을 가리킨다.

```json
{
 "title": "과제 제목",
 "summary": "무엇을 · 누구를 위해 · 최종 결과가 무엇인지 3~5줄(쉬운 말)",
 "deliverables": ["제출 파일 · 형식(README 원문 기준)"],
 "stack": "쓸 언어 · 프레임워크와 이유 한 줄",
 "req":      [{"text": "README 요구 문장 원문 그대로", "where": "어느 기능 · 결정 · 검증에 반영(F1 · D2 · A3)"}],
 "question": [{"text": "담당자에게 물을 것(업무 말로, 한 번에 한 가지)", "stage": 1, "why": "답에 따라 무엇이 바뀌나"}],
 "feature":  [{"title": "기능", "priority": "must|should|wont|red", "note": "근거(R번호 · 담당자) · 안 하면 왜 안 하나"}],
 "decision": [{"title": "정할 것", "options": ["안1", "안2"], "recommend": "AI 추천안(이유)", "who": "담당자|유저", "rejected": "버린 안과 이유(정한 뒤)"}],
 "auto":     [{"title": "확인할 것(C 기준)", "cmd": "bash -lc 로 돌 명령", "expect_code": 0, "expect_text": "출력에 있어야 할 글자(선택)", "todo": "T번호(통과하면 완료)", "watch": false, "timeout": 60}],
 "manual":   [{"title": "사람이 봐야 하는 것", "how": "어디서 무엇을 보고 무엇이면 통과"}],
 "todo":     [{"title": "순서대로 할 일", "kind": "process|build", "check": "끝났다는 증거"}],
 "commit":   [{"when": "어느 단계가 끝나면", "files": "파일 경로(이름으로)", "message": "[단계] 무엇 - 왜"}]
}
```

- question: 1단계(업무 흐름 · 사실 · 용어 · 키 요청) → 2단계(세는 기준 · 경계 · 실패 시 동작) 순 · 결과를 크게 바꾸는 것부터. 데이터 · 명세로 알 수 있는 건 질문하지 말고 직접 확인.
- decision: 담당자 몫(업무 기준)과 유저 몫(화면 · 범위 · 기술)을 `who` 로 가른다. 추천을 한 줄로.
- auto: 성공 기준마다 하나. 바깥에서 보이는 결과로(응답 코드 · 본문 · 행 수 · 파일 내용). 예: `curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/api/health` + `expect_text: "200"`, `python3 -m pytest -q tests` · 서버가 필요하면 그 사실을 title 에 적는다. 가벼운 health 는 `watch: true`.
- manual: 화면 모양 · 문구 · 담당자 의도와 맞는지처럼 명령으로 못 보는 것만.
- todo: 세로 조각(입력 → 처리 → 출력이 한 바퀴 도는 얇은 기능) 먼저 · 덜 위험한 것 → 위험한 것. 구현 todo 는 `kind: build` 이고 검증(auto 의 `todo`)과 연결한다.
- commit: 단계가 끝날 때마다 작게. `git add -A` · `git add .` 금지(파일 이름으로).

## $jm 제출문서 <README 의 제출 문서 지시 원문>
- README(또는 유저가 붙여 넣은 지시)가 요구하는 md 파일마다 파일 이름 · 칸(제목) · 칸마다 적을 내용을 그대로 옮겨 `docs/jm/deliver.json` 을 쓴다 → `python3 jmkit/jm.py deliver`
- 칸마다 내용 출처(source)를 고른다. 진행판이 바뀔 때마다 자동으로 다시 써진다:
  - `summary` 문제 요약 · `deliverables` 제출물 · `requirements` README 요구
  - `answers` 담당자와 확인한 기준(답 받은 질문) · `questions_open` 아직 못 물은 것 · `open_items` 남은 확인 사항(질문 + 미정 결정 + 남은 할 일)
  - `decisions` 결정 · 이유 · 선택지 · 버린 안(`rejected` 칸) · `ai_judgments` AI 제안(recommend) ↔ 내 결정(chosen) · 채택 여부
  - `features` 기능 · `unfinished` 구현 안 됨 · 안 함과 이유 · `checks` 자동 + 직접 검증 결과 · `todos` 할 일 · `commits` 커밋 기록 · `prompts` 내가 Codex 에 한 요청(대화 기록)
  - `note:이름` 서술형 글 칸 — `python3 jmkit/jm.py note 이름 "사실만 담은 글"` 로 채운다 · `text:고정 글`
- **README 가 «본인이 직접 작성» 을 요구한 칸은 `"mode": "manual"` 로** 둔다(자동으로 안 씀 · `hint` 에 무엇을 쓸지). 그 칸에 넣을 재료는 채팅으로만 정리해 준다.
- 시험이 **양식 파일을 이미 준 경우**(예: HOW_TO_RUN.md · AI_COLLABORATION.md): 칸 제목을 양식의 `##` 제목과 **글자 그대로**(번호 포함, 예 `1. 실행 방법`) 적는다 → 제목 바로 아래에 자동 칸이 들어가고 `(답변)` 자리 글은 걷힌다 · 양식의 원래 줄은 남는다. 실행 방법 · 주소 · 설정 · 저장처럼 사실 칸은 `note:` 로, 미구현은 `unfinished`, 테스트는 `checks`.
- 양식 머리말이 «직접 겪은 내용으로 답해 주세요» 처럼 본인 경험을 요구하면(AI_COLLABORATION 류) 그 칸들은 `manual` — 대신 채팅으로 재료(실제 겪은 실패 · 버린 안 · 결정 번호)만 정리해 준다.
- 칸 제목 · 파일 이름은 README 원문 그대로. 자동 칸은 `<!-- jm:begin … -->` 표시 안만 바뀌고, 표시 밖에 사람이 쓴 글은 그대로 남는다.

```json
{"files": [{"path": "DECISIONS.md", "title": "판단 기록", "sections": [
  {"title": "판단 근거", "source": "decisions"},
  {"title": "담당자와 확인한 기준", "source": "answers"},
  {"title": "남은 확인 사항", "source": "open_items"},
  {"title": "AI 협업 회고", "mode": "manual", "hint": "AI 에게 맡긴 것 · 직접 판단한 것을 내 말로"}]}]}
```

## $jm 답 Q번호 <담당자 답 원문>
- `set Q번호 status=answered answer="원문"` → 그 답이 바꾸는 기능 · 결정 · 검증 · 할 일을 고친다(`set` · `add`) → 새로 생긴 애매함은 새 질문으로 → 바뀐 번호만 한 줄씩 보고.

## $jm 진행 — 구현 단계마다 (MAIN)
- 시작할 때: 지금 할 todo 를 `set T번호 status=doing` · 수정 범위(파일 · 함수)를 채팅에 적고 유저 승인 뒤 구현.
- 끝날 때: 관련 auto 를 만들거나 고치고 `python3 jmkit/jm.py run all` → 실패는 고치고 같은 검증 재통과 · 기능 `done` · 커밋은 commit 계획대로(파일 이름으로) 하고 `done C번호`.
- «다 됐다» 는 `jm.py run` 결과(종료코드 · 출력)로만 말한다. 못 돌린 것은 «미검증» 으로 남긴다.

## $jm 서술형 — 마감 40분 전쯤
- essay 칸(E1 ~ E12)마다 `set E번호 answer="..." evidence="파일:함수"` — **실제 제출물에서** 확인한 사실만: 파일 · 모듈 · 함수 이름, 데이터 흐름, 결정과 이유(D 번호), 검증 결과(A 번호), 실패 · timeout 때 동작, 미구현과 이유.
- 답 메모는 유저가 5분 안에 자기 말로 쓸 수 있게 3~6줄 · 핵심어 먼저. 일반론 · 지어낸 내용 금지.

## $jm 마무리 — 마감 15분 전
- `run all` · 커밋 안 된 파일 점검(위험 표시: .env · 가상환경 · DB · 로그 · 기록 파일 · kit/jmkit) · run.sh 냉시동 명령 한 줄 · DECISIONS.md(판단 근거 · 담당자와 확인한 기준 · 남은 확인 사항)가 있는지 · 남은 todo 를 보고.

## $jm 도우미 — HELP 세션 (저장소의 코드는 고치지 않는다)
- 유저의 질문 문장 다듬기(한 번에 한 가지 · 업무 말), 코드 · 구조 설명(약자는 풀어서), 서술형 답 연습 상대. 진행판은 읽기만 하고, 바꿀 것이 생기면 MAIN 에 보낼 한 줄을 써 준다.
