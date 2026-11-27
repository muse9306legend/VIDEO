// Regenerates the crawler-readable parts of twinroozi.com from website/episodes.js:
//   - static HTML inside index.html between <!-- static:NAME --> markers (curriculum, latest episode words, basics)
//     so search engines and AI crawlers that do not run JavaScript still see the content
//   - website/llms.txt (summary for AI assistants)
//   - video structured data (VideoObject) for released episodes
//   - website/sitemap.xml with a video sitemap of every video on the page
// Run after editing episodes.js:  node scripts/site_seo.js
const fs = require('fs');
const path = require('path');
const site = path.join(__dirname, '..', 'website');

global.window = {};
global.document = { getElementById: () => null };
require(path.join(site, 'episodes.js'));
const { basics, episodes } = window.HANGUL;

const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const label = ep => 'EP' + String(ep.no).padStart(2, '0');
const live = ep => ep.status === '공개' && (ep.youtube || ep.video);
const chips = ws => ws.map(w => `<span class="word">${esc(w[0])}<small>${esc(w[2])} · ${esc(w[3])}</small></span>`).join('');
const latest = episodes.filter(live).pop() || episodes[0];
const today = new Date().toISOString().slice(0, 10);
const SITE = 'https://twinroozi.com/';

// 1) static blocks in index.html (the same markup episodes.js renders at runtime)
const blocks = {
  title: `${label(latest)} · ${esc(latest.title)}`,
  words: chips(latest.words),
  basics: chips(basics),
  ldvideos: (() => {
    const vids = episodes.filter(live).filter(e => e.published).map(e => ({
      '@type': 'VideoObject',
      name: `루지의 한글 산책 ${label(e)} ${e.place} — ${e.title}`,
      description: `쌍둥이 루루와 지지가 ${e.place}에서 한국어 단어를 배워요: ${e.words.map(w => `${w[0]}(${w[3]})`).join(', ')}.`,
      thumbnailUrl: e.youtube ? `https://i.ytimg.com/vi/${e.youtube}/hqdefault.jpg` : SITE + e.poster,
      uploadDate: e.published,
      ...(e.duration ? { duration: e.duration } : {}),
      ...(e.youtube ? { embedUrl: `https://www.youtube.com/embed/${e.youtube}` } : { contentUrl: SITE + e.video }),
      inLanguage: 'ko', isFamilyFriendly: true,
      publisher: { '@id': SITE + '#org' }
    }));
    return vids.length ? `<script type="application/ld+json">${JSON.stringify({ '@context': 'https://schema.org', '@graph': vids }).replace(/</g, '\\u003c')}</script>` : '';
  })(),
  curriculum: episodes.map(ep => `<tr><th scope="row">${label(ep)}</th><td>${esc(ep.place)}</td><td>${ep.words.map(w => esc(w[0])).join(', ')}</td><td class="jamo">${esc(ep.consonant)}</td><td>${live(ep) ? '<span class="tag on">공개</span>' : '<span class="tag">준비 중</span>'}</td></tr>`).join('')
};
const indexPath = path.join(site, 'index.html');
let html = fs.readFileSync(indexPath, 'utf8');
for (const [name, body] of Object.entries(blocks)) {
  const re = new RegExp(`<!-- static:${name} -->[\\s\\S]*?<!-- /static:${name} -->`);
  if (!re.test(html)) throw new Error(`marker static:${name} not found in index.html`);
  html = html.replace(re, `<!-- static:${name} -->${body}<!-- /static:${name} -->`);
}
fs.writeFileSync(indexPath, html);

// 2) llms.txt
const epLines = episodes.map(e => `- ${label(e)} ${e.place} — ${e.title} (${e.status}) · 오늘의 자음 ${e.consonant} · 단어: ${e.words.map(w => `${w[0]} (${w[2]}, ${w[3]})`).join(', ')}` +
  (e.youtube ? ` · 영상: https://youtu.be/${e.youtube}` : '')).join('\n');
