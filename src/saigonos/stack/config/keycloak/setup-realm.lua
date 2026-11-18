-- SPDX-License-Identifier: Apache-2.0
local http = require("resty.http")
local cjson = require("cjson")

cjson.decode_array_with_array_mt(true)

local REALM = "saigonos"
local MASTER = "master"
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

local OPERATON = "operaton"
local OPERATON_FLOW = "saigonos operaton"
local NOT_ADMIN_FLOW = "saigonos operaton not admin"
local ADMIN_ONLY = "saigonos-operaton-admin-only"
local ADMIN_ONLY_TEXTS = {
    { locale = "vi", text = "Chỉ tài khoản quản trị mới vào được trang này." },
    { locale = "en", text = "Only administrator accounts can open this page." },
}
local OPERATON_STEPS = {
    { provider = "auth-username-password-form", requirement = "REQUIRED" },
    { flow = NOT_ADMIN_FLOW, requirement = "CONDITIONAL" },
    {
        parent = NOT_ADMIN_FLOW,
        provider = "conditional-user-role",
        requirement = "REQUIRED",
        config_alias = NOT_ADMIN_FLOW .. " role",
        config = { condUserRole = "admin", negate = "true" },
    },
    {
        parent = NOT_ADMIN_FLOW,
        provider = "deny-access-authenticator",
        requirement = "REQUIRED",
        config_alias = NOT_ADMIN_FLOW .. " message",
        config = { denyErrorMessage = ADMIN_ONLY },
    },
    { provider = "auth-otp-form", requirement = "REQUIRED" },
}
local GROUPS_MAPPER = {
    name = "groups",
    protocol = "openid-connect",
    protocolMapper = "oidc-usermodel-realm-role-mapper",
    config = {
        ["claim.name"] = "groups",
        ["multivalued"] = "true",
        ["jsonType.label"] = "String",
        ["access.token.claim"] = "false",
        ["id.token.claim"] = "true",
        ["userinfo.token.claim"] = "true",
        ["introspection.token.claim"] = "false",
    },
}

local keycloak_url = os.getenv("KEYCLOAK_URL")
local master_frontend_url = os.getenv("MASTER_FRONTEND_URL")
local saigonos_url = os.getenv("SAIGONOS_URL")
local operaton_secret = os.getenv("OPERATON_CLIENT_SECRET")
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
    local admin_path = "/admin/realms/" .. path
    local response = send(method, admin_path, data and cjson.encode(data))
    if response.status >= 300 then
        fail("Keycloak từ chối lời gọi " .. method .. " " .. admin_path .. ": " .. response.body)
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

local function secure_master()
    local master = call("GET", MASTER)
    local attributes = master.attributes or {}
    local changes = {}
    local messages = {}
    if attributes.frontendUrl ~= master_frontend_url then
        attributes.frontendUrl = master_frontend_url
        changes.attributes = attributes
        table.insert(messages, "Đã đặt Frontend URL của realm " .. MASTER .. " là " .. master_frontend_url)
    end
    if not master.bruteForceProtected then
        changes.bruteForceProtected = true
        table.insert(messages, "Đã bật chặn đăng nhập sai nhiều lần cho realm " .. MASTER)
    end
    if next(changes) == nil then
        print("Realm " .. MASTER .. " không cần thay đổi")
        return
    end
    call("PUT", MASTER, changes)
    for _, message in ipairs(messages) do
        print(message)
    end
    if changes.attributes then
        log_in()
    end
end

local function add_attribute()
    local profile = call("GET", REALM .. "/users/profile")
    if find(profile.attributes, ATTRIBUTE.name) then
        return false
    end
    table.insert(profile.attributes, ATTRIBUTE)
    call("PUT", REALM .. "/users/profile", profile)
    print("Đã thêm thuộc tính " .. ATTRIBUTE.name .. " vào user profile của realm " .. REALM)
    return true
end

local function add_mapper()
    local scope = find(call("GET", REALM .. "/client-scopes"), SCOPE)
    if not scope then
        fail("Realm " .. REALM .. " không có client scope " .. SCOPE)
    end
    if find(scope.protocolMappers, MAPPER.name) then
        return false
    end
    call("POST", REALM .. "/client-scopes/" .. scope.id .. "/protocol-mappers/models", MAPPER)
    print("Đã thêm mapper " .. MAPPER.name .. " vào client scope " .. SCOPE .. " của realm " .. REALM)
    return true
end

local function flow_path(alias)
    return REALM .. "/authentication/flows/" .. ngx.escape_uri(alias)
end

local function find_flow()
    for _, flow in ipairs(call("GET", REALM .. "/authentication/flows")) do
        if flow.alias == OPERATON_FLOW then
            return flow
        end
    end
end

local function step_matches(step, execution)
    local name = step.flow and execution.displayName or execution.providerId
    if
        execution.level ~= (step.parent and 1 or 0)
        or execution.requirement ~= step.requirement
        or (step.flow ~= nil) ~= (execution.authenticationFlow == true)
        or name ~= (step.flow or step.provider)
    then
        return false
    end
    if not step.config then
        return true
    end
    if not execution.authenticationConfig then
        return false
    end
    local config = call("GET", REALM .. "/authentication/config/" .. execution.authenticationConfig)
    for key, value in pairs(step.config) do
        if (config.config or {})[key] ~= value then
            return false
        end
    end
    return true
end

local function flow_matches()
    local executions = call("GET", flow_path(OPERATON_FLOW) .. "/executions")
    if #executions ~= #OPERATON_STEPS then
        return false
    end
    for index, step in ipairs(OPERATON_STEPS) do
        if not step_matches(step, executions[index]) then
            return false
        end
    end
    return true
