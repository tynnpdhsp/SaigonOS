#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
set -eu

for bucket in $(echo "$S3_BUCKET" | tr ',' ' '); do
    printf 'user = "%s:%s"\n' "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY" |
        curl --silent --fail --head --config - --aws-sigv4 aws:amz:us-east-1:s3 \
            --output /dev/null "http://127.0.0.1:8333/$bucket"
done
