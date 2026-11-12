// 루지의 한글 짝꿍 게임: match each Hangul word card with its picture card.
(function () {
  var WORDS = [
    ['안녕하세요', '👋', 'annyeonghaseyo', 'Hello'],
    ['편의점', '🏪', 'pyeonuijeom', 'convenience store'],
    ['삼각김밥', '🍙', 'samgak-gimbap', 'triangle kimbap'],
    ['지하철', '🚇', 'jihacheol', 'subway'],
    ['횡단보도', '🚸', 'hoengdanbodo', 'crosswalk'],
    ['라면', '🍜', 'ramyeon', 'ramen'],
    ['떡볶이', '🌶️', 'tteokbokki', 'spicy rice cakes'],
    ['바나나우유', '🍌', 'banana uyu', 'banana milk'],
    ['한강', '🌉', 'hangang', 'Han River'],
    ['노래', '🎤', 'norae', 'song'],
    ['감사합니다', '🙏', 'gamsahamnida', 'Thank you'],
    ['친구', '👭', 'chingu', 'friend']
  ];
  var CHEERS = ['맞았어!', '최고야!', '대박!', '잘했어!', '천재인데?'];
  var MISS = ['앗, 다시!', '아깝다~', '한 번 더!', '괜찮아, 다시 해 보자!'];

  var board = document.getElementById('g-board');
  if (!board) return;
  var $ = function (id) { return document.getElementById(id); };
  var level = 6, first = null, lock = false, moves = 0, found = 0, t0 = 0, timer = 0, turn = 0;
  var back = '<svg viewBox="0 0 88 48" aria-hidden="true"><circle cx="22" cy="24" r="17" fill="none" stroke="#F6B500" stroke-width="6"/><circle cx="66" cy="24" r="17" fill="none" stroke="#F0399A" stroke-width="6"/><path d="M39 22q5-5 10 0" fill="none" stroke="#2E2A26" stroke-width="4" stroke-linecap="round"/></svg>';

  function store(key, val) {
    try { if (val === undefined) return localStorage.getItem(key); localStorage.setItem(key, val); } catch (e) { return null; }
  }
  function shuffle(a) {
    for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; }
    return a;
  }
  function pick(a) { return a[Math.floor(Math.random() * a.length)]; }
  function say(text) {
    // Alternate speakers: 루루 (yellow) and 지지 (pink).
    turn++;
    var roo = turn % 2 === 1;
    $('g-face').src = roo ? 'img/roo.webp' : 'img/zi.webp';
    $('g-say').textContent = (roo ? '루루: ' : '지지: ') + text;
    return roo;
  }
  function speak(word) {
    if (!('speechSynthesis' in window)) return;
    try {
      speechSynthesis.cancel();
      var u = new SpeechSynthesisUtterance(word);
      u.lang = 'ko-KR'; u.rate = 0.8;
      speechSynthesis.speak(u);
    } catch (e) { /* no voice: the game still works silently */ }
  }
  function showBest() {
    var b = store('roozi-best-' + level);
    $('g-best').textContent = b ? b + '번' : '-';
  }
  function tick() { $('g-time').textContent = Math.floor((Date.now() - t0) / 1000); }

  function makeCard(w, i, kind) {
    var c = document.createElement('button');
    c.type = 'button';
    c.className = 'card';
    c.dataset.pair = i;
    c.setAttribute('aria-label', '뒤집힌 카드');
    var face = kind === 'ko'
      ? '<span><span class="ko">' + w[0] + '</span><small>' + w[2] + '</small></span>'
      : '<span><span class="emo">' + w[1] + '</span><small>' + w[3] + '</small></span>';
    c.innerHTML = '<span class="in"><span class="f">' + back + '</span><span class="b">' + face + '</span></span>';
    c.dataset.label = kind === 'ko' ? w[0] : w[3];
    c.addEventListener('click', function () { flip(c); });
    return c;
  }

  function flip(c) {
    if (lock || c === first || c.classList.contains('done')) return;
    if (!t0) { t0 = Date.now(); timer = setInterval(tick, 500); }
    c.classList.add('open');
    c.setAttribute('aria-label', c.dataset.label);
    if (!first) { first = c; return; }
    moves++;
    $('g-moves').textContent = moves;
    var a = first; first = null;
    if (a.dataset.pair === c.dataset.pair) {
      var w = WORDS[+c.dataset.pair];
      var roo = say(pick(CHEERS) + ' "' + w[0] + '" = ' + w[3]);
      [a, c].forEach(function (x) { x.classList.add('done', roo ? 'roo' : 'zi'); x.classList.remove('open'); });
      speak(w[0]);
      found++;
      if (found === level) win();
    } else {
      lock = true;
      say(pick(MISS));
      setTimeout(function () {
        [a, c].forEach(function (x) {
          x.classList.remove('open'); x.classList.add('shake'); x.setAttribute('aria-label', '뒤집힌 카드');
          setTimeout(function () { x.classList.remove('shake'); }, 400);
        });
        lock = false;
      }, 850);
    }
  }

  function win() {
    clearInterval(timer);
    tick();
    var secs = $('g-time').textContent;
    var best = +store('roozi-best-' + level) || 0;
    var record = !best || moves < best;
    if (record) store('roozi-best-' + level, String(moves));
    showBest();
    $('g-result').textContent = moves + '번 뒤집어서 ' + secs + '초 만에 성공!' + (record ? ' 새 기록이에요 🏆' : '');
    $('g-win').classList.add('show');
    say('우리 짝꿍 최고! 하이파이브 ✋');
  }

  function start() {
    clearInterval(timer);
    first = null; lock = false; moves = 0; found = 0; t0 = 0; turn = 0;
    $('g-moves').textContent = '0';
    $('g-time').textContent = '0';
    $('g-win').classList.remove('show');
    say('가 보자고! 카드를 눌러 봐!');
    var ids = shuffle(WORDS.map(function (_, i) { return i; })).slice(0, level);
    var cards = [];
    ids.forEach(function (i) { cards.push(makeCard(WORDS[i], i, 'ko'), makeCard(WORDS[i], i, 'pic')); });
    board.replaceChildren.apply(board, shuffle(cards));
    showBest();
  }

  document.querySelectorAll('#game [data-level]').forEach(function (b) {
    b.addEventListener('click', function () {
      level = +b.dataset.level;
      document.querySelectorAll('#game [data-level]').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
      start();
    });
  });
  $('g-reset').addEventListener('click', start);
  $('g-again').addEventListener('click', function () { start(); board.scrollIntoView({ block: 'center' }); });
  start();
})();
