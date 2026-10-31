-- Invariant 5 and review item (c): every write to runs (and scenarios) is audited with its actor.
CREATE TRIGGER runs_audit AFTER INSERT OR UPDATE OR DELETE ON runs
  FOR EACH ROW EXECUTE FUNCTION ergplan_audit();
CREATE TRIGGER scenarios_audit AFTER INSERT OR UPDATE OR DELETE ON scenarios
  FOR EACH ROW EXECUTE FUNCTION ergplan_audit();
