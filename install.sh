#!/usr/bin/env bash
# ======= jm 하네스 설치 — 작업 폴더에서: curl -sL jm9069.github.io/j | bash =======
# 하는 일: jmkit/ 에 풀기 → kit 이 커밋에 안 섞이게 exclude → $jm 스킬 복사 → 진행판 만들기 → 허브(3156) 켜기
# 과제 파일은 건드리지 않는다. 이미 있는 jmkit/ · 스킬은 덮어쓰지 않는다.
set -eu
REPO="${JM_REPO:-JM9069/jm-harness}"
BRANCH="${JM_BRANCH:-main}"
DEST="${JM_DIR:-jmkit}"
URL="${JM_URL:-https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz}"

if [ -e "$DEST" ]; then
    # 새 판으로 바꾸기: curl -sL jm9069.github.io/j | JM_UPDATE=1 bash  (진행판 docs/jm 은 그대로 남는다)
    if [ "${JM_UPDATE:-0}" = "1" ] && [ -f "$DEST/jm.py" ]; then
        bash "$DEST/start.sh" stop >/dev/null 2>&1 || true
        rm -rf "$DEST"
        echo "옛 $DEST 지움(진행판 docs/jm 은 유지)"
    else
        echo "중단: $PWD/$DEST 가 이미 있음 — 새 판으로 바꾸려면: curl -sL jm9069.github.io/j | JM_UPDATE=1 bash"; exit 1
    fi
fi

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if ! curl -fsSL --connect-timeout 15 "$URL" -o "$TMP/jm.tar.gz"; then
    echo "받기 실패: $URL (네트워크 · 저장소 공개 여부 확인)"; exit 1
fi
mkdir "$TMP/x"
tar xzf "$TMP/jm.tar.gz" -C "$TMP/x" --strip-components=1
mv "$TMP/x" "$DEST"
echo "설치: $PWD/$DEST · 파일 $(find "$DEST" -type f | wc -l)개"

# 과제 커밋에 하네스가 섞이지 않게(이 컴퓨터에만 적용되는 무시 목록)
if [ -d .git ]; then
    touch .git/info/exclude
    for p in "$DEST/" "kit/"; do grep -qxF "$p" .git/info/exclude || echo "$p" >> .git/info/exclude; done
    echo "git 무시 목록: $DEST/ · kit/"
fi

# Codex 가 읽는 곳에 $jm 스킬 복사
SK="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$SK"
if [ -e "$SK/jm" ] && ! grep -q "jm 하네스" "$SK/jm/SKILL.md" 2>/dev/null; then
    echo "다른 jm 스킬이 이미 있음 — 그대로 둠"
else
    rm -rf "$SK/jm" && cp -r "$DEST/skills/jm" "$SK/jm" && echo "스킬 → $SK/jm (Codex 를 새로 띄우면 반영)"
fi

python3 "$DEST/jm.py" init
bash "$DEST/start.sh" || echo "허브를 못 켰음 — 터미널에서 bash $DEST/start.sh"

cat <<EOF

다음(새 터미널 탭마다 붙여 넣기 · Ctrl+Shift+V):
  MAIN : codex -m gpt-6.1-sol -c model_reasoning_effort=medium '\$jm 분석'
  HELP : codex -m gpt-6.1-sol -c model_reasoning_effort=medium '\$jm 도우미'
IDE 왼쪽 Browser 칸 PORT 3156 → 원형 화살표. 자동 검증: python3 $DEST/jm.py run all
EOF