const llms = `# 쌍둥이루지 TWINROOZI

> 쌍둥이루지(TWINROOZI)는 트윈루지컴퍼니가 운영하는 한국의 쌍둥이 유튜브 크리에이터입니다. 노란 안경의 루루(Roo)와 핑크 안경의 지지(Zi)가 K-푸드, 한국 문화, 한국의 일상을 소개하고, 애니메이션으로 한국어를 가르칩니다.
> TWINROOZI is a Korean twin YouTube creator brand run by TwinRoozi Company. Roo (yellow glasses) and Zi (pink glasses) share K-food, Korean culture and everyday Korea, and teach beginner Korean through animation.

## 핵심 정보 / Key facts
- 공식 사이트 / Website: https://twinroozi.com/
- 운영사 / Company: 주식회사 트윈루지컴퍼니 (TwinRoozi Company), 2019년 국내 키즈 크리에이터로 시작
- 주소 / Address: 서울 금천구 디지털로10길 78, 1337-22호 (한국산업지능화협회), Seoul, Korea
- 전화 / Phone: 070-7576-4564 · 이메일 / Email: teruha@twinroozi.com
- 쇼핑 / Shop: 쌍둥이루지몰 (네이버 스마트스토어) https://smartstore.naver.com/twinroozi
- 인스타그램 / Instagram: https://www.instagram.com/twinroozicompany/

## 유튜브 채널 / YouTube channels
- 쌍둥이루지 TWINROOZI: https://www.youtube.com/@twinroozi
- 조안나 ZOANA: https://www.youtube.com/@zoanabak
- 해피봄봄 HappyBomBom: https://www.youtube.com/@happybombom
- 달달영심이 DalDalYoungsimi: https://www.youtube.com/@daldalyoungsimi

## 루지의 한글 산책 / Learn Korean with Roo & Zi
쌍둥이가 한국의 장소를 걸으며 단어를 배우는 애니메이션 시리즈입니다. 단어는 한글·로마자·영어 3줄로 보여 줍니다.
An animated series where the twins visit places in Korea and learn words, shown in Hangul, romanization and English.
${epLines}
- 매 편 기본 인사 / Basic greetings: ${basics.map(w => `${w[0]} (${w[2]}, ${w[3]})`).join(', ')}

## 루지 한글 교실 / Roo & Zi Korean Class
무료 한국어 입문 과정 / Free beginner Korean course: 1) 애니메이션 보기 2) 단어 카드 3) 오늘의 자음 4) 짝꿍 게임으로 복습.
- 과정 / Course: https://twinroozi.com/#edu
- 한글 짝꿍 게임 / Hangul matching game: https://twinroozi.com/#game
- 문의 / Contact: teruha@twinroozi.com

## 자주 묻는 질문 / FAQ
- https://twinroozi.com/#faq
`;
fs.writeFileSync(path.join(site, 'llms.txt'), llms);

// 3) sitemap.xml with a video sitemap (Google needs thumbnail, title, description and a player or file URL)
const FEATURED = [ // videos on the page that are not episodes (channel cards, films)
  { title: 'TWINROOZI 2027', description: '쌍둥이루지 TWINROOZI 2027 영상', thumb: SITE + 'img/vimeo_2027.webp', player: 'https://player.vimeo.com/video/1246242300' },
  { title: '명화 먹방 진주 귀걸이를 한 소녀 - 해피봄봄', description: '해피봄봄 HappyBomBom 명화 먹방: 진주 귀걸이를 한 소녀와 스포츠볼젤리', thumb: 'https://i.ytimg.com/vi/-sx51duVoVY/hqdefault.jpg', player: 'https://www.youtube.com/embed/-sx51duVoVY' },
  { title: '명화 먹방 클레오파트라 - 달달영심이', description: '달달영심이 DalDalYoungsimi ASMR 명화 먹방: 클레오파트라', thumb: 'https://i.ytimg.com/vi/dI37nK_vMOY/hqdefault.jpg', player: 'https://www.youtube.com/embed/dI37nK_vMOY' }
];
const xml = s => esc(s).replace(/'/g, '&apos;');
const epVideos = episodes.filter(live).map(e => ({
  title: `루지의 한글 산책 ${label(e)} ${e.place} — ${e.title}`,
  description: `쌍둥이 루루와 지지가 ${e.place}에서 한국어 단어를 배워요: ${e.words.map(w => w[0]).join(', ')}`,
  thumb: e.youtube ? `https://i.ytimg.com/vi/${e.youtube}/hqdefault.jpg` : SITE + e.poster,
  ...(e.youtube ? { player: `https://www.youtube.com/embed/${e.youtube}` } : { content: SITE + e.video }),
  published: e.published, family: true
}));
const videoTags = [...epVideos, ...FEATURED].map(v => `
    <video:video>
      <video:thumbnail_loc>${xml(v.thumb)}</video:thumbnail_loc>
      <video:title>${xml(v.title)}</video:title>
      <video:description>${xml(v.description)}</video:description>
      ${v.content ? `<video:content_loc>${xml(v.content)}</video:content_loc>` : `<video:player_loc>${xml(v.player)}</video:player_loc>`}${v.published ? `
      <video:publication_date>${v.published}</video:publication_date>` : ''}${v.family ? `
      <video:family_friendly>yes</video:family_friendly>` : ''}
    </video:video>`).join('');
fs.writeFileSync(path.join(site, 'sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:video="http://www.google.com/schemas/sitemap-video/1.1">
  <url>
    <loc>${SITE}</loc>
    <lastmod>${today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>${videoTags}
  </url>
  <url><loc>${SITE}llms.txt</loc><lastmod>${today}</lastmod><changefreq>weekly</changefreq><priority>0.5</priority></url>
</urlset>
`);

console.log(`updated index.html static blocks (latest ${label(latest)}), llms.txt, sitemap.xml (${today})`);
