"""예시: 폴더 안의 모든 JSON 파일을 돌며 버전을 판별하고,
'명시된 버전'이면 파싱 결과를 output 폴더에 저장한다. (추상화 없이 그대로)

실행 (repo 루트에서):
    python -m parsers.example_batch <input_dir> <output_dir>
    python -m parsers.example_batch samples out --only FILT_DATA_STRUCT@v1
"""

import argparse
import json
from pathlib import Path

from jsonparser import load_file, UnknownTypeError, AmbiguousTypeError
from parsers import parse_file, CLASSIFIER

# 저장할 '명시된 버전' 목록 (기본값 = 현재 등록된 모든 버전).
DEFAULT_ALLOWED = {p.name for p in CLASSIFIER.profiles}


def run(input_dir: str, output_dir: str, allowed: set) -> dict:
    in_dir = Path(input_dir)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    saved = skipped = failed = 0

    for path in sorted(in_dir.glob("*.json")):
        # 1) 로드
        try:
            data = load_file(str(path))
        except (OSError, ValueError) as e:
            print(f"[read-fail] {path.name}: {e}")
            failed += 1
            continue

        # 2) 버전 판별 + 파싱
        try:
            kind, out = parse_file(data)
        except (UnknownTypeError, AmbiguousTypeError) as e:
            print(f"[no-match ] {path.name}: {e}")
            skipped += 1
            continue

        # 3) '명시된 버전'만 저장
        if kind not in allowed:
            print(f"[skip     ] {path.name}: {kind} (명시된 버전 아님)")
            skipped += 1
            continue

        out_path = out_dir / f"{path.stem}.out.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"source": path.name, "kind": kind, **out},
                      f, ensure_ascii=False, indent=2)
        print(f"[saved    ] {path.name} -> {out_path.name} ({kind})")
        saved += 1

    print(f"\n총 {saved} 저장, {skipped} 스킵, {failed} 실패.")
    return {"saved": saved, "skipped": skipped, "failed": failed}


def main():
    ap = argparse.ArgumentParser(
        description="폴더 내 JSON 버전 판별 후 지정 버전만 파싱·저장")
    ap.add_argument("input_dir", help="입력 JSON 폴더")
    ap.add_argument("output_dir", help="결과 저장 폴더")
    ap.add_argument("--only", nargs="*", default=None,
                    help=f"저장할 버전 name (기본: 등록된 전부 {sorted(DEFAULT_ALLOWED)})")
    args = ap.parse_args()
    allowed = set(args.only) if args.only else DEFAULT_ALLOWED
    run(args.input_dir, args.output_dir, allowed)


if __name__ == "__main__":
    main()
