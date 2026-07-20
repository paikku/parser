"""dump 파이프라인 — .tdf → 디코드 → 버전 판별 → 시각화 레코드.

순수 조립 계층: HTTP 도 파일 저장도 모른다. router(API)와 배치 스크립트가
이 함수들을 공유한다. 디코드(ddformat)·추출(extract) 모두 stdlib 만 쓰므로
이 폴더는 다른 프로젝트로 통째 이식 가능하다.

레코드 계약 (시각화 입력과 필드 단위 일치):
    {
      "source":   "<tdf이름>::<dd이름>",     # 시각화 라벨
      "kind":     "SCAN_ROW_DATA_STRUCT@v1", # 선택된 버전 name
      "value":    {채널: [값...]},            # 채널별 측정값 배열
      "xyz":      {"x": [...], "y": [...], "z": [...]},
      "warnings": [...],                      # 디코드+추출 경고 (부분 성공 기본)
    }

필터는 버전 판별이 담당한다: 스캔 데이터가 아닌 .dd(설정/기타 구조)는
UnknownVersionError 로 자연 스킵되며, 스킵 사유는 DumpReport.skipped 에 남는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ddformat import decode_dd, iter_tdf
from .extract import AmbiguousVersionError, UnknownVersionError, dispatch


@dataclass
class DumpRecord:
    """시각화 레코드 하나 (= 매칭된 .dd 하나)."""

    source: str
    kind: str
    value: dict[str, list]
    xyz: dict[str, list]
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "kind": self.kind,
            "value": self.value,
            "xyz": self.xyz,
            "warnings": self.warnings,
        }


@dataclass
class DumpReport:
    """한 .tdf 처리 결과 — 레코드 + 스킵 목록 (부분 실패 격리)."""

    tdf: str
    records: list[DumpRecord] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)   # {"dd", "reason"}

    def as_dict(self) -> dict[str, Any]:
        return {
            "tdf": self.tdf,
            "records": [r.as_dict() for r in self.records],
            "skipped": self.skipped,
        }


def find_tdf_files(path: str | Path) -> list[Path]:
    """경로에서 .tdf 목록 수집. 파일이면 그 파일, 폴더면 하위까지 재귀."""
    p = Path(path)
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted(set(p.rglob("*.tdf")) | set(p.rglob("*.TDF")))
    return []


def run_tdf(tdf_path: str | Path, dd_filter: str | None = None) -> DumpReport:
    """단일 .tdf 안의 .dd 들을 디코드→판별→정규화해 DumpReport 반환.

    한 .dd 의 실패는 그 .dd 만 스킵한다 — 나머지는 계속 처리 (부분 실패 격리).
    """
    tdf_path = Path(tdf_path)
    report = DumpReport(tdf=tdf_path.name)

    for dd_name, raw in iter_tdf(tdf_path, dd_filter=dd_filter):
        source = f"{tdf_path.name}::{dd_name}"

        decoded = decode_dd(raw, name=dd_name)
        if decoded.format == "text" or not decoded.tree:
            report.skipped.append({
                "dd": dd_name,
                "reason": "; ".join(decoded.warnings) or "빈 디코드 결과",
            })
            continue

        try:
            kind, out = dispatch(decoded.tree)
        except UnknownVersionError as e:
            report.skipped.append({"dd": dd_name, "reason": str(e)})
            continue
        except AmbiguousVersionError as e:
            report.skipped.append({"dd": dd_name, "reason": str(e)})
            continue

        report.records.append(DumpRecord(
            source=source,
            kind=kind,
            value=out.get("value", {}),
            xyz=out.get("xyz", {"x": [], "y": [], "z": []}),
            warnings=decoded.warnings + out.get("warnings", []),
        ))

    return report


def run_tree(path: str | Path, dd_filter: str | None = None) -> list[DumpReport]:
    """폴더(또는 단일 .tdf)의 모든 .tdf 를 처리. 파일 단위 실패 격리."""
    reports: list[DumpReport] = []
    for tdf in find_tdf_files(path):
        try:
            reports.append(run_tdf(tdf, dd_filter=dd_filter))
        except (ValueError, OSError) as e:
            reports.append(DumpReport(
                tdf=Path(tdf).name,
                skipped=[{"dd": "*", "reason": f"TDF 열기 실패: {e}"}],
            ))
    return reports
