#!/usr/bin/env python3
"""NotebookLM 자동화 파이프라인 CLI 진입점.

사용 예시:
    # 수동 실행 (URL)
    python scripts/run_pipeline.py --url "https://example.com/article"

    # 수동 실행 (텍스트)
    python scripts/run_pipeline.py --text "여기에 요약본 내용..."

    # 설정 파일 지정
    python scripts/run_pipeline.py --config configs/default.yaml --url "https://..."

    # 노트북 ID 오버라이드
    python scripts/run_pipeline.py --url "..." --notebook-id "abc-123"

    # 파일 감시 모드
    python scripts/run_pipeline.py --mode watch

    # Webhook 서버 모드
    python scripts/run_pipeline.py --mode webhook
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# src/ 를 import path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pipeline import delivery, trigger
from pipeline.config import load_config
from pipeline.core import run


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NotebookLM 자동화 파이프라인",
    )
    parser.add_argument("--url", help="입력 URL")
    parser.add_argument("--text", help="입력 텍스트 (웹 요약본)")
    parser.add_argument("--text-file", help="텍스트 파일 경로")
    parser.add_argument("--notebook-id", help="NotebookLM 노트북 UUID")
    parser.add_argument(
        "--config",
        default="configs/default.yaml",
        help="설정 파일 경로 (기본: configs/default.yaml)",
    )
    parser.add_argument(
        "--mode",
        choices=["manual", "watch", "webhook"],
        default="manual",
        help="실행 모드 (기본: manual)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="상세 로그")
    return parser.parse_args()


async def run_once(config, url: str | None, text: str | None) -> None:
    """단일 파이프라인 실행 + 전달."""
    result = await run(config, url=url, text=text)

    print(f"\n{'=' * 60}")
    print(f"파이프라인 완료")
    print(f"{'=' * 60}")
    print(f"  소스 ID:     {result['source_id']}")
    print(f"  아티팩트 ID: {result['artifact_id']}")
    print(f"  파일 경로:   {result['file_path']}")
    print(f"  타임스탬프:  {result['timestamp']}")
    print(f"  요약 (앞 200자):")
    print(f"    {result['summary'][:200]}...")
    print()

    # 전달
    delivery_result = await delivery.deliver(
        config.delivery,
        result["file_path"],
        result["summary"],
    )
    print(f"  전달 [{delivery_result['method']}]: {delivery_result['message']}")


async def run_watch(config) -> None:
    """파일 감시 모드 — 파일 생성 시마다 파이프라인 실행."""
    logger = logging.getLogger("watch")
    logger.info("파일 감시 모드 시작")

    async for event in trigger.watch_directory(config.trigger):
        logger.info("이벤트 수신: %s", event)
        try:
            await run_once(config, url=event["url"], text=event["text"])
        except Exception as e:
            logger.error("파이프라인 실패: %s", e)


async def run_webhook(config) -> None:
    """Webhook 서버 모드 — HTTP POST 수신 시마다 파이프라인 실행."""
    logger = logging.getLogger("webhook")
    logger.info("Webhook 서버 모드 시작")

    async for event in trigger.webhook_server(config.trigger):
        logger.info("이벤트 수신: %s", event)
        try:
            await run_once(config, url=event["url"], text=event["text"])
        except Exception as e:
            logger.error("파이프라인 실패: %s", e)


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    # 설정 로드
    overrides = {}
    if args.notebook_id:
        overrides["notebook_id"] = args.notebook_id
    if args.mode != "manual":
        overrides["trigger"] = {"method": args.mode}

    config = load_config(args.config, overrides)

    if not config.notebook_id:
        print("오류: notebook_id가 필요합니다.")
        print("  --notebook-id 인자를 전달하거나 configs/default.yaml에 설정하세요.")
        print("  노트북 목록 확인: nlm notebook list")
        sys.exit(1)

    # 텍스트 파일 읽기
    text = args.text
    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")

    # 모드별 실행
    if args.mode == "manual":
        if not args.url and not text:
            print("오류: --url 또는 --text (또는 --text-file) 중 하나가 필요합니다.")
            sys.exit(1)
        asyncio.run(run_once(config, url=args.url, text=text))

    elif args.mode == "watch":
        asyncio.run(run_watch(config))

    elif args.mode == "webhook":
        asyncio.run(run_webhook(config))


if __name__ == "__main__":
    main()
