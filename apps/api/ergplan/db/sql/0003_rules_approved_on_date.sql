-- Invariant 2, tightened: the view itself applies the evaluation date, so no consumer of rules_approved
-- can see a rule outside its effective dates. The date comes from the session variable ergplan.on_date
-- (set by rulebook.repository) and defaults to today.
CREATE OR REPLACE VIEW rules_approved AS
  SELECT r.id, r.rulebook_version_id, r.family, r.position, r.label, r.scope, r.body, r.source_ref,
         r.field_refs, v.jurisdiction_id, v.version, v.effective_from, v.effective_to
  FROM rules r JOIN rulebook_versions v ON v.id = r.rulebook_version_id
  WHERE v.status = 'approved'
    AND v.effective_from <= coalesce(nullif(current_setting('ergplan.on_date', true), '')::date, current_date)
    AND (v.effective_to IS NULL
         OR v.effective_to >= coalesce(nullif(current_setting('ergplan.on_date', true), '')::date, current_date));
