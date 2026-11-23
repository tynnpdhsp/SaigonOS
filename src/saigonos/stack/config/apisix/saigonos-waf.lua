-- SPDX-License-Identifier: Apache-2.0
local core = require("apisix.core")
local ngx = ngx

local LIMIT = 1048576
local MESSAGES = {
    [400] = "Nội dung của lời gọi không đúng định dạng nên tường lửa ứng dụng web không kiểm tra được.",
    [403] = "Tường lửa ứng dụng web đã chặn lời gọi này vì có dấu hiệu tấn công.",
    [413] = "Nội dung của lời gọi lớn hơn 1 MB nên tường lửa ứng dụng web không kiểm tra được.",
}

local schema = {
    type = "object",
    properties = {
        mode = {type = "string", enum = {"block", "detect"}},
    },
    required = {"mode"},
}

local _M = {
    version = 0.1,
    priority = 8000,
    name = "saigonos-waf",
    schema = schema,
}

function _M.check_schema(conf)
    return core.schema.check(schema, conf)
end

function _M.rewrite(conf, ctx)
    ctx.saigonos_waf = true
    local length = tonumber(ngx.var.http_content_length)
    if length and length > LIMIT then
        core.log.warn("Tường lửa ứng dụng web không kiểm tra nội dung ", length, " byte của ",
            ngx.var.request_method, " ", ngx.var.uri)
        if conf.mode == "block" then
            return 413
        end
        return
    end
    ngx.var.wasm_process_req_body = "on"
end

function _M.header_filter(conf, ctx)
    local message = ctx.saigonos_waf and not ctx.plugins and MESSAGES[ngx.status]
    if not message then
        return
    end
    ctx.saigonos_waf_reply = '{"code":"SGN04","details":null,"hint":null,"message":'
        .. core.json.encode(message) .. "}"
    core.response.set_header("Content-Type", "application/json; charset=utf-8")
    core.response.set_header("X-SaigonOS-Denied-By", "waf")
    core.response.clear_header_as_body_modified()
    core.log.warn("Tường lửa ứng dụng web trả mã ", ngx.status, " cho ", ngx.var.request_method,
        " ", ngx.var.uri, " từ ", ngx.var.remote_addr)
end

function _M.body_filter(conf, ctx)
    local reply = ctx.saigonos_waf_reply
    if reply then
        ngx.arg[1] = reply
        ctx.saigonos_waf_reply = ""
    end
end

return _M
