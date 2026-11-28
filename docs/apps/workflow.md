<!-- SPDX-License-Identifier: Apache-2.0 -->
# Quy trình

Quy trình của ứng dụng là các file BPMN 2.0 trong thư mục `processes` của ứng dụng. Lệnh cài đặt triển khai các file này vào Operaton. Ứng dụng bắt đầu quy trình và xử lý việc qua API của service `core`, với access token của ứng dụng. Ví dụ trên trang này lấy từ quy trình đặt phòng của ứng dụng mẫu, gồm file [`processes/dat-phong.bpmn`](https://github.com/tynnpdhsp/SaigonOS/blob/main/examples/phong-may/processes/dat-phong.bpmn) và các hàm trong file [`database/0004_quy_trinh.sql`](https://github.com/tynnpdhsp/SaigonOS/blob/main/examples/phong-may/database/0004_quy_trinh.sql).

## File BPMN của ứng dụng

File BPMN của ứng dụng tuân theo các quy tắc sau:

- Mã quy trình, tức thuộc tính `id` của thẻ `process`, có dạng `<schema>.<tên quy trình>`, ví dụ `phong_may.dat_phong`. Tên quy trình gồm chữ thường không dấu, chữ số và dấu gạch dưới. Mỗi quy trình chỉ được khai báo trong một file.
- Mỗi quy trình có thuộc tính `operaton:historyTimeToLive`, tức thời gian giữ lịch sử, ví dụ `P180D` là 180 ngày.
- Thuộc tính `operaton:candidateStarterGroups` của quy trình và `operaton:candidateGroups` của việc chỉ gồm role của ứng dụng, cách nhau bằng dấu phẩy, không dùng expression.
- Bước máy làm chỉ gọi hàm trong schema của ứng dụng. Call activity chỉ gọi quy trình trong các file BPMN của chính ứng dụng.
- File không chứa mã chạy bên trong Operaton. Script task, business rule task, send task, listener, class Java, delegate expression, connector và ràng buộc `validator` của form đều bị từ chối.
- Expression chỉ gồm tên biến, giá trị, phép so sánh và phép logic, ví dụ `${so_may > 30 && !hop_le}`. Expression gọi hàm như `${now()}` hoặc đọc thuộc tính như `${don.so_may}` bị từ chối.
- Tên file gồm chữ cái không dấu, chữ số, dấu chấm, dấu gạch ngang, dấu gạch dưới và kết thúc bằng `.bpmn`.

File chỉ dùng được các thẻ sau:

- Sự kiện bắt đầu, kết thúc, sự kiện trung gian và sự kiện biên. Sự kiện dùng được hẹn giờ, error, escalation, terminate, link và conditional.
- Việc của người dùng (`userTask`), bước máy làm, `task`, `manualTask`, call activity và subprocess.
- Các gateway, luồng (`sequenceFlow`) và multi-instance.
- Lane, pool, chú thích và phần hình vẽ.

Message và signal chưa được hỗ trợ. File thiếu phần hình vẽ (BPMNDI) vẫn được cài đặt, nhưng lệnh kiểm tra in cảnh báo vì Cockpit không vẽ được quy trình.

Mỗi file là một bản triển khai riêng trong tenant của Operaton trùng tên ứng dụng. File không thay đổi thì không tạo phiên bản mới. File đã sửa tạo một phiên bản mới, còn các quy trình đang chạy vẫn dùng phiên bản cũ. Service `core` lọc quy trình và việc theo client của access token, tức claim `azp`. Access token của một ứng dụng chỉ thấy, bắt đầu, nhận và hoàn thành quy trình của ứng dụng đó. Quy trình và việc của ứng dụng khác nhận mã 404.

## Form

Form khai báo các giá trị mà người dùng nhập khi bắt đầu quy trình hoặc khi hoàn thành việc. Form bắt đầu nằm trong thẻ `startEvent`, form của việc nằm trong thẻ `userTask`. Mỗi trường là một thẻ `operaton:formField`. Thuộc tính `id` là tên biến, `label` là tên hiển thị và `type` là kiểu của trường. Ví dụ, việc duyệt đơn trong file `processes/dat-phong.bpmn` có trường `ket_qua` bắt buộc chọn và trường `y_kien` dài tối đa 1000 ký tự:

```xml
<bpmn:userTask id="duyet" name="Duyệt đơn" operaton:candidateGroups="phong-may.phu-trach"
               operaton:dueDate="${han_duyet}">
  <bpmn:documentation>Đơn đặt phòng số ${ma_don}</bpmn:documentation>
  <bpmn:extensionElements>
    <operaton:formData>
      <operaton:formField id="ket_qua" label="Kết quả" type="enum">
        <operaton:validation>
          <operaton:constraint name="required" />
        </operaton:validation>
        <operaton:value id="dong_y" name="Đồng ý" />
        <operaton:value id="tu_choi" name="Từ chối" />
      </operaton:formField>
      <operaton:formField id="y_kien" label="Ý kiến" type="string">
        <operaton:validation>
          <operaton:constraint name="maxlength" config="1000" />
        </operaton:validation>
      </operaton:formField>
    </operaton:formData>
  </bpmn:extensionElements>
</bpmn:userTask>
```

Service `core` chỉ nhận các trường được khai báo trong form. Lời gọi gửi biến không có trong form nhận mã 422. Do đó, người dùng không ghi đè được các biến khác của quy trình. Quy trình hoặc việc không có form chỉ nhận nội dung không có biến nào.

Tên biến bắt đầu bằng chữ cái không dấu hoặc dấu gạch dưới. Các ký tự tiếp theo là chữ cái không dấu, chữ số hoặc dấu gạch dưới. Tên dài tối đa 64 ký tự. Kiểu của trường quy định giá trị được nhận:

| Kiểu | Giá trị trong JSON | Kiểu biến trong Operaton |
|---|---|---|
| `string` | Chuỗi tối đa 4.000 ký tự | `String` |
| `long` | Số nguyên từ -2^63 tới 2^63 - 1 | `Long` |
| `boolean` | `true` hoặc `false` | `Boolean` |
| `date` | Chuỗi ngày giờ theo ISO 8601 có múi giờ, ví dụ `2026-12-01T07:00:00+07:00` | `Date`, lưu theo giờ UTC |
| `enum` | Chuỗi bằng thuộc tính `id` của một thẻ `operaton:value` trong trường | `String` |

Trường không bắt buộc nhận thêm giá trị `null`. Các ràng buộc của trường nằm trong phần `operaton:validation`:

| Ràng buộc | Ý nghĩa |
|---|---|
| `required` | Bắt buộc nhập. Giá trị `null`, chuỗi rỗng và chuỗi chỉ có khoảng trắng được coi là chưa nhập |
| `minlength` | Số ký tự tối thiểu của chuỗi, không tính khoảng trắng ở đầu và cuối |
| `maxlength` | Số ký tự tối đa của chuỗi |
| `min`, `max` | Giá trị nhỏ nhất và lớn nhất của trường kiểu `long` |
| `readonly` | Trường chỉ để xem. Service `core` không nhận giá trị của trường này |

Service `core` kiểm tra form trước khi gửi các giá trị tới Operaton. Khi một giá trị không đạt, lời gọi nhận mã 422 với nội dung bắt đầu bằng `LỖI TUÂN THỦ`, kèm tên hiển thị và tên biến của từng trường không đạt. Khi đó, quy trình chưa được bắt đầu, hoặc việc vẫn thuộc người nhận. Ví dụ, lời gọi hoàn thành việc duyệt đơn mà thiếu trường `ket_qua` nhận nội dung sau:

```json
{"detail": "LỖI TUÂN THỦ: Phải nhập Kết quả (ket_qua)"}
```

## Bắt đầu quy trình

Lời gọi `POST /core/processes/{key}/start` bắt đầu phiên bản mới nhất của quy trình có mã `key`. Người gọi phải có một realm role nằm trong thuộc tính `operaton:candidateStarterGroups` của quy trình. Quy trình không có thuộc tính này thì không ai bắt đầu được qua API. Nội dung của lời gọi chứa giá trị của các trường trong form bắt đầu, đặt trong trường `variables`. Ví dụ, giáo viên gửi đơn đặt phòng với nội dung sau:

```json
{
  "variables": {
    "ma_phong": "PM1",
    "bat_dau": "2026-12-01T07:00:00+07:00",
    "ket_thuc": "2026-12-01T09:00:00+07:00",
    "so_may": 30,
    "lop": "Lập trình cơ bản",
    "muc_dich": "day_hoc",
    "phan_mem": "Visual Studio Code"
  }
}
```

Với `body` là nội dung trên, một trang web gửi lời gọi như sau:

```js
const reply = await fetch("/core/processes/phong_may.dat_phong/start", {
  method: "POST",
  headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
  body: JSON.stringify(body),
});
const { id, version } = await reply.json();
```

Lời gọi trả về mã 201 kèm mã của quy trình vừa bắt đầu trong trường `id` và phiên bản của quy trình trong trường `version`. Service `core` ghi mã người gọi, tức claim `sub` của access token, vào biến `initiator`. Khi điểm bắt đầu có thuộc tính `operaton:initiator`, biến mang tên ghi trong thuộc tính này cũng nhận mã người gọi. Người gọi không gửi được các biến này.

## Danh sách việc

Lời gọi `GET /core/tasks` trả về các việc mà người gọi xử lý được, gồm việc người gọi đã nhận và việc chưa ai nhận có nhóm ứng viên là một realm role của người gọi. Nhóm ứng viên được khai báo trong thuộc tính `operaton:candidateGroups` của việc. Các việc được xếp theo thời điểm tạo, việc cũ nhất đứng đầu. Tham số `limit` đặt số việc tối đa được trả về, mặc định là 50 và tối đa là 200. Tham số `offset` đặt số việc được bỏ qua ở đầu danh sách. Mỗi việc gồm các trường sau:

| Trường | Ý nghĩa |
|---|---|
| `id` | Mã của việc |
| `name`, `description` | Tên của việc và nội dung thẻ `documentation` của việc trong file BPMN |
| `assignee` | Mã người nhận việc. Giá trị `null` nghĩa là việc đang chờ nhận |
| `created`, `due` | Thời điểm tạo và hạn xử lý |
| `priority` | Độ ưu tiên |
| `task_key` | Mã của việc trong file BPMN, tức thuộc tính `id` của thẻ `userTask` |
| `process_instance_id` | Mã của quy trình chứa việc, bằng trường `id` khi bắt đầu quy trình |
| `process_definition_id` | Mã phiên bản của quy trình |
| `suspended` | Việc đang tạm ngưng |

Ứng dụng mẫu ghi `Đơn đặt phòng số ${ma_don}` vào thẻ `documentation` của mỗi việc. Nhờ đó, giao diện biết mỗi việc thuộc đơn nào qua trường `description`.

## Nhận việc và hoàn thành việc

Lời gọi `POST /core/tasks/{id}/claim` nhận việc cho người gọi. Người gọi phải có một realm role nằm trong nhóm ứng viên của việc. Khi nhiều người cùng nhận một việc, chỉ một người nhận được, những người còn lại nhận mã 409.

Lời gọi `POST /core/tasks/{id}/complete` hoàn thành việc mà người gọi đã nhận. Nội dung của lời gọi chứa giá trị của các trường trong form của việc, đặt trong trường `variables`. Sau đó, quy trình đi tiếp sang bước sau. Ví dụ, phụ trách phòng đồng ý một đơn đặt phòng với nội dung sau:

```json
{"variables": {"ket_qua": "dong_y", "y_kien": "Phòng đã cài sẵn Visual Studio Code"}}
```

Với `task` là một việc trong danh sách việc và `body` là nội dung trên, một trang web nhận và hoàn thành việc như sau:

```js
const headers = { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" };
await fetch(`/core/tasks/${task.id}/claim`, { method: "POST", headers });
await fetch(`/core/tasks/${task.id}/complete`, { method: "POST", headers, body: JSON.stringify(body) });
```

Khi thành công, hai lời gọi trả về mã 204 và không có nội dung. Các mã lỗi của các lời gọi về quy trình và việc:

| Mã | Lời gọi | Ý nghĩa |
|---|---|---|
| 401 | Tất cả | Thiếu access token hoặc access token không hợp lệ |
| 403 | Bắt đầu quy trình | Người gọi không có realm role nằm trong `candidateStarterGroups`, hoặc quy trình không khai báo thuộc tính này |
| 403 | Nhận việc | Người gọi không có realm role nằm trong nhóm ứng viên của việc |
| 403 | Hoàn thành việc | Người gọi không phải là người nhận việc |
| 404 | Tất cả | Không có quy trình hoặc việc với mã này, ví dụ việc đã được hoàn thành, hoặc quy trình và việc thuộc ứng dụng khác |
| 409 | Bắt đầu quy trình | Quy trình đang tạm ngưng trong Cockpit |
| 409 | Nhận việc | Việc đã có người khác nhận |
| 409 | Nhận việc, hoàn thành việc | Việc đang tạm ngưng vì quy trình chứa việc bị tạm ngưng trong Cockpit |
| 422 | Bắt đầu quy trình, hoàn thành việc | Giá trị không theo form trong file BPMN, ví dụ thiếu trường bắt buộc hoặc gửi biến không có trong form |
| 422 | Tất cả | Nội dung hoặc tham số không hợp lệ, ví dụ người gọi gửi biến `initiator` |
| 502 | Tất cả | Operaton báo lỗi. Nội dung lỗi được ghi vào log của service `core` |
| 503 | Tất cả | Operaton chưa sẵn sàng hoặc đang từ chối tài khoản `core` |

## Bước máy làm

Bước máy làm là một service task gọi một hàm trong schema của ứng dụng. Service `core` lấy các bước này từ Operaton, gọi hàm rồi ghi kết quả của hàm thành biến của quy trình. Thẻ `serviceTask` có thuộc tính `operaton:type="external"` và `operaton:topic="saigonos-function"`. Tên hàm nằm trong thuộc tính `function`, có dạng `<schema>.<tên hàm>`. Ví dụ, bước kiểm tra và ghi đơn trong file `processes/dat-phong.bpmn`:

```xml
<bpmn:serviceTask id="ghi_don" name="Kiểm tra và ghi đơn" operaton:type="external"
                  operaton:topic="saigonos-function">
  <bpmn:extensionElements>
    <operaton:properties>
      <operaton:property name="function" value="phong_may.ghi_don" />
    </operaton:properties>
  </bpmn:extensionElements>
</bpmn:serviceTask>
```

Hàm nhận đúng một tham số kiểu `jsonb` và trả về kiểu `jsonb`. Tham số là một object chứa mọi biến của quy trình. Biến kiểu ngày giờ được truyền dưới dạng chuỗi theo giờ UTC, ví dụ `2026-12-01T00:00:00.000+0000`. Hàm trả về một object hoặc `null`. Mỗi khóa của object trở thành một biến của quy trình, với tên theo quy tắc ở mục [Form](#form). Giá trị là chuỗi tối đa 4.000 ký tự, số, `true`, `false` hoặc `null`. Ví dụ, hàm `ghi_don` trong file `database/0004_quy_trinh.sql` trả về ba biến mà các bước sau của quy trình dùng:

```sql
RETURN jsonb_build_object(
    'hop_le', true,
    'ma_don', ban_ghi.id,
    'han_duyet', to_char(ban_ghi.han_duyet AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
);
```

Hàm phải được cấp cho role `workflow` bằng lệnh `GRANT EXECUTE`. Quyền cấp cho `PUBLIC` không được tính. Hàm chỉ cấp cho role `workflow` thì người dùng không gọi được qua API của ứng dụng. Bước máy làm không có người gọi, nên `core.uid()` trả về `NULL` và biến `initiator` cho biết người đã bắt đầu quy trình. Do đó, hàm cập nhật bảng có chính sách Row-Level Security (RLS) thường khai `SECURITY DEFINER`, như các hàm của ứng dụng mẫu.

Service `core` chạy bước máy làm theo các quy tắc sau:

- Hàm chạy trong một transaction và tối đa 20 giây.
- Mỗi bước chỉ chạy hàm một lần, kể cả khi service `core` dừng đột ngột sau khi hàm chạy xong.
- Khi hàm báo lỗi, mọi thay đổi của hàm bị hủy. Service `core` thử lại sau 5 giây, 30 giây rồi 2 phút. Sau lần lỗi thứ tư, bước trở thành incident trong Cockpit.
- Khi hàm không tồn tại, chưa được cấp cho role `workflow`, sai kiểu tham số hoặc kiểu trả về, bước trở thành incident ngay mà không thử lại.

Nội dung lỗi của incident nằm ở thẻ Incidents của quy trình trong Cockpit, gồm mã SQLSTATE và vị trí lỗi trong hàm. Sau khi sửa lỗi, bước được chạy lại bằng thao tác Increment Number of Retries của incident.

## Hẹn giờ

Hẹn giờ gắn trên biên của một việc cho phép quy trình rẽ sang một nhánh khác khi tới hạn. Ví dụ, quy trình đặt phòng nhắc phụ trách phòng khi đơn tới hạn duyệt mà chưa được duyệt. Hẹn giờ trong file `processes/dat-phong.bpmn` như sau:

```xml
<bpmn:boundaryEvent id="qua_han" name="Quá hạn duyệt" attachedToRef="duyet"
                    cancelActivity="false">
  <bpmn:timerEventDefinition id="qua_han_hen_gio">
    <bpmn:timeDate>${han_duyet}</bpmn:timeDate>
  </bpmn:timerEventDefinition>
</bpmn:boundaryEvent>
```

Thuộc tính `attachedToRef` nêu việc được gắn hẹn giờ. Biến `han_duyet` do hàm `ghi_don` trả về. Thuộc tính `operaton:dueDate` của việc `duyet` cũng lấy biến này, nên hạn được ghi vào trường `due` của việc. Với `cancelActivity="false"`, việc duyệt vẫn còn sau khi hẹn giờ chạy. Khi không có thuộc tính này, Operaton hủy việc lúc tới hạn, kể cả khi việc đã có người nhận. Lời gọi hoàn thành việc đã bị hủy nhận mã 404.

Job executor của Operaton tìm các hẹn giờ đã tới hạn 2 giây một lần. Hẹn giờ được lưu trong cơ sở dữ liệu, nên vẫn chạy sau khi Operaton khởi động lại. Operaton chạy theo giờ UTC. Do đó, ngày giờ không ghi múi giờ và biểu thức cron được tính theo giờ UTC. Ví dụ, `2026-12-01T08:00:00` là 15:00 giờ Việt Nam. Để đặt hẹn giờ theo giờ Việt Nam, ghi ngày giờ kèm múi giờ, ví dụ `2026-12-01T08:00:00+07:00`.
