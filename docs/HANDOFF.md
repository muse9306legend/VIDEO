# 작업 인수인계 — 트윈루지컴퍼니 (Codex·Claude 공용)

새 작업 창(Codex, Claude Code 등)은 **이 파일부터 읽고** 이어서 작업한다.
마지막 갱신: 2026-11-27 · 이전 작업 방: Claude Code 「트윈루지 홈페이지·영상제작·교육」

## 0. 먼저 읽을 문서 (순서대로)
1. `docs/작업지침.md` — 사용자(전설)와 일하는 규칙 10가지, **업무 범위(트윈루지컴퍼니만)**, 자율 개선 루프 사용 규칙
2. `docs/brand/TWINROOZI.md` — **채널 정체성의 기준(확정)**. 다른 문서와 다르면 이 문서가 이긴다
3. `docs/brand/트윈루지컴퍼니.md` — 회사·브랜드 구성
4. `docs/자율개선시스템.md` — Supabase `growth` 스키마 사용법
5. `AGENTS.md` — 저장소 안 영상 편집기(Python) 규칙

## 1. 업무 범위
- 한다: 트윈루지 홈페이지(twinroozi.com), 쌍둥이루지·패밀리 채널 영상·애니메이션, 「루지의 한글 산책」·「루지 한글 교실」 교육, 트윈루지용 자율 개선 시스템
- 안 한다(링크만): 커밍스톤(comingstone.com, teruha-gift-mvp), 루지샵(store-studio), 사업계획서·쿠팡

## 2. 저장소 구조
| 경로 | 내용 |
|---|---|
| `website/` | twinroozi.com 정적 사이트 (빌드 없음, 순수 HTML/CSS/JS) |
| `website/episodes.js` | **에피소드 목록 하나**로 한글 산책·교육 커리큘럼·짝꿍 게임이 함께 바뀜 |
| `website/vercel.json` | 보안 헤더(CSP)·캐시 설정. 외부 서비스 추가 시 CSP 허용 목록 수정 필요 |
| `website/api/health.js` | 상태 확인 `/api/health` (UptimeRobot 감시 중) |
| `scripts/site_seo.js` | `node scripts/site_seo.js` → 크롤러용 정적 HTML, `llms.txt`, `sitemap.xml`(동영상 포함) 재생성 |
| `db/` | Supabase `growth` 설치 SQL (`growth_schema.sql` + `growth_seed_twinroozi.sql`) |
| `animation/` | EP01 편의점 결과물, `characters/` 캐릭터 시안 9종 |
| `docs/` | 지침·브랜드·기획·이 인수인계 문서 |
| `editor/`, `app.py`, `cli.py` | 키즈 영상 AI 편집기(Windows, 별도 도구). `AGENTS.md` 참고 |

## 3. 배포 (twinroozi.com)
- 호스팅: **Vercel** 팀 `team_bfc3coI04kgRrPwE7s8rN1de`, 프로젝트 `twinroozi` (`prj_cIxJl7mcqZ5uBBGY2J1KZLfhcZUZ`), Root Directory `website`, Framework 없음
- 지금까지는 Claude의 Vercel 연결로 커밋마다 **수동 배포**했다 (GitHub `muse9306legend/VIDEO`의 작업 브랜치 커밋을 production으로).
- 다른 도구에서 이어가려면: Vercel 대시보드 → 프로젝트 twinroozi → Settings → **Git**에서 저장소를 연결하고 Production Branch를 작업 브랜치로 지정 → push만 하면 자동 배포.
- 도메인 DNS: 후이즈(whois.co.kr) 네임서버. A 레코드 `@`, `www` = **76.76.21.21** (바꾸지 말 것. 183.111.183.104는 예전 워드프레스 서버). 메일 MX = whoisworks, `w`/`desk.w`/`mail.w`/`contact.w`/`setting.w`/`infra.w` = 132.145.87.189
- 검색 등록: 구글 서치 콘솔·네이버 서치어드바이저 소유확인 완료, `sitemap.xml` 제출 완료
- 분석: Google Tag Manager `GTM-PRBFTPD2` (GA4 `G-E8TZFT3ZR7`), `website/analytics.js`
- JS를 바꾸면 `index.html`의 `?v=` 버전 값을 올린다

