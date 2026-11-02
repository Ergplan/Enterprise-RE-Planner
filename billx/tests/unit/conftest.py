import pytest


@pytest.fixture(scope="session")
def ocr_cache(tmp_path_factory):
    """One OCR cache for the whole run: the synthetic pages are byte-identical for a seed, so
    every module after the first reads them from the cache instead of the engine."""
    return tmp_path_factory.mktemp("ocr-cache")


def pytest_collection_modifyitems(items):
    """OCR tests share one xdist worker (`--dist loadgroup`): two OCR engines on one machine
    thrash each other's threads and run tens of times slower."""
    for item in items:
        if item.get_closest_marker("ocr"):
            item.add_marker(pytest.mark.xdist_group("ocr"))


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch, ocr_cache):
    """No test reads ~/billx-data, ~/billx/.env or a real key."""
    monkeypatch.setenv("BILLX_DATA_DIR", str(tmp_path / "billx-data"))
    monkeypatch.setenv("BILLX_OCR_CACHE", str(ocr_cache))
    monkeypatch.setenv("BILLX_ENV_FILE", str(tmp_path / "no.env"))
    for name in (
        "BILLX_OPENAI_API_KEY",
        "BILLX_ANTHROPIC_API_KEY",
        "BILLX_MODEL_A",
        "BILLX_MODEL_B",
        "BILLX_CONFIG_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
