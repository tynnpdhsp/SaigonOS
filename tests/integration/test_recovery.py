# SPDX-License-Identifier: Apache-2.0
import base64
import json
import secrets
import tarfile
import time
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.integration

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
BROWSER = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8", "User-Agent": "Mozilla/5.0"}
NOTES_SQL = """\
CREATE TABLE notes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    body text NOT NULL,
    owner text NOT NULL DEFAULT core.uid()
);
ALTER TABLE notes ENABLE ROW LEVEL SECURITY;
CREATE POLICY own ON notes USING (owner = core.uid());
CREATE TRIGGER audit AFTER INSERT OR UPDATE OR DELETE ON notes
    FOR EACH ROW EXECUTE FUNCTION core.audit();
GRANT SELECT, INSERT ON notes TO {schema}_user;
"""
SAVED = "Ghi chú trước khi sao lưu"
LATER = "Ghi chú sau khi sao lưu"
PARTS = ["manifest.json", "SHA256SUMS", "env", "postgres.sql", "seaweedfs.tar", "apps.tar"]
SERVICES = ("postgres", "seaweedfs", "keycloak", "apisix")


def notes_app(folder, name):
    manifest = {
        "name": name,
        "title": "Ghi chú thử",
        "version": "0.1.0",
        "roles": [{"name": f"{name}.nguoi-dung", "description": "Người dùng ghi chú"}],
        "database": "database",
    }
    (folder / "database").mkdir(parents=True)
    sql = NOTES_SQL.format(schema=name.replace("-", "_"))
    (folder / "database" / "0001_notes.sql").write_text(sql, encoding="utf-8")
    text = json.dumps(manifest, ensure_ascii=False, indent=2)
    (folder / "saigonos-app.json").write_text(text, encoding="utf-8")
    return folder


def notes(stack, method, name, token, body=None):
    return stack.call(method, f"{stack.url}/apps/{name}/api/notes", token=token, body=body)


def served_notes(stack, name, token):
    deadline = time.monotonic() + 15
    while (reply := notes(stack, "GET", name, token)).status != 200:
        assert time.monotonic() < deadline, "PostgREST chưa phục vụ schema của ứng dụng"
        time.sleep(0.2)
    return [(note["body"], note["owner"]) for note in json.loads(reply.body)]


def upload(stack, token, content):
    fields = {"name": "anh-may-hong.png", "type": "image/png", "size": len(content)}
    declared = stack.call("POST", f"{stack.url}/core/files", token=token, body=fields)
    assert declared.status == 201, declared.body
    file = json.loads(declared.body)
    sent = stack.call("PUT", file["upload_url"], token=token, content=content)
    assert sent.status == 200, sent.body
    deadline = time.monotonic() + 60
    while stack.sql(f"SELECT status FROM core.files WHERE id = '{file['id']}'") != [["clean"]]:
        assert time.monotonic() < deadline, "File chưa được quét xong"
        time.sleep(0.5)
    return file


def download(stack, token, file):
    link = stack.call("POST", f"{stack.url}/core/files/{file['id']}/download-url", token=token)
    assert link.status == 200, link.body
    return stack.call("GET", json.loads(link.body)["download_url"], headers=BROWSER)


def roles_in(token):
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return sorted(claims["realm_access"]["roles"])


def started_at(stack, service):
    return stack.inspect(stack.container(service), "{{.State.StartedAt}}")


def assert_restored(stack, saved):
    token = stack.app_token(saved.user, saved.name)
    reply = download(stack, stack.token(saved.user), saved.file)
    audit = stack.saigonos("audit", "verify")
    doctor = stack.saigonos("doctor")
    assert served_notes(stack, saved.name, token) == [(SAVED, saved.user.id)]
    assert roles_in(token) == ["authenticated", f"{saved.name}.nguoi-dung"]
    assert (reply.status, reply.body) == (200, saved.content)
    assert (audit.returncode, audit.stdout) == (0, saved.audit)
    assert doctor.returncode == 0, doctor.stdout


