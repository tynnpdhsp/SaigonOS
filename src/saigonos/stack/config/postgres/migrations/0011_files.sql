-- SPDX-License-Identifier: Apache-2.0
CREATE TABLE core.files (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner text NOT NULL DEFAULT core.uid() CHECK (owner <> ''),
    name text NOT NULL CHECK (name <> ''),
    type text NOT NULL CHECK (type <> ''),
    size bigint NOT NULL CHECK (size > 0),
    sha256 text CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    status text NOT NULL DEFAULT 'pending_upload',
    created_at timestamptz NOT NULL DEFAULT now(),
    uploaded_at timestamptz,
    CONSTRAINT files_status_check CHECK (status IN ('pending_upload', 'pending_scan')),
    CONSTRAINT files_upload_check CHECK (
        (status = 'pending_upload') = (sha256 IS NULL)
        AND (status = 'pending_upload') = (uploaded_at IS NULL)
    )
);

CREATE TRIGGER audit AFTER INSERT OR UPDATE OR DELETE ON core.files
    FOR EACH ROW EXECUTE FUNCTION core.audit();

ALTER TABLE core.files ENABLE ROW LEVEL SECURITY;
CREATE POLICY owner_reads ON core.files FOR SELECT TO authenticated
    USING (owner = core.uid());
CREATE POLICY core_service_writes ON core.files TO core_service
    USING (true) WITH CHECK (true);

GRANT USAGE ON SCHEMA core TO core_service;
GRANT SELECT ON core.files TO authenticated;
GRANT SELECT, INSERT, UPDATE ON core.files TO core_service;