## 4. 새 에피소드를 올릴 때
1. `website/episodes.js`에서 회차를 찾아 `youtube: '영상ID'`, `status: '공개'`, `published: 'YYYY-MM-DD'` 입력
2. `node scripts/site_seo.js`
3. 커밋 → 배포 → `https://twinroozi.com/#hangul` 확인

## 5. Supabase 자율 개선 시스템
- 트윈루지용 위치: Supabase **twinroozi_hompage** (`hfxxsviprhhlyfzxnejy`, 트윈루지 계정). 2026-11-27 기준 일시정지 해제(복구) 중.
- 이관 절차: 복구 완료 후 SQL Editor에서 `db/growth_schema.sql` → `db/growth_seed_twinroozi.sql` 순서로 **한 번씩** 실행.
- 이관 완료 전 임시 사본: STORE-studio(`odlenhvdonociempcenv`, 루지샵 계정)의 `growth` 스키마. 쇼핑몰 `public` 테이블은 절대 건드리지 않는다. 이관 확인 후 사본의 트윈루지 부분과 `growth-daily-improve` 예약 작업 정리 필요.
- 비밀값(토큰·DB 비밀번호)은 저장소와 채팅에 넣지 않는다. 작업 도구의 환경 비밀값(Secrets) 기능에만 넣는다.

## 6. 남은 일 (우선순위)
1. **브랜드 기준 통일** (`docs/brand/TWINROOZI.md` 기준): 아래 표의 기존 내용을 고친다 — 홈페이지 문구(인사말·소개·FAQ·`llms.txt`), `docs/기획_루지_한글편_EP01.md`, Supabase `image_prompt`·`shorts_script` 플레이북
   | 항목 | 기존 | 기준 |
   |---|---|---|
   | 타깃 | 해외 10대 소녀 | 동남아 젊은 성인 여성 (구독자 약 60% 동남아) |
   | 쌍둥이 나이 | 명시 없음 | 18살 성인(그림체만 어린이 비율, 아이로 묘사 금지) |
   | 루루 티셔츠 | 주황 | 노랑 |
   | 인사말 | Hi guys~ 하이 가이즈~ | "쌍둥이 루!지!", 끝 인사 "그럼 또 만나자! 안녕~", 애칭 "칭구" |
   | 등장인물 | 루루·지지 | 조안나 언니 포함 3인 ("방글라데시에서 온 언니"까지만 공개) |
   | 형식 | 5초 클립·8분 기획 | 긴 영상 약 5분 + 쇼츠 분할, 주 1편 이상 |
2. **캐릭터 시안 수정**: `05_baseball`, `06_soccer`, `07_badminton`에 "LG퇴원스"·LG 유사 로고 → 유니폼 글자 TWINROOZI로 재생성. 루루(왼쪽)는 **앞머리 없음** 기준과 다른 시안 수정
3. EP01을 유튜브에 올리면 §4 절차로 연결
4. Supabase twinroozi_hompage 이관 (§5)
5. 쌍둥이루지몰 2번 상품 실제 이름 (현재 임시 "루지 간식", `website/index.html` `#shop`)
6. 쌍둥이루지몰 제품 영상(Vimeo 1246450841) 미리보기 이미지 → 동영상 사이트맵 추가

## 7. 지켜야 할 규칙
- 커밋 전 비밀값 검사: `git grep --cached -nE "sk-ant-|sk-proj-|sk-[A-Za-z0-9]{20,}"`
- 사용자 개인 이메일 등 개인정보를 외부 서비스·커밋에 넣지 않는다 (회사 공개 이메일 teruha@twinroozi.com은 사이트에 공개됨)
- 이미지 속 한글·브랜드 로고는 AI가 틀리므로 넣지 않고 편집 단계에서 합성
- 실존 아이돌·구단·브랜드의 이름·로고·초상 사용 금지
- 사용자 안내는 쉬운 한국어로, 칭찬보다 사실·시장성·실행 가능성 기준 (작업지침 9번)
