// 루지의 한글 짝꿍 게임: match each Hangul word card with its picture card.
(function () {
  // Word pool = every word in episodes.js (기본 인사 + all episodes), so new episodes join the game automatically.
  var H = window.HANGUL || { basics: [], episodes: [] };
  var WORDS = H.episodes.reduce(function (all, ep) { return all.concat(ep.words); }, H.basics.slice());
  var CHEERS = ['맞았어!', '최고야!', '대박!', '잘했어!', '천재인데?'];
  var MISS = ['앗, 다시!', '아깝다~', '한 번 더!', '괜찮아, 다시 해 보자!'];
  var HIDDEN = '뒤집힌 카드';

  var $ = function (id) { return document.getElementById(id); };
  var board = $('g-board');
  if (!board) return;
  var el = { face: $('g-face'), say: $('g-say'), moves: $('g-moves'), time: $('g-time'), best: $('g-best'),
    win: $('g-win'), result: $('g-result') };
  var levels = document.querySelectorAll('#game [data-level]');
  var back = document.querySelector('.logo svg').outerHTML; // card back = the site logo
  var level = 6, first = null, lock = false, moves = 0, found = 0, t0 = 0, timer = 0, roo = false;

  function bestKey() { return 'roozi-best-' + level; }
  function getBest() { try { return +localStorage.getItem(bestKey()) || 0; } catch (e) { return 0; } }
  function setBest(n) { try { localStorage.setItem(bestKey(), String(n)); } catch (e) { /* private mode */ } }
  function showBest(n) { el.best.textContent = n ? n + '번' : '-'; }
  function shuffle(a) {
    for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; }
    return a;
  }
  function pick(a) { return a[Math.floor(Math.random() * a.length)]; }
  function seconds() { return Math.floor((Date.now() - t0) / 1000); }
  function tick() { el.time.textContent = seconds(); }
  function say(text) { // 루루 (yellow) and 지지 (pink) take turns
    roo = !roo;
    el.face.src = roo ? 'img/roo.webp' : 'img/zi.webp';
    el.say.textContent = (roo ? '루루: ' : '지지: ') + text;
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
  function setOpen(c, open) {
    c.classList.toggle('open', open);
    c.setAttribute('aria-label', open ? c.dataset.label : HIDDEN);
  }

  function makeCard(w, i, ko) {
    var c = document.createElement('button');
    c.type = 'button';
    c.className = 'card';
    c.dataset.pair = i;
    c.dataset.label = ko ? w[0] : w[3];
    c.setAttribute('aria-label', HIDDEN);
    c.innerHTML = '<span class="in"><span class="f">' + back + '</span><span class="b"><span><span class="' +
      (ko ? 'ko' : 'emo') + '">' + (ko ? w[0] : w[1]) + '</span><small>' + (ko ? w[2] : w[3]) + '</small></span></span></span>';
    return c;
  }

  function flip(c) {
    if (lock || c === first || c.classList.contains('done')) return;
    if (!t0) { t0 = Date.now(); timer = setInterval(tick, 1000); }
    setOpen(c, true);
    if (!first) { first = c; return; }
    el.moves.textContent = ++moves;
    var a = first; first = null;
    if (a.dataset.pair === c.dataset.pair) {
      var w = WORDS[+c.dataset.pair];
      say(pick(CHEERS) + ' "' + w[0] + '" = ' + w[3]);
      [a, c].forEach(function (x) { x.classList.remove('open'); x.classList.add('done', roo ? 'roo' : 'zi'); });
      speak(w[0]);
      if (++found === level) win();
    } else {
      lock = true;
      say(pick(MISS));
      setTimeout(function () {
        [a, c].forEach(function (x) { setOpen(x, false); x.classList.add('shake'); });
        lock = false;
      }, 850);
    }
  }

  function win() {
    clearInterval(timer);
    var secs = seconds(), best = getBest(), record = !best || moves < best;
    el.time.textContent = secs;
    if (record) setBest(moves);
    showBest(record ? moves : best);
    el.result.textContent = moves + '번 뒤집어서 ' + secs + '초 만에 성공!' + (record ? ' 새 기록이에요 🏆' : '');
    el.win.classList.add('show');
    say('우리 짝꿍 최고! 하이파이브 ✋');
  }

  function start() {
    clearInterval(timer);
    first = null; lock = false; moves = 0; found = 0; t0 = 0; roo = false;
    el.moves.textContent = '0';
    el.time.textContent = '0';
    el.win.classList.remove('show');
    say('가 보자고! 카드를 눌러 봐!');
    var cards = [];
    shuffle(WORDS.map(function (_, i) { return i; })).slice(0, level).forEach(function (i) {
      cards.push(makeCard(WORDS[i], i, true), makeCard(WORDS[i], i, false));
    });
    board.replaceChildren.apply(board, shuffle(cards));
    showBest(getBest());
  }

  board.addEventListener('click', function (e) { var c = e.target.closest('.card'); if (c) flip(c); });
  board.addEventListener('animationend', function (e) { e.target.closest('.card').classList.remove('shake'); });
  levels.forEach(function (b) {
    b.addEventListener('click', function () {
      level = +b.dataset.level;
      levels.forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
      start();
    });
  });
  $('g-reset').addEventListener('click', start);
  $('g-again').addEventListener('click', function () { start(); board.scrollIntoView({ block: 'center' }); });
  start();
})();