end

local function build_flow()
    call("POST", REALM .. "/authentication/flows", {
        alias = OPERATON_FLOW,
        description = "Đăng nhập Operaton, chỉ dành cho vai trò admin và bắt buộc OTP",
        providerId = "basic-flow",
        topLevel = true,
        builtIn = false,
    })
    for _, step in ipairs(OPERATON_STEPS) do
        local parent = step.parent or OPERATON_FLOW
        if step.flow then
            call("POST", flow_path(parent) .. "/executions/flow", {
                alias = step.flow,
                description = "Từ chối người dùng không có vai trò admin",
                provider = "registration-page-form",
                type = "basic-flow",
            })
        else
            call("POST", flow_path(parent) .. "/executions/execution", { provider = step.provider })
        end
        local executions = call("GET", flow_path(parent) .. "/executions")
        local execution = executions[#executions]
        execution.requirement = step.requirement
        call("PUT", flow_path(parent) .. "/executions", execution)
        if step.config then
            call("POST", REALM .. "/authentication/executions/" .. execution.id .. "/config", {
                alias = step.config_alias,
                config = step.config,
            })
        end
    end
    local flow = find_flow()
    if not flow or not flow_matches() then
        fail("Không tạo được luồng đăng nhập " .. OPERATON_FLOW .. " của realm " .. REALM)
    end
    return flow.id
end

local function add_texts()
    local added = false
    for _, entry in ipairs(ADMIN_ONLY_TEXTS) do
        local path = REALM .. "/localization/" .. entry.locale
        if call("GET", path)[ADMIN_ONLY] == nil then
            local key_path = "/admin/realms/" .. path .. "/" .. ADMIN_ONLY
            local response = send("PUT", key_path, entry.text, "text/plain; charset=utf-8")
            if response.status >= 300 then
                fail("Keycloak từ chối việc thêm thông báo " .. ADMIN_ONLY .. ": " .. response.body)
            end
            print("Đã thêm thông báo " .. ADMIN_ONLY .. " (" .. entry.locale .. ") vào realm " .. REALM)
            added = true
        end
    end
    return added
end

local function find_client()
    local clients = call("GET", REALM .. "/clients?clientId=" .. OPERATON)
    return clients[1]
end

local function operaton_settings(flow_id)
    return {
        protocol = "openid-connect",
        publicClient = false,
        clientAuthenticatorType = "client-secret",
        secret = operaton_secret,
        standardFlowEnabled = true,
        implicitFlowEnabled = false,
        directAccessGrantsEnabled = false,
        serviceAccountsEnabled = false,
        rootUrl = saigonos_url .. "/operaton",
        baseUrl = "/app/",
        redirectUris = { saigonos_url .. "/operaton/login/oauth2/code/" .. OPERATON },
        webOrigins = setmetatable({}, cjson.array_mt),
        attributes = { ["pkce.code.challenge.method"] = "S256" },
        authenticationFlowBindingOverrides = { browser = flow_id },
    }
end

local function differs(current, wanted)
    if type(wanted) ~= "table" then
        return current ~= wanted
    end
    if type(current) ~= "table" then
        return true
    end
    if getmetatable(wanted) == cjson.array_mt or #wanted > 0 then
        return cjson.encode(current) ~= cjson.encode(wanted)
    end
    for key, value in pairs(wanted) do
        if differs(current[key], value) then
            return true
        end
    end
    return false
end

local function setup_operaton()
    local client = find_client()
    local changed = false
    local flow = find_flow()
    local flow_id = flow and flow.id
    if not flow or not flow_matches() then
        if client then
            call("PUT", REALM .. "/clients/" .. client.id, {
                enabled = false,
                authenticationFlowBindingOverrides = { browser = "" },
            })
        end
        if flow then
            call("DELETE", REALM .. "/authentication/flows/" .. flow.id)
            print("Luồng đăng nhập " .. OPERATON_FLOW .. " đã bị thay đổi nên được tạo lại")
        end
        flow_id = build_flow()
        print("Đã tạo luồng đăng nhập " .. OPERATON_FLOW .. " của realm " .. REALM)
        changed = true
    end

    local settings = operaton_settings(flow_id)
    if changed or not client then
        settings.enabled = true
    end
    if not client then
        settings.clientId = OPERATON
        settings.name = "Operaton"
        settings.description = "Cockpit, Tasklist và Admin của Operaton"
        settings.protocolMappers = { GROUPS_MAPPER }
        call("POST", REALM .. "/clients", settings)
        print("Đã tạo client " .. OPERATON .. " của realm " .. REALM)
        return true
    end

    client.secret = call("GET", REALM .. "/clients/" .. client.id .. "/client-secret").value
    if not changed then
        for key, value in pairs(settings) do
            if differs(client[key], value) then
                changed = true
                break
            end
        end
    end
    if changed then
        call("PUT", REALM .. "/clients/" .. client.id, settings)
        print("Đã cập nhật client " .. OPERATON .. " của realm " .. REALM)
    end
    if not find(client.protocolMappers, GROUPS_MAPPER.name) then
        call("POST", REALM .. "/clients/" .. client.id .. "/protocol-mappers/models", GROUPS_MAPPER)
        print("Đã thêm mapper " .. GROUPS_MAPPER.name .. " vào client " .. OPERATON)
        changed = true
    end
    return changed
end

log_in()
secure_master()
local attribute_added = add_attribute()
local mapper_added = add_mapper()
local texts_added = add_texts()
local operaton_changed = setup_operaton()
if not attribute_added and not mapper_added and not texts_added and not operaton_changed then
    print("Realm " .. REALM .. " không cần thay đổi")
end
