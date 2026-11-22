# SPDX-License-Identifier: Apache-2.0
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import NamedTuple
from xml.parsers import expat

from saigonos_core.forms import CHECKS
from saigonos_core.processes import BPMN, EXTENSIONS, MAX_NAME, NAME, listed
from saigonos_core.steps import FUNCTION, PROPERTY, TOPIC

BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"
DRAWING = frozenset(
    {
        BPMNDI,
        "http://www.omg.org/spec/DD/20100524/DC",
        "http://www.omg.org/spec/DD/20100524/DI",
    }
)
LEGACY = "http://activiti.org/bpmn"
SEPARATOR = " "
PATTERN = "*.bpmn"
FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.bpmn")
VARIABLE = re.compile(NAME)
EXTERNAL = "external"
CONSTRAINTS = ("required", "readonly", "minlength", "maxlength", "min", "max")
SHOWN = 80
LISTED = 5
NAMED = frozenset({"id", "name"})
ASYNC = frozenset({"asyncBefore", "asyncAfter", "exclusive"})
NONE: frozenset[str] = frozenset()
ELEMENTS = {
    "definitions": (NAMED | {"targetNamespace", "exporter", "exporterVersion"}, NONE),
    "process": (
        NAMED | {"isExecutable"},
        frozenset(
            {"historyTimeToLive", "candidateStarterGroups", "versionTag", "isStartableInTasklist"}
        ),
    ),
    "collaboration": (NAMED, NONE),
    "participant": (NAMED | {"processRef"}, NONE),
    "messageFlow": (NAMED | {"sourceRef", "targetRef"}, NONE),
    "laneSet": (NAMED, NONE),
    "lane": (NAMED, NONE),
    "childLaneSet": (NAMED, NONE),
    "flowNodeRef": (NONE, NONE),
    "documentation": (frozenset({"id", "textFormat"}), NONE),
    "extensionElements": (NONE, NONE),
    "textAnnotation": (frozenset({"id", "textFormat"}), NONE),
    "text": (NONE, NONE),
    "association": (frozenset({"id", "sourceRef", "targetRef", "associationDirection"}), NONE),
    "group": (frozenset({"id", "categoryValueRef"}), NONE),
    "category": (NAMED, NONE),
    "categoryValue": (frozenset({"id", "value"}), NONE),
    "startEvent": (NAMED | {"isInterrupting"}, ASYNC | {"initiator"}),
    "endEvent": (NAMED, ASYNC),
    "intermediateCatchEvent": (NAMED, ASYNC),
    "intermediateThrowEvent": (NAMED, ASYNC),
    "boundaryEvent": (NAMED | {"attachedToRef", "cancelActivity"}, ASYNC),
    "userTask": (
        NAMED,
        ASYNC | {"candidateGroups", "assignee", "dueDate", "followUpDate", "priority"},
    ),
    "serviceTask": (NAMED, ASYNC | {"type", "topic"}),
    "manualTask": (NAMED, ASYNC),
    "task": (NAMED, ASYNC),
    "callActivity": (
        NAMED | {"calledElement"},
        ASYNC | {"calledElementBinding", "calledElementVersion", "calledElementVersionTag"},
    ),
    "subProcess": (NAMED | {"triggeredByEvent"}, ASYNC),
    "exclusiveGateway": (NAMED | {"gatewayDirection", "default"}, ASYNC),
    "inclusiveGateway": (NAMED | {"gatewayDirection", "default"}, ASYNC),
    "parallelGateway": (NAMED | {"gatewayDirection"}, ASYNC),
    "eventBasedGateway": (NAMED | {"gatewayDirection"}, ASYNC),
    "sequenceFlow": (NAMED | {"sourceRef", "targetRef"}, NONE),
    "conditionExpression": (frozenset({"id"}), NONE),
    "incoming": (NONE, NONE),
    "outgoing": (NONE, NONE),
    "timerEventDefinition": (frozenset({"id"}), NONE),
    "timeDate": (frozenset({"id"}), NONE),
    "timeDuration": (frozenset({"id"}), NONE),
    "timeCycle": (frozenset({"id"}), NONE),
    "errorEventDefinition": (
        frozenset({"id", "errorRef"}),
        frozenset({"errorCodeVariable", "errorMessageVariable"}),
    ),
    "escalationEventDefinition": (
        frozenset({"id", "escalationRef"}),
        frozenset({"escalationCodeVariable"}),
    ),
    "terminateEventDefinition": (frozenset({"id"}), NONE),
    "linkEventDefinition": (NAMED, NONE),
    "conditionalEventDefinition": (
        frozenset({"id"}),
        frozenset({"variableName", "variableEvents"}),
    ),
    "condition": (frozenset({"id"}), NONE),
    "error": (NAMED | {"errorCode"}, frozenset({"errorMessage"})),
    "escalation": (NAMED | {"escalationCode"}, NONE),
    "multiInstanceLoopCharacteristics": (
        frozenset({"id", "isSequential"}),
        ASYNC | {"collection", "elementVariable"},
    ),
    "loopCardinality": (frozenset({"id"}), NONE),
    "completionCondition": (frozenset({"id"}), NONE),
}
EXTENSION_ELEMENTS = {
    "formData": NONE,
    "formField": frozenset({"id", "label", "type", "defaultValue", "datePattern"}),
    "validation": NONE,
    "constraint": frozenset({"name", "config"}),
    "value": NAMED,
    "properties": NONE,
    "property": frozenset({"id", "name", "value"}),
    "in": frozenset({"source", "sourceExpression", "target", "variables", "local", "businessKey"}),
    "out": frozenset({"source", "sourceExpression", "target", "variables", "local"}),
}
DRAWN = frozenset(
    {
        "startEvent",
        "endEvent",
        "intermediateCatchEvent",
        "intermediateThrowEvent",
        "boundaryEvent",
        "userTask",
        "serviceTask",
        "manualTask",
        "task",
        "callActivity",
        "subProcess",
        "exclusiveGateway",
        "inclusiveGateway",
        "parallelGateway",
        "eventBasedGateway",
        "sequenceFlow",
    }
)
LITERAL = frozenset({"candidateGroups", "candidateStarterGroups", "calledElement"})
CODE_ELEMENTS = {
    "scriptTask": "chạy script trong Operaton",
    "businessRuleTask": "chạy bảng quyết định hoặc class Java trong Operaton",
    "sendTask": "chạy class Java trong Operaton",
}
CODE_EXTENSIONS = {
    "executionListener": "chạy mã trong Operaton khi quy trình đi qua",
    "taskListener": "chạy mã trong Operaton theo sự kiện của việc",
    "connector": "gọi service bên ngoài từ Operaton",
    "script": "chạy script trong Operaton",
    "field": "truyền giá trị cho class Java",
}
CODE_ATTRIBUTES = {
    "class": "chạy class Java trong Operaton",
    "delegateExpression": "chạy mã Java trong Operaton",
    "expression": "chạy expression trong Operaton",
    "formHandlerClass": "chạy class Java trong Operaton",
    "variableMappingClass": "chạy class Java trong Operaton",
    "variableMappingDelegateExpression": "chạy mã Java trong Operaton",
    "resource": "nạp script từ file khác",
    "calledElementTenantId": "gọi quy trình của ứng dụng khác",
}
PLAIN_CODE = {"language": "chạy script trong Operaton"}
KEYWORDS = frozenset(
    {"and", "or", "not", "eq", "ne", "lt", "gt", "le", "ge", "empty", "true", "false", "null"}
)
OPENING = re.compile(r"[$#]\{")
TOKEN = re.compile(
    r"(?P<string>'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")"
    r"|(?P<number>[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)"
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<operator>==|!=|<=|>=|&&|\|\||[<>!()])"
)
EXPRESSION_RULE = "Expression chỉ được gồm tên biến, giá trị, phép so sánh và phép logic."
NOT_BPMN = "File không phải BPMN 2.0. Thẻ gốc phải là thẻ definitions của BPMN 2.0."
NO_DRAWING = "File không có phần hình vẽ (BPMNDI) nên Cockpit của Operaton không vẽ được quy trình."
FILE_RULE = (
    "Tên file không hợp lệ. Tên file chỉ gồm chữ cái không dấu, chữ số, dấu chấm, "
    "dấu gạch ngang, dấu gạch dưới và kết thúc bằng .bpmn."
)


