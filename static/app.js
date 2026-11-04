// jm 허브 화면 — 2초마다 /api/state 를 읽어 다시 그린다. 고칠 수 있는 칸만 POST /api/item 으로 저장.
'use strict';
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const NEXT = { todo: ['todo', 'doing', 'done'], feature: ['todo', 'doing', 'done', 'wont'], manual: ['todo', 'done', 'fail'], commit: ['todo', 'done'], question: ['draft', 'asked', 'answered'] };
const LABEL = { todo: '할 일', doing: '진행 중', done: '완료', wont: '안 만듦', draft: '초안', asked: '물어봄', answered: '답 받음', open: '미정', decided: '결정', fail: '실패' };
const PRIO = { must: '⭐ 필수', should: '🟢 하면 좋음', wont: '🟠 안 함', red: '🔴 금지' };
const CMDS = [
  ['키트 설치(작업 폴더에서, 허브까지 켜짐)', 'cd ~/workspace && curl -sL jm9069.github.io/h | bash'],
  ['허브 다시 켜기 · 끄기 · 상태', 'bash ~/workspace/jmkit/start.sh  # stop · status'],
  ['MAIN(설계 + 구현) — 새 터미널 탭', "codex -m gpt-6.1-sol -c model_reasoning_effort=medium '$jm 분석'"],
  ['HELP(질문 다듬기 · 서술형 · 설명) — 새 터미널 탭', "codex -m gpt-6.1-sol -c model_reasoning_effort=medium '$jm 도우미'"],
  ['자동 검증 전부 실행', 'python3 ~/workspace/jmkit/jm.py run all'],
  ['가벼운 검증 실시간 감시(30초마다)', 'python3 ~/workspace/jmkit/jm.py watch 30'],
  ['진행판 요약(터미널)', 'python3 ~/workspace/jmkit/jm.py show'],
];
let S = null, tab = localStorage.getItem('jm.tab') || 'prog', lastKey = '', practice = null;

