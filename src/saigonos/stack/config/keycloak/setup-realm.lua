-- SPDX-License-Identifier: Apache-2.0
local http = require("resty.http")
local cjson = require("cjson")

cjson.decode_array_with_array_mt(true)

local REALM = "saigonos"
local SCOPE = "roles"
local ATTRIBUTE = {
    name = "unit",
    displayName = "Đơn vị",
    permissions = { view = { "admin", "user" }, edit = { "admin" } },
    validations = { length = { max = 255 } },
    multivalued = false,
}
local MAPPER = {
    name = "unit",
    protocol = "openid-connect",
    protocolMapper = "oidc-usermodel-attribute-mapper",
    config = {
        ["user.attribute"] = "unit",
        ["claim.name"] = "unit",
        ["jsonType.label"] = "String",
        ["access.token.claim"] = "true",
        ["id.token.claim"] = "true",
        ["userinfo.token.claim"] = "true",
        ["introspection.token.claim"] = "true",
    },
}

local keycloak_url = os.getenv("KEYCLOAK_URL")
local admin_path = "/admin/realms/" .. REALM
local token

local function fail(message)
    io.stderr:write(message, "\n")
    os.exit(1)
end

local function send(method, path, body, content_type)
    local headers = { ["Content-Type"] = content_type or "application/json" }
    if token then
        headers["Authorization"] = "Bearer " .. token
    end
    local response, err = http.new():request_uri(keycloak_url .. path, {
        method = method,
        body = body,
        headers = headers,
    })
    if not response then
        fail("Không kết nối được Keycloak: " .. err)
    end
    return response
end

local function call(method, path, data)
    local response = send(method, admin_path .. path, data and cjson.encode(data))
    if response.status >= 300 then
        fail("Keycloak từ chối lời gọi " .. method .. " " .. admin_path .. path .. ": " .. response.body)
    end
    return response.body ~= "" and cjson.decode(response.body) or nil
end

local function find(items, name)
    for _, item in ipairs(items or {}) do
        if item.name == name then
            return item
        end
    end
end

local function log_in()
    local form = ngx.encode_args({
        grant_type = "password",
        client_id = "admin-cli",
        username = os.getenv("KEYCLOAK_ADMIN_USERNAME"),
        password = os.getenv("KEYCLOAK_ADMIN_PASSWORD"),
    })
    local path = "/realms/master/protocol/openid-connect/token"
    local response = send("POST", path, form, "application/x-www-form-urlencoded")
    if response.status ~= 200 then
        fail(
            "Không đăng nhập được realm master của Keycloak: "
                .. response.body
                .. "\nMật khẩu của tài khoản quản trị phải trùng giá trị KEYCLOAK_ADMIN_PASSWORD trong file .env."
        )
    end
    token = cjson.decode(response.body).access_token
end

local function add_attribute()
    local profile = call("GET", "/users/profile")
    if find(profile.attributes, ATTRIBUTE.name) then
        return false
    end
    table.insert(profile.attributes, ATTRIBUTE)
    call("PUT", "/users/profile", profile)
    print("Đã thêm thuộc tính " .. ATTRIBUTE.name .. " vào user profile của realm " .. REALM)
    return true
end

local function add_mapper()
    local scope = find(call("GET", "/client-scopes"), SCOPE)
    if not scope then
        fail("Realm " .. REALM .. " không có client scope " .. SCOPE)
    end
    if find(scope.protocolMappers, MAPPER.name) then
        return false
    end
    call("POST", "/client-scopes/" .. scope.id .. "/protocol-mappers/models", MAPPER)
    print("Đã thêm mapper " .. MAPPER.name .. " vào client scope " .. SCOPE .. " của realm " .. REALM)
    return true
end

log_in()
local attribute_added = add_attribute()
local mapper_added = add_mapper()
if not attribute_added and not mapper_added then
    print("Realm " .. REALM .. " không cần thay đổi")
end