@pytest.fixture(scope="module")
def saved(stack, tmp_path_factory):
    name = f"thu-{secrets.token_hex(3)}"
    app = notes_app(tmp_path_factory.mktemp("ung-dung") / name, name)
    applied = stack.saigonos("apply", str(app))
    assert applied.returncode == 0, applied.stdout + applied.stderr
    user = stack.new_user(role=f"{name}.nguoi-dung")
    token = stack.app_token(user, name)
    assert served_notes(stack, name, token) == []
    assert notes(stack, "POST", name, token, {"body": SAVED}).status == 201
    content = PNG + secrets.token_bytes(200)
    file = upload(stack, stack.token(user), content)
    audit = stack.saigonos("audit", "verify")
    assert audit.returncode == 0, audit.stdout
    made = stack.saigonos("backup")
    assert made.returncode == 0, made.stdout + made.stderr
    [bundle] = (stack.home / "backups").glob("saigonos-*.tar.gz")
    assert f"Đã tạo gói sao lưu {bundle}, " in made.stdout
    return SimpleNamespace(
        name=name, user=user, file=file, content=content, audit=audit.stdout, bundle=bundle
    )


def test_backup_packs_every_part_and_only_owner_can_read_it(stack, saved):
    with tarfile.open(saved.bundle) as bundle:
        names = bundle.getnames()
        with tarfile.open(fileobj=bundle.extractfile("apps.tar")) as apps:
            copied = apps.getnames()

    assert names == PARTS
    assert f"./{saved.name}/saigonos-app.json" in copied
    assert saved.bundle.stat().st_mode & 0o777 == 0o600
    assert saved.bundle.parent.stat().st_mode & 0o777 == 0o700
    assert stack.inspect(stack.container("seaweedfs"), "{{.State.Health.Status}}") == "healthy"


def test_bundle_changed_by_one_byte_is_refused_and_system_is_left_alone(stack, saved, tmp_path):
    data = bytearray(saved.bundle.read_bytes())
    data[len(data) // 2] ^= 0x01
    changed = tmp_path / saved.bundle.name
    changed.write_bytes(data)
    env = (stack.home / ".env").read_bytes()
    before = {service: started_at(stack, service) for service in SERVICES}

    result = stack.saigonos("restore", "--yes", str(changed))

    assert result.returncode == 1, result.stdout
    assert f"Không khôi phục được từ gói {changed}: " in result.stderr
    assert (stack.home / ".env").read_bytes() == env
    assert {service: started_at(stack, service) for service in SERVICES} == before
    assert list(stack.home.glob(".khoi-phuc-*")) == []


def test_restore_puts_back_data_files_accounts_and_apps_changed_after_backup(stack, saved):
    token = stack.app_token(saved.user, saved.name)
    assert notes(stack, "POST", saved.name, token, {"body": LATER}).status == 201
    assert stack.s3("DELETE", f"/clean/{saved.file['id']}", stack.s3_key)[0] == 204
    removed = stack.saigonos("remove", saved.name)
    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert stack.admin("DELETE", f"/users/{saved.user.id}").status == 204

    restored = stack.restore(saved.bundle)

    assert restored.returncode == 0, restored.stdout + restored.stderr
    assert_restored(stack, saved)


def test_restore_into_new_working_folder_after_down_volumes(stack, saved, new_home_stack):
    with tarfile.open(saved.bundle) as bundle:
        env = bundle.extractfile("env").read()
    down = stack.saigonos("down", "--volumes")
    assert down.returncode == 0, down.stdout + down.stderr

    restored = new_home_stack.restore(saved.bundle)

    assert restored.returncode == 0, restored.stdout + restored.stderr
    assert (new_home_stack.home / ".env").read_bytes() == env
    assert_restored(new_home_stack, saved)