function editing() {
  const a = document.activeElement;
  return a && (a.tagName === 'TEXTAREA' || (a.tagName === 'INPUT' && a.type === 'text')) && $('#view').contains(a);
}
async function load(force) {
  try {
    const r = await fetch('api/state', { cache: 'no-store' });
    S = await r.json();
  } catch (e) { $('#clock').textContent = '서버 연결 끊김'; return; }
  $('#clock').textContent = '갱신 ' + S.now;
  $('#title').textContent = S.board.title || '';
  const dirty = (S.git.files || []).length;
  $('#dirty').innerHTML = S.git.repo ? (dirty ? `<span class="pill warn">커밋 안 된 파일 ${dirty}</span>` : '<span class="pill ok">커밋 깨끗</span>') : '';
  const key = JSON.stringify([S.board, S.git, (S.codex || []).map(c => [c.file, c.msgs.length])]);
  if (force || (key !== lastKey && !editing() && !practice)) { lastKey = key; render(); }
}
async function save(section, id, fields) {
  const r = await fetch('api/item', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-JM': '1' }, body: JSON.stringify({ section, id, fields }) });
  const j = await r.json();
  if (!j.ok) alert('저장 실패: ' + j.error);
  await load(true);
}
const pill = st => `<span class="pill s-${esc(st)}">${esc(LABEL[st] || st || '-')}</span>`;
const stBtn = (sec, x) => `<button class="pill st s-${esc(x.status)}" data-act="cycle" data-sec="${sec}" data-id="${esc(x.id)}" title="눌러서 상태 바꾸기">${esc(LABEL[x.status] || x.status)}</button>`;
const count = (arr, f) => (arr || []).filter(f).length;
function stat(name, done, total, extra = '') {
  const pct = total ? Math.round(done * 100 / total) : 0;
  return `<div class="card stat">${name}<b>${done} / ${total}</b>${extra}<div class="bar"><i style="width:${pct}%"></i></div></div>`;
}
function empty(what, how) { return `<div class="hint">${what} 아직 없음 — ${how}</div>`; }

// ======= 탭 =======
const VIEWS = {
  prog() {
    const b = S.board, auto = b.auto || [];
    let h = '<div class="grid">' +
      stat('할 일', count(b.todo, x => x.status === 'done'), (b.todo || []).length) +
      stat('담당자 답', count(b.question, x => x.status === 'answered'), (b.question || []).length) +
      stat('결정', count(b.decision, x => x.status === 'decided'), (b.decision || []).length) +
      stat('필수 기능', count(b.feature, x => x.priority === 'must' && x.status === 'done'), count(b.feature, x => x.priority === 'must')) +
      stat('자동 검증 통과', count(auto, x => x.last && x.last.ok), auto.length, count(auto, x => x.last && !x.last.ok) ? ` <span class="pill bad">실패 ${count(auto, x => x.last && !x.last.ok)}</span>` : '') +
      stat('직접 검증', count(b.manual, x => x.status === 'done'), (b.manual || []).length) + '</div>';
    h += '<h2>할 일 — 위에서부터 차례로</h2>';
    h += '<table><tr><th>번호</th><th>상태</th><th>할 일</th><th>끝 확인</th></tr>' + (b.todo || []).map(x =>
      `<tr><td class="id">${esc(x.id)}</td><td>${stBtn('todo', x)}${x.by ? `<div class="small muted">${esc(x.by)}</div>` : ''}</td><td>${esc(x.title)}${x.kind === 'build' ? ' <span class="pill">구현</span>' : ''}</td><td class="small muted">${esc(x.check || '')}${x.auto ? ' · ' + esc(x.auto) : ''}</td></tr>`).join('') + '</table>';
    const nextT = (b.todo || []).find(x => x.status !== 'done');
    if (nextT) h = `<div class="hint">다음 할 일: <b>${esc(nextT.id)} ${esc(nextT.title)}</b></div>` + h;
    return h;
  },
  prob() {
    const b = S.board;
    if (!b.summary && !(b.req || []).length) return empty('문제 정리가', 'MAIN 에서 «$jm 분석» 을 실행하세요');
    let h = `<div class="card"><b>${esc(b.title)}</b><p>${esc(b.summary).replace(/\n/g, '<br>')}</p>` +
      (b.stack ? `<div class="small muted">기술: ${esc(b.stack)}</div>` : '') + '</div>';
    if ((b.deliverables || []).length) h += '<h2>제출물</h2><div class="card">' + b.deliverables.map(d => '• ' + esc(d)).join('<br>') + '</div>';
    h += '<h2>README 요구 문장</h2><table><tr><th>번호</th><th>원문</th><th>어디에 반영</th></tr>' +
      (b.req || []).map(x => `<tr><td class="id">${esc(x.id)}</td><td>${esc(x.text)}</td><td class="small muted">${esc(x.where || '')}</td></tr>`).join('') + '</table>';
    return h;
  },
  ques() {
    const q = S.board.question || [];
    if (!q.length) return empty('담당자 질문이', '«$jm 분석» 이 확인할 것을 뽑아 줍니다');
    return '<div class="hint">쉬운 것(1단계)부터 한 번에 하나씩, 문장은 내가 직접 써서 DM 으로 보낸다. 받은 답은 아래에 붙여 넣고 저장 → MAIN 에 «$jm 답 Q번호» 로 반영.</div>' +
      q.map(x => `<div class="card"><div class="row"><span class="id">${esc(x.id)}</span>${stBtn('question', x)}<span class="pill">${esc(x.stage ? x.stage + '단계' : '')}</span><b>${esc(x.text)}</b></div>` +
        (x.why ? `<div class="small muted">답에 따라 바뀌는 것: ${esc(x.why)}</div>` : '') +
        `<textarea data-field="answer" data-sec="question" data-id="${esc(x.id)}" placeholder="담당자 답 원문">${esc(x.answer || '')}</textarea>` +
        `<div class="row"><button class="btn" data-act="saveq" data-id="${esc(x.id)}">답 저장</button></div></div>`).join('');
  },
  feat() {
    const b = S.board;
    let h = '<h2>기능</h2>';
    h += (b.feature || []).length ? '<table><tr><th>번호</th><th>상태</th><th>기능</th><th>중요도</th><th>메모</th></tr>' + b.feature.map(x =>
      `<tr><td class="id">${esc(x.id)}</td><td>${stBtn('feature', x)}</td><td>${esc(x.title)}</td><td>${esc(PRIO[x.priority] || x.priority || '')}</td><td class="small muted">${esc(x.note || '')}</td></tr>`).join('') + '</table>'
      : empty('기능 목록이', '«$jm 분석»');
    h += '<h2>정해야 할 것</h2>';
    h += (b.decision || []).length ? b.decision.map(x => `<div class="card"><div class="row"><span class="id">${esc(x.id)}</span>${pill(x.status)}<b>${esc(x.title)}</b></div>` +
      (x.options ? `<div class="small muted">선택지: ${esc(Array.isArray(x.options) ? x.options.join(' / ') : x.options)}</div>` : '') +
      (x.recommend ? `<div class="small">추천: ${esc(x.recommend)}</div>` : '') +
      (x.who ? `<div class="small muted">누가 정함: ${esc(x.who)}</div>` : '') +
      `<div class="row"><input type="text" data-field="chosen" data-id="${esc(x.id)}" placeholder="결정" value="${esc(x.chosen || '')}"></div>` +
      `<textarea data-field="reason" data-id="${esc(x.id)}" placeholder="이유(서술형에서 그대로 쓴다)">${esc(x.reason || '')}</textarea>` +
      `<div class="row"><button class="btn" data-act="saved" data-id="${esc(x.id)}">결정 저장</button></div></div>`).join('') : empty('결정할 것이', '«$jm 분석»');
    return h;
  },
  veri() {
    const b = S.board;
    let h = '<div class="hint">자동 검증은 터미널에서 실행한다: <code>python3 ~/workspace/jmkit/jm.py run all</code> · 통과하면 연결된 할 일이 저절로 완료된다. (이 화면은 명령을 실행하지 않는다)</div>';
    h += '<h2>자동 검증 — 명령으로 확인</h2>';
    h += (b.auto || []).length ? '<table><tr><th>번호</th><th>결과</th><th>확인</th><th>명령</th></tr>' + b.auto.map(x => {
      const l = x.last;
      const res = l ? `<span class="pill ${l.ok ? 'ok' : 'bad'}">${l.ok ? '통과' : '실패'}</span><div class="small muted">${esc(l.at)} · ${esc(l.sec)}초</div>` : '<span class="pill">안 돌림</span>';
      return `<tr><td class="id">${esc(x.id)}</td><td>${res}</td><td>${esc(x.title)}${x.todo ? ` <span class="small muted">→ ${esc(x.todo)}</span>` : ''}${x.watch ? ' <span class="pill">감시</span>' : ''}` +
        (l && l.out ? `<details><summary class="small muted">출력</summary><pre>${esc(l.out)}</pre></details>` : '') + `</td><td><code>${esc(x.cmd)}</code></td></tr>`;
    }).join('') + '</table>' : empty('자동 검증이', '«$jm 분석» 이 C 기준마다 명령을 만든다');
    h += '<h2>직접 검증 — 내 눈으로 확인</h2>';
    h += (b.manual || []).length ? '<table><tr><th>번호</th><th>상태</th><th>확인</th><th>방법</th></tr>' + b.manual.map(x =>
      `<tr><td class="id">${esc(x.id)}</td><td>${stBtn('manual', x)}</td><td>${esc(x.title)}</td><td class="small">${esc(x.how || '')}</td></tr>`).join('') + '</table>' : empty('직접 검증이', '«$jm 분석»');
    return h;
  },
  comm() {
    const b = S.board, g = S.git;
    let h = '<h2>커밋 계획</h2>';
    h += (b.commit || []).length ? '<table><tr><th>번호</th><th>상태</th><th>언제</th><th>파일</th><th>메시지</th></tr>' + b.commit.map(x =>
      `<tr><td class="id">${esc(x.id)}</td><td>${stBtn('commit', x)}</td><td>${esc(x.when || '')}</td><td class="small"><code>${esc(x.files || '')}</code></td><td>${esc(x.message || '')}</td></tr>`).join('') + '</table>' : empty('커밋 계획이', '«$jm 분석»');
    if (!g.repo) return h + '<div class="hint">git 저장소가 아님</div>';
    h += `<h2>커밋 안 된 파일 (${g.files.length}) · 브랜치 ${esc(g.branch)}</h2>`;
    if (g.files.length) {
      h += '<div class="hint">체크한 파일로 커밋 명령을 만든다(복사해서 터미널에). git add -A · git add . 는 쓰지 않는다.</div><table>' + g.files.map((f, i) =>
        `<tr><td><input type="checkbox" data-git="${i}" ${f.warn.length ? '' : 'checked'}></td><td><code>${esc(f.st)}</code></td><td><code>${esc(f.path)}</code></td><td>${f.warn.map(w => `<span class="pill bad">${esc(w)}</span>`).join(' ')}</td></tr>`).join('') + '</table>' +
        '<div class="row"><input type="text" id="cmsg" placeholder="[섹션] 무엇 - 왜"><button class="btn ghost" data-act="mkcommit">명령 만들기</button></div><pre id="cmdout" class="muted">파일을 고르고 메시지를 쓴 뒤 «명령 만들기»</pre>';
    } else h += '<div class="card ok">모두 커밋됨</div>';
    h += '<h2>최근 커밋</h2><div class="card">' + (g.log || []).map(c => `<code>${esc(c.hash)}</code> ${esc(c.msg)}`).join('<br>') + '</div>';
    return h;
  },
  essa() {
    const e = S.board.essay || [];
    if (practice) return practiceView();
    return '<div class="hint">제출 후 서술형은 6문항 · 문항당 5분 · 붙여넣기 불가 · AI 금지. «$jm 서술형» 으로 답 메모를 실제 코드 근거로 채우고, 읽은 뒤 «연습» 으로 직접 써 본다.</div>' +
      e.map(x => `<div class="card"><div class="row"><span class="id">${esc(x.id)}</span><span class="pill">${esc(x.cat || '')}</span><b>${esc(x.q)}</b><span class="small muted">연습 ${(x.practice || []).length}회</span></div>` +
        `<details ${x.answer ? '' : 'open'}><summary class="small muted">답 메모 · 근거</summary><textarea data-field="answer" data-id="${esc(x.id)}" placeholder="«$jm 서술형» 이 채우거나 직접 쓴다">${esc(x.answer || '')}</textarea>` +
        (x.evidence ? `<div class="small muted">근거: ${esc(x.evidence)}</div>` : '') +
        `<div class="row"><button class="btn ghost" data-act="savee" data-id="${esc(x.id)}">메모 저장</button></div></details>` +
        `<div class="row"><button class="btn" data-act="practice" data-id="${esc(x.id)}">연습(5분)</button></div></div>`).join('');
  },
  codx() {
    const cs = S.codex || [];
    if (!cs.length) return empty('작업 폴더에서 띄운 Codex 대화가', '터미널에서 codex 를 띄우면 여기에 보인다(최근 12시간)');
    return cs.map(c => `<div class="card"><div class="row"><b>세션 ${esc(c.id || c.file)}</b><span class="small muted">${esc(c.cwd)}</span>${c.tokens ? `<span class="pill">토큰 ${Number(c.tokens).toLocaleString()}</span>` : ''}</div>` +
      c.msgs.slice().reverse().map(m => `<div class="msg ${m.role}"><div class="small muted">${m.role === 'user' ? '🚹 나' : '🤖 Codex'} · ${esc((m.ts || '').slice(11, 19))}</div><div>${esc(m.text).replace(/\n/g, '<br>')}</div></div>`).join('') + '</div>').join('');
  },
  cmds() {
    return '<div class="hint">IDE 터미널 붙여넣기는 Ctrl+Shift+V. 서버는 Codex 가 아니라 터미널 탭에서 직접 띄운다(Codex 안에서는 소켓이 막힘).</div>' +
      CMDS.map(([t, c], i) => `<div class="card"><div class="row"><b>${esc(t)}</b><button class="btn ghost" data-act="copy" data-i="${i}">복사</button></div><pre>${esc(c)}</pre></div>`).join('');
  },
};

function practiceView() {
  const x = (S.board.essay || []).find(e => e.id === practice.id);
  const left = Math.max(0, practice.end - Date.now()), done = practice.submitted || left === 0;
  const mm = String(Math.floor(left / 60000)).padStart(1, '0'), ss = String(Math.floor(left / 1000) % 60).padStart(2, '0');
  return `<div class="card"><div class="row"><span class="id">${esc(x.id)}</span><b>${esc(x.q)}</b></div>` +
    `<div class="row"><span class="timer ${left < 60000 ? 'low' : ''}" id="tmr">${mm}:${ss}</span><span class="small muted">붙여넣기 막힘 · 시험처럼 직접 입력</span></div>` +
    `<textarea id="ptext" style="min-height:180px" ${done ? 'readonly' : ''}>${esc(practice.text || '')}</textarea>` +
    `<div class="row">${done ? '' : '<button class="btn" data-act="psubmit">제출</button>'}<button class="btn ghost" data-act="pclose">닫기</button></div>` +
    (done ? `<h2>내 답 메모와 비교</h2><pre>${esc(x.answer || '(메모 없음 — «$jm 서술형» 으로 채우기)')}</pre>` : '') + '</div>';
}
function tick() {
  if (!practice || practice.submitted) return;
  const t = $('#ptext');
  if (t) practice.text = t.value;
  if (Date.now() >= practice.end) { submitPractice(); return; }
  const el = $('#tmr');
  if (el) { const left = practice.end - Date.now(); el.textContent = Math.floor(left / 60000) + ':' + String(Math.floor(left / 1000) % 60).padStart(2, '0'); el.classList.toggle('low', left < 60000); }
}
async function submitPractice() {
  const x = (S.board.essay || []).find(e => e.id === practice.id);
  const t = $('#ptext'); if (t) practice.text = t.value;
  practice.submitted = true;
  const d = new Date(), p2 = n => String(n).padStart(2, '0');
  const at = `${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`;
  const list = (x.practice || []).concat([{ at, text: practice.text || '' }]).slice(-50);
  await save('essay', x.id, { practice: list });
  render();
}

function render() {
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === tab));
  $('#view').innerHTML = S ? VIEWS[tab]() : '';
}

