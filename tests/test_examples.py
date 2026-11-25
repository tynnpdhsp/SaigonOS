# SPDX-License-Identifier: Apache-2.0
from itertools import combinations
from pathlib import Path

from saigonos_core.bpmn import BPMN, BPMNDI, DRAWN, parse
from saigonos_core.manifest import check_app

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "phong-may"
PROCESS = EXAMPLE / "processes" / "dat-phong.bpmn"
DI = "http://www.omg.org/spec/DD/20100524/DI"
BOUNDS = ("x", "y", "width", "height")
STEPS = [
    "phong_may.ghi_don",
    "phong_may.nhac_duyet",
    "phong_may.ghi_ket_qua",
    "phong_may.ghi_san_sang",
]


def diagram():
    root, _ = parse(PROCESS.read_bytes())
    nodes = list(root.tree())
    elements = {node.id: node for node in nodes if node.namespace == BPMN and node.name in DRAWN}
    shapes, edges = {}, {}
    for node in nodes:
        if node.namespace != BPMNDI:
            continue
        element = node.attributes.get(("", "bpmnElement"))
        if node.name == "BPMNShape":
            bounds = next(child for child in node.children if child.name == "Bounds")
            shapes[element] = tuple(float(bounds.attributes["", key]) for key in BOUNDS)
        elif node.name == "BPMNEdge":
            points = [
                child
                for child in node.children
                if (child.namespace, child.name) == (DI, "waypoint")
            ]
            edges[element] = [
                (float(point.attributes["", "x"]), float(point.attributes["", "y"]))
                for point in points
            ]
    return elements, shapes, edges


def on_border(point, box):
    x, y = point
    left, top, width, height = box
    inside = left - 1 <= x <= left + width + 1 and top - 1 <= y <= top + height + 1
    gaps = (abs(x - left), abs(x - left - width), abs(y - top), abs(y - top - height))
    return inside and min(gaps) <= 1


def overlap(first, second):
    left, top, width, height = first
    other_left, other_top, other_width, other_height = second
    apart_x = left + width <= other_left or other_left + other_width <= left
    apart_y = top + height <= other_top or other_top + other_height <= top
    return not (apart_x or apart_y)


def test_sample_app_passes_check_without_warnings():
    checked = check_app(EXAMPLE)

    assert checked.problems == []
    assert checked.warnings == ()
    assert checked.manifest.name == "phong-may"


def test_sql_files_of_sample_app_run_in_name_order():
    names = [path.name for path in sorted((EXAMPLE / "database").glob("*.sql"))]

    assert names == ["0001_phong.sql", "0002_nguoi_dung.sql", "0003_don.sql", "0004_quy_trinh.sql"]


def test_every_step_and_flow_of_sample_process_is_drawn():
    elements, shapes, edges = diagram()
    flows = {key for key, node in elements.items() if node.name == "sequenceFlow"}

    assert set(shapes) == set(elements) - flows
    assert set(edges) == flows
    assert all(len(points) >= 2 for points in edges.values())


def test_flows_of_sample_process_start_and_end_on_their_shapes():
    elements, shapes, edges = diagram()

    for key, points in edges.items():
        flow = elements[key]
        assert on_border(points[0], shapes[flow.attributes["", "sourceRef"]]), key
        assert on_border(points[-1], shapes[flow.attributes["", "targetRef"]]), key


def test_shapes_of_sample_process_do_not_overlap():
    elements, shapes, _ = diagram()
    attached = {
        key: node.attributes["", "attachedToRef"]
        for key, node in elements.items()
        if node.name == "boundaryEvent"
    }

    for (first, box), (second, other) in combinations(shapes.items(), 2):
        if second == attached.get(first) or first == attached.get(second):
            continue
        assert not overlap(box, other), (first, second)


def test_steps_of_sample_process_call_functions_granted_to_workflow():
    sql = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((EXAMPLE / "database").glob("*.sql"))
    )
    root, _ = parse(PROCESS.read_bytes())
    functions = [
        node.attributes["", "value"]
        for node in root.tree()
        if node.name == "property" and node.attributes.get(("", "name")) == "function"
    ]

    assert functions == STEPS
    for function in functions:
        name = function.removeprefix("phong_may.")
        assert f"CREATE FUNCTION {name}(bien jsonb) RETURNS jsonb" in sql
        assert f"GRANT EXECUTE ON FUNCTION {name}(jsonb) TO workflow;" in sql
