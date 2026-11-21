-- SPDX-License-Identifier: Apache-2.0
local dns_client = require("apisix.core.dns.client")
local new = dns_client.new

-- Mặc định lỗi name error được giữ 30 giây, nên service vừa chạy lại vẫn nhận 503
dns_client.new = function(opts)
    if opts.emptyTtl == nil then
        opts.emptyTtl = 1
    end
    return new(opts)
end
