"""명령줄 실행.

    python cli.py 영상.mp4 --twin-a 하윤 --twin-b 하린 --desc-a "단발머리, 노란 티셔츠" --photo-a 하윤.jpg
    python cli.py 영상.mp4 --plan jobs/20261107_120000/plan.json   # 저장된 계획으로 다시 렌더 (AI 호출 없음)
"""
import argparse
import json
from pathlib import Path

from editor.pipeline import Settings, run


def main():
    p = argparse.ArgumentParser(description="키즈 유튜브 AI 편집기: 설명 그림 + 쌍둥이 캐릭터")
    p.add_argument("video")
    p.add_argument("--twin-a", default="첫째")
    p.add_argument("--twin-b", default="둘째")
    p.add_argument("--desc-a", default="", help="쌍둥이 A 생김새/성격 (예: 단발머리, 노란 티셔츠, 활발함)")
    p.add_argument("--desc-b", default="")
    p.add_argument("--photo-a", nargs="*", default=[], help="쌍둥이 A 참고 사진 (캐릭터를 닮게 그림)")
    p.add_argument("--photo-b", nargs="*", default=[])
    p.add_argument("--topic", default="", help="영상 주제 (예: 마라탕 먹방)")
    p.add_argument("--cards", type=int, default=6, help="설명 그림 최대 개수")
    p.add_argument("--reactions", type=int, default=12, help="쌍둥이 반응 최대 개수")
    p.add_argument("--plan", help="저장된 plan.json 으로 다시 렌더")
    p.add_argument("--max-side", type=int, default=1920)
    a = p.parse_args()

    s = Settings(a.twin_a, a.twin_b, a.desc_a, a.desc_b,
                 [Path(x).read_bytes() for x in a.photo_a], [Path(x).read_bytes() for x in a.photo_b],
                 a.topic, a.cards, a.reactions, a.max_side)
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8")) if a.plan else None
    print(run(a.video, s, plan=plan))


if __name__ == "__main__":
    main()
