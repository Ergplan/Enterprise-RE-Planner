-- Invariants 2 and 3, enforced in the database so no code path can skip them.

-- Every write to an audited table names its actor and is appended to audit_log.
CREATE OR REPLACE FUNCTION ergplan_audit() RETURNS trigger AS $$
DECLARE
  actor text := nullif(current_setting('ergplan.actor', true), '');
  rid text;
BEGIN
  IF actor IS NULL THEN
    RAISE EXCEPTION 'write to % refused: no ergplan.actor set (invariant 3)', TG_TABLE_NAME
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  rid := CASE WHEN TG_OP = 'DELETE' THEN OLD.id::text ELSE NEW.id::text END;
  INSERT INTO audit_log(table_name, row_id, action, actor, at, before, after)
  VALUES (TG_TABLE_NAME, rid, TG_OP, actor, now(),
          CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN to_jsonb(OLD) END,
          CASE WHEN TG_OP IN ('INSERT','UPDATE') THEN to_jsonb(NEW) END);
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER rules_audit AFTER INSERT OR UPDATE OR DELETE ON rules
  FOR EACH ROW EXECUTE FUNCTION ergplan_audit();
CREATE TRIGGER rulebook_versions_audit AFTER INSERT OR UPDATE OR DELETE ON rulebook_versions
  FOR EACH ROW EXECUTE FUNCTION ergplan_audit();
CREATE TRIGGER rule_tests_audit AFTER INSERT OR UPDATE OR DELETE ON rule_tests
  FOR EACH ROW EXECUTE FUNCTION ergplan_audit();

-- Rows of a version that is no longer a draft are frozen.
CREATE OR REPLACE FUNCTION ergplan_rules_frozen() RETURNS trigger AS $$
DECLARE
  vid text := CASE WHEN TG_OP = 'DELETE' THEN OLD.rulebook_version_id ELSE NEW.rulebook_version_id END;
  st text;
BEGIN
  SELECT status INTO st FROM rulebook_versions WHERE id = vid;
  IF st IS DISTINCT FROM 'draft' THEN
    RAISE EXCEPTION 'rules of a % version cannot change; duplicate it into a draft', coalesce(st, 'missing')
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER rules_frozen BEFORE INSERT OR UPDATE OR DELETE ON rules
  FOR EACH ROW EXECUTE FUNCTION ergplan_rules_frozen();

-- Approval: only an analyst, only with every golden test of the family and jurisdiction run
-- against this version and passed (at least one test must exist).
CREATE OR REPLACE FUNCTION ergplan_version_gate() RETURNS trigger AS $$
DECLARE
  role text := nullif(current_setting('ergplan.role', true), '');
  n_tests int; n_passed int;
BEGIN
  IF NEW.status = 'approved' AND OLD.status IS DISTINCT FROM 'approved' THEN
    IF OLD.status <> 'draft' THEN
      RAISE EXCEPTION 'only a draft can be approved (was %)', OLD.status USING ERRCODE = 'check_violation';
    END IF;
    IF role IS DISTINCT FROM 'analyst' THEN
      RAISE EXCEPTION 'approval needs role analyst (invariant 3)' USING ERRCODE = 'insufficient_privilege';
    END IF;
    SELECT count(*) INTO n_tests FROM rule_tests t
      WHERE t.jurisdiction_id = NEW.jurisdiction_id AND t.family = NEW.family;
    SELECT count(DISTINCT r.test_id) INTO n_passed FROM rule_test_runs r
      JOIN rule_tests t ON t.id = r.test_id
      WHERE r.rulebook_version_id = NEW.id AND t.jurisdiction_id = NEW.jurisdiction_id AND t.family = NEW.family
        AND r.passed AND NOT EXISTS (
          SELECT 1 FROM rule_test_runs r2 WHERE r2.rulebook_version_id = NEW.id AND r2.test_id = r.test_id
            AND r2.ran_at > r.ran_at);
    IF n_tests = 0 OR n_passed < n_tests THEN
      RAISE EXCEPTION 'approval refused: % of % golden tests passed on this version', n_passed, n_tests
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  IF OLD.status IN ('superseded', 'rejected') AND NEW.status <> OLD.status THEN
    RAISE EXCEPTION 'a % version is final', OLD.status USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER rulebook_versions_gate BEFORE UPDATE ON rulebook_versions
  FOR EACH ROW EXECUTE FUNCTION ergplan_version_gate();

-- What the engines read (invariant 2): approved rows only.
CREATE VIEW rules_approved AS
  SELECT r.id, r.rulebook_version_id, r.family, r.position, r.label, r.scope, r.body, r.source_ref,
         r.field_refs, v.jurisdiction_id, v.version, v.effective_from, v.effective_to
  FROM rules r JOIN rulebook_versions v ON v.id = r.rulebook_version_id
  WHERE v.status = 'approved';