class Finding(NamedTuple):
    file: str
    line: int | None
    message: str


class Report(NamedTuple):
    problems: list[Finding]
    warnings: list[Finding]


class RefusedFileError(Exception):
    def __init__(self, message: str, line: int | None) -> None:
        super().__init__(message)
        self.line = line


@dataclass
class Node:
    namespace: str
    name: str
    attributes: dict[tuple[str, str], str]
    line: int
    children: list["Node"] = field(default_factory=list)
    text: str = ""

    @property
    def id(self) -> str:
        return self.attributes.get(("", "id"), "")

    def extension(self, name: str) -> list[tuple[str, str]]:
        return [
            (namespace, self.attributes[namespace, name])
            for namespace in EXTENSIONS
            if (namespace, name) in self.attributes
        ]

    def tree(self) -> Iterator["Node"]:
        yield self
        for child in self.children:
            yield from child.tree()

    def nested(self, *path: str) -> Iterator["Node"]:
        if not path:
            yield self
            return
        for child in self.children:
            if child.name == path[0] and child.namespace in (BPMN, *EXTENSIONS):
                yield from child.nested(*path[1:])


def split(name: str) -> tuple[str, str]:
    namespace, _, local = name.rpartition(SEPARATOR)
    return namespace, local


def parse(content: bytes) -> tuple[Node, dict[str, str]]:
    parser = expat.ParserCreate(namespace_separator=SEPARATOR)
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    prefixes: dict[str, str] = {}
    roots: list[Node] = []
    open_nodes: list[Node] = []

    def start(name: str, attributes: dict[str, str]) -> None:
        namespace, local = split(name)
        found = {split(key): value for key, value in attributes.items()}
        node = Node(namespace, local, found, parser.CurrentLineNumber)
        (open_nodes[-1].children if open_nodes else roots).append(node)
        open_nodes.append(node)

    def end(name: str) -> None:
        open_nodes.pop()

    def text(data: str) -> None:
        if open_nodes:
            open_nodes[-1].text += data

    def declared(prefix: str | None, uri: str) -> None:
        prefixes.setdefault(uri, prefix or "")

    def doctype(*details: object) -> None:
        raise RefusedFileError("File không được có khai báo DOCTYPE.", parser.CurrentLineNumber)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = text
    parser.StartNamespaceDeclHandler = declared
    parser.StartDoctypeDeclHandler = doctype
    try:
        parser.Parse(content, True)
    except expat.ExpatError as error:
        message = f"File không phải XML hợp lệ ở cột {error.offset + 1}."
        raise RefusedFileError(message, error.lineno) from None
    return roots[0], prefixes


