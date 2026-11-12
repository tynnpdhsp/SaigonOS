-- SPDX-License-Identifier: Apache-2.0
local http = require("resty.http")

local admin_url = os.getenv("APISIX_ADMIN_URL")
local admin_key = os.getenv("APISIX_ADMIN_KEY")

local function fail(message)
    io.stderr:write(message, "\n")
    os.exit(1)
end

for _, path in ipairs(arg) do
    local name = path:match("([^/]+)%.json$")
    local file = assert(io.open(path, "rb"))
    local body = file:read("*a")
    file:close()

    local response, err = http.new():request_uri(admin_url .. "/apisix/admin/routes/" .. name, {
        method = "PUT",
        body = body,
        headers = {
            ["X-API-KEY"] = admin_key,
            ["Content-Type"] = "application/json",
        },
    })
    if not response then
        fail("Không kết nối được Admin API của APISIX: " .. err)
    end
    if response.status >= 300 then
        fail("Không nạp được route " .. name .. ": " .. response.body)
    end
    print("Đã nạp route " .. name)
end
