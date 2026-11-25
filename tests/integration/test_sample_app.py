# SPDX-License-Identifier: Apache-2.0
import json
import secrets
import subprocess
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote, urlencode

import pytest

pytestmark = pytest.mark.integration

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "phong-may"
APP = "phong-may"
KEY = "phong_may.dat_phong"
TEACHER = "phong-may.giao-vien"
MANAGER = "phong-may.phu-trach"
STAFF = "phong-may.chuyen-vien"
STUDENT = "phong-may.hoc-sinh"
VIETNAM = timezone(timedelta(hours=7))
ENGINE = "http://127.0.0.1:8080/operaton/engine-rest"
CLASH = "Phòng đã có lịch trùng giờ với một đơn khác vừa được duyệt."


def wait_for(found, message, timeout=30):
    deadline = time.monotonic() + timeout
    while not (value := found()):
        assert time.monotonic() < deadline, message
        time.sleep(0.5)
    return value


def api(stack, user, method, path, body=None, headers=None):
    token = None if user is None else stack.app_token(user, APP)
    url = f"{stack.url}/apps/{APP}/api/{path}"
    return stack.call(method, url, token=token, body=body, headers=headers)


def rows(stack, user, path):
    reply = api(stack, user, "GET", path)
    assert reply.status == 200, reply.body
    return json.loads(reply.body)


def core(stack, user, method, path, body=None):
    reply = stack.call(
        method, f"{stack.url}/core/{path}", token=stack.app_token(user, APP), body=body
    )
    return reply.status, json.loads(reply.body) if reply.body else None


def engine(stack, path):
    account = f"core:{stack.env['CORE_OPERATON_PASSWORD']}"
    command = ["exec", "-T", "operaton", "curl", "--silent", "--fail", "--user", account]
    result = stack.compose_result(*command, f"{ENGINE}{path}")
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def ended(stack, instance):
    def state():
        found = engine(stack, f"/history/process-instance/{instance}")["state"]
        return None if found == "ACTIVE" else found

    return wait_for(state, f"Quy trình {instance} chưa kết thúc")


def passed(stack, instance):
    query = urlencode({"processInstanceId": instance, "finished": "true"})
    return {item["activityId"] for item in engine(stack, f"/history/activity-instance?{query}")}


def code_of(reply):
    return json.loads(reply.body).get("code")


def later(hours):
    moment = datetime.now(UTC) + timedelta(hours=hours)
    return moment.replace(minute=0, second=0, microsecond=0).astimezone(VIETNAM)


def booking(room, start, hours=2, machines=30):
    begin = later(start)
    return {
        "ma_phong": room,
        "bat_dau": begin.isoformat(),
        "ket_thuc": (begin + timedelta(hours=hours)).isoformat(),
        "so_may": machines,
        "lop": f"Lập trình cơ bản, lớp thử {secrets.token_hex(3)}",
        "muc_dich": "day_hoc",
        "phan_mem": "Visual Studio Code, Python 3.12",
        "ghi_chu": None,
    }


def submit(stack, user, variables):
    status, started = core(stack, user, "POST", f"processes/{KEY}/start", {"variables": variables})
    assert status == 201, started
    return started["id"]


def booked(stack, user, variables):
    path = f"don?lop=eq.{quote(variables['lop'])}"
    [row] = wait_for(lambda: rows(stack, user, path), f"Chưa có đơn {variables['lop']}")
    return row


def row_of(stack, booking_id, column="trang_thai"):
    return stack.sql(f"SELECT {column} FROM phong_may.don WHERE id = {booking_id}")


def task_for(stack, user, key, booking_id):
    def found():
        status, tasks = core(stack, user, "GET", "tasks?limit=200")
        assert status == 200, tasks
        wanted = f"Đơn đặt phòng số {booking_id}"
        return next(
            (task for task in tasks if (task["task_key"], task["description"]) == (key, wanted)),
            None,
        )

    return wait_for(found, f"Chưa có việc {key} của đơn {booking_id}")


