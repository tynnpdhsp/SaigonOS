-- SPDX-License-Identifier: Apache-2.0
CREATE TABLE phong (
    id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma text NOT NULL UNIQUE CHECK (ma ~ '^[A-Z0-9][A-Z0-9.-]{0,19}$'),
    ten text NOT NULL CHECK (ten = btrim(ten) AND length(ten) BETWEEN 1 AND 100),
    so_may integer NOT NULL CHECK (so_may BETWEEN 0 AND 500)
);
ALTER TABLE phong ENABLE ROW LEVEL SECURITY;
CREATE POLICY moi_nguoi_xem ON phong FOR SELECT USING (true);
CREATE POLICY phu_trach_sua ON phong FOR UPDATE
    USING ((SELECT core.has_role('phong-may.phu-trach')))
    WITH CHECK ((SELECT core.has_role('phong-may.phu-trach')));
CREATE TRIGGER audit AFTER INSERT OR UPDATE OR DELETE ON phong
    FOR EACH ROW EXECUTE FUNCTION core.audit();
GRANT SELECT, UPDATE (so_may) ON phong TO phong_may_user;

INSERT INTO phong (ma, ten, so_may) VALUES
    ('PM1', 'Phòng máy 1', 70),
    ('PM2', 'Phòng máy 2', 40),
    ('PM3', 'Phòng máy 3', 40),
    ('PM4', 'Phòng máy 4', 72);
