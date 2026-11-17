# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
import secrets
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

pytestmark = pytest.mark.integration

MB = 1024 * 1024
LIMIT = 10 * MB
STALL = 3
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
# ghép từ hai phần để phần mềm diệt virus không xóa file này
EICAR = b"".join([b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$", b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"])
NOT_FOUND = {"detail": "Không tìm thấy file"}
ROW = "SELECT owner, status, size, sha256 FROM core.files WHERE id = '{id}'"
CLAIMS = """{{"sub": "{subject}", "role": "authenticated"}}"""
PRIVILEGES = """
SELECT role, privilege, has_table_privilege(role, 'core.files', privilege)
FROM unnest(ARRAY['anon', 'authenticated', 'core_service']) AS role,
    unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE']) AS privilege
ORDER BY role, privilege
"""


def png(size=200):
    return PNG + secrets.token_bytes(size - len(PNG))


def core(stack, method, path, token=None, **options):
    return stack.call(method, f"{stack.url}/core{path}", token=token, **options)


def declare(stack, token, name="anh-may-hong.png", type="image/png", size=200):
    fields = {"name": name, "type": type, "size": size}
    return core(stack, "POST", "/files", token, body=fields)


def declared(stack, token, content, **fields):
    reply = declare(stack, token, size=len(content), **fields)
    assert reply.status == 201, reply.body
    return json.loads(reply.body)


def upload(stack, token, file, content):
    return stack.call("PUT", file["upload_url"], token=token, content=content)


def row_of(stack, file):
    [row] = stack.sql(ROW.format(id=file["id"]))
    return row


def stored(stack, file, bucket="quarantine"):
    image = stack.inspect(stack.container("seaweedfs"), "{{.Config.Image}}")
    options = ["--rm", "--network", stack.network("storage"), "--entrypoint", "curl"]
    fields = ["--silent", "--fail", "--aws-sigv4", "aws:amz:us-east-1:s3"]
    fields += ["--user", ":".join(stack.s3_key)]
    url = f"http://seaweedfs:8333/{bucket}/{file['id']}"
    command = [stack.docker, "run", *options, image, *fields, url]
    result = subprocess.run(command, check=False, capture_output=True, timeout=60)
    return result.stdout if result.returncode == 0 else None


def audit_of(stack, file):
    query = (
        "SELECT row_to_json(log) FROM core.audit_log AS log WHERE table_name = 'files' "
        f"AND coalesce(new_row, old_row) ->> 'id' = '{file['id']}' ORDER BY id"
    )
    return [json.loads("|".join(row)) for row in stack.sql(query)]


def visible_to(stack, subject, file):
    claims = CLAIMS.format(subject=subject)
    query = f"SELECT count(*) FROM core.files WHERE id = '{file['id']}'"
    return stack.sql(f"SET ROLE authenticated; SET request.jwt.claims = '{claims}'; {query}")[-1]


@pytest.fixture
def user(stack):
    return stack.new_user()


@pytest.fixture
def token(stack, user):
    return stack.token(user)


def test_uploaded_file_waits_for_scan_in_quarantine(stack, user, token):
    content = png()
    file = declared(stack, token, content)

    reply = upload(stack, token, file, content)

    body = json.loads(reply.body)
    digest = hashlib.sha256(content).hexdigest()
    assert file["upload_url"] == f"{stack.url}/core/files/{file['id']}/content"
    assert file["status"] == "pending_upload"
    assert reply.status == 200
    assert (body["status"], body["sha256"]) == ("pending_scan", digest)
    assert row_of(stack, file) == [user.id, "pending_scan", str(len(content)), digest]
    assert stored(stack, file) == content
    assert stored(stack, file, "clean") is None


def test_audit_log_records_declaration_and_upload_by_caller(stack, user, token):
    content = png()
    file = declared(stack, token, content)
    upload(stack, token, file, content)

    entries = audit_of(stack, file)

    assert [(entry["operation"], entry["actor"], entry["db_role"]) for entry in entries] == [
        ("INSERT", user.id, "core_service"),
        ("UPDATE", user.id, "core_service"),
    ]
    assert entries[0]["new_row"]["status"] == "pending_upload"
    assert entries[1]["new_row"]["status"] == "pending_scan"
    assert entries[1]["new_row"]["sha256"] == hashlib.sha256(content).hexdigest()


def test_eicar_text_file_is_kept_in_quarantine_until_scanned(stack, token):
    file = declared(stack, token, EICAR, name="eicar.txt", type="text/plain")

    reply = upload(stack, token, file, EICAR)

    assert reply.status == 200
    assert json.loads(reply.body)["status"] == "pending_scan"
    assert stored(stack, file) == EICAR
    assert stored(stack, file, "clean") is None


def test_file_of_largest_allowed_size_passes_gateway_and_core(stack, token):
    content = png(LIMIT)
    file = declared(stack, token, content)

    too_big = upload(stack, token, file, content + b"\x00")
    reply = upload(stack, token, file, content)

    assert too_big.status == 413
    assert too_big.headers.get_content_type() == "text/html"
    assert reply.status == 200
    assert stored(stack, file) == content


