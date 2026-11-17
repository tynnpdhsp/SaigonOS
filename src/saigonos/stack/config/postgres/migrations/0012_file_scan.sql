-- SPDX-License-Identifier: Apache-2.0
ALTER TABLE core.files
    ADD COLUMN malware text CHECK (malware <> ''),
    ADD COLUMN scanned_at timestamptz,
    DROP CONSTRAINT files_status_check,
    ADD CONSTRAINT files_status_check
        CHECK (status IN ('pending_upload', 'pending_scan', 'clean', 'infected')),
    ADD CONSTRAINT files_scan_check CHECK (
        (status IN ('clean', 'infected')) = (scanned_at IS NOT NULL)
        AND (status = 'infected') = (malware IS NOT NULL)
    );

CREATE INDEX files_pending_scan ON core.files (uploaded_at, id) WHERE status = 'pending_scan';
