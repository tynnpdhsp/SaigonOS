-- SPDX-License-Identifier: Apache-2.0
local http = require("resty.http")
local cjson = require("cjson.safe")
local random = require("resty.random")
local hex = require("resty.string").to_hex

local SOURCE = "saigonos"
local VALID_NAME = "^[%w][%w._-]*%.bpmn$"

io.stdout:setvbuf("line")

local api_url = os.getenv("OPERATON_URL")
local authorization = "Basic " .. ngx.encode_base64("core:" .. os.getenv("CORE_OPERATON_PASSWORD"))

local function fail(message)
    io.stderr:write(message, "\n")
    os.exit(1)
end

local function request(method, path, body, content_type)
    local headers = { Authorization = authorization, Accept = "application/json" }
    if content_type then
        headers["Content-Type"] = content_type
    end
    local response, err = http.new():request_uri(api_url .. path, {
        method = method,
        body = body,
        headers = headers,
    })
    if not response then
        fail("Không kết nối được REST API của Operaton: " .. err)
    end
    return response
end

local function message_of(response)
    local data = cjson.decode(response.body)
    return type(data) == "table" and data.message or response.body
end

local function read(path)
    local file, err = io.open(path, "rb")
    if not file then
        fail("Không đọc được file " .. path .. ": " .. err)
    end
    local content = file:read("*a")
    file:close()
    return content
end

local function multipart(fields, name, content)
    local boundary = "saigonos-" .. hex(random.bytes(16))
    local parts = {}
    for _, field in ipairs(fields) do
        table.insert(parts, "--" .. boundary .. "\r\n")
        table.insert(parts, 'Content-Disposition: form-data; name="' .. field[1] .. '"\r\n\r\n')
        table.insert(parts, field[2] .. "\r\n")
    end
    table.insert(parts, "--" .. boundary .. "\r\n")
    table.insert(parts, 'Content-Disposition: form-data; name="data"; filename="' .. name .. '"\r\n')
    table.insert(parts, "Content-Type: application/octet-stream\r\n\r\n")
    table.insert(parts, content .. "\r\n--" .. boundary .. "--\r\n")
    return table.concat(parts), "multipart/form-data; boundary=" .. boundary
end

local function definitions_of(deployment)
    if type(deployment.deployedProcessDefinitions) == "table" then
        local definitions = {}
        for _, definition in pairs(deployment.deployedProcessDefinitions) do
            table.insert(definitions, definition)
        end
        return definitions, true
    end
    local response = request("GET", "/process-definition?deploymentId=" .. deployment.id)
    if response.status ~= 200 then
        fail("Không đọc được quy trình của bản triển khai " .. deployment.id .. ": " .. message_of(response))
    end
    return cjson.decode(response.body), false
end

local function deploy(file)
    local body, content_type = multipart({
        { "deployment-name", file.name },
        { "deployment-source", SOURCE },
        { "enable-duplicate-filtering", "true" },
        { "deploy-changed-only", "true" },
    }, file.name, read(file.path))
    local response = request("POST", "/deployment/create", body, content_type)
    if response.status ~= 200 then
        fail("Không triển khai được file " .. file.name .. ": " .. message_of(response))
    end
    local deployment = cjson.decode(response.body)
    local definitions, created = definitions_of(deployment)
    table.sort(definitions, function(a, b)
        return a.key < b.key
    end)
    if created then
        for _, definition in ipairs(definitions) do
            print(
                "Đã triển khai file "
                    .. file.name
                    .. ": quy trình "
                    .. definition.key
                    .. ", phiên bản "
                    .. definition.version
            )
        end
    else
        print("File " .. file.name .. " không thay đổi")
    end
    return { id = deployment.id, created = created, definitions = definitions }
end

local function find_conflicts(files, deployments)
    local owners, keys = {}, {}
    for _, file in ipairs(files) do
        for _, definition in ipairs(deployments[file.name].definitions) do
            if not owners[definition.key] then
                owners[definition.key] = {}
                table.insert(keys, definition.key)
            end
            table.insert(owners[definition.key], file.name)
        end
    end
    table.sort(keys)
    local conflicts = {}
    for _, key in ipairs(keys) do
        if #owners[key] > 1 then
            table.insert(conflicts, { key = key, files = owners[key] })
        end
    end
    return conflicts
end

local function undo(conflicts, deployments)
    for _, conflict in ipairs(conflicts) do
        for _, name in ipairs(conflict.files) do
            local deployment = deployments[name]
            if deployment.created and not deployment.undone then
                local response = request("DELETE", "/deployment/" .. deployment.id)
                if response.status ~= 204 then
                    fail("Không gỡ được bản triển khai mới của file " .. name .. ": " .. message_of(response))
                end
                deployment.undone = true
                print("Đã gỡ bản triển khai mới của file " .. name)
            end
        end
    end
    for _, conflict in ipairs(conflicts) do
        io.stderr:write(
            "Quy trình "
                .. conflict.key
                .. " được khai báo trong nhiều file: "
                .. table.concat(conflict.files, ", ")
                .. ". Mỗi quy trình chỉ được khai báo trong một file.\n"
        )
    end
    os.exit(1)
end

local files = {}
for _, path in ipairs(arg) do
    local name = path:match("([^/]+)$")
    if not name:find("*", 1, true) then
        if not name:match(VALID_NAME) then
            fail(
                "Tên file "
                    .. name
                    .. " không hợp lệ. Tên file chỉ gồm chữ cái không dấu, chữ số, "
                    .. "dấu chấm, dấu gạch ngang, dấu gạch dưới và kết thúc bằng .bpmn."
            )
        end
        table.insert(files, { path = path, name = name })
    end
end
if #files == 0 then
    print("Không có file BPMN nào")
    os.exit(0)
end

local version = request("GET", "/version")
if version.status == 401 then
    fail(
        "Operaton từ chối tài khoản core. Hãy kiểm tra giá trị CORE_OPERATON_PASSWORD trong file .env. "
            .. "Sau mỗi lần đăng nhập sai, Operaton tạm khóa tài khoản này."
    )
end
if version.status ~= 200 then
    fail("REST API của Operaton trả về mã " .. version.status .. ": " .. message_of(version))
end

local deployments = {}
for _, file in ipairs(files) do
    deployments[file.name] = deploy(file)
end
local conflicts = find_conflicts(files, deployments)
if #conflicts > 0 then
    undo(conflicts, deployments)
end
