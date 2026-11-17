# SPDX-License-Identifier: Apache-2.0
import re
from importlib.metadata import version

import dependencies
import pytest

DEV_ALLOWED = dependencies.ALLOWED_LICENSES | dependencies.DEV_ONLY_LICENSES


@pytest.fixture
def table_file(monkeypatch, tmp_path):
    path = tmp_path / "DEPENDENCIES.md"
    monkeypatch.setattr(dependencies, "TABLE_FILE", path)
    return path


def write_lock(tmp_path, content, name="requirements.txt"):
    lock_file = tmp_path / name
    lock_file.write_text(content, encoding="utf-8")
    return lock_file


def write_stack(tmp_path, *references):
    stack_file = tmp_path / "compose.yaml"
    services = [f"  s{index}:\n    image: {image}\n" for index, image in enumerate(references)]
    stack_file.write_text("services:\n" + "".join(services), encoding="utf-8")
    return stack_file


def test_read_lock_returns_pinned_versions(tmp_path):
    lock_file = write_lock(
        tmp_path,
        "# header\nClick==8.5.1\n    # via saigonos\nboolean.py==5.0 ; python_version < '3.13'\n",
    )

    assert dependencies.read_lock(lock_file) == {"click": "8.5.1", "boolean-py": "5.0"}


def test_read_declared_splits_product_core_and_dev_dependencies():
    runtime, core, dev = dependencies.read_declared(dependencies.PROJECT_FILE)

    assert runtime == {"click"}
    assert core == {"asyncpg", "fastapi", "pyjwt", "uvicorn"}
    assert {"pytest", "reuse", "ruff"} <= dev
    assert not dev & (runtime | core)


@pytest.mark.parametrize("reported", ["MIT", "Apache-2.0 OR BSD-2-Clause", "(MIT AND ISC)"])
def test_allowed_license_is_kept(reported):
    assert dependencies.resolve_license("demo", reported, dependencies.ALLOWED_LICENSES) == reported


@pytest.mark.parametrize(
    "reported", ["GPL-3.0-or-later", "BSD License", "UNKNOWN", "MIT OR Proprietary", ""]
)
def test_unknown_license_is_rejected(reported):
    with pytest.raises(dependencies.DependencyError, match="ngoài danh sách cho phép"):
        dependencies.resolve_license("demo", reported, dependencies.ALLOWED_LICENSES)


def test_dev_tool_may_use_dev_only_license():
    license_expression = dependencies.resolve_license("demo", "GPL-3.0-or-later", DEV_ALLOWED)

    assert license_expression == "GPL-3.0-or-later"


def test_verified_license_replaces_reported_one(monkeypatch):
    monkeypatch.setitem(dependencies.VERIFIED_LICENSES, "demo", "BSD-3-Clause")

    assert dependencies.resolve_license("demo", "BSD License", DEV_ALLOWED) == "BSD-3-Clause"


@pytest.mark.parametrize(
    ("items", "expected"),
    [([], ""), (["MIT"], "MIT"), (["MIT", "ISC"], "ISC và MIT"), (["c", "a", "b"], "a, b và c")],
)
def test_vietnamese_list_joins_last_item_with_va(items, expected):
    assert dependencies.vietnamese_list(items) == expected


def test_table_lists_every_product_library_and_dev_tool():
    table = dependencies.build_table()

    locked = dependencies.read_lock(dependencies.LOCK_FILE)
    dev_locked = dependencies.read_lock(dependencies.DEV_LOCK_FILE)
    _, _, dev = dependencies.read_declared(dependencies.PROJECT_FILE)
    assert locked
    for name, pinned in locked.items():
        assert f"| {name} | {pinned} |" in table
    for name in dev:
        assert f"| {name} | {dev_locked[name]} |" in table
    assert table.index(dependencies.RUNTIME_SECTION) < table.index(dependencies.DEV_SECTION)


def test_table_lists_every_library_of_core_service():
    table = dependencies.build_table()

    locked = dependencies.read_lock(dependencies.CORE_LOCK_FILE)
    _, core, _ = dependencies.read_declared(dependencies.PROJECT_FILE)
    rows = table[table.index(dependencies.CORE_SECTION) : table.index(dependencies.IMAGE_SECTION)]
    assert core <= locked.keys()
    for name, pinned in locked.items():
        assert f"| {name} | {pinned} |" in rows
    for name in core:
        assert f"| {dependencies.DESCRIPTIONS[name]} |" in rows
    assert f"| click | {locked['click']} | BSD-3-Clause | {dependencies.INDIRECT} |" in rows
    assert table.index(dependencies.RUNTIME_SECTION) < table.index(dependencies.CORE_SECTION)


