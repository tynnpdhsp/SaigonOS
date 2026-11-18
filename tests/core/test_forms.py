# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import HTTPException

from saigonos_core.forms import START_FORM, TASK_FORM, FormField, submitted
from saigonos_core.processes import form_of, rules_of

DEFINITIONS = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:operaton="http://operaton.org/schema/1.0/bpmn"
                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                  id="dinh_nghia" targetNamespace="https://dx.example.com/bpmn">
  <bpmn:process id="yeu_cau" isExecutable="true">
    <bpmn:startEvent id="theo_tin_nhan">
      <bpmn:extensionElements>
        <operaton:formData>
          <operaton:formField id="tu_tin_nhan" type="string" />
        </operaton:formData>
      </bpmn:extensionElements>
      <bpmn:messageEventDefinition messageRef="tin_nhan" />
    </bpmn:startEvent>
    <bpmn:startEvent id="bat_dau">
      <bpmn:extensionElements>
        <operaton:formData>
          <operaton:formField id="noi_dung" label=" Nội dung " type="string">
            <operaton:validation>
              <operaton:constraint name="required" />
              <operaton:constraint name="minlength" config="5" />
              <operaton:constraint name="minlength" config="+10" />
              <operaton:constraint name="maxlength" config="abc" />
              <operaton:constraint name="maxlength" config="200" />
              <operaton:constraint name="maxlength" config="100" />
            </operaton:validation>
          </operaton:formField>
          <operaton:formField id="so_luong" label="" type="long">
            <operaton:validation>
              <operaton:constraint name="min" config="-1" />
              <operaton:constraint name="max" config="1.5" />
              <operaton:constraint name="readonly" />
            </operaton:validation>
          </operaton:formField>
          <operaton:formField id="muc_uu_tien" type="enum">
            <operaton:value id="cao" name="Cao" />
            <operaton:value name="Không có mã" />
            <operaton:value id="thap" name="Thấp" />
          </operaton:formField>
          <operaton:formField id="noi_dung" type="long" />
        </operaton:formData>
      </bpmn:extensionElements>
    </bpmn:startEvent>
    <bpmn:userTask id="xu_ly">
      <bpmn:extensionElements>
        <camunda:formData>
          <camunda:formField id="ket_qua" type="string" />
        </camunda:formData>
      </bpmn:extensionElements>
    </bpmn:userTask>
    <bpmn:subProcess id="nhanh">
      <bpmn:userTask id="duyet">
        <bpmn:extensionElements>
          <camunda:formData>
            <camunda:formField id="bi_bo_qua" type="string" />
          </camunda:formData>
          <operaton:formData>
            <operaton:formField id="dong_y" type="boolean">
              <camunda:validation>
                <camunda:constraint name="required" />
              </camunda:validation>
            </operaton:formField>
          </operaton:formData>
        </bpmn:extensionElements>
      </bpmn:userTask>
    </bpmn:subProcess>
    <bpmn:userTask id="xem" />
  </bpmn:process>
  <bpmn:process id="chi_tin_nhan" isExecutable="true">
    <bpmn:startEvent id="nhan_tin">
      <bpmn:extensionElements>
        <operaton:formData>
          <operaton:formField id="tu_tin_nhan" type="string" />
        </operaton:formData>
      </bpmn:extensionElements>
      <bpmn:messageEventDefinition messageRef="tin_nhan" />
    </bpmn:startEvent>
  </bpmn:process>
