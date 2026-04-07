"""설정 로드 및 검증."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

_DEFAULTS = {
    "notebook_id": "",
    "source": {"wait": True, "wait_timeout": 300},
    "summary": {
        "prompt": "이 내용의 핵심을 3가지로 요약하고 시사점을 도출해줘",
        "use_as_focus": True,
        "max_focus_length": 500,
    },
    "infographic": {
        "orientation": "landscape",
        "detail_level": "detailed",
        "style": "professional",
        "language": "ko",
        "focus_prompt": "",
    },
    "poller": {"interval": 10, "max_wait": 300},
    "download": {
        "output_dir": "./output",
        "filename_template": "infographic_{timestamp}.png",
    },
    "delivery": {"method": "file"},
    "trigger": {"method": "manual"},
}


@dataclass
class SourceConfig:
    wait: bool = True
    wait_timeout: float = 300


@dataclass
class SummaryConfig:
    prompt: str = "이 내용의 핵심을 3가지로 요약하고 시사점을 도출해줘"
    use_as_focus: bool = True
    max_focus_length: int = 500


@dataclass
class InfographicConfig:
    orientation: str = "landscape"
    detail_level: str = "detailed"
    style: str = "professional"
    language: str = "ko"
    focus_prompt: str = ""


@dataclass
class PollerConfig:
    interval: int = 10
    max_wait: int = 300


@dataclass
class DownloadConfig:
    output_dir: str = "./output"
    filename_template: str = "infographic_{timestamp}.png"


@dataclass
class DeliveryConfig:
    method: str = "file"
    slack: dict = field(default_factory=dict)
    email: dict = field(default_factory=dict)


@dataclass
class TriggerConfig:
    method: str = "manual"
    cron: dict = field(default_factory=dict)
    webhook: dict = field(default_factory=dict)
    watch: dict = field(default_factory=dict)


@dataclass
class PipelineConfig:
    notebook_id: str = ""
    source: SourceConfig = field(default_factory=SourceConfig)
    summary: SummaryConfig = field(default_factory=SummaryConfig)
    infographic: InfographicConfig = field(default_factory=InfographicConfig)
    poller: PollerConfig = field(default_factory=PollerConfig)
    download: DownloadConfig = field(default_factory=DownloadConfig)
    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)
    trigger: TriggerConfig = field(default_factory=TriggerConfig)


def _merge(base: dict, override: dict) -> dict:
    """딥 머지: override 값으로 base를 업데이트."""
    merged = base.copy()
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _merge(merged[key], val)
        else:
            merged[key] = val
    return merged


def _dict_to_config(data: dict) -> PipelineConfig:
    """딕셔너리를 PipelineConfig 데이터클래스로 변환."""
    return PipelineConfig(
        notebook_id=data.get("notebook_id", ""),
        source=SourceConfig(**data.get("source", {})),
        summary=SummaryConfig(**data.get("summary", {})),
        infographic=InfographicConfig(**data.get("infographic", {})),
        poller=PollerConfig(**data.get("poller", {})),
        download=DownloadConfig(**data.get("download", {})),
        delivery=DeliveryConfig(**data.get("delivery", {})),
        trigger=TriggerConfig(**data.get("trigger", {})),
    )


def load_config(
    config_path: str | Path | None = None,
    overrides: dict | None = None,
) -> PipelineConfig:
    """설정 파일 로드.

    Args:
        config_path: YAML 설정 파일 경로. None이면 기본값 사용.
        overrides: 설정 파일 위에 덮어쓸 값 (CLI 인자 등).

    Returns:
        PipelineConfig 인스턴스
    """
    data = _DEFAULTS.copy()

    if config_path:
        path = Path(config_path)
        if path.exists():
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = _merge(data, raw)

    if overrides:
        data = _merge(data, overrides)

    return _dict_to_config(data)
