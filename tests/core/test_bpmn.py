# SPDX-License-Identifier: Apache-2.0
import pytest

from saigonos_core.bpmn import EXPRESSION_RULE, NO_DRAWING, check_processes, expression_problem

APP = "nghi-phep"
ROLES = ["nghi-phep.nhan-vien", "nghi-phep.quan-ly"]
FLOW = """\
    <bpmn:startEvent id="bat_dau" />
    <bpmn:sequenceFlow id="luong_1" sourceRef="bat_dau" targetRef="ket_thuc" />
    <bpmn:endEvent id="ket_thuc" />
"""
STEP = """\
    <bpmn:serviceTask id="ghi" operaton:type="external" operaton:topic="saigonos-function">
      <bpmn:extensionElements>
        <operaton:properties>
          <operaton:property name="function" value="{function}" />
        </operaton:properties>
      </bpmn:extensionElements>
    </bpmn:serviceTask>
"""
NOT_STEP = (
    'phải là bước máy làm, với operaton:type="external" và operaton:topic="saigonos-function".'
)


def drawing(process, *ids):
    shapes = "".join(
        f'<bpmndi:BPMNShape id="{name}_hinh" bpmnElement="{name}">'
        f'<dc:Bounds x="{100 * index}" y="80" width="36" height="36" /></bpmndi:BPMNShape>\n'
        for index, name in enumerate(ids)
    )
    return f"""\
  <bpmndi:BPMNDiagram id="hinh">
    <bpmndi:BPMNPlane id="mat_phang" bpmnElement="{process}">
{shapes}    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
"""


