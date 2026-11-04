"""Command-line use:  .venv\\Scripts\\python cli.py 설교.mp4 --start 2:10 --end 41:30 --title "두려워하지 말라" --name "홍길동 목사" """
import argparse

from editor.pipeline import Options, parse_time, run

p = argparse.ArgumentParser(description="자동 영상 편집기 (설교)")
p.add_argument("video")
p.add_argument("--start", default="", help="트림 시작점 (예: 2:10)")
p.add_argument("--end", default="", help="트림 종료점 (예: 41:30)")
p.add_argument("--no-silence", action="store_true")
p.add_argument("--no-fillers", action="store_true")
p.add_argument("--follow", action="store_true", help="설교자를 천천히 따라가기")
p.add_argument("--zoom", type=float, default=1.0)
p.add_argument("--pos-x", type=float, default=0.0)
p.add_argument("--pos-y", type=float, default=0.0)
p.add_argument("--title", default="")
p.add_argument("--title-align", choices=["left", "center", "right"], default="center")
p.add_argument("--title-x", type=float, default=0.0)
p.add_argument("--title-y", type=float, default=0.0)
p.add_argument("--title-secs", type=float, default=0)
p.add_argument("--name", default="")
p.add_argument("--name-secs", type=float, default=15)
p.add_argument("--no-cards", action="store_true")
p.add_argument("--max-cards", type=int, default=6)
p.add_argument("--fullscreen", action="store_true", help="설명 그림을 전체 화면으로")
p.add_argument("--silence-db", type=float, default=-40)
p.add_argument("--whisper", default="large-v3")
a = p.parse_args()

res = run(a.video, Options(
    trim_start=parse_time(a.start) or 0.0, trim_end=parse_time(a.end),
    remove_silence=not a.no_silence, remove_fillers=not a.no_fillers, silence_db=a.silence_db,
    follow=a.follow, zoom=a.zoom, pos_x=a.pos_x, pos_y=a.pos_y,
    title_on=bool(a.title), title=a.title, title_align=a.title_align, title_x=a.title_x, title_y=a.title_y, title_secs=a.title_secs,
    name_on=bool(a.name), name=a.name, name_secs=a.name_secs,
    cards=not a.no_cards, max_cards=a.max_cards, card_mode="fullscreen" if a.fullscreen else "overlay",
    whisper_model=a.whisper,
), progress=lambda f, m: print(f"{f * 100:5.1f}% {m}", flush=True))
print("결과:", res["output"])
print("리포트:", res["report"])
