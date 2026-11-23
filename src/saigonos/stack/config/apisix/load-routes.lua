-- SPDX-License-Identifier: Apache-2.0
local http = require("resty.http")

local admin_url = os.getenv("APISIX_ADMIN_URL")
local admin_key = os.getenv("APISIX_ADMIN_KEY")
local engines = {block = "On", detect = "DetectionOnly"}
local resources = {
    routes = {path = "routes", label = "route"},
    ["global-rules"] = {path = "global_rules", label = "global rule"},
}

local function fail(message)
    io.stderr:write(message, "\n")
    os.exit(1)
end

local mode = os.getenv("SAIGONOS_WAF_MODE") or ""
if not engines[mode] then
    fail("Giá trị SAIGONOS_WAF_MODE không hợp lệ: '" .. mode .. "'. Chỉ dùng block hoặc detect.")
end
local values = {SAIGONOS_WAF_MODE = mode, SAIGONOS_WAF_ENGINE = engines[mode]}

for _, path in ipairs(arg) do
    local folder, name = path:match("([^/]+)/([^/]+)%.json$")
    local resource = resources[folder] or resources.routes
    local file = assert(io.open(path, "rb"))
    local body = file:read("*a"):gsub("%${(SAIGONOS_WAF_[A-Z]+)}", values)
    file:close()

    local response, err = http.new():request_uri(
        admin_url .. "/apisix/admin/" .. resource.path .. "/" .. name,
        {
            method = "PUT",
            body = body,
            headers = {
                ["X-API-KEY"] = admin_key,
                ["Content-Type"] = "application/json",
            },
        }
    )
    if not response then
        fail("Không kết nối được Admin API của APISIX: " .. err)
    end
    if response.status >= 300 then
        fail("Không nạp được " .. resource.label .. " " .. name .. ": " .. response.body)
    end
    print("Đã nạp " .. resource.label .. " " .. name)
end
