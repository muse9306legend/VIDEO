// 루지의 한글 산책 — 에피소드 목록 (사이트 전체가 이 파일 하나를 봅니다)
//
// 새 애니메이션을 유튜브에 올렸으면 아래 목록에서 그 회차를 찾아:
//   1) youtube: 영상 ID 를 넣고   (https://youtu.be/AbCdEf12345  →  'AbCdEf12345')
//   2) status: '공개' 로 바꾸면 끝.
// 그러면 한글 산책(영상 + 단어 카드), 교육 프로그램 커리큘럼, 짝꿍 게임 단어가 함께 바뀝니다.
//
// words: [한글, 그림(이모지), 로마자, English]
window.HANGUL = {
  basics: [ // 매 편 쓰는 기본 인사
    ['안녕하세요', '👋', 'annyeonghaseyo', 'Hello'],
    ['감사합니다', '🙏', 'gamsahamnida', 'Thank you'],
    ['친구', '👭', 'chingu', 'friend']
  ],
  episodes: [
    {
      no: 1, place: '편의점', title: '편의점에서 삼각김밥', status: '공개', consonant: 'ㅍ',
      youtube: '', video: 'img/hangul_ep01.mp4', poster: 'img/hangul_ep01.jpg',
      words: [
        ['편의점', '🏪', 'pyeonuijeom', 'convenience store'],
        ['삼각김밥', '🍙', 'samgak-gimbap', 'triangle kimbap'],
        ['맛있어', '😋', 'masisseo', "it's delicious"],
        ['라면', '🍜', 'ramyeon', 'ramen'],
        ['바나나우유', '🍌', 'banana uyu', 'banana milk']
      ]
    },
    {
      no: 2, place: '지하철', title: '삑! 지하철 타기', status: '준비 중', consonant: 'ㅈ',
      words: [
        ['지하철', '🚇', 'jihacheol', 'subway'],
        ['교통카드', '💳', 'gyotong kadeu', 'transit card']
      ]
    },
    {
      no: 3, place: '횡단보도', title: '바닥도 신호등이야!', status: '준비 중', consonant: 'ㅎ',
      words: [
        ['횡단보도', '🚸', 'hoengdanbodo', 'crosswalk'],
        ['초록불', '🟢', 'chorokbul', 'green light']
      ]
    },
    {
      no: 4, place: '한강', title: '한강 피크닉', status: '준비 중', consonant: 'ㅊ',
      words: [
        ['한강', '🌉', 'hangang', 'Han River'],
        ['치킨', '🍗', 'chikin', 'fried chicken']
      ]
    },
    {
      no: 5, place: '분식집', title: '떡볶이는 매워!', status: '준비 중', consonant: 'ㄸ',
      words: [
        ['떡볶이', '🌶️', 'tteokbokki', 'spicy rice cakes'],
        ['김밥', '🥢', 'gimbap', 'gimbap']
      ]
    }
  ]
};

// Renders the 한글 산책 section and the 교육 프로그램 curriculum from the list above.
(function () {
  var H = window.HANGUL, eps = H.episodes;
  var $ = function (id) { return document.getElementById(id); };
  var player = $('ep-player');
  if (!player) return;
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  var label = function (ep) { return 'EP' + (ep.no < 10 ? '0' : '') + ep.no; };
  var live = function (ep) { return ep.status === '공개' && (ep.youtube || ep.video); };
  var wordChips = function (ws) {
    return ws.map(function (w) { return '<span class="word">' + esc(w[0]) + '<small>' + esc(w[2]) + ' · ' + esc(w[3]) + '</small></span>'; }).join('');
  };

  function show(ep) {
    var name = '루지의 한글 산책 ' + label(ep) + ' ' + ep.place;
    if (ep.youtube) {
      // Click-to-load YouTube (no YouTube cookies until the viewer presses play).
      player.innerHTML = '<div class="paper vimeo"><button type="button" aria-label="' + esc(name) + ' 재생">' +
        '<img src="https://i.ytimg.com/vi/' + esc(ep.youtube) + '/hqdefault.jpg" alt="" loading="lazy">' +
        '<span class="play" aria-hidden="true">▶</span></button></div>';
      player.querySelector('button').addEventListener('click', function () {
        var f = document.createElement('iframe');
        f.src = 'https://www.youtube-nocookie.com/embed/' + encodeURIComponent(ep.youtube) + '?autoplay=1&rel=0';
        f.title = name;
        f.allow = 'autoplay; encrypted-media; picture-in-picture';
        f.allowFullscreen = true;
        player.firstChild.replaceChildren(f);
      });
    } else {
      player.innerHTML = '<video controls playsinline preload="none" poster="' + esc(ep.poster || '') + '" aria-label="' + esc(name) + '">' +
        '<source src="' + esc(ep.video) + '" type="video/mp4"></video>';
    }
    $('ep-title').textContent = label(ep) + ' · ' + ep.title;
    $('ep-words').innerHTML = wordChips(ep.words);
    $('ep-consonant').textContent = ep.consonant;
    $('ep-list').querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-pressed', String(+b.dataset.no === ep.no)); });
  }

  $('ep-list').innerHTML = eps.map(function (ep) {
    var on = live(ep);
    return '<button type="button" class="ep' + (on ? '' : ' soon') + '" data-no="' + ep.no + '"' + (on ? '' : ' disabled') + '>' +
      '<b>' + label(ep) + '</b><span>' + esc(ep.place) + '</span><em>' + (on ? '▶ 보기' : '준비 중') + '</em></button>';
  }).join('');
  $('ep-list').addEventListener('click', function (e) {
    var b = e.target.closest('button.ep');
    if (b && !b.disabled) show(eps.filter(function (ep) { return ep.no === +b.dataset.no; })[0]);
  });
  var released = eps.filter(live);
  if (released.length) show(released[released.length - 1]);

  var cur = $('edu-curriculum');
  if (cur) {
    cur.innerHTML = eps.map(function (ep) {
      return '<tr><th scope="row">' + label(ep) + '</th><td>' + esc(ep.place) + '</td><td>' +
        ep.words.map(function (w) { return esc(w[0]); }).join(', ') + '</td><td class="jamo">' + esc(ep.consonant) +
        '</td><td>' + (live(ep) ? '<span class="tag on">공개</span>' : '<span class="tag">준비 중</span>') + '</td></tr>';
    }).join('');
    $('edu-basics').innerHTML = wordChips(H.basics);
  }
})();
