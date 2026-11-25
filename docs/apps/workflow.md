<!-- SPDX-License-Identifier: Apache-2.0 -->
# Quy trình

## Quy trình của ứng dụng

Lệnh cài đặt triển khai các file `.bpmn` trong thư mục `processes` của ứng dụng vào Operaton. Quy tắc chung của file BPMN, form và bước máy làm được trình bày ở mục [Quy trình](../admin/operaton.md). Quy trình của ứng dụng tuân theo thêm các quy tắc sau:

- Mỗi file là một bản triển khai riêng. Tên của bản triển khai là tên file, nguồn (deployment source) là `app:<tên ứng dụng>`. File không thay đổi thì không tạo phiên bản mới. File đã sửa tạo một phiên bản mới, còn các quy trình đang chạy vẫn dùng phiên bản cũ.
- Quy trình của ứng dụng nằm trong tenant của Operaton có tên là tên ứng dụng. Do đó, quy trình của ứng dụng không trùng mã được với quy trình của ứng dụng khác hay quy trình trong thư mục `config/operaton/processes`.
- Mã quy trình có dạng `<schema>.<tên quy trình>`, ví dụ `nghi_phep.duyet`. Tên quy trình gồm chữ thường không dấu, chữ số và dấu gạch dưới. Mỗi quy trình chỉ được khai báo trong một file.
- Thuộc tính `operaton:candidateStarterGroups` của quy trình và `operaton:candidateGroups` của việc chỉ gồm role của ứng dụng, không dùng expression.
- Bước máy làm chỉ gọi hàm trong schema của ứng dụng. Call activity chỉ gọi quy trình có trong các file BPMN của chính ứng dụng.
- Tên file chỉ gồm chữ cái không dấu, chữ số, dấu chấm, dấu gạch ngang, dấu gạch dưới và kết thúc bằng `.bpmn`.

Lệnh soát từ chối file BPMN chạy mã bên trong Operaton. Script task, business rule task, send task, listener, class Java, delegate expression, connector và ràng buộc `validator` của form đều bị từ chối. Expression chỉ được gồm tên biến, giá trị, phép so sánh và phép logic, ví dụ `${so_ngay > 3 && !khan}`. Expression gọi hàm như `${now()}` hoặc đọc thuộc tính như `${don.so_ngay}` bị từ chối.

File chỉ được dùng các thẻ sau:

- Sự kiện bắt đầu, kết thúc, sự kiện trung gian và sự kiện biên. Sự kiện dùng được hẹn giờ, error, escalation, terminate, link và conditional.
- Việc của người dùng (`userTask`), bước máy làm, `task`, `manualTask`, call activity và subprocess.
- Các gateway, luồng (`sequenceFlow`) và multi-instance.
- Lane, pool, chú thích và phần hình vẽ.

Message và signal chưa được hỗ trợ. File thiếu phần hình vẽ (BPMNDI), hoặc có phần hình vẽ thiếu một số phần tử, vẫn được cài đặt. Khi đó, lệnh soát in cảnh báo, vì Cockpit không vẽ được quy trình hoặc các phần tử đó.

