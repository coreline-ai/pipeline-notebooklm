"""config 모듈 테스트."""

from pipeline.config import PipelineConfig, load_config


def test_load_defaults():
    """기본값으로 설정 로드."""
    config = load_config()
    assert isinstance(config, PipelineConfig)
    assert config.notebook_id == ""
    assert config.source.wait is True
    assert config.source.wait_timeout == 300
    assert config.infographic.orientation == "landscape"
    assert config.infographic.style == "professional"
    assert config.poller.interval == 10
    assert config.poller.max_wait == 300
    assert config.delivery.method == "file"
    assert config.trigger.method == "manual"


def test_load_with_overrides():
    """오버라이드 적용."""
    config = load_config(overrides={
        "notebook_id": "test-123",
        "infographic": {"style": "editorial"},
    })
    assert config.notebook_id == "test-123"
    assert config.infographic.style == "editorial"
    # 오버라이드하지 않은 값은 기본값 유지
    assert config.infographic.orientation == "landscape"


def test_load_yaml_file(tmp_path):
    """YAML 파일에서 설정 로드."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text(
        "notebook_id: yaml-123\n"
        "infographic:\n"
        "  style: scientific\n"
        "  orientation: portrait\n"
    )
    config = load_config(yaml_file)
    assert config.notebook_id == "yaml-123"
    assert config.infographic.style == "scientific"
    assert config.infographic.orientation == "portrait"
    # YAML에 없는 값은 기본값
    assert config.infographic.detail_level == "detailed"
