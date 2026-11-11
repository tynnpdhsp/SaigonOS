# SPDX-License-Identifier: Apache-2.0
import base64
import json

import pytest

pytestmark = pytest.mark.integration


def encode(data):
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def decode(segment):
    return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))


def test_doctor_reports_working_stack(stack):
    result = stack.saigonos("doctor")

    assert result.returncode == 0, result.stdout
    assert "Hệ thống hoạt động bình thường." in result.stdout


def test_api_rejects_call_without_token(stack):
    assert stack.api().status == 401


def test_api_accepts_token_of_user(stack):
    token = stack.token(stack.new_user())

    assert "authenticated" in decode(token.split(".")[1])["realm_access"]["roles"]
    assert stack.api(token).status == 200


def test_api_rejects_forged_tokens(stack):
    header, payload, signature = stack.token(stack.new_user()).split(".")
    claims = decode(payload)
    forged = {
        "không phải JWT": "khong-phai-token",
        "sửa nội dung": f"{header}.{encode(claims | {'preferred_username': 'admin'})}.{signature}",
        "không ký": f"{encode({'alg': 'none', 'typ': 'JWT'})}.{payload}.",
    }

    statuses = {name: stack.api(token).status for name, token in forged.items()}

    assert statuses == dict.fromkeys(forged, 401)