Ứng dụng bắt đầu quy trình và xử lý việc qua service `core` như mục [Bắt đầu quy trình](#bắt-đầu-quy-trình) và [Nhận việc và hoàn thành việc](#nhận-việc-và-hoàn-thành-việc), với access token của ứng dụng. Ví dụ, lời gọi `POST /core/processes/nghi_phep.duyet/start` bắt đầu quy trình `nghi_phep.duyet`. Service `core` lọc quy trình và việc theo client của access token, tức claim `azp`:

- Access token của một ứng dụng chỉ thấy, nhận, hoàn thành và bắt đầu quy trình của ứng dụng đó.
- Access token của client khác, kể cả của ứng dụng khác, không thấy quy trình và việc của ứng dụng. Lời gọi tới quy trình hoặc việc đó nhận mã 404.
- Access token của ứng dụng không thấy quy trình trong thư mục `config/operaton/processes`.

Hàm của bước máy làm được khai báo bằng lệnh `GRANT EXECUTE` cho role `workflow` như mục [Bước máy làm](#bước-máy-làm). Hàm chạy bằng role `<schema>_user` như mọi hàm khác của ứng dụng, hoặc bằng role sở hữu schema khi khai `SECURITY DEFINER`. Hàm chỉ cấp cho role `workflow` thì người dùng không gọi được qua API của ứng dụng. Bước máy làm không có người gọi, nên `core.uid()` trả về `NULL`. Do đó, hàm cập nhật bảng có chính sách RLS theo `core.uid()` thường khai `SECURITY DEFINER`. Biến `initiator` cho biết người đã bắt đầu quy trình.

Khi bước máy làm gọi hàm ngoài schema của ứng dụng sở hữu quy trình, bước này trở thành incident. Quy trình trong thư mục `config/operaton/processes` cũng không gọi được hàm của ứng dụng.

Ví dụ, file `processes/duyet.bpmn` của ứng dụng nghỉ phép khai báo quy trình duyệt đơn. Người có realm role `nghi-phep.nhan-vien` tạo đơn qua API của ứng dụng rồi bắt đầu quy trình với mã đơn. Người có realm role `nghi-phep.quan-ly` duyệt đơn. Sau đó, bước máy làm ghi kết quả vào bảng `don`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                  xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
                  xmlns:operaton="http://operaton.org/schema/1.0/bpmn"
                  id="duyet_dinh_nghia" targetNamespace="https://dx.example.com/bpmn">
  <bpmn:process id="nghi_phep.duyet" name="Duyệt đơn nghỉ phép" isExecutable="true"
                operaton:historyTimeToLive="P180D"
                operaton:candidateStarterGroups="nghi-phep.nhan-vien">
    <bpmn:startEvent id="gui_don" name="Gửi đơn">
      <bpmn:extensionElements>
        <operaton:formData>
          <operaton:formField id="ma_don" label="Mã đơn" type="long">
            <operaton:validation>
              <operaton:constraint name="required" />
            </operaton:validation>
          </operaton:formField>
        </operaton:formData>
      </bpmn:extensionElements>
    </bpmn:startEvent>
    <bpmn:sequenceFlow id="luong_1" sourceRef="gui_don" targetRef="duyet" />
    <bpmn:userTask id="duyet" name="Duyệt đơn" operaton:candidateGroups="nghi-phep.quan-ly">
      <bpmn:extensionElements>
        <operaton:formData>
          <operaton:formField id="ket_qua" label="Kết quả" type="enum">
            <operaton:validation>
              <operaton:constraint name="required" />
            </operaton:validation>
            <operaton:value id="dong_y" name="Đồng ý" />
            <operaton:value id="tu_choi" name="Từ chối" />
          </operaton:formField>
        </operaton:formData>
      </bpmn:extensionElements>
    </bpmn:userTask>
    <bpmn:sequenceFlow id="luong_2" sourceRef="duyet" targetRef="ghi_ket_qua" />
    <bpmn:serviceTask id="ghi_ket_qua" name="Ghi kết quả" operaton:type="external"
                      operaton:topic="saigonos-function">
      <bpmn:extensionElements>
        <operaton:properties>
          <operaton:property name="function" value="nghi_phep.ghi_ket_qua" />
        </operaton:properties>
      </bpmn:extensionElements>
    </bpmn:serviceTask>
    <bpmn:sequenceFlow id="luong_3" sourceRef="ghi_ket_qua" targetRef="ket_thuc" />
    <bpmn:endEvent id="ket_thuc" name="Đã xử lý" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="hinh_duyet">
    <bpmndi:BPMNPlane id="mat_phang_duyet" bpmnElement="nghi_phep.duyet">
      <bpmndi:BPMNShape id="gui_don_hinh" bpmnElement="gui_don">
        <dc:Bounds x="152" y="102" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="duyet_hinh" bpmnElement="duyet">
        <dc:Bounds x="240" y="80" width="100" height="80" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="ghi_ket_qua_hinh" bpmnElement="ghi_ket_qua">
        <dc:Bounds x="400" y="80" width="100" height="80" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="ket_thuc_hinh" bpmnElement="ket_thuc">
        <dc:Bounds x="562" y="102" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNEdge id="luong_1_hinh" bpmnElement="luong_1">
        <di:waypoint x="188" y="120" />
        <di:waypoint x="240" y="120" />
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="luong_2_hinh" bpmnElement="luong_2">
        <di:waypoint x="340" y="120" />
        <di:waypoint x="400" y="120" />
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="luong_3_hinh" bpmnElement="luong_3">
        <di:waypoint x="500" y="120" />
        <di:waypoint x="562" y="120" />
      </bpmndi:BPMNEdge>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>
```

File `database/0002_duyet.sql` thêm cột trạng thái và hàm ghi kết quả. Người gửi đơn chỉ ghi được cột `ly_do`, nên không tự duyệt được đơn của mình. Người có realm role `nghi-phep.quan-ly` xem được mọi đơn. Hàm chỉ cập nhật đơn của người đã bắt đầu quy trình:

```sql
ALTER TABLE don ADD COLUMN trang_thai text NOT NULL DEFAULT 'cho_duyet'
    CHECK (trang_thai IN ('cho_duyet', 'dong_y', 'tu_choi'));
REVOKE INSERT ON don FROM nghi_phep_user;
GRANT INSERT (ly_do) ON don TO nghi_phep_user;
CREATE POLICY quan_ly_xem ON don FOR SELECT
    USING ((SELECT core.has_role('nghi-phep.quan-ly')));

CREATE FUNCTION ghi_ket_qua(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
    UPDATE nghi_phep.don SET trang_thai = bien ->> 'ket_qua'
    WHERE id = (bien ->> 'ma_don')::bigint AND nguoi_gui = bien ->> 'initiator';
    RETURN jsonb_build_object('da_ghi', FOUND);
END
$$;
GRANT EXECUTE ON FUNCTION ghi_ket_qua(jsonb) TO workflow;
```

## Form

Form khai báo các giá trị mà người dùng nhập khi bắt đầu quy trình hoặc khi hoàn thành việc. Form bắt đầu nằm trong thẻ `startEvent` của quy trình. Form của việc nằm trong thẻ `userTask`. Mỗi trường của form là một thẻ `operaton:formField` trong phần `operaton:formData`. Thuộc tính `id` là tên biến của trường, `label` là tên hiển thị và `type` là kiểu của trường. Form viết với tiền tố `camunda:` của Camunda 7 cũng được đọc như Operaton đọc.

Ví dụ sau khai báo trường `ket_qua` của một việc. Trường này bắt buộc nhập và phải có ít nhất 10 ký tự:

```xml
<bpmn:userTask id="xu_ly" name="Xử lý yêu cầu" operaton:candidateGroups="nhan-vien">
  <bpmn:extensionElements>
    <operaton:formData>
      <operaton:formField id="ket_qua" label="Kết quả" type="string">
        <operaton:validation>
          <operaton:constraint name="required" />
          <operaton:constraint name="minlength" config="10" />
        </operaton:validation>
      </operaton:formField>
    </operaton:formData>
  </bpmn:extensionElements>
</bpmn:userTask>
```

Service `core` chỉ nhận các trường được khai báo trong form. Lời gọi gửi biến không có trong form nhận mã 422. Nhờ đó, người dùng không ghi đè được các biến khác của quy trình. Ví dụ, form của việc không khai báo trường `noi_dung` thì người hoàn thành việc không sửa được biến `noi_dung`. Quy trình hoặc việc không có form chỉ nhận nội dung không có biến nào.

Thuộc tính `id` của trường bắt đầu bằng chữ cái không dấu hoặc dấu gạch dưới. Các ký tự tiếp theo là chữ cái không dấu, chữ số hoặc dấu gạch dưới. Tên dài tối đa 64 ký tự. Kiểu của trường quy định giá trị được nhận:

| Kiểu | Giá trị trong JSON | Kiểu biến trong Operaton |
|---|---|---|
| `string` | Chuỗi tối đa 4.000 ký tự | `String` |
| `long` | Số nguyên từ -2^63 tới 2^63 - 1 | `Long` |
| `boolean` | `true` hoặc `false` | `Boolean` |
| `date` | Chuỗi ngày giờ theo ISO 8601 có múi giờ, ví dụ `2026-11-20T09:00:00+07:00` | `Date`, lưu theo giờ UTC |
| `enum` | Chuỗi bằng thuộc tính `id` của một thẻ `operaton:value` trong trường | `String` |

Trường không bắt buộc nhận thêm giá trị `null`. Các ràng buộc của trường nằm trong phần `operaton:validation`:

| Ràng buộc | Ý nghĩa |
|---|---|
| `required` | Bắt buộc nhập. Giá trị `null`, chuỗi rỗng và chuỗi chỉ có khoảng trắng được coi là chưa nhập |
| `minlength` | Số ký tự tối thiểu của chuỗi, không tính khoảng trắng ở đầu và cuối |
| `maxlength` | Số ký tự tối đa của chuỗi |
| `min`, `max` | Giá trị nhỏ nhất và lớn nhất của trường kiểu `long` |
| `readonly` | Trường chỉ để xem. Service `core` không nhận giá trị của trường này |

Service `core` kiểm tra form trước khi gửi các giá trị tới Operaton. Khi một giá trị không đạt, lời gọi nhận mã 422 với nội dung bắt đầu bằng `LỖI TUÂN THỦ`. Nội dung lỗi nêu tên hiển thị và tên biến của từng trường không đạt. Khi đó, quy trình chưa được bắt đầu, hoặc việc vẫn thuộc người nhận và quy trình không đi tiếp. Ví dụ, lời gọi hoàn thành việc `xu_ly` ở trên mà thiếu trường `ket_qua` nhận nội dung sau:

```json
{"detail": "LỖI TUÂN THỦ: Phải nhập Kết quả (ket_qua)"}
```

## Bắt đầu quy trình

Lời gọi `POST /core/processes/{key}/start` bắt đầu phiên bản mới nhất của quy trình có mã `key`. Mã quy trình là thuộc tính `id` của thẻ `process`. Lời gọi cần access token của người dùng đã đăng nhập.

Người gọi phải có một realm role nằm trong thuộc tính `operaton:candidateStarterGroups` của thẻ `process`. Giá trị của thuộc tính là danh sách tên realm role, cách nhau bởi dấu phẩy, không dùng biểu thức `${...}`. Quy trình không có thuộc tính này thì không ai bắt đầu được qua API. File BPMN viết cho Camunda 7 với tiền tố `camunda:` cũng được đọc như Operaton đọc.

Nội dung của lời gọi chứa giá trị của các trường trong form bắt đầu, đặt trong trường `variables`. Quy tắc của form được trình bày ở mục [Form](#form).

Service `core` ghi mã người gọi, tức claim `sub` của access token, vào biến `initiator`. Khi điểm bắt đầu của quy trình có thuộc tính `operaton:initiator`, biến mang tên ghi trong thuộc tính này cũng nhận mã người gọi. Người gọi không gửi được các biến này, kể cả khi form khai báo trường cùng tên.

Ví dụ, một ứng dụng web bắt đầu quy trình `yeu_cau` như sau:

```js
const reply = await fetch("/core/processes/yeu_cau/start", {
  method: "POST",
  headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
  body: JSON.stringify({ variables: { noi_dung: "Máy 12 không lên màn hình" } }),
});
const { id, version } = await reply.json();
```

Lời gọi trả về mã 201 kèm mã của quy trình vừa bắt đầu trong trường `id` và phiên bản của quy trình trong trường `version`.

Quy trình `yeu_cau` trong ví dụ được lưu trong file `yeu-cau.bpmn`. Người có realm role `nguoi-gui` bắt đầu được quy trình. Form bắt đầu có trường `noi_dung` bắt buộc nhập. Việc `xu_ly` chờ một người có realm role `nhan-vien` nhận. Form của việc này có trường `ket_qua` bắt buộc nhập và phải có ít nhất 10 ký tự:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:operaton="http://operaton.org/schema/1.0/bpmn"
                  id="yeu_cau_dinh_nghia" targetNamespace="https://dx.example.com/bpmn">
  <bpmn:process id="yeu_cau" name="Tiếp nhận yêu cầu" isExecutable="true"
                operaton:historyTimeToLive="P30D" operaton:candidateStarterGroups="nguoi-gui">
    <bpmn:startEvent id="bat_dau">
      <bpmn:extensionElements>
        <operaton:formData>
          <operaton:formField id="noi_dung" label="Nội dung" type="string">
            <operaton:validation>
              <operaton:constraint name="required" />
            </operaton:validation>
          </operaton:formField>
        </operaton:formData>
      </bpmn:extensionElements>
    </bpmn:startEvent>
    <bpmn:sequenceFlow id="luong_1" sourceRef="bat_dau" targetRef="xu_ly" />
    <bpmn:userTask id="xu_ly" name="Xử lý yêu cầu" operaton:candidateGroups="nhan-vien">
      <bpmn:extensionElements>
        <operaton:formData>
          <operaton:formField id="ket_qua" label="Kết quả" type="string">
            <operaton:validation>
              <operaton:constraint name="required" />
              <operaton:constraint name="minlength" config="10" />
            </operaton:validation>
          </operaton:formField>
        </operaton:formData>
      </bpmn:extensionElements>
    </bpmn:userTask>
    <bpmn:sequenceFlow id="luong_2" sourceRef="xu_ly" targetRef="ket_thuc" />
    <bpmn:endEvent id="ket_thuc" />
  </bpmn:process>
</bpmn:definitions>
```

## Danh sách việc

Lời gọi `GET /core/tasks` trả về các việc mà người gọi xử lý được. Danh sách gồm hai loại việc:

- Việc mà người gọi đã nhận.
- Việc chưa ai nhận và có nhóm ứng viên là một realm role của người gọi. Nhóm ứng viên được khai báo trong thuộc tính `operaton:candidateGroups` của thẻ `userTask`.

Việc mà người khác đã nhận không có trong danh sách. Các việc được xếp theo thời điểm tạo, việc cũ nhất đứng đầu. Tham số `limit` đặt số việc tối đa được trả về, mặc định là 50 và tối đa là 200. Tham số `offset` đặt số việc được bỏ qua ở đầu danh sách. Ví dụ, lời gọi `GET /core/tasks?offset=50&limit=50` trả về trang thứ hai.

Mỗi việc gồm các trường sau:

| Trường | Ý nghĩa |
|---|---|
| `id` | Mã của việc |
| `name`, `description` | Tên và mô tả của việc trong file BPMN |
| `assignee` | Mã người nhận việc. Giá trị `null` nghĩa là việc đang chờ nhận |
| `created`, `due` | Thời điểm tạo và hạn xử lý |
| `priority` | Độ ưu tiên |
| `task_key` | Mã của việc trong file BPMN, tức thuộc tính `id` của thẻ `userTask` |
| `process_instance_id` | Mã của quy trình chứa việc, bằng trường `id` khi bắt đầu quy trình |
| `process_definition_id` | Mã phiên bản của quy trình |
| `suspended` | Việc đang tạm ngưng |

## Nhận việc và hoàn thành việc

Lời gọi `POST /core/tasks/{id}/claim` nhận việc có mã `id` cho người gọi. Mã việc là trường `id` trong danh sách việc. Người gọi phải có một realm role nằm trong nhóm ứng viên của việc. Việc đã có người khác nhận thì không nhận được. Khi nhiều người cùng nhận một việc, chỉ một người nhận được. Những người còn lại nhận mã 409. Gọi lại lời gọi này với việc mà người gọi đã nhận thì không có gì thay đổi.

Lời gọi `POST /core/tasks/{id}/complete` hoàn thành việc mà người gọi đã nhận. Chỉ người nhận việc mới hoàn thành được việc. Nội dung của lời gọi chứa giá trị của các trường trong form của việc, đặt trong trường `variables`. Service `core` kiểm tra các giá trị theo mục [Form](#form) rồi gửi qua form của việc trong Operaton. Sau đó, quy trình đi tiếp sang bước sau. Người hoàn thành việc cũng không gửi được biến `initiator` và biến ghi trong thuộc tính `operaton:initiator`.

Cả hai lời gọi cần access token của người dùng đã đăng nhập. Khi thành công, lời gọi trả về mã 204 và không có nội dung.

Ví dụ, một ứng dụng web nhận và hoàn thành việc `task` lấy từ danh sách việc như sau:

```js
const headers = { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" };
await fetch(`/core/tasks/${task.id}/claim`, { method: "POST", headers });
await fetch(`/core/tasks/${task.id}/complete`, {
  method: "POST",
  headers,
  body: JSON.stringify({ variables: { ket_qua: "Đã thay cáp màn hình" } }),
});
```

Các mã lỗi của các lời gọi về quy trình và việc:

| Mã | Lời gọi | Ý nghĩa |
|---|---|---|
| 401 | Tất cả | Thiếu access token hoặc access token không hợp lệ |
| 403 | Bắt đầu quy trình | Người gọi không có realm role nằm trong `candidateStarterGroups`, hoặc quy trình không khai báo thuộc tính này |
| 403 | Nhận việc | Người gọi không có realm role nằm trong nhóm ứng viên của việc |
| 403 | Hoàn thành việc | Người gọi không phải là người nhận việc |
| 404 | Bắt đầu quy trình | Không có quy trình với mã này, hoặc quy trình nằm ngoài phạm vi của access token như mục [Quy trình của ứng dụng](#quy-trình-của-ứng-dụng) |
| 404 | Nhận việc, hoàn thành việc | Không có việc với mã này, ví dụ việc đã được hoàn thành, hoặc việc nằm ngoài phạm vi của access token |
| 409 | Bắt đầu quy trình | Quy trình đang tạm ngưng trong Cockpit |
| 409 | Nhận việc | Việc đã có người khác nhận |
| 409 | Nhận việc, hoàn thành việc | Việc đang tạm ngưng vì quy trình chứa việc bị tạm ngưng trong Cockpit |
| 422 | Bắt đầu quy trình, hoàn thành việc | Giá trị không theo form trong file BPMN, ví dụ thiếu trường bắt buộc hoặc gửi biến không có trong form |
| 422 | Tất cả | Nội dung hoặc tham số không hợp lệ, ví dụ người gọi gửi biến `initiator` |
| 502 | Tất cả | Operaton báo lỗi. Nội dung lỗi được ghi vào log của service `core` |
| 503 | Tất cả | Operaton chưa sẵn sàng hoặc đang từ chối tài khoản `core` |

## Bước máy làm

Bước máy làm là một service task trong file BPMN. Bước này gọi một hàm trong cơ sở dữ liệu `saigonos`. Service `core` lấy các bước này từ Operaton, gọi hàm rồi ghi kết quả của hàm thành biến của quy trình.

Để khai báo bước máy làm, thẻ `serviceTask` cần có thuộc tính `operaton:type="external"` và `operaton:topic="saigonos-function"`. Tên hàm nằm trong thuộc tính `function` của phần `operaton:properties`, có dạng `schema.ten_ham`. Tên chỉ gồm chữ thường không dấu, chữ số và dấu gạch dưới. Ví dụ, bước sau gọi hàm `ung_dung.ghi_ket_qua`:

```xml
<bpmn:serviceTask id="ghi_ket_qua" name="Ghi kết quả" operaton:type="external"
                  operaton:topic="saigonos-function">
  <bpmn:extensionElements>
    <operaton:properties>
      <operaton:property name="function" value="ung_dung.ghi_ket_qua" />
    </operaton:properties>
  </bpmn:extensionElements>
</bpmn:serviceTask>
```

Hàm nhận đúng một tham số kiểu `jsonb` và trả về kiểu `jsonb`. Tham số là một object chứa mọi biến của quy trình, ví dụ `{"ma_yeu_cau": "YC-01", "ket_qua": "Đã thay cáp màn hình"}`. Biến kiểu ngày giờ được truyền dưới dạng chuỗi theo giờ UTC, ví dụ `2026-11-20T02:00:00.000+0000`. Quy trình có biến thuộc kiểu khác chuỗi, số, ngày giờ, `true`, `false` và `null` thì bước máy làm không chạy được. Hàm trả về một object hoặc `null`. Mỗi khóa của object trở thành một biến của quy trình. Tên biến theo quy tắc của thuộc tính `id` ở mục [Form](#form). Giá trị là chuỗi tối đa 4.000 ký tự, số nguyên, số thực, `true`, `false` hoặc `null`. Hàm không ghi được biến `initiator` và biến ghi trong thuộc tính `operaton:initiator`.

Hàm phải được khai báo cho quy trình bằng lệnh `GRANT EXECUTE` cho role `workflow` của cơ sở dữ liệu. Quyền cấp cho `PUBLIC` không được tính. Hàm chạy với quyền của role `workflow`, nên role này cần quyền trên schema và các bảng mà hàm dùng. Hàm của ứng dụng chạy với quyền khác, như mục [Quy trình của ứng dụng](#quy-trình-của-ứng-dụng). Ví dụ, một schema do quản trị viên tạo khai báo hàm `ung_dung.ghi_ket_qua` bằng các lệnh SQL sau:

```sql
GRANT USAGE ON SCHEMA ung_dung TO workflow;
GRANT SELECT, UPDATE ON ung_dung.yeu_cau TO workflow;

CREATE FUNCTION ung_dung.ghi_ket_qua(bien jsonb) RETURNS jsonb
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE ung_dung.yeu_cau SET trang_thai = 'da_xu_ly', ket_qua = bien ->> 'ket_qua'
    WHERE ma = bien ->> 'ma_yeu_cau';
    RETURN jsonb_build_object('da_cap_nhat', FOUND);
END
$$;
GRANT EXECUTE ON FUNCTION ung_dung.ghi_ket_qua(jsonb) TO workflow;
```

Service `core` chạy bước máy làm theo các quy tắc sau:

- Hàm chạy trong một transaction và tối đa 20 giây. Audit log ghi role `workflow` trong cột `db_role`. Cột `actor` để trống vì bước này không có người gọi.
- Hàm được gọi qua một hàm `SECURITY DEFINER` của role `workflow`. Do đó, hàm không đổi được role của phiên làm việc, ví dụ bằng lệnh `RESET ROLE`.
- Mỗi bước máy làm chỉ chạy hàm một lần. Kết quả của hàm được ghi vào bảng `core.step_runs` trong cùng transaction với hàm. Khi service `core` dừng đột ngột sau khi hàm chạy xong, bước này được chạy tiếp sau tối đa 1 phút bằng kết quả đã ghi, không gọi lại hàm.
- Khi hàm báo lỗi, mọi thay đổi của hàm bị hủy. Service `core` thử lại sau 5 giây, 30 giây rồi 2 phút. Sau lần lỗi thứ tư, bước máy làm trở thành incident trong Cockpit.
- Khi hàm không tồn tại, chưa được khai báo, sai kiểu tham số hoặc kiểu trả về, hoặc kết quả không ghi được thành biến, bước máy làm trở thành incident ngay mà không thử lại.

Nội dung lỗi của incident nằm trong Cockpit, ở thẻ Incidents của quy trình. Bấm vào nội dung lỗi để xem chi tiết, gồm mã SQLSTATE và vị trí lỗi trong hàm. Sau khi sửa lỗi, bước máy làm được chạy lại bằng thao tác Increment Number of Retries của incident.

## Hẹn giờ

Hẹn giờ (timer) gắn trên biên của một việc cho phép quy trình rẽ sang nhánh khác khi việc quá hạn. Ví dụ sau chuyển việc `xu_ly` cho nhóm quản lý khi tới thời điểm ghi trong biến `han_xu_ly`:

```xml
<bpmn:userTask id="xu_ly" name="Xử lý yêu cầu" operaton:candidateGroups="nhan-vien"
               operaton:dueDate="${han_xu_ly}" />
<bpmn:boundaryEvent id="qua_han" name="Quá hạn" attachedToRef="xu_ly">
  <bpmn:timerEventDefinition>
    <bpmn:timeDate>${han_xu_ly}</bpmn:timeDate>
  </bpmn:timerEventDefinition>
</bpmn:boundaryEvent>
<bpmn:sequenceFlow id="luong_qua_han" sourceRef="qua_han" targetRef="xu_ly_qua_han" />
<bpmn:userTask id="xu_ly_qua_han" name="Xử lý yêu cầu quá hạn" operaton:candidateGroups="quan-ly" />
```

Thẻ `boundaryEvent` chứa hẹn giờ. Thuộc tính `attachedToRef` nêu việc được gắn hẹn giờ. Thuộc tính `operaton:dueDate` ghi hạn vào trường `due` của việc trong [Danh sách việc](#danh-sách-việc).

Biến `han_xu_ly` cần là một trường kiểu `date` bắt buộc nhập trong form bắt đầu. Khi quy trình thiếu biến này, Operaton báo lỗi và quy trình không được bắt đầu.

Khi tới hạn mà việc `xu_ly` chưa hoàn thành, Operaton hủy việc này, kể cả khi việc đã có người nhận. Lời gọi hoàn thành việc đã bị hủy nhận mã 404. Sau đó, quy trình tạo việc `xu_ly_qua_han` chờ một người có realm role `quan-ly` nhận. Khi việc `xu_ly` được hoàn thành trước hạn, hẹn giờ cũng bị hủy.

Job executor của Operaton tìm các hẹn giờ đã tới hạn 2 giây một lần. Do đó, hẹn giờ chạy chậm nhất khoảng 2 giây sau hạn. Việc tìm này thêm khoảng 120 câu lệnh mỗi phút vào cơ sở dữ liệu `operaton`.

Các hẹn giờ được lưu trong cơ sở dữ liệu `operaton`. Khi Operaton dừng rồi chạy lại, các hẹn giờ vẫn còn. Hẹn giờ tới hạn trong lúc Operaton dừng sẽ chạy ngay khi Operaton chạy lại.

Operaton chạy theo giờ UTC. Do đó, ngày giờ không ghi múi giờ và biểu thức cron trong file BPMN được tính theo giờ UTC. Ví dụ, `2026-12-01T08:00:00` là 15:00 giờ Việt Nam. Để đặt hẹn giờ theo giờ Việt Nam, ghi ngày giờ kèm múi giờ, ví dụ `2026-12-01T08:00:00+07:00`.
