# SPDX-License-Identifier: Apache-2.0
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

COMPLIANCE = "LỖI TUÂN THỦ"
START_FORM = "Form bắt đầu của quy trình"
TASK_FORM = "Form của việc"
DATE_EXAMPLE = "2026-11-20T09:00:00+07:00"


class RefusedValueError(ValueError):
    pass


@dataclass(frozen=True)
class FormField:
    name: str
    kind: str
    label: str | None = None
    required: bool = False
    readonly: bool = False
    min_length: int | None = None
    max_length: int | None = None
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple[str, ...] = ()

    @property
    def title(self) -> str:
        if self.label and self.label != self.name:
            return f"{self.label} ({self.name})"
        return self.name


Form = tuple[FormField, ...]


def java_length(text: str) -> int:
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def text_of(field: FormField, value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        raise RefusedValueError(f"{field.title} phải là chuỗi")
    if field.min_length is not None and java_length(value.strip()) < field.min_length:
        raise RefusedValueError(f"{field.title} phải có ít nhất {field.min_length} ký tự")
    if field.max_length is not None and java_length(value) > field.max_length:
        raise RefusedValueError(f"{field.title} không được dài quá {field.max_length} ký tự")
    return {"value": value, "type": "String"}


def choice_of(field: FormField, value: Any) -> dict[str, Any]:
    if value not in field.choices:
        choices = ", ".join(field.choices)
        raise RefusedValueError(f"{field.title} phải là một trong các giá trị {choices}")
    return text_of(field, value)


def whole_of(field: FormField, value: Any) -> dict[str, Any]:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RefusedValueError(f"{field.title} phải là số nguyên")
    if field.minimum is not None and value < field.minimum:
        raise RefusedValueError(f"{field.title} không được nhỏ hơn {field.minimum}")
    if field.maximum is not None and value > field.maximum:
        raise RefusedValueError(f"{field.title} không được lớn hơn {field.maximum}")
    return {"value": value, "type": "Long"}


def flag_of(field: FormField, value: Any) -> dict[str, Any]:
    if not isinstance(value, bool):
        raise RefusedValueError(f"{field.title} phải là true hoặc false")
    return {"value": value, "type": "Boolean"}


def utc_text(value: Any) -> str | None:
    try:
        moment = datetime.fromisoformat(value)
        if moment.utcoffset() is None:
            return None
        return moment.astimezone(UTC).isoformat(timespec="milliseconds")
    except (TypeError, ValueError, OverflowError):
        return None


def instant_of(field: FormField, value: Any) -> dict[str, Any]:
    text = utc_text(value)
    if text is None:
        raise RefusedValueError(
            f"{field.title} phải là ngày giờ theo ISO 8601 có múi giờ. Ví dụ: {DATE_EXAMPLE}"
        )
    return {"value": text.removesuffix("+00:00") + "+0000", "type": "Date"}


CHECKS: dict[str, Callable[[FormField, Any], dict[str, Any]]] = {
    "string": text_of,
    "enum": choice_of,
    "long": whole_of,
    "boolean": flag_of,
    "date": instant_of,
}


def typed_value(field: FormField, value: Any) -> dict[str, Any]:
    if value is None or (isinstance(value, str) and not value.strip()):
        if field.required:
            raise RefusedValueError(f"Phải nhập {field.title}")
        if value is None:
            return {"value": None, "type": "Null"}
    check = CHECKS.get(field.kind)
    if check is None:
        raise RefusedValueError(
            f"{field.title} có kiểu {field.kind}. Service core chưa hỗ trợ kiểu này"
        )
    return check(field, value)


def submitted(form: Form, variables: dict[str, Any], owner: str) -> dict[str, dict[str, Any]]:
    fields = [field for field in form if not field.readonly]
    refused = sorted(variables.keys() - {field.name for field in fields})
    if refused:
        raise HTTPException(422, f"{owner} không nhận biến {', '.join(refused)}")
    sent: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for field in fields:
        if field.name in variables or field.required:
            try:
                sent[field.name] = typed_value(field, variables.get(field.name))
            except RefusedValueError as error:
                problems.append(str(error))
    if problems:
        raise HTTPException(422, f"{COMPLIANCE}: {'. '.join(problems)}")
    return sent
