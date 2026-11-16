# SPDX-License-Identifier: Apache-2.0
import json
import re
import secrets
import time

import pytest

pytestmark = pytest.mark.integration

BUCKETS = ["clean", "quarantine"]
ADMIN_UI_PORT = "12535"
TELEMETRY = "Reporting anonymous cluster statistics"


def wait_for(condition, timeout=60):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "Hết thời gian chờ"
        time.sleep(0.5)


def cookies_of(*replies):
    jar = {}
    for reply in replies:
        for cookie in reply.headers.get_all("Set-Cookie", []):
            name, _, value = cookie.split(";", 1)[0].partition("=")
            jar[name] = value
    return "; ".join(f"{name}={value}" for name, value in jar.items())


def admin_ui(stack):
    return f"http://127.0.0.1:{stack.env['SAIGONOS_SEAWEEDFS_PORT']}"


def admin_ui_login(stack, username, password):
    page = stack.call("GET", f"{admin_ui(stack)}/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', page.body.decode())[1]
    form = {"csrf_token": token, "username": username, "password": password}
    sent = stack.call(
        "POST", f"{admin_ui(stack)}/login", form=form, headers={"Cookie": cookies_of(page)}
    )
    return sent, cookies_of(page, sent)


def put_file(stack, bucket):
    path = f"/{bucket}/{secrets.token_hex(4)}.txt"
    content = secrets.token_hex(16)
    assert stack.s3("PUT", path, stack.s3_key, content)[0] == 200
    return path, content


def can_connect(stack, service, host, port):
    script = f"exec 3<>/dev/tcp/{host}/{port}"
    return stack.exec(service, "timeout", "3", "bash", "-c", script).returncode == 0


def test_doctor_reports_seaweedfs(stack):
    result = stack.saigonos("doctor")

    assert result.returncode == 0, result.stdout
    assert re.search(r"BÌNH THƯỜNG\s+seaweedfs\s+đang chạy", result.stdout)


def test_seaweedfs_has_only_the_two_buckets(stack):
    status, body = stack.s3("GET", "/", stack.s3_key)

    assert status == 200
    assert sorted(re.findall(r"<Name>([^<]+)</Name>", body)) == BUCKETS
    assert stack.s3("PUT", "/khac/a.txt", stack.s3_key, "noi dung")[0] == 404


@pytest.mark.parametrize("bucket", BUCKETS)
def test_seaweedfs_stores_and_returns_file_with_right_key(stack, bucket):
    path, content = put_file(stack, bucket)

    assert stack.s3("GET", path, stack.s3_key) == (200, content)


def test_seaweedfs_rejects_unsigned_calls(stack):
    path, _ = put_file(stack, "clean")

    assert stack.s3("GET", "/")[0] == 403
    assert stack.s3("GET", "/clean")[0] == 403
    assert stack.s3("GET", path)[0] == 403
    assert stack.s3("PUT", "/clean/khong-ky.txt", body="noi dung")[0] == 403


def test_seaweedfs_rejects_wrong_signature(stack):
    path, _ = put_file(stack, "clean")
    access_key, secret_key = stack.s3_key

    assert stack.s3("GET", path, (access_key, f"{secret_key}x"))[0] == 403
    assert stack.s3("GET", path, ("khoa-khong-co", secret_key))[0] == 403
    assert stack.s3("PUT", path, (access_key, "sai"), "ghi de")[0] == 403
    assert stack.s3("GET", path, stack.s3_key)[0] == 200


def test_seaweedfs_lists_no_directory(stack):
    put_file(stack, "clean")

    status, _ = stack.storage_call("GET", "http://seaweedfs:8888/buckets/clean/")

    assert status == 403


def test_seaweedfs_sends_no_statistics(stack):
    logs = stack.logs("seaweedfs")

    assert "S3 Endpoint" in logs
    assert TELEMETRY not in logs


def test_admin_ui_listens_on_loopback_only(stack):
    port = stack.env["SAIGONOS_SEAWEEDFS_PORT"]

    assert stack.compose("port", "seaweedfs", ADMIN_UI_PORT) == f"127.0.0.1:{port}"


def test_admin_ui_requires_password(stack):
    page = stack.call("GET", f"{admin_ui(stack)}/")
    api = f"{admin_ui(stack)}/api/s3/buckets"

    wrong, wrong_session = admin_ui_login(stack, "admin", "sai-mat-khau")
    right, session = admin_ui_login(stack, "admin", stack.env["SEAWEEDFS_ADMIN_PASSWORD"])

    assert page.status == 307
    assert page.headers["Location"].endswith("/login")
    assert stack.call("GET", api).status == 401
    assert wrong.status == 303
    assert "error=" in wrong.headers["Location"]
    assert stack.call("GET", api, headers={"Cookie": wrong_session}).status == 401
    assert right.status == 303
    assert right.headers["Location"].endswith("/admin")
    reply = stack.call("GET", api, headers={"Cookie": session})
    assert reply.status == 200
    assert sorted(bucket["name"] for bucket in json.loads(reply.body)["buckets"]) == BUCKETS


def test_only_seaweedfs_joins_storage_network(stack):
    services = json.loads(stack.compose("config", "--format", "json"))["services"]

    members = {name for name, service in services.items() if "storage" in service["networks"]}

    assert members == {"seaweedfs"}
    assert set(services["seaweedfs"]["networks"]) == {"storage"}


def test_gateway_cannot_reach_seaweedfs(stack):
    container = stack.container("seaweedfs")
    address = stack.inspect(container, "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}")

    for path in ["/clean/a.txt", "/quarantine", "/buckets/clean/", "/admin"]:
        assert stack.call("GET", f"{stack.url}{path}").status == 404
    assert can_connect(stack, "apisix", "keycloak", 8080)
    assert not can_connect(stack, "apisix", "seaweedfs", 8333)
    assert not can_connect(stack, "apisix", address, 8333)
    assert not can_connect(stack, "apisix", address, 8888)


def test_seaweedfs_keeps_files_when_container_is_recreated(stack):
    path, content = put_file(stack, "quarantine")
    container = stack.container("seaweedfs")

    result = stack.compose_result("up", "-d", "--wait", "--force-recreate", "seaweedfs")

    assert result.returncode == 0, result.stderr
    assert stack.container("seaweedfs") != container
    assert stack.s3("GET", path, stack.s3_key) == (200, content)


def test_killed_seaweedfs_restarts_by_itself(stack):
    path, content = put_file(stack, "clean")
    container = stack.container("seaweedfs")
    restarts = int(stack.inspect(container, "{{.RestartCount}}"))
    state = "{{.RestartCount}} {{.State.Health.Status}}"

    stack.kill(container)

    wait_for(lambda: stack.inspect(container, state) == f"{restarts + 1} healthy")
    assert stack.s3("GET", path, stack.s3_key) == (200, content)


def test_seaweedfs_accepts_only_new_key_after_change_in_env(stack):
    path, content = put_file(stack, "clean")
    old_key = stack.s3_key
    env_file = stack.home / ".env"
    lines = env_file.read_text(encoding="utf-8").splitlines()
    changed = [
        f"SEAWEEDFS_SECRET_KEY={secrets.token_hex(16)}"
        if line.startswith("SEAWEEDFS_SECRET_KEY=")
        else line
        for line in lines
    ]
    env_file.write_text("\n".join(changed) + "\n", encoding="utf-8")

    result = stack.saigonos("up")

    assert result.returncode == 0, result.stderr
    assert stack.s3_key != old_key
    assert stack.s3("GET", path, old_key)[0] == 403
    assert stack.s3("GET", path, stack.s3_key) == (200, content)
