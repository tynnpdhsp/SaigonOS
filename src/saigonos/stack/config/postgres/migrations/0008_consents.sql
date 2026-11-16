-- SPDX-License-Identifier: Apache-2.0
CREATE TABLE core.consents (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subject text NOT NULL DEFAULT core.uid() CHECK (subject <> ''),
    policy text NOT NULL CHECK (policy <> ''),
    policy_version text NOT NULL CHECK (policy_version <> ''),
    given_at timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON core.consents
    FOR EACH STATEMENT EXECUTE FUNCTION core.append_only();
ALTER TABLE core.consents ENABLE ALWAYS TRIGGER append_only;

CREATE TRIGGER audit AFTER INSERT OR UPDATE OR DELETE ON core.consents
    FOR EACH ROW EXECUTE FUNCTION core.audit();
