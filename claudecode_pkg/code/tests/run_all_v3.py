"""
I5 — v3 회귀 전체 실행기. 각 test_*.py는 자기 완결형(격리 DB_PATH)이라 서브프로세스로 하나씩 돌리고
통과/실패를 모아 보여준다. 하나라도 실패하면 exit code 1 (CI/스크립트에서 그대로 게이트로 쓸 수 있게).

실행: python tests/run_all_v3.py
"""
import re
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).parent

# 09번 보드 순서(I0→I4)대로 나열 — 실패 시 어느 단계부터 깨졌는지 바로 보이게.
TEST_FILES = [
    "test_v3_data.py",
    "test_engine_v3.py",
    "test_report_v3.py",
    "test_ai_explain_v3.py",
    "test_report_route_v3.py",
    "test_campaign_db_v4.py",
    "test_campaign_route_v4.py",
    "test_map_route_v4.py",
]

COUNT_RE = re.compile(r"\((\d+)개\)")


def run_one(filename: str) -> tuple[bool, int, str]:
    result = subprocess.run(
        [sys.executable, str(TESTS_DIR / filename)],
        capture_output=True, text=True,
    )
    ok = result.returncode == 0
    m = COUNT_RE.search(result.stdout)
    count = int(m.group(1)) if m else 0
    tail = (result.stdout + result.stderr).strip().splitlines()
    detail = tail[-1] if tail else ""
    return ok, count, detail


def main() -> int:
    total = 0
    failed = []
    print(f"── v3 회귀 {len(TEST_FILES)}개 파일 실행 ──\n")
    for filename in TEST_FILES:
        ok, count, detail = run_one(filename)
        total += count
        status = "✅" if ok else "❌"
        print(f"{status} {filename:<28} {count:>3}개  {detail if not ok else ''}")
        if not ok:
            failed.append(filename)

    print(f"\n총 {total}개 체크, 파일 {len(TEST_FILES)}개 중 실패 {len(failed)}개")
    if failed:
        print("실패 파일:", ", ".join(failed))
        return 1
    print("전 회귀 green ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
