"""Static checks of the engine image, the compose file, the CI file and the memory script
(build prompt Stage 2.5; developer guide section 12). They read the files as text and YAML;
nothing here needs docker."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "docker" / "engine.Dockerfile").read_text(encoding="utf-8")
COMPOSE_TEXT = (ROOT / "docker" / "compose.yaml").read_text(encoding="utf-8")
CI_TEXT = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
MEASURE = ROOT / "tools" / "image" / "measure_memory.sh"

IMAGE_JOBS = ["images", "identifier-search-image", "release-to-esgos", "ocr-check-amd64"]
SECRET_NAMES = ["PASSWORD", "_KEY", "TOKEN", "SECRET"]
# What a key or token literal looks like; none may appear in a tracked docker or CI file.
LITERAL_SECRET = re.compile(
    r"(sk-[A-Za-z0-9]{10,}|sk-ant-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{12,}|glpat-[A-Za-z0-9_-]{10,}"
    r"|BILLX_TOKEN\s*[=:]\s*[\"']?[A-Za-z0-9+/=_-]{8,})"
)


def _instructions(name: str) -> list[str]:
    """The arguments of every `name` instruction in the Dockerfile, continuation lines joined."""
    joined = re.sub(r"\\\n\s*", " ", DOCKERFILE)
    return [
        line[len(name) :].strip()
        for line in joined.splitlines()
        if line.startswith(name + " ") or line == name
    ]


# --- docker/engine.Dockerfile ------------------------------------------------------------------


def test_dockerfile_runs_as_the_non_root_user_10001():
    users = _instructions("USER")
    assert users, "no USER instruction"
    assert users[-1] in ("billx", "10001", "billx:billx", "10001:10001")
    assert "--uid 10001" in DOCKERFILE


def test_dockerfile_declares_the_data_volume_port_entrypoint_and_command():
    assert '["/data"]' in "".join(_instructions("VOLUME"))
    assert _instructions("EXPOSE") == ["8080"]
    assert _instructions("ENTRYPOINT") == ['["billx"]']
    assert _instructions("CMD") == ['["serve"]']


def test_dockerfile_sets_the_runtime_paths_in_the_environment():
    env = " ".join(_instructions("ENV"))
    assert "BILLX_DATA_DIR=/data" in env
    assert "BILLX_OCR_CACHE=/data/cache/ocr" in env
    assert "PADDLE_PDX_CACHE_HOME=" in env, "the OCR models must have a home inside the image"


def test_dockerfile_builds_the_ocr_models_in_and_installs_the_ocr_extra():
    runs = " ".join(_instructions("RUN"))
    assert "docker/ocr_warmup.py" in runs, "the warm-up that downloads the models at build time"
    assert "[ocr]" in runs
    for lib in ("libgl1", "libglib2.0-0", "libgomp1"):
        assert lib in runs


def test_dockerfile_health_check_calls_v1_health_with_the_token_from_the_environment():
    (health,) = _instructions("HEALTHCHECK")
    assert "/v1/health" in health
    assert "BILLX_TOKEN" in health and "environ" in health


def test_dockerfile_bases_on_python_312_slim():
    assert _instructions("FROM") == ["python:3.12-slim"]


# --- docker/compose.yaml -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE_TEXT)


def test_compose_has_the_bill_engine_service_read_only_with_tmpfs_and_a_memory_limit(compose):
    service = compose["services"]["bill-engine"]
    assert service["read_only"] is True
    assert any(str(t).startswith("/tmp") for t in service["tmpfs"])
    assert service["mem_limit"] == "2g"
    assert "./data:/data" in service["volumes"]
    assert any(str(p).endswith(":8080") for p in service["ports"])


def test_compose_passes_the_env_names_the_api_reads(compose):
    env = compose["services"]["bill-engine"]["environment"]
    assert "BILLX_TOKEN" in env["BILLX_TOKEN"], "the token comes from .env, never a literal"
    assert env["BILLX_API_MODE"] == "${BILLX_API_MODE:-esgos-1.1}"
    assert env["BILLX_DATA_DIR"] == "/data"
    assert "BILLX_MAX_JOBS" in env


def test_compose_says_how_esgos_wires_it():
    assert "BILL_ENGINE_URL=http://bill-engine:8080" in COMPOSE_TEXT
    assert "BILL_ENGINE_TOKEN" in COMPOSE_TEXT


# --- .gitlab-ci.yml ----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ci() -> dict:
    return yaml.safe_load(CI_TEXT)


def test_ci_keeps_the_stage_0_jobs_and_adds_the_four_image_jobs(ci):
    assert ci["stages"] == ["checks", "images", "release"]
    assert "checks" in ci and "gitleaks" in ci
    for job in IMAGE_JOBS:
        assert job in ci, f"missing job {job}"
    assert ci["images"]["stage"] == "images"
    assert ci["identifier-search-image"]["stage"] == "images"
    assert ci["release-to-esgos"]["stage"] == "release"
    assert ci["ocr-check-amd64"]["stage"] == "checks"


def test_ci_image_jobs_use_docker_in_docker_and_buildx(ci):
    for job in IMAGE_JOBS:
        assert ci[job]["image"] == "docker:27"
        assert "docker:27-dind" in ci[job]["services"]
    script = "\n".join(ci["images"]["before_script"] + ci["images"]["script"])
    assert "binfmt" in script, "QEMU for the other platform"
    assert "docker buildx build" in script and "--push" in script
    assert "$CI_COMMIT_SHA" in script and "$CI_COMMIT_REF_SLUG" in script
    assert "$CI_REGISTRY_USER" in script and "$CI_REGISTRY_PASSWORD" in script


def test_ci_identifier_search_runs_over_the_exported_amd64_image(ci):
    script = "\n".join(ci["identifier-search-image"]["script"])
    assert "docker export" in script
    assert "tools/identifiers.py --require --tar" in script
    assert "linux/amd64" in script


def test_ci_release_copies_by_digest_on_a_tag_only_when_the_esgos_variables_exist(ci):
    job = ci["release-to-esgos"]
    rule = job["rules"][0]["if"]
    assert "$CI_COMMIT_TAG" in rule and "$ESGOS_REGISTRY" in rule and "$ESGOS_REGISTRY_KEY" in rule
    script = "\n".join(job["before_script"] + job["script"])
    assert "_json_key" in script
    assert "docker buildx imagetools create" in script
    assert "@$DIGEST" in script, "the copy is by digest"


def test_ci_amd64_ocr_check_is_manual_on_the_default_branch(ci):
    job = ci["ocr-check-amd64"]
    assert job["rules"][0]["when"] == "manual"
    assert "$CI_DEFAULT_BRANCH" in job["rules"][0]["if"]
    assert "docker/ocr-check.Dockerfile" in "\n".join(job["script"])


def test_ci_never_echoes_a_secret():
    """A secret may reach stdout only as the piped input of `docker login --password-stdin`."""
    for line in CI_TEXT.splitlines():
        if "echo" not in line:
            continue
        if any(name in line for name in SECRET_NAMES):
            assert "--password-stdin" in line, line
    assert "CI_DEBUG_TRACE" not in CI_TEXT
    assert "set -x" not in CI_TEXT


def test_ci_documents_its_variables():
    for name in ("CLIENT_IDENTIFIERS", "ESGOS_REGISTRY", "ESGOS_REGISTRY_KEY"):
        assert name in CI_TEXT.split("stages:")[0], f"{name} is not documented at the top"


# --- no secret literal anywhere in these files ---------------------------------------------------


@pytest.mark.parametrize(
    "text", [DOCKERFILE, COMPOSE_TEXT, CI_TEXT], ids=["docker", "compose", "ci"]
)
def test_no_key_or_token_literal(text):
    assert not LITERAL_SECRET.search(text)


# --- tools/image/measure_memory.sh -------------------------------------------------------------


def test_measure_memory_script_is_executable_and_parses():
    assert MEASURE.stat().st_mode & 0o111, "not executable"
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash")
    subprocess.run([bash, "-n", str(MEASURE)], check=True)
    text = MEASURE.read_text(encoding="utf-8")
    assert "BILLX_MAX_JOBS=$JOBS" in text and "JOBS=4" in text
    assert "/v1/jobs" in text and "/v1/health" in text and "docker stats" in text
    assert "--read-only" in text
    for line in text.splitlines():
        if "echo" in line or "printf" in line:
            assert "TOKEN" not in line or "headers" in line, f"the token is never printed: {line}"