def document(
    body=FLOW,
    key="nghi_phep.duyet",
    attributes=' operaton:historyTimeToLive="P30D"',
    drawn=("bat_dau", "luong_1", "ket_thuc"),
    prefix="operaton",
    extra="",
):
    space = "http://operaton.org/schema/1.0/bpmn"
    if prefix == "camunda":
        space = "http://camunda.org/schema/1.0/bpmn"
    picture = "" if drawn is None else drawing(key, *drawn)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                  xmlns:{prefix}="{space}"
                  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                  id="dinh_nghia" targetNamespace="https://dx.example.com/bpmn">
{extra}  <bpmn:process id="{key}" isExecutable="true"{attributes}>
{body}  </bpmn:process>
{picture}</bpmn:definitions>
"""


def write(folder, files):
    folder.mkdir(exist_ok=True)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def checked(tmp_path, files, app=APP, roles=ROLES):
    return check_processes(write(tmp_path / "processes", files), app, roles)


def messages(tmp_path, text, **options):
    report = checked(tmp_path, {"duyet.bpmn": text}, **options)
    return [problem.message for problem in report.problems]


def test_process_made_only_of_allowed_parts_passes(tmp_path):
    report = checked(tmp_path, {"duyet.bpmn": document()})

    assert report == ([], [])


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            '<bpmn:scriptTask id="chay" scriptFormat="javascript">'
            "<bpmn:script>1</bpmn:script></bpmn:scriptTask>",
            ["Thẻ scriptTask chạy script trong Operaton nên không được dùng."],
        ),
        (
            '<bpmn:task id="viec"><bpmn:extensionElements>'
            '<operaton:executionListener class="vi.Lop" event="start" />'
            "</bpmn:extensionElements></bpmn:task>",
            [
                "Thẻ operaton:executionListener chạy mã trong Operaton khi quy trình đi qua "
                "nên không được dùng."
            ],
        ),
        (
            '<bpmn:userTask id="xu_ly"><bpmn:extensionElements>'
            '<operaton:taskListener expression="${x}" event="create" />'
            "</bpmn:extensionElements></bpmn:userTask>",
            [
                "Thẻ operaton:taskListener chạy mã trong Operaton theo sự kiện của việc "
                "nên không được dùng."
            ],
        ),
        (
            '<bpmn:serviceTask id="lop" operaton:class="vi.Lop" />',
            [
                "Thuộc tính operaton:class chạy class Java trong Operaton nên không được dùng.",
                f"Thẻ serviceTask lop {NOT_STEP}",
            ],
        ),
        (
            '<bpmn:serviceTask id="uy_quyen" operaton:delegateExpression="${dich_vu}" />',
            [
                "Thuộc tính operaton:delegateExpression chạy mã Java trong Operaton "
                "nên không được dùng.",
                f"Thẻ serviceTask uy_quyen {NOT_STEP}",
            ],
        ),
        (
            '<bpmn:serviceTask id="bieu_thuc" operaton:expression="${x}" />',
            [
                "Thuộc tính operaton:expression chạy expression trong Operaton "
                "nên không được dùng.",
                f"Thẻ serviceTask bieu_thuc {NOT_STEP}",
            ],
        ),
        (
            '<bpmn:serviceTask id="ket_noi"><bpmn:extensionElements><operaton:connector>'
            "<operaton:connectorId>http-connector</operaton:connectorId></operaton:connector>"
            "</bpmn:extensionElements></bpmn:serviceTask>",
            [
                f"Thẻ serviceTask ket_noi {NOT_STEP}",
                "Thẻ operaton:connector gọi service bên ngoài từ Operaton nên không được dùng.",
            ],
        ),
        (
            '<bpmn:sendTask id="gui" />',
            ["Thẻ sendTask chạy class Java trong Operaton nên không được dùng."],
        ),
        (
            '<bpmn:businessRuleTask id="quyet_dinh" />',
            [
                "Thẻ businessRuleTask chạy bảng quyết định hoặc class Java trong Operaton "
                "nên không được dùng."
            ],
        ),
        (
            '<bpmn:task id="viec"><bpmn:extensionElements><operaton:field name="x" />'
            "</bpmn:extensionElements></bpmn:task>",
            ["Thẻ operaton:field truyền giá trị cho class Java nên không được dùng."],
        ),
        (
            '<bpmn:callActivity id="goi" calledElement="khac.duyet" />',
            [
                "Thẻ callActivity goi gọi quy trình khac.duyet không thuộc ứng dụng. Quy trình "
                "chỉ gọi được quy trình của chính ứng dụng, có mã dạng nghi_phep.<tên quy trình>."
            ],
        ),
        (
            '<bpmn:callActivity id="goi" calledElement="nghi_phep.duyet" '
            'operaton:calledElementTenantId="khac" />',
            [
                "Thuộc tính operaton:calledElementTenantId gọi quy trình của ứng dụng khác "
                "nên không được dùng."
            ],
        ),
        (
            '<bpmn:callActivity id="goi" calledElement="${quy_trinh}" />',
            [
                "Thuộc tính calledElement của thẻ callActivity goi phải là mã quy trình, "
                "không dùng expression."
            ],
        ),
        (
            '<bpmn:callActivity id="goi" calledElement="nghi_phep.duyet">'
            '<bpmn:extensionElements><operaton:in businessKey="#{execution.processBusinessKey}" />'
            "</bpmn:extensionElements></bpmn:callActivity>",
            [f'Expression "#{{execution.processBusinessKey}}" đọc thuộc tính. {EXPRESSION_RULE}'],
        ),
        (
            '<bpmn:sequenceFlow id="dieu_kien" sourceRef="bat_dau" targetRef="ket_thuc">'
            '<bpmn:conditionExpression xsi:type="bpmn:tFormalExpression" language="javascript">'
            "true</bpmn:conditionExpression></bpmn:sequenceFlow>",
            ["Thuộc tính language chạy script trong Operaton nên không được dùng."],
        ),
        (
            '<bpmn:userTask id="xu_ly"><bpmn:extensionElements><operaton:formData>'
            '<operaton:formField id="ly_do" type="string"><operaton:validation>'
            '<operaton:constraint name="validator" config="vi.KiemTra" />'
            "</operaton:validation></operaton:formField></operaton:formData>"
            "</bpmn:extensionElements></bpmn:userTask>",
            [
                "Ràng buộc validator chạy class Java hoặc expression trong Operaton "
                "nên không được dùng."
            ],
        ),
        (
            '<bpmn:userTask id="xu_ly" operaton:formHandlerClass="vi.Lop" />',
            [
                "Thuộc tính operaton:formHandlerClass chạy class Java trong Operaton "
                "nên không được dùng."
            ],
        ),
    ],
    ids=[
        "script-task",
        "execution-listener",
        "task-listener",
        "java-class",
        "delegate-expression",
        "expression",
        "connector",
        "send-task",
        "business-rule-task",
        "field-injection",
        "call-activity-ung-dung-khac",
        "call-activity-tenant-khac",
        "call-activity-expression",
        "expression-doc-thuoc-tinh",
        "dieu-kien-bang-script",
        "validator",
        "form-handler-class",
    ],
)
def test_bpmn_running_code_inside_operaton_is_refused(tmp_path, body, expected):
    assert messages(tmp_path, document(FLOW + f"    {body}\n")) == expected


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("${now() > han_xu_ly}", f'Expression "${{now() > han_xu_ly}}" gọi hàm. {EXPRESSION_RULE}'),
        ("${fn:length(ly_do) > 0}", 'Expression "${fn:length(ly_do) > 0}" gọi hàm. '),
        ("${don.so_ngay > 3}", 'Expression "${don.so_ngay > 3}" đọc thuộc tính. '),
        ("${don['so_ngay'] > 3}", "Expression \"${don['so_ngay'] > 3}\" đọc thuộc tính. "),
        ("${so_ngay + 1 > 3}", 'Expression "${so_ngay + 1 > 3}" có ký hiệu "+". '),
        ("${a = 1}", 'Expression "${a = 1}" có ký hiệu "=". '),
        ("${x -> x}", 'Expression "${x -> x}" có ký hiệu "-". '),
        ("PT${so_phut", 'Expression "${so_phut" thiếu dấu "}".'),
        ("${a} và #{b.c}", 'Expression "#{b.c}" đọc thuộc tính. '),
    ],
    ids=[
        "goi-ham",
        "goi-ham-co-namespace",
        "doc-thuoc-tinh",
        "doc-phan-tu",
        "phep-cong",
        "gan-gia-tri",
        "lambda",
        "thieu-dau-dong",
        "expression-thu-hai",
    ],
)
def test_expression_calling_function_or_reading_property_is_refused(text, problem):
    assert expression_problem(text).startswith(problem)


@pytest.mark.parametrize(
    "text",
    [
        "PT${so_phut}M",
        "${so_ngay >= 3 && !khan || loai == 'phep'}",
        '${not empty ghi_chu and ket_qua eq "dong_y"}',
        "${(so_ngay gt 1.5e1) or (so_ngay le 0)}",
        "${ghi_chu == '}'} và ${khan != null}",
        "Không có expression",
    ],
    ids=["ghep-chuoi", "phep-logic", "tu-khoa", "ngoac-va-so", "dau-dong-trong-chuoi", "chu"],
)
def test_expression_of_names_values_comparisons_and_logic_passes(text):
    assert expression_problem(text) is None


def test_step_must_call_function_in_schema_of_app(tmp_path):
    good = document(FLOW + STEP.format(function="nghi_phep.ghi_ket_qua"))
    other = document(FLOW + STEP.format(function="khac.ghi_ket_qua"), key="nghi_phep.khac")
    wrong = document(FLOW + STEP.format(function="Nghi-Phep.ghi"), key="nghi_phep.sai")
    missing = document(FLOW + STEP.replace('name="function"', 'name="ham"'), key="nghi_phep.thieu")

    files = {"a.bpmn": good, "b.bpmn": other, "c.bpmn": wrong, "d.bpmn": missing}

    report = checked(tmp_path, files)

    assert [(problem.file, problem.message) for problem in report.problems] == [
        (
            "b.bpmn",
            "Bước máy làm ghi gọi hàm khac.ghi_ket_qua nằm ngoài schema nghi_phep của ứng dụng.",
        ),
        (
            "c.bpmn",
            "Tên hàm Nghi-Phep.ghi của bước máy làm ghi không hợp lệ. Tên hàm có dạng "
            "schema.ten_ham, chỉ gồm chữ thường không dấu, chữ số và dấu gạch dưới.",
        ),
        (
            "d.bpmn",
            "Bước máy làm ghi thiếu thuộc tính function nêu tên hàm dạng nghi_phep.ten_ham.",
        ),
    ]


def test_step_must_be_external_task_of_saigonos_topic(tmp_path):
    body = STEP.format(function="nghi_phep.ghi").replace("saigonos-function", "khac")

    assert messages(tmp_path, document(FLOW + body)) == [f"Thẻ serviceTask ghi {NOT_STEP}"]


def test_step_names_one_function_only(tmp_path):
    body = STEP.format(function="nghi_phep.ghi").replace(
        "</operaton:properties>",
        '<operaton:property name="function" value="nghi_phep.khac" /></operaton:properties>',
    )

    assert messages(tmp_path, document(FLOW + body)) == [
        "Bước máy làm ghi khai thuộc tính function nhiều lần."
    ]


@pytest.mark.parametrize("prefix", ["operaton", "camunda"])
def test_candidate_groups_are_roles_of_app_only(tmp_path, prefix):
    starters = f' {prefix}:historyTimeToLive="P30D" {prefix}:candidateStarterGroups'
    attributes = f'{starters}="nghi-phep.nhan-vien, admin"'
    groups = f"{prefix}:candidateGroups"
    body = (
        FLOW
        + f'    <bpmn:userTask id="xu_ly" {groups}="nghi-phep.quan-ly,khac.quan-ly" />\n'
        + f'    <bpmn:userTask id="giao" {groups}="${{nhom}}" />\n'
    )

    found = messages(tmp_path, document(body, attributes=attributes, prefix=prefix))

    assert found == [
        f"Thuộc tính {prefix}:candidateStarterGroups của quy trình nghi_phep.duyet có admin "
        "không phải role của ứng dụng.",
        f"Thuộc tính {prefix}:candidateGroups của việc xu_ly có khac.quan-ly "
        "không phải role của ứng dụng.",
        f"Thuộc tính {prefix}:candidateGroups của việc giao phải là danh sách role, "
        "không dùng expression.",
    ]


@pytest.mark.parametrize("key", ["duyet", "khac.duyet", "nghi_phep.Duyet", "nghi_phep.duyet-don"])
def test_process_id_starts_with_schema_of_app(tmp_path, key):
    assert messages(tmp_path, document(key=key)) == [
        f"Mã quy trình {key} phải có dạng nghi_phep.<tên quy trình>. "
        "Tên quy trình gồm chữ thường không dấu, chữ số và dấu gạch dưới."
    ]


def test_executable_process_needs_history_time_to_live(tmp_path):
    other = document(key="nghi_phep.khong_chay", attributes="").replace(
        'isExecutable="true"', 'isExecutable="false"'
    )

    report = checked(
        tmp_path, {"a.bpmn": document(attributes=""), "b.bpmn": other}, app=None, roles=None
    )

    assert [(problem.file, problem.message) for problem in report.problems] == [
        ("a.bpmn", "Quy trình nghi_phep.duyet thiếu thuộc tính operaton:historyTimeToLive.")
    ]


def test_rules_of_app_are_skipped_when_manifest_is_wrong(tmp_path):
    body = FLOW + '    <bpmn:scriptTask id="chay" />\n' + STEP.format(function="khac.ham")

    found = messages(tmp_path, document(body, key="khac.duyet"), app=None, roles=None)

    assert found == ["Thẻ scriptTask chạy script trong Operaton nên không được dùng."]


def test_process_is_declared_in_one_file_only(tmp_path):
    twice = document().replace(
        "</bpmn:definitions>",
        '<bpmn:process id="nghi_phep.duyet" isExecutable="false" />\n</bpmn:definitions>',
    )

    report = checked(tmp_path, {"a.bpmn": document(), "b.bpmn": document(), "c.bpmn": twice})

    assert [(problem.file, problem.message) for problem in report.problems] == [
        (
            "b.bpmn",
            "Quy trình nghi_phep.duyet được khai báo trong nhiều file: a.bpmn, b.bpmn, c.bpmn. "
            "Mỗi quy trình chỉ được khai báo trong một file.",
        )
    ]


def test_call_activity_reaches_process_declared_by_app(tmp_path):
    caller = document(
        FLOW + '    <bpmn:callActivity id="goi" calledElement="nghi_phep.con" />\n'
        '    <bpmn:callActivity id="goi_sai" calledElement="nghi_phep.khong_co" />\n'
    )

    report = checked(tmp_path, {"cha.bpmn": caller, "con.bpmn": document(key="nghi_phep.con")})

    assert [problem.message for problem in report.problems] == [
        "Thẻ callActivity goi_sai gọi quy trình nghi_phep.khong_co nhưng không file BPMN nào "
        "của ứng dụng khai báo quy trình này."
    ]


@pytest.mark.parametrize(
    ("field", "message"),
    [
        (
            '<operaton:formField id="ly-do" type="string" />',
            "Trường ly-do của form có id không hợp lệ. Id bắt đầu bằng chữ cái không dấu hoặc "
            "dấu gạch dưới, tiếp theo là chữ cái không dấu, chữ số hoặc dấu gạch dưới, "
            "dài tối đa 64 ký tự.",
        ),
        (
            '<operaton:formField id="tep" type="file" />',
            "Trường tep của form có kiểu file. Service core chỉ nhận các kiểu "
            "string, enum, long, boolean, date.",
        ),
        ('<operaton:formField id="ly_do" />', "Trường ly_do của form thiếu thuộc tính type."),
        (
            '<operaton:formField id="ly_do" type="string"><operaton:validation>'
            '<operaton:constraint name="pattern" config="x" /></operaton:validation>'
            "</operaton:formField>",
            "Ràng buộc pattern không được hỗ trợ. Các ràng buộc được dùng gồm required, "
            "readonly, minlength, maxlength, min và max.",
        ),
    ],
    ids=["id-sai", "kieu-la", "thieu-kieu", "rang-buoc-la"],
)
def test_form_fields_follow_rules_of_core(tmp_path, field, message):
    body = (
        FLOW + '    <bpmn:userTask id="xu_ly"><bpmn:extensionElements><operaton:formData>'
        f"{field}</operaton:formData></bpmn:extensionElements></bpmn:userTask>\n"
    )

    assert messages(tmp_path, document(body)) == [message]


def test_elements_outside_bpmn_and_operaton_are_refused(tmp_path):
    extra = '  <bpmn:signal id="tin_hieu" name="tin_hieu" />\n'
    body = (
        FLOW + '    <bpmn:task id="viec" xmlns:zeebe="http://camunda.org/schema/zeebe/1.0" '
        'xmlns:activiti="http://activiti.org/bpmn" activiti:async="true">'
        "<bpmn:extensionElements><zeebe:taskDefinition type="
        '"x" /></bpmn:extensionElements></bpmn:task>\n'
    )

    found = messages(tmp_path, document(body, extra=extra))

    assert found == [
        "Thẻ signal không được hỗ trợ trong quy trình của ứng dụng.",
        "Thuộc tính activiti:async của thẻ task không được hỗ trợ trong quy trình của ứng dụng.",
        "Thẻ zeebe:taskDefinition không thuộc BPMN 2.0 hay Operaton nên không được dùng.",
    ]


@pytest.mark.parametrize(
    ("content", "message", "line"),
    [
        (b"<a>\n<b>\n</a>\n", "File không phải XML hợp lệ ở cột 3.", 3),
        (
            b'<?xml version="1.0"?>\n<!DOCTYPE a [<!ENTITY x "y">]>\n<a>&x;</a>\n',
            "File không được có khai báo DOCTYPE.",
            2,
        ),
        (
            b'<definitions xmlns="urn:khac" />\n',
            "File không phải BPMN 2.0. Thẻ gốc phải là thẻ definitions của BPMN 2.0.",
            1,
        ),
    ],
    ids=["xml-sai", "doctype", "khong-phai-bpmn"],
)
def test_file_that_is_not_bpmn_is_refused_with_its_line(tmp_path, content, message, line):
    (tmp_path / "processes").mkdir()
    (tmp_path / "processes" / "duyet.bpmn").write_bytes(content)

    report = check_processes(tmp_path / "processes", APP, ROLES)

    assert [(problem.line, problem.message) for problem in report.problems] == [(line, message)]


def test_problem_carries_line_of_element(tmp_path):
    text = document(FLOW + '    <bpmn:scriptTask id="chay" />\n')

    [problem] = checked(tmp_path, {"duyet.bpmn": text}).problems

    assert text.splitlines()[problem.line - 1].strip() == '<bpmn:scriptTask id="chay" />'


def test_file_named_outside_rule_is_refused(tmp_path):
    report = checked(tmp_path, {"duyệt đơn.bpmn": document(), "ghi-chu.txt": "x"})

    assert [(problem.file, problem.message) for problem in report.problems] == [
        (
            "duyệt đơn.bpmn",
            "Tên file không hợp lệ. Tên file chỉ gồm chữ cái không dấu, chữ số, dấu chấm, "
            "dấu gạch ngang, dấu gạch dưới và kết thúc bằng .bpmn.",
        )
    ]


def test_file_without_drawing_gets_warning(tmp_path):
    report = checked(tmp_path, {"duyet.bpmn": document(drawn=None)})

    assert report.problems == []
    assert [(warning.file, warning.message) for warning in report.warnings] == [
        ("duyet.bpmn", NO_DRAWING)
    ]


@pytest.mark.parametrize(
    ("drawn", "listed"),
    [
        (("bat_dau",), "luong_1, ket_thuc"),
        ((), "bat_dau, luong_1, ket_thuc, viec_1, viec_2 và 1 phần tử khác"),
    ],
    ids=["thieu-hai", "thieu-nhieu"],
)
def test_drawing_missing_elements_gets_warning(tmp_path, drawn, listed):
    body = FLOW + "".join(f'    <bpmn:task id="viec_{index}" />\n' for index in (1, 2, 3))
    if drawn:
        body = FLOW

    report = checked(tmp_path, {"duyet.bpmn": document(body, drawn=drawn)})

    assert [warning.message for warning in report.warnings] == [
        f"Phần hình vẽ thiếu {listed} nên Cockpit của Operaton không vẽ được các phần tử này."
    ]


def test_call_activity_names_process_to_call(tmp_path):
    body = FLOW + '    <bpmn:callActivity id="goi" />\n'

    assert messages(tmp_path, document(body)) == [
        "Thẻ callActivity goi thiếu thuộc tính calledElement."
    ]


def test_call_activity_is_not_checked_against_app_when_manifest_is_wrong(tmp_path):
    body = FLOW + '    <bpmn:callActivity id="goi" calledElement="khac.duyet" />\n'

    assert messages(tmp_path, document(body), app=None, roles=None) == []


def test_process_declared_twice_in_one_file_is_refused(tmp_path):
    twice = document().replace(
        "</bpmn:definitions>",
        '<bpmn:process id="nghi_phep.duyet" isExecutable="false" />\n</bpmn:definitions>',
    )

    report = checked(tmp_path, {"duyet.bpmn": twice})

    assert [problem.message for problem in report.problems] == [
        "Quy trình nghi_phep.duyet được khai báo nhiều lần trong file duyet.bpmn."
    ]