def shown(text: str) -> str:
    return text if len(text) <= SHOWN else f"{text[: SHOWN - 1]}…"


def scan(text: str, start: int) -> tuple[int, str | None]:
    position = start
    previous = None
    while True:
        while position < len(text) and text[position].isspace():
            position += 1
        if position >= len(text):
            return position, 'thiếu dấu "}".'
        if text[position] == "}":
            return position + 1, None
        found = TOKEN.match(text, position)
        if found is None:
            character = text[position]
            if character in ".[":
                return position, f"đọc thuộc tính. {EXPRESSION_RULE}"
            if character == ":":
                return position, f"gọi hàm. {EXPRESSION_RULE}"
            return position, f'có ký hiệu "{character}". {EXPRESSION_RULE}'
        kind = found.lastgroup or ""
        if kind == "operator" and found[kind] == "(" and previous == "name":
            return position, f"gọi hàm. {EXPRESSION_RULE}"
        previous = "keyword" if kind == "name" and found[kind] in KEYWORDS else kind
        position = found.end()


def expression_problem(text: str) -> str | None:
    position = 0
    while (opening := OPENING.search(text, position)) is not None:
        end, problem = scan(text, opening.end())
        if problem is not None:
            closing = text.find("}", end)
            whole = text[opening.start() : len(text) if closing < 0 else closing + 1]
            return f'Expression "{shown(whole)}" {problem}'
        position = end
    return None