def finish(stack, user, task, variables):
    assert core(stack, user, "POST", f"tasks/{task['id']}/claim") == (204, None)
    done = core(stack, user, "POST", f"tasks/{task['id']}/complete", {"variables": variables})
    assert done == (204, None)


def notification(stack, user, title):
    def found():
        status, items = core(stack, user, "GET", "notifications?limit=200")
        assert status == 200, items
        return next((item for item in items if item["title"] == title), None)

    return wait_for(found, f"Chưa có thông báo {title}")


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def sql_error(stack, query):
    options = ["--username=postgres", "--dbname=saigonos", "--no-psqlrc", "--set=ON_ERROR_STOP=1"]
    command = [stack.docker, "compose", "exec", "-T", "postgres", "psql", *options]
    result = subprocess.run(
        [*command, f"--command={query}"],
        cwd=stack.home,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0, result.stdout
    return result.stderr


@pytest.fixture(scope="module")
def sample(stack):
    begin = time.monotonic()
    result = stack.saigonos("apply", str(EXAMPLE))
    seconds = time.monotonic() - begin
    assert result.returncode == 0, result.stdout + result.stderr
    people = SimpleNamespace(
        teacher=stack.new_user(role=TEACHER),
        other_teacher=stack.new_user(role=TEACHER),
        manager=stack.new_user(role=MANAGER),
        staff=stack.new_user(role=STAFF),
        student=stack.new_user(role=STUDENT),
        nobody=stack.new_user(),
        output=result.stdout,
        seconds=seconds,
    )
    wait_for(lambda: api(stack, people.student, "GET", "phong").status == 200, "Chưa có API")
    for user in (people.teacher, people.other_teacher, people.manager, people.staff):
        reply = api(stack, user, "POST", "rpc/cap_nhat_nguoi_dung", {})
        assert reply.status == 204, reply.body
    return people


def test_sample_app_is_installed_into_running_system_within_30_seconds(sample):
    assert sample.seconds < 30


def test_install_creates_every_part_of_sample_app(stack, sample):
    for line in (
        "Đã chạy file 0004_quy_trinh.sql.",
        f"Đã tạo realm role {STUDENT}.",
        "Đã tạo client phong-may.",
        "Đã tạo route app-phong-may.",
        f"Đã triển khai file dat-phong.bpmn: quy trình {KEY}, phiên bản 1.",
        "Đã cài đặt ứng dụng phong-may 0.1.0.",
    ):
        assert f"{line}\n" in sample.output
    rooms = rows(stack, sample.student, "phong?order=ma")
    assert [(room["ma"], room["so_may"]) for room in rooms] == [
        ("PM1", 70),
        ("PM2", 40),
        ("PM3", 40),
        ("PM4", 72),
    ]
    assert stack.sql(
        "SELECT ma, vai[1] FROM phong_may.nguoi_dung "
        f"WHERE ma IN ('{sample.manager.id}', '{sample.staff.id}') ORDER BY vai[1]"
    ) == [[sample.staff.id, STAFF], [sample.manager.id, MANAGER]]


def test_approved_booking_is_prepared_and_shown_on_schedule(stack, sample):
    variables = booking("PM1", 72)

    instance = submit(stack, sample.teacher, variables)

    row = booked(stack, sample.teacher, variables)
    assert (row["trang_thai"], row["ten_nguoi_gui"], row["nguoi_gui"]) == (
        "cho_duyet",
        "Người Thử",
        sample.teacher.id,
    )
    due = instant(row["han_duyet"]) - datetime.now(UTC)
    assert timedelta(hours=23) < due < timedelta(hours=25)
    task = task_for(stack, sample.manager, "duyet", row["id"])
    assert instant(task["due"]) == instant(row["han_duyet"])
    finish(stack, sample.manager, task, {"ket_qua": "dong_y", "y_kien": "Nhớ tắt máy sau buổi học"})
    approved = notification(stack, sample.teacher, f"Đơn đặt phòng số {row['id']} đã được duyệt")
    assert approved["body"].endswith("Ý kiến: Nhớ tắt máy sau buổi học")
    notification(stack, sample.staff, f"Cần chuẩn bị Phòng máy 1 cho đơn số {row['id']}")
    preparing = task_for(stack, sample.staff, "chuan_bi", row["id"])
    assert instant(preparing["due"]) == instant(variables["bat_dau"])
    ready = {"so_may_san_sang": 28, "ghi_chu_chuan_bi": "Hai máy chờ thay ổ cứng"}
    finish(stack, sample.staff, preparing, ready)
    told = notification(stack, sample.teacher, f"Phòng máy 1 đã sẵn sàng cho đơn số {row['id']}")
    assert told["body"] == ("Có 28 máy sẵn sàng, đơn cần 30 máy. Ghi chú: Hai máy chờ thay ổ cứng")
    assert ended(stack, instance) == "COMPLETED"
    assert "san_sang" in passed(stack, instance)
    assert row_of(stack, row["id"], "trang_thai, so_may_san_sang") == [["san_sang", "28"]]
    [shown] = rows(stack, sample.student, f"lich?id=eq.{row['id']}")
    assert (shown["ma_phong"], shown["lop"], shown["trang_thai"]) == (
        "PM1",
        variables["lop"],
        "san_sang",
    )
    assert "y_kien" not in shown
    assert stack.sql(
        "SELECT operation, db_role FROM core.audit_log WHERE table_name = 'don' "
        f"AND coalesce(new_row, old_row) ->> 'id' = '{row['id']}' ORDER BY id"
    ) == [["INSERT", "workflow"], ["UPDATE", "workflow"], ["UPDATE", "workflow"]]


def test_rejected_booking_tells_teacher_why_and_stays_off_schedule(stack, sample):
    variables = booking("PM2", 72)

    instance = submit(stack, sample.teacher, variables)

    row = booked(stack, sample.teacher, variables)
    task = task_for(stack, sample.manager, "duyet", row["id"])
    finish(stack, sample.manager, task, {"ket_qua": "tu_choi", "y_kien": "Phòng đang bảo trì"})
    rejected = notification(stack, sample.teacher, f"Đơn đặt phòng số {row['id']} bị từ chối")
    assert rejected["body"].endswith("Ý kiến: Phòng đang bảo trì")
    assert ended(stack, instance) == "COMPLETED"
    assert "bi_tu_choi" in passed(stack, instance)
    assert row_of(stack, row["id"], "trang_thai, y_kien") == [["tu_choi", "Phòng đang bảo trì"]]
    assert rows(stack, sample.student, f"lich?id=eq.{row['id']}") == []


def test_booking_close_to_start_reminds_managers_and_keeps_task_open(stack, sample):
    variables = booking("PM4", 2, hours=1)

    instance = submit(stack, sample.teacher, variables)

    row = booked(stack, sample.teacher, variables)
    reminder = notification(stack, sample.manager, f"Đơn đặt phòng số {row['id']} đã tới hạn duyệt")
    assert reminder["link"] == f"/apps/phong-may/?don={row['id']}"
    assert stack.sql(
        f"SELECT channel FROM core.deliveries WHERE dedup_key = 'don:{row['id']}:nhac-duyet'"
    ) == [["telegram"]]
    wait_for(lambda: "da_nhac" in passed(stack, instance), "Nhánh nhắc hạn chưa kết thúc")
    task = task_for(stack, sample.manager, "duyet", row["id"])
    assert instant(task["due"]) < datetime.now(UTC)
    assert engine(stack, f"/history/process-instance/{instance}")["state"] == "ACTIVE"
    finish(stack, sample.manager, task, {"ket_qua": "tu_choi", "y_kien": "Gửi quá sát giờ học"})
    assert ended(stack, instance) == "COMPLETED"


def test_overlapping_bookings_cannot_both_be_approved(stack, sample):
    first, second = booking("PM3", 96), booking("PM3", 97)
    first_instance = submit(stack, sample.teacher, first)
    second_instance = submit(stack, sample.other_teacher, second)
    first_row = booked(stack, sample.teacher, first)
    second_row = booked(stack, sample.other_teacher, second)

    for row in (first_row, second_row):
        task = task_for(stack, sample.manager, "duyet", row["id"])
        finish(stack, sample.manager, task, {"ket_qua": "dong_y", "y_kien": None})
        wait_for(lambda row=row: row_of(stack, row["id"]) != [["cho_duyet"]], "Chưa ghi kết quả")

    assert ended(stack, second_instance) == "COMPLETED"
    assert row_of(stack, first_row["id"]) == [["da_duyet"]]
    assert row_of(stack, second_row["id"], "trang_thai, y_kien") == [["tu_choi", CLASH]]
    told = notification(
        stack, sample.other_teacher, f"Đơn đặt phòng số {second_row['id']} bị từ chối"
    )
    assert told["body"].endswith(f"Ý kiến: {CLASH}")
    error = sql_error(
        stack, f"UPDATE phong_may.don SET trang_thai = 'da_duyet' WHERE id = {second_row['id']}"
    )
    assert "khong_trung_lich" in error
    third = booking("PM3", 96, hours=1)
    third_instance = submit(stack, sample.teacher, third)
    assert ended(stack, third_instance) == "COMPLETED"
    assert "khong_hop_le" in passed(stack, third_instance)
    assert stack.sql(f"SELECT count(*) FROM phong_may.don WHERE lop = '{third['lop']}'") == [["0"]]
    refused = notification(stack, sample.teacher, "Đơn đặt phòng chưa được ghi")
    assert refused["body"].startswith("Phòng máy 3 đã có lịch từ ")
    assert engine(stack, f"/history/process-instance/{first_instance}")["state"] == "ACTIVE"


def test_check_function_lists_every_problem_of_a_booking(stack, sample):
    def problems(room, start, end, machines):
        query = urlencode({"ma_phong": room, "bat_dau": start, "ket_thuc": end, "so_may": machines})
        return rows(stack, sample.teacher, f"rpc/kiem_tra_don?{query}")

    past, soon = later(-3).isoformat(), later(-4).isoformat()
    free = booking("PM2", 200)

    assert problems("PM2", past, soon, 41) == [
        "Giờ bắt đầu phải sau thời điểm hiện tại.",
        "Giờ kết thúc phải sau giờ bắt đầu.",
        "Phòng máy 2 chỉ có 40 máy dùng được.",
    ]
    assert problems("PM9", past, soon, 1) == ["Không có phòng PM9."]
    assert problems("PM2", free["bat_dau"], free["ket_thuc"], 40) == []
    assert problems("PM2", free["bat_dau"], later(220).isoformat(), 1) == [
        "Mỗi đơn dài tối đa 12 giờ."
    ]


def test_each_role_sees_and_changes_only_its_own_part(stack, sample):
    variables = booking("PM2", 120)
    submit(stack, sample.teacher, variables)
    row = booked(stack, sample.teacher, variables)
    path = f"don?id=eq.{row['id']}"

    assert rows(stack, sample.other_teacher, path) == []
    assert rows(stack, sample.student, path) == []
    assert rows(stack, sample.staff, path) == []
    assert [item["id"] for item in rows(stack, sample.manager, path)] == [row["id"]]
    status, refused = core(stack, sample.student, "POST", f"processes/{KEY}/start", {})
    assert status == 403, refused
    for user, method, target, body in (
        (sample.student, "POST", "rpc/cap_nhat_nguoi_dung", {}),
        (sample.student, "PATCH", "phong?ma=eq.PM4", {"so_may": 1}),
        (sample.teacher, "PATCH", "phong?ma=eq.PM4", {"so_may": 1}),
        (sample.staff, "PATCH", "phong?ma=eq.PM4", {"so_may": 1}),
        (sample.nobody, "GET", "lich", None),
        (sample.nobody, "GET", "phong", None),
    ):
        reply = api(stack, user, method, target, body)
        assert (reply.status, code_of(reply)) == (403, "SGN03"), (user, method, target)
    assert api(stack, None, "GET", "lich").status == 401
    returned = {"Prefer": "return=representation"}
    changed = api(stack, sample.manager, "PATCH", "phong?ma=eq.PM4", {"so_may": 71}, returned)
    assert changed.status == 200, changed.body
    assert [room["so_may"] for room in json.loads(changed.body)] == [71]
    assert stack.sql(
        "SELECT actor, new_row ->> 'so_may' FROM core.audit_log "
        "WHERE table_name = 'phong' AND operation = 'UPDATE' ORDER BY id DESC LIMIT 1"
    ) == [[sample.manager.id, "71"]]
    restored = api(stack, sample.manager, "PATCH", "phong?ma=eq.PM4", {"so_may": 72})
    assert restored.status == 204, restored.body


def test_page_and_calls_of_page_pass_the_firewall(stack, sample):
    page = stack.call("GET", f"{stack.url}/apps/{APP}/")
    assert page.status == 200, page.body
    assert b'<script type="module" src="app.js"></script>' in page.body
    assert "script-src 'self'" in page.headers["Content-Security-Policy"]
    for name in ("app.js", "style.css"):
        assert stack.call("GET", f"{stack.url}/apps/{APP}/{name}").status == 200
    week = later(24).date()
    schedule = urlencode(
        [
            ("order", "bat_dau"),
            ("bat_dau", f"gte.{week}T00:00:00+07:00"),
            ("bat_dau", f"lt.{week + timedelta(days=7)}T00:00:00+07:00"),
            ("ma_phong", "eq.PM1"),
        ]
    )
    mine = urlencode(
        {"nguoi_gui": f"eq.{sample.teacher.id}", "order": "gui_luc.desc", "limit": "100"}
    )
    free = booking("PM1", 300)
    check = urlencode(
        {
            "ma_phong": "PM1",
            "bat_dau": free["bat_dau"],
            "ket_thuc": free["ket_thuc"],
            "so_may": "30",
        }
    )
    for user, target in (
        (sample.student, f"lich?{schedule}"),
        (sample.teacher, f"don?{mine}"),
        (sample.teacher, f"rpc/kiem_tra_don?{check}"),
        (sample.manager, "don?trang_thai=eq.cho_duyet&order=bat_dau"),
        (sample.manager, "don?order=bat_dau.desc&limit=200&trang_thai=eq.da_duyet&phong_id=eq.1"),
    ):
        reply = api(stack, user, "GET", target)
        assert reply.status == 200, (target, reply.body)
    status, notifications = core(stack, sample.teacher, "GET", "notifications?limit=50")
    assert status == 200, notifications


def test_removed_sample_app_leaves_rest_running_and_keeps_its_bookings(stack, sample):
    bookings = stack.sql("SELECT count(*) FROM phong_may.don")

    removed = stack.saigonos("remove", APP)
    page = stack.call("GET", f"{stack.url}/apps/{APP}/")
    doctor = stack.saigonos("doctor")
    again = stack.saigonos("apply", str(EXAMPLE))

    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert page.status == 404, page.body
    assert doctor.returncode == 0, doctor.stdout + doctor.stderr
    assert again.returncode == 0, again.stdout + again.stderr
    wait_for(lambda: api(stack, sample.student, "GET", "phong").status == 200, "Chưa có API")
    assert stack.sql("SELECT count(*) FROM phong_may.don") == bookings