def test_declared_size_over_limit_is_refused(stack, token):
    reply = declare(stack, token, size=LIMIT + 1)

    assert reply.status == 413
    assert json.loads(reply.body) == {"detail": "File vượt quá dung lượng tối đa 10 MB"}


def test_type_outside_list_is_refused(stack, token):
    reply = declare(stack, token, name="cai-dat.exe", type="application/x-msdownload")

    assert reply.status == 415
    assert "không được phép" in json.loads(reply.body)["detail"]


@pytest.mark.parametrize("change", [1, -1], ids=["dài hơn", "ngắn hơn"])
def test_content_with_other_size_is_refused_and_not_stored(stack, user, token, change):
    content = png()
    file = declared(stack, token, content)

    reply = upload(stack, token, file, content + b"\x00" if change > 0 else content[:-1])

    assert reply.status == 422
    assert "khác dung lượng đã khai báo" in json.loads(reply.body)["detail"]
    assert row_of(stack, file)[:2] == [user.id, "pending_upload"]
    assert stored(stack, file) is None


def test_content_of_other_type_is_refused_and_not_stored(stack, user, token):
    content = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff" + secrets.token_bytes(100)
    file = declared(stack, token, content)

    reply = upload(stack, token, file, content)

    assert reply.status == 422
    assert json.loads(reply.body) == {
        "detail": "Phần đầu của nội dung không đúng định dạng image/png"
    }
    assert row_of(stack, file)[:2] == [user.id, "pending_upload"]
    assert stored(stack, file) is None


def test_uploaded_file_cannot_be_replaced(stack, token):
    content = png()
    file = declared(stack, token, content)
    upload(stack, token, file, content)

    reply = upload(stack, token, file, png())

    assert (reply.status, json.loads(reply.body)) == (409, {"detail": "File đã được tải lên"})
    assert stored(stack, file) == content


def test_only_one_of_concurrent_uploads_is_kept(stack, token):
    contents = [png(MB) for _ in range(4)]
    file = declared(stack, token, contents[0])

    with ThreadPoolExecutor(len(contents)) as pool:
        paused = stack.compose_result("pause", "seaweedfs")
        try:
            futures = [pool.submit(upload, stack, token, file, content) for content in contents]
            time.sleep(STALL)
        finally:
            resumed = stack.compose_result("unpause", "seaweedfs")
        replies = [future.result() for future in futures]

    assert paused.returncode == 0, paused.stderr
    assert resumed.returncode == 0, resumed.stderr
    assert sorted(reply.status for reply in replies) == [200, 409, 409, 409]
    [winner] = [json.loads(reply.body) for reply in replies if reply.status == 200]
    assert hashlib.sha256(stored(stack, file)).hexdigest() == winner["sha256"]
    assert row_of(stack, file)[3] == winner["sha256"]


def test_user_cannot_read_or_upload_file_of_another_user(stack, token):
    other = stack.token(stack.new_user())
    content = png()
    file = declared(stack, token, content)

    uploaded_by_other = upload(stack, other, file, content)
    read_by_other = core(stack, "GET", f"/files/{file['id']}", other)
    read_by_owner = core(stack, "GET", f"/files/{file['id']}", token)

    assert (uploaded_by_other.status, json.loads(uploaded_by_other.body)) == (404, NOT_FOUND)
    assert (read_by_other.status, json.loads(read_by_other.body)) == (404, NOT_FOUND)
    assert read_by_owner.status == 200
    assert stored(stack, file) is None


def test_row_security_shows_file_to_its_owner_only(stack, user, token):
    file = declared(stack, token, png())

    assert visible_to(stack, user.id, file) == ["1"]
    assert visible_to(stack, stack.new_user().id, file) == ["0"]


def test_only_core_service_writes_files_table(stack):
    granted = {(role, privilege) for role, privilege, held in stack.sql(PRIVILEGES) if held == "t"}

    assert granted == {
        ("authenticated", "SELECT"),
        ("core_service", "INSERT"),
        ("core_service", "SELECT"),
        ("core_service", "UPDATE"),
    }


def test_file_calls_need_token_of_logged_in_user(stack, token):
    file = declared(stack, token, png())
    forged = stack.forged_tokens(stack.new_user())["sửa nội dung"]

    assert declare(stack, None).status == 401
    assert upload(stack, None, file, png()).status == 401
    assert upload(stack, forged, file, png()).status == 401
    assert core(stack, "GET", f"/files/{file['id']}").status == 401


def test_upload_waits_while_storage_is_down(stack, user, token):
    content = png()
    file = declared(stack, token, content)

    stopped = stack.compose_result("stop", "seaweedfs")
    try:
        refused = upload(stack, token, file, content)
        status_while_down = row_of(stack, file)[1]
    finally:
        started = stack.compose_result("up", "-d", "--wait", "seaweedfs")
    reply = upload(stack, token, file, content)

    assert stopped.returncode == 0, stopped.stderr
    assert started.returncode == 0, started.stderr
    assert refused.status == 503
    assert json.loads(refused.body) == {"detail": "Chưa lưu được file vì kho file chưa sẵn sàng"}
    assert status_while_down == "pending_upload"
    assert reply.status == 200
    assert stored(stack, file) == content