document.addEventListener('click', async ev => {
  const t = ev.target.closest('[data-tab],[data-act]');
  if (!t) return;
  if (t.dataset.tab) { tab = t.dataset.tab; localStorage.setItem('jm.tab', tab); practice = null; render(); return; }
  const act = t.dataset.act, id = t.dataset.id;
  const val = (f, sec) => { const el = document.querySelector(`[data-field="${f}"][data-id="${id}"]${sec ? `[data-sec="${sec}"]` : ''}`); return el ? el.value : ''; };
  if (act === 'cycle') {
    const sec = t.dataset.sec, item = S.board[sec].find(x => x.id === id), order = NEXT[sec];
    await save(sec, id, { status: order[(order.indexOf(item.status) + 1) % order.length] });
  } else if (act === 'saveq') {
    const answer = val('answer', 'question');
    await save('question', id, answer.trim() ? { answer, status: 'answered' } : { answer });
  } else if (act === 'saved') {
    const chosen = val('chosen'), reason = val('reason');
    await save('decision', id, { chosen, reason, status: chosen.trim() ? 'decided' : 'open' });
  } else if (act === 'savee') {
    await save('essay', id, { answer: val('answer') });
  } else if (act === 'practice') {
    practice = { id, end: Date.now() + 5 * 60000, text: '' }; render();
  } else if (act === 'psubmit') {
    await submitPractice();
  } else if (act === 'pclose') {
    practice = null; render();
  } else if (act === 'mkcommit') {
    const files = [...document.querySelectorAll('[data-git]')].filter(c => c.checked).map(c => S.git.files[+c.dataset.git].path);
    const msg = ($('#cmsg').value || '').trim();
    const q = s => "'" + s.replace(/'/g, "'\\''") + "'";
    $('#cmdout').textContent = !files.length ? '고른 파일이 없음' : !msg ? '메시지를 쓰세요' : `git add -- ${files.map(q).join(' ')} && git commit -m ${q(msg)}`;
  } else if (act === 'copy') {
    copyText(CMDS[+t.dataset.i][1], t);
  }
});
document.addEventListener('paste', ev => { if (practice && ev.target.id === 'ptext') { ev.preventDefault(); } });
function copyText(text, btn) {
  const done = () => { btn.textContent = '복사됨'; setTimeout(() => { btn.textContent = '복사'; }, 1200); };
  if (navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(text).then(done, () => fallback()); } else fallback();
  function fallback() { const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); done(); } catch (e) { alert(text); } ta.remove(); }
}
load(true);
setInterval(load, 2000);
setInterval(tick, 500);