def test_core_lock_pins_every_file_by_hash():
    text = dependencies.CORE_LOCK_FILE.read_text(encoding="utf-8")

    pins = re.findall(r"^\S+==\S+( \\\n    --hash=sha256:[0-9a-f]{64})?", text, re.MULTILINE)
    assert pins
    assert all(pins)


def test_footer_states_allowed_licenses():
    table = dependencies.build_table()

    assert "Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, MIT, MIT-0 và PSF-2.0" in table
    assert "CC-BY-SA-4.0, CC0-1.0 và GPL-3.0-or-later" in table
    assert "Apache-2.0, GPL-2.0-only, MIT, PostgreSQL và Python-2.0.1" in table
    assert "GPL-2.0-only chỉ được chạy trong container riêng" in table


def test_gpl_is_allowed_for_images_only():
    expression = dependencies.resolve_license("demo", "GPL-2.0-only", dependencies.IMAGE_LICENSES)

    assert expression == "GPL-2.0-only"
    with pytest.raises(dependencies.DependencyError, match="ngoài danh sách cho phép"):
        dependencies.resolve_license("demo", "GPL-2.0-only", DEV_ALLOWED)


def test_empty_lock_gives_product_table_without_rows(tmp_path):
    table = dependencies.build_table(write_lock(tmp_path, ""))

    assert dependencies.RUNTIME_SECTION + dependencies.CORE_SECTION in table


def test_indirect_dependency_gets_generic_description(tmp_path):
    pinned = version("iniconfig")
    lock_file = write_lock(tmp_path, f"iniconfig=={pinned}\n")

    table = dependencies.build_table(lock_file)

    assert f"| iniconfig | {pinned} | MIT | {dependencies.INDIRECT} |" in table


@pytest.mark.parametrize("name", ["click", "fastapi", "httpx2"])
def test_direct_dependency_without_description_is_rejected(monkeypatch, name):
    monkeypatch.delitem(dependencies.DESCRIPTIONS, name)

    with pytest.raises(dependencies.DependencyError, match=f"{name} chưa có mô tả"):
        dependencies.build_table()


def test_dev_tool_missing_from_dev_lock_is_rejected(tmp_path):
    dev_lock_file = write_lock(tmp_path, "", "requirements-dev.txt")

    with pytest.raises(dependencies.DependencyError, match=r"chưa có trong requirements-dev\.txt"):
        dependencies.build_table(dev_lock_file=dev_lock_file)


def test_lock_that_differs_from_environment_is_rejected(tmp_path):
    lock_file = write_lock(tmp_path, "click==0.0.1\n")

    with pytest.raises(dependencies.DependencyError, match=r"lock file ghi 0\.0\.1"):
        dependencies.build_table(lock_file)


def test_core_lock_that_differs_from_environment_is_rejected(tmp_path):
    core_lock_file = write_lock(tmp_path, "fastapi==0.0.1\n")

    with pytest.raises(dependencies.DependencyError, match=r"fastapi: lock file ghi 0\.0\.1"):
        dependencies.build_table(core_lock_file=core_lock_file)


def test_package_that_is_not_installed_is_rejected(tmp_path):
    lock_file = write_lock(tmp_path, "khong-co-goi-nay==1.0\n")

    with pytest.raises(dependencies.DependencyError, match="chưa cài"):
        dependencies.build_table(lock_file)


def test_read_images_returns_each_image_once(tmp_path):
    stack_file = write_stack(tmp_path, "demo/b:2.0", "quay.io/demo/a:v1.0", "demo/b:2.0")

    assert dependencies.read_images(stack_file) == ["demo/b:2.0", "quay.io/demo/a:v1.0"]


def test_table_lists_every_image_of_the_stack():
    table = dependencies.build_table()

    references = dependencies.read_images(dependencies.STACK_FILE)
    assert references
    for reference in references:
        name, _, tag = reference.rpartition(":")
        image = dependencies.IMAGES[reference]
        assert f"| {name} | {tag} | {image.license} | {image.description} |" in table
    assert table.index(dependencies.RUNTIME_SECTION) < table.index(dependencies.IMAGE_SECTION)
    assert table.index(dependencies.IMAGE_SECTION) < table.index(dependencies.DEV_SECTION)


def write_dockerfile(tmp_path, *references):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("".join(f"FROM {image}\n" for image in references), encoding="utf-8")
    return dockerfile