def listing(names: list[str]) -> str:
    if len(names) <= LISTED:
        return ", ".join(names)
    return f"{', '.join(names[:LISTED])} và {len(names) - LISTED} phần tử khác"


class BpmnFile:
    def __init__(self, name: str, app: str | None, roles: frozenset[str] | None) -> None:
        self.name = name
        self.schema = None if app is None else app.replace("-", "_")
        self.roles = roles
        self.problems: list[Finding] = []
        self.warnings: list[Finding] = []
        self.prefixes: dict[str, str] = {}
        self.processes: list[tuple[str, int]] = []
        self.calls: list[tuple[str, str, int]] = []

    def problem(self, line: int | None, message: str) -> None:
        self.problems.append(Finding(self.name, line, message))

    def label(self, namespace: str, name: str) -> str:
        if namespace in ("", BPMN):
            return name
        prefix = self.prefixes.get(namespace)
        return f"{prefix}:{name}" if prefix else name

    def check(self, content: bytes) -> None:
        try:
            root, self.prefixes = parse(content)
        except RefusedFileError as error:
            self.problem(error.line, str(error))
            return
        if (root.namespace, root.name) != (BPMN, "definitions"):
            self.problem(root.line, NOT_BPMN)
            return
        self.visit(root)
        self.check_drawing(root)

    def refuse_element(self, node: Node, reason: str | None) -> None:
        name = self.label(node.namespace, node.name)
        if reason:
            self.problem(node.line, f"Thẻ {name} {reason} nên không được dùng.")
        else:
            self.problem(node.line, f"Thẻ {name} không được hỗ trợ trong quy trình của ứng dụng.")

    def visit(self, node: Node) -> None:
        if node.namespace in DRAWING:
            return
        if node.namespace == BPMN and node.name in ELEMENTS:
            plain, extended = ELEMENTS[node.name]
        elif node.namespace in EXTENSIONS and node.name in EXTENSION_ELEMENTS:
            plain, extended = EXTENSION_ELEMENTS[node.name], NONE
        elif node.namespace == BPMN:
            self.refuse_element(node, CODE_ELEMENTS.get(node.name))
            return
        elif node.namespace in EXTENSIONS:
            self.refuse_element(node, CODE_EXTENSIONS.get(node.name))
            return
        else:
            name = self.label(node.namespace, node.name)
            self.problem(
                node.line, f"Thẻ {name} không thuộc BPMN 2.0 hay Operaton nên không được dùng."
            )
            return
        self.check_attributes(node, plain, extended)
        if node.text.strip():
            self.check_expression(node.line, node.text)
        rule = RULES.get((node.namespace in EXTENSIONS, node.name))
        if rule is not None:
            rule(self, node)
        for child in node.children:
            self.visit(child)

    def check_attributes(self, node: Node, plain: frozenset[str], extended: frozenset[str]) -> None:
        for (namespace, name), value in node.attributes.items():
            if namespace == "":
                reason = None if name in plain else PLAIN_CODE.get(name, "")
            elif namespace in EXTENSIONS:
                reason = None if name in extended else CODE_ATTRIBUTES.get(name, "")
            elif namespace in (BPMN, LEGACY):
                reason = ""
            else:
                continue
            if reason is None:
                if name not in LITERAL:
                    self.check_expression(node.line, value)
                continue
            attribute = self.label(namespace, name)
            if reason:
                message = f"Thuộc tính {attribute} {reason} nên không được dùng."
            else:
                element = self.label(node.namespace, node.name)
                message = (
                    f"Thuộc tính {attribute} của thẻ {element} không được hỗ trợ "
                    "trong quy trình của ứng dụng."
                )
            self.problem(node.line, message)

    def check_expression(self, line: int, text: str) -> None:
        problem = expression_problem(text)
        if problem is not None:
            self.problem(line, problem)

    def check_groups(self, node: Node, attribute: str, owner: str) -> None:
        for namespace, value in node.extension(attribute):
            label = self.label(namespace, attribute)
            if OPENING.search(value):
                self.problem(
                    node.line,
                    f"Thuộc tính {label} của {owner} phải là danh sách role, "
                    "không dùng expression.",
                )
            elif self.roles is not None:
                foreign = sorted(listed(value) - self.roles)
                if foreign:
                    self.problem(
                        node.line,
                        f"Thuộc tính {label} của {owner} có {', '.join(foreign)} "
                        "không phải role của ứng dụng.",
                    )

    def check_process(self, node: Node) -> None:
        key = node.id
        if self.schema is not None:
            found = FUNCTION.fullmatch(key)
            if found is None or found[1] != self.schema:
                self.problem(
                    node.line,
                    f"Mã quy trình {key} phải có dạng {self.schema}.<tên quy trình>. "
                    "Tên quy trình gồm chữ thường không dấu, chữ số và dấu gạch dưới.",
                )
        executable = node.attributes.get(("", "isExecutable")) != "false"
        if executable and not node.extension("historyTimeToLive"):
            self.problem(node.line, f"Quy trình {key} thiếu thuộc tính operaton:historyTimeToLive.")
        self.check_groups(node, "candidateStarterGroups", f"quy trình {key}")
        self.processes.append((key, node.line))

    def check_user_task(self, node: Node) -> None:
        self.check_groups(node, "candidateGroups", f"việc {node.id}")

    def check_step(self, node: Node) -> None:
        kinds = [value for _, value in node.extension("type")]
        topics = [value for _, value in node.extension("topic")]
        if set(kinds) != {EXTERNAL} or set(topics) != {TOPIC}:
            self.problem(
                node.line,
                f"Thẻ serviceTask {node.id} phải là bước máy làm, với "
                f'operaton:type="{EXTERNAL}" và operaton:topic="{TOPIC}".',
            )
            return
        functions = [
            item.attributes.get(("", "value"), "")
            for item in node.nested("extensionElements", "properties", "property")
            if item.attributes.get(("", "name")) == PROPERTY
        ]
        schema = self.schema or "schema"
        if not functions:
            self.problem(
                node.line,
                f"Bước máy làm {node.id} thiếu thuộc tính {PROPERTY} nêu tên hàm "
                f"dạng {schema}.ten_ham.",
            )
            return
        if len(functions) > 1:
            self.problem(node.line, f"Bước máy làm {node.id} khai thuộc tính {PROPERTY} nhiều lần.")
            return
        [value] = functions
        found = FUNCTION.fullmatch(value)
        if found is None:
            self.problem(
                node.line,
                f"Tên hàm {value} của bước máy làm {node.id} không hợp lệ. Tên hàm có dạng "
                "schema.ten_ham, chỉ gồm chữ thường không dấu, chữ số và dấu gạch dưới.",
            )
        elif self.schema is not None and found[1] != self.schema:
            self.problem(
                node.line,
                f"Bước máy làm {node.id} gọi hàm {value} nằm ngoài schema {self.schema} "
                "của ứng dụng.",
            )

    def check_call(self, node: Node) -> None:
        called = node.attributes.get(("", "calledElement"))
        if called is None:
            self.problem(node.line, f"Thẻ callActivity {node.id} thiếu thuộc tính calledElement.")
            return
        if OPENING.search(called):
            self.problem(
                node.line,
                f"Thuộc tính calledElement của thẻ callActivity {node.id} phải là mã quy trình, "
                "không dùng expression.",
            )
            return
        if self.schema is None:
            return
        found = FUNCTION.fullmatch(called)
        if found is None or found[1] != self.schema:
            self.problem(
                node.line,
                f"Thẻ callActivity {node.id} gọi quy trình {called} không thuộc ứng dụng. "
                "Quy trình chỉ gọi được quy trình của chính ứng dụng, có mã dạng "
                f"{self.schema}.<tên quy trình>.",
            )
            return
        self.calls.append((node.id, called, node.line))

    def check_field(self, node: Node) -> None:
        name = node.id
        if not VARIABLE.fullmatch(name) or len(name) > MAX_NAME:
            self.problem(
                node.line,
                f"Trường {name} của form có id không hợp lệ. Id bắt đầu bằng chữ cái không dấu "
                "hoặc dấu gạch dưới, tiếp theo là chữ cái không dấu, chữ số hoặc dấu gạch dưới, "
                f"dài tối đa {MAX_NAME} ký tự.",
            )
        kind = node.attributes.get(("", "type"))
        if kind is None:
            self.problem(node.line, f"Trường {name} của form thiếu thuộc tính type.")
        elif kind not in CHECKS:
            self.problem(
                node.line,
                f"Trường {name} của form có kiểu {kind}. Service core chỉ nhận các kiểu "
                f"{', '.join(CHECKS)}.",
            )

    def check_constraint(self, node: Node) -> None:
        name = node.attributes.get(("", "name"))
        if name == "validator":
            self.problem(
                node.line,
                "Ràng buộc validator chạy class Java hoặc expression trong Operaton "
                "nên không được dùng.",
            )
        elif name not in CONSTRAINTS:
            self.problem(
                node.line,
                f"Ràng buộc {name} không được hỗ trợ. Các ràng buộc được dùng gồm "
                f"{', '.join(CONSTRAINTS[:-1])} và {CONSTRAINTS[-1]}.",
            )

    def check_drawing(self, root: Node) -> None:
        nodes = list(root.tree())
        if not any(node.namespace == BPMNDI and node.name == "BPMNDiagram" for node in nodes):
            self.warnings.append(Finding(self.name, None, NO_DRAWING))
            return
        drawn = {node.attributes.get(("", "bpmnElement")) for node in nodes}
        missing = [
            node.id
            for node in nodes
            if node.namespace == BPMN and node.name in DRAWN and node.id not in drawn
        ]
        if missing:
            self.warnings.append(
                Finding(
                    self.name,
                    None,
                    f"Phần hình vẽ thiếu {listing(missing)} nên Cockpit của Operaton "
                    "không vẽ được các phần tử này.",
                )
            )