</bpmn:definitions>
"""

RESULT = FormField("ket_qua", "string", "Kết quả", required=True, min_length=5, max_length=20)
HOURS = FormField("so_gio", "long", "Số giờ", minimum=1, maximum=8)
URGENT = FormField("khan", "boolean", "Khẩn")
DUE = FormField("han_xu_ly", "date", "Hạn xử lý")
PRIORITY = FormField("muc_uu_tien", "enum", "Mức ưu tiên", choices=("cao", "thap"))
CONTENT = FormField("noi_dung", "string", "Nội dung", readonly=True)
FORM = (RESULT, HOURS, URGENT, DUE, PRIORITY, CONTENT)
VALID = {"ket_qua": "Đã thay cáp màn hình"}


def refusal(form, variables, owner=TASK_FORM):
    with pytest.raises(HTTPException) as caught:
        submitted(form, variables, owner)
    assert caught.value.status_code == 422
    return caught.value.detail


def test_declared_fields_are_sent_with_types_of_form():
    variables = VALID | {"so_gio": 2, "khan": False, "muc_uu_tien": "cao"}

    assert submitted(FORM, variables | {"han_xu_ly": "2026-11-20T09:00:00+07:00"}, TASK_FORM) == {
        "ket_qua": {"value": "Đã thay cáp màn hình", "type": "String"},
        "so_gio": {"value": 2, "type": "Long"},
        "khan": {"value": False, "type": "Boolean"},
        "han_xu_ly": {"value": "2026-11-20T02:00:00.000+0000", "type": "Date"},
        "muc_uu_tien": {"value": "cao", "type": "String"},
    }


def test_optional_field_left_out_is_not_sent_and_null_is_sent_as_null():
    assert submitted(FORM, VALID | {"so_gio": None, "han_xu_ly": None}, TASK_FORM) == {
        "ket_qua": {"value": "Đã thay cáp màn hình", "type": "String"},
        "so_gio": {"value": None, "type": "Null"},
        "han_xu_ly": {"value": None, "type": "Null"},
    }


@pytest.mark.parametrize(
    ("owner", "variables", "names"),
    [
        (TASK_FORM, {"ghi_chu": "x"}, "ghi_chu"),
        (TASK_FORM, {"noi_dung": "Sửa nội dung", "initiator": "nguoi-khac"}, "initiator, noi_dung"),
        (START_FORM, {"noi_dung": None}, "noi_dung"),
    ],
    ids=[
        "bien-khong-co-trong-form",
        "truong-chi-de-xem-va-initiator",
        "truong-chi-de-xem-gui-null",
    ],
)
def test_variable_outside_form_or_read_only_is_refused(owner, variables, names):
    assert refusal(FORM, VALID | variables, owner) == f"{owner} không nhận biến {names}"


def test_form_without_fields_accepts_only_empty_variables():
    assert submitted((), {}, START_FORM) == {}
    assert refusal((), {"noi_dung": "x"}, START_FORM) == (
        "Form bắt đầu của quy trình không nhận biến noi_dung"
    )


@pytest.mark.parametrize(
    "variables",
    [{}, {"ket_qua": None}, {"ket_qua": ""}, {"ket_qua": "   "}, {"ket_qua": "\t\n\u00a0\u3000"}],
    ids=["thieu", "null", "rong", "dau-cach", "khoang-trang-khac"],
)
def test_required_field_missing_or_blank_is_compliance_error(variables):
    assert refusal(FORM, variables) == "LỖI TUÂN THỦ: Phải nhập Kết quả (ket_qua)"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (FormField("so_gio", "long", required=True), "  "),
        (FormField("khan", "boolean", required=True), None),
        (FormField("muc", "enum", required=True, choices=("cao",)), ""),
        (FormField("han", "date", required=True), " "),
    ],
)
def test_required_field_of_any_type_needs_value(field, value):
    assert refusal((field,), {field.name: value}) == f"LỖI TUÂN THỦ: Phải nhập {field.name}"


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("  abcd  ", "Kết quả (ket_qua) phải có ít nhất 5 ký tự"),
        ("x" * 21, "Kết quả (ket_qua) không được dài quá 20 ký tự"),
        ("😀" * 11, "Kết quả (ket_qua) không được dài quá 20 ký tự"),
        (12345, "Kết quả (ket_qua) phải là chuỗi"),
        (True, "Kết quả (ket_qua) phải là chuỗi"),
    ],
    ids=["qua-ngan", "qua-dai", "emoji-qua-dai", "so-nguyen", "true"],
)
def test_text_outside_constraints_is_compliance_error(value, message):
    assert refusal(FORM, {"ket_qua": value}) == f"LỖI TUÂN THỦ: {message}"


@pytest.mark.parametrize(
    "value",
    ["abcde", "  abcde  ", "x" * 20, "😀" * 10, "ạ" * 20],
    ids=[
        "vua-du-toi-thieu",
        "khoang-trang-hai-dau",
        "vua-du-toi-da",
        "emoji-vua-du-toi-da",
        "chu-co-dau-vua-du-toi-da",
    ],
)
def test_text_inside_constraints_is_accepted(value):
    assert submitted(FORM, {"ket_qua": value}, TASK_FORM)["ket_qua"]["value"] == value


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (0, "Số giờ (so_gio) không được nhỏ hơn 1"),
        (9, "Số giờ (so_gio) không được lớn hơn 8"),
        (2.0, "Số giờ (so_gio) phải là số nguyên"),
        ("2", "Số giờ (so_gio) phải là số nguyên"),
        (True, "Số giờ (so_gio) phải là số nguyên"),
        ("  ", "Số giờ (so_gio) phải là số nguyên"),
    ],
    ids=["nho-hon-min", "lon-hon-max", "so-thuc", "chuoi-so", "true", "khoang-trang"],
)
def test_whole_number_outside_constraints_is_compliance_error(value, message):
    assert refusal(FORM, VALID | {"so_gio": value}) == f"LỖI TUÂN THỦ: {message}"


@pytest.mark.parametrize("value", [1, 8])
def test_whole_number_on_bounds_is_accepted(value):
    assert submitted(FORM, VALID | {"so_gio": value}, TASK_FORM)["so_gio"]["value"] == value


@pytest.mark.parametrize("value", [1, 0, "true", "false"])
def test_flag_must_be_true_or_false(value):
    assert refusal(FORM, VALID | {"khan": value}) == (
        "LỖI TUÂN THỦ: Khẩn (khan) phải là true hoặc false"
    )


@pytest.mark.parametrize(
    ("value", "sent"),
    [
        ("2026-11-20T09:00:00+07:00", "2026-11-20T02:00:00.000+0000"),
        ("2026-11-20T02:00:00Z", "2026-11-20T02:00:00.000+0000"),
        ("2026-11-20T02:00:00.123456-05:30", "2026-11-20T07:30:00.123+0000"),
        ("2026-11-20 09:00+07:00", "2026-11-20T02:00:00.000+0000"),
    ],
)
def test_date_with_offset_is_sent_in_utc(value, sent):
    assert submitted(FORM, VALID | {"han_xu_ly": value}, TASK_FORM)["han_xu_ly"] == {
        "value": sent,
        "type": "Date",
    }


@pytest.mark.parametrize(
    "value",
    [
        "2026-11-20",
        "2026-11-20T09:00:00",
        "20/11/2026",
        "32/13/2026",
        "2026-02-30T09:00:00+07:00",
        "0001-01-01T00:00:00+07:00",
        1763600000,
    ],
)
def test_date_without_offset_or_outside_iso_8601_is_compliance_error(value):
    assert refusal(FORM, VALID | {"han_xu_ly": value}) == (
        "LỖI TUÂN THỦ: Hạn xử lý (han_xu_ly) phải là ngày giờ theo ISO 8601 có múi giờ. "
        "Ví dụ: 2026-11-20T09:00:00+07:00"
    )


@pytest.mark.parametrize("value", ["trung_binh", "Cao", " cao", 1])
def test_choice_outside_declared_values_is_compliance_error(value):
    assert refusal(FORM, VALID | {"muc_uu_tien": value}) == (
        "LỖI TUÂN THỦ: Mức ưu tiên (muc_uu_tien) phải là một trong các giá trị cao, thap"
    )


def test_every_problem_is_named_in_order_of_form():
    variables = {"ket_qua": " ", "so_gio": "2", "muc_uu_tien": "vua"}

    assert refusal(FORM, variables) == (
        "LỖI TUÂN THỦ: Phải nhập Kết quả (ket_qua). Số giờ (so_gio) phải là số nguyên. "
        "Mức ưu tiên (muc_uu_tien) phải là một trong các giá trị cao, thap"
    )


@pytest.mark.parametrize(
    ("field", "title"),
    [
        (FormField("ket_qua", "string", "Kết quả", required=True), "Kết quả (ket_qua)"),
        (FormField("ket_qua", "string", required=True), "ket_qua"),
        (FormField("ket_qua", "string", "ket_qua", required=True), "ket_qua"),
    ],
    ids=["co-label", "khong-co-label", "label-trung-id"],
)
def test_field_is_named_by_label_and_id(field, title):
    assert refusal((field,), {}) == f"LỖI TUÂN THỦ: Phải nhập {title}"


def test_start_form_comes_from_start_event_without_event_definition():
    assert rules_of(DEFINITIONS, "yeu_cau").start_form == (
        FormField("noi_dung", "string", "Nội dung", required=True, min_length=10, max_length=100),
        FormField("so_luong", "long", readonly=True, minimum=-1),
        FormField("muc_uu_tien", "enum", choices=("cao", "thap")),
    )


def test_task_forms_are_read_by_task_id_as_operaton_reads_them():
    assert rules_of(DEFINITIONS, "yeu_cau").task_forms == {
        "xu_ly": (FormField("ket_qua", "string"),),
        "duyet": (FormField("dong_y", "boolean", required=True),),
        "xem": (),
    }


@pytest.mark.parametrize("key", ["chi_tin_nhan", "khong_co"])
def test_process_without_none_start_event_has_no_forms(key):
    rules = rules_of(DEFINITIONS, key)

    assert (rules.start_form, rules.task_forms) == ((), {})
    assert form_of(None) == ()


def test_field_of_unknown_type_is_refused():
    form = (FormField("ty_le", "double", "Tỷ lệ"),)

    assert refusal(form, {"ty_le": 0.5}) == (
        "LỖI TUÂN THỦ: Tỷ lệ (ty_le) có kiểu double. Service core chưa hỗ trợ kiểu này"
    )