def test_read_base_images_returns_images_without_digest(tmp_path):
    digest = "sha256:" + "a" * 64
    dockerfile = write_dockerfile(tmp_path, f"demo/a:1.0@{digest} AS build", f"demo/b:2.0@{digest}")

    assert dependencies.read_base_images(dockerfile) == ["demo/a:1.0", "demo/b:2.0"]


@pytest.mark.parametrize("reference", ["python:3.14.10-slim", "python:3.14.10-slim@sha256:abc"])
def test_base_image_without_digest_is_rejected(tmp_path, reference):
    with pytest.raises(dependencies.DependencyError, match="chưa ghi digest"):
        dependencies.build_table(dockerfile=write_dockerfile(tmp_path, reference))


def test_table_lists_base_image_of_core_service():
    table = dependencies.build_table()

    [reference] = dependencies.read_base_images(dependencies.DOCKERFILE)
    name, _, tag = reference.rpartition(":")
    image = dependencies.IMAGES[reference]
    assert f"| {name} | {tag} | {image.license} | {image.description} |" in table
    assert reference not in dependencies.read_images(dependencies.STACK_FILE)


def test_undeclared_base_image_is_rejected(tmp_path):
    dockerfile = write_dockerfile(tmp_path, "python:3.15.2-slim-trixie@sha256:" + "a" * 64)

    with pytest.raises(dependencies.DependencyError, match="chưa được khai báo"):
        dependencies.build_table(dockerfile=dockerfile)


@pytest.mark.parametrize("reference", ["demo/new:1.0", "postgres:19.0-alpine"])
def test_undeclared_image_is_rejected(tmp_path, reference):
    stack_file = write_stack(tmp_path, *dependencies.IMAGES, reference)

    with pytest.raises(dependencies.DependencyError, match="chưa được khai báo"):
        dependencies.build_table(stack_file=stack_file)


@pytest.mark.parametrize("reference", ["postgres", "postgres:latest", "localhost:5000/postgres"])
def test_image_without_pinned_version_is_rejected(monkeypatch, reference):
    image = dependencies.Image("MIT", "Mô tả", "https://example.org/demo")
    monkeypatch.setattr(dependencies, "IMAGES", {reference: image})

    with pytest.raises(dependencies.DependencyError, match="chưa cố định phiên bản"):
        dependencies.build_image_rows([reference])


def test_declared_image_missing_from_stack_is_rejected(tmp_path):
    kept = sorted(dependencies.IMAGES)[1:]

    with pytest.raises(dependencies.DependencyError, match=r"không còn trong compose\.yaml"):
        dependencies.build_table(stack_file=write_stack(tmp_path, *kept))


def test_image_license_outside_allowed_list_is_rejected(monkeypatch):
    image = dependencies.Image("SSPL-1.0", "Mô tả", "https://example.org/demo/tree/v7.0")
    monkeypatch.setattr(dependencies, "IMAGES", {"demo/db:7.0": image})

    with pytest.raises(dependencies.DependencyError, match="ngoài danh sách cho phép"):
        dependencies.build_image_rows(["demo/db:7.0"])


def test_image_source_of_another_version_is_rejected(monkeypatch):
    image = dependencies.Image("MIT", "Mô tả", "https://example.org/demo/tree/v6.9")
    monkeypatch.setattr(dependencies, "IMAGES", {"demo/db:7.0-alpine": image})

    with pytest.raises(dependencies.DependencyError, match="không dẫn tới mã nguồn"):
        dependencies.build_image_rows(["demo/db:7.0-alpine"])


def test_generated_table_passes_check(table_file):
    assert dependencies.main([]) == 0
    assert dependencies.main(["--check"]) == 0


def test_check_fails_when_table_differs(table_file, capsys):
    table_file.write_text("bảng cũ\n", encoding="utf-8")

    assert dependencies.main(["--check"]) == 1
    assert "không khớp với lock file" in capsys.readouterr().err
    assert table_file.read_text(encoding="utf-8") == "bảng cũ\n"


def test_check_fails_on_undeclared_image(monkeypatch, table_file, capsys):
    monkeypatch.delitem(dependencies.IMAGES, "postgres:18.6-alpine")

    assert dependencies.main(["--check"]) == 1
    assert "Image postgres:18.6-alpine chưa được khai báo" in capsys.readouterr().err
    assert not table_file.exists()


def test_check_fails_on_unknown_license(monkeypatch, table_file, capsys):
    monkeypatch.setattr(dependencies, "ALLOWED_LICENSES", set())

    assert dependencies.main(["--check"]) == 1
    assert "ngoài danh sách cho phép" in capsys.readouterr().err
    assert not table_file.exists()