RULES = {
    (False, "process"): BpmnFile.check_process,
    (False, "userTask"): BpmnFile.check_user_task,
    (False, "serviceTask"): BpmnFile.check_step,
    (False, "callActivity"): BpmnFile.check_call,
    (True, "formField"): BpmnFile.check_field,
    (True, "constraint"): BpmnFile.check_constraint,
}


def bpmn_files(folder: Path) -> list[Path]:
    return sorted(
        entry for entry in folder.iterdir() if entry.is_file() and fnmatchcase(entry.name, PATTERN)
    )


def check_processes(folder: Path, app: str | None, roles: Iterable[str] | None) -> Report:
    allowed = None if roles is None else frozenset(roles)
    problems: list[Finding] = []
    warnings: list[Finding] = []
    declared: dict[str, list[tuple[str, int]]] = {}
    calls: list[tuple[str, str, str, int]] = []
    for entry in bpmn_files(folder):
        if not FILE_NAME.fullmatch(entry.name):
            problems.append(Finding(entry.name, None, FILE_RULE))
            continue
        checked = BpmnFile(entry.name, app, allowed)
        checked.check(entry.read_bytes())
        problems += checked.problems
        warnings += checked.warnings
        for key, line in checked.processes:
            declared.setdefault(key, []).append((entry.name, line))
        calls += [(entry.name, *call) for call in checked.calls]
    for key, places in declared.items():
        files = list(dict.fromkeys(file for file, _ in places))
        if len(places) < 2:
            continue
        file, line = places[1]
        if len(files) == 1:
            message = f"Quy trình {key} được khai báo nhiều lần trong file {file}."
        else:
            message = (
                f"Quy trình {key} được khai báo trong nhiều file: {', '.join(files)}. "
                "Mỗi quy trình chỉ được khai báo trong một file."
            )
        problems.append(Finding(file, line, message))
    for file, task, called, line in calls:
        if called not in declared:
            problems.append(
                Finding(
                    file,
                    line,
                    f"Thẻ callActivity {task} gọi quy trình {called} nhưng không file BPMN nào "
                    "của ứng dụng khai báo quy trình này.",
                )
            )
    return Report(problems, warnings)
