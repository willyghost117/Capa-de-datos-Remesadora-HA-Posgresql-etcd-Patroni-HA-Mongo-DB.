-- ============================================================
-- GlobalRemit - Etapa 4
-- Auditoria PostgreSQL academica
-- Ejecutar como usuario administrador: postgres
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS security_audit;

CREATE TABLE IF NOT EXISTS security_audit.audit_event (
    audit_event_id bigserial PRIMARY KEY,
    event_time timestamptz NOT NULL DEFAULT now(),
    database_user text NOT NULL DEFAULT current_user,
    application_name text,
    client_addr inet,
    schema_name text NOT NULL,
    table_name text NOT NULL,
    operation text NOT NULL,
    row_pk text,
    old_data jsonb,
    new_data jsonb
);

CREATE OR REPLACE FUNCTION security_audit.fn_audit_row_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, security_audit
AS $$
DECLARE
    v_row_pk text;
    v_old jsonb;
    v_new jsonb;
    v_data jsonb;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        v_old := to_jsonb(OLD);
    END IF;

    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        v_new := to_jsonb(NEW);
    END IF;

    IF TG_OP = 'DELETE' THEN
        v_data := v_old;
    ELSE
        v_data := v_new;
    END IF;

    v_row_pk := COALESCE(
        v_data ->> 'remittance_id',
        v_data ->> 'party_id',
        v_data ->> 'party_document_id',
        v_data ->> 'payout_method_id',
        v_data ->> 'financial_movement_id',
        v_data ->> 'aml_alert_id',
        v_data ->> 'risk_assessment_id',
        v_data ->> 'travel_rule_record_id',
        v_data ->> 'settlement_batch_id',
        v_data ->> 'event_id'
    );

    INSERT INTO security_audit.audit_event (
        database_user,
        application_name,
        client_addr,
        schema_name,
        table_name,
        operation,
        row_pk,
        old_data,
        new_data
    )
    VALUES (
        session_user,
        current_setting('application_name', true),
        inet_client_addr(),
        TG_TABLE_SCHEMA,
        TG_TABLE_NAME,
        TG_OP,
        v_row_pk,
        CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) ELSE NULL END,
        CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) ELSE NULL END
    );

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_party ON customer.party;
CREATE TRIGGER trg_audit_party
AFTER INSERT OR UPDATE OR DELETE ON customer.party
FOR EACH ROW EXECUTE FUNCTION security_audit.fn_audit_row_change();

DROP TRIGGER IF EXISTS trg_audit_party_document ON customer.party_document;
CREATE TRIGGER trg_audit_party_document
AFTER INSERT OR UPDATE OR DELETE ON customer.party_document
FOR EACH ROW EXECUTE FUNCTION security_audit.fn_audit_row_change();

DROP TRIGGER IF EXISTS trg_audit_payout_method ON customer.beneficiary_payout_method;
CREATE TRIGGER trg_audit_payout_method
AFTER INSERT OR UPDATE OR DELETE ON customer.beneficiary_payout_method
FOR EACH ROW EXECUTE FUNCTION security_audit.fn_audit_row_change();

DROP TRIGGER IF EXISTS trg_audit_remittance_order ON remittance.remittance_order;
CREATE TRIGGER trg_audit_remittance_order
AFTER INSERT OR UPDATE OR DELETE ON remittance.remittance_order
FOR EACH ROW EXECUTE FUNCTION security_audit.fn_audit_row_change();

DROP TRIGGER IF EXISTS trg_audit_financial_detail ON remittance.remittance_financial_detail;
CREATE TRIGGER trg_audit_financial_detail
AFTER INSERT OR UPDATE OR DELETE ON remittance.remittance_financial_detail
FOR EACH ROW EXECUTE FUNCTION security_audit.fn_audit_row_change();

DROP TRIGGER IF EXISTS trg_audit_financial_movement ON remittance.remittance_financial_movement;
CREATE TRIGGER trg_audit_financial_movement
AFTER INSERT OR UPDATE OR DELETE ON remittance.remittance_financial_movement
FOR EACH ROW EXECUTE FUNCTION security_audit.fn_audit_row_change();

DROP TRIGGER IF EXISTS trg_audit_aml_alert ON compliance.aml_alert;
CREATE TRIGGER trg_audit_aml_alert
AFTER INSERT OR UPDATE OR DELETE ON compliance.aml_alert
FOR EACH ROW EXECUTE FUNCTION security_audit.fn_audit_row_change();

DROP TRIGGER IF EXISTS trg_audit_risk_assessment ON compliance.risk_assessment;
CREATE TRIGGER trg_audit_risk_assessment
AFTER INSERT OR UPDATE OR DELETE ON compliance.risk_assessment
FOR EACH ROW EXECUTE FUNCTION security_audit.fn_audit_row_change();

DROP TRIGGER IF EXISTS trg_audit_travel_rule ON compliance.travel_rule_record;
CREATE TRIGGER trg_audit_travel_rule
AFTER INSERT OR UPDATE OR DELETE ON compliance.travel_rule_record
FOR EACH ROW EXECUTE FUNCTION security_audit.fn_audit_row_change();

DROP TRIGGER IF EXISTS trg_audit_settlement_batch ON settlement.settlement_batch;
CREATE TRIGGER trg_audit_settlement_batch
AFTER INSERT OR UPDATE OR DELETE ON settlement.settlement_batch
FOR EACH ROW EXECUTE FUNCTION security_audit.fn_audit_row_change();

DROP TRIGGER IF EXISTS trg_audit_outbox_event ON integration.outbox_event;
CREATE TRIGGER trg_audit_outbox_event
AFTER INSERT OR UPDATE OR DELETE ON integration.outbox_event
FOR EACH ROW EXECUTE FUNCTION security_audit.fn_audit_row_change();

GRANT USAGE ON SCHEMA security_audit TO gr_auditor, gr_dba_admin;
GRANT SELECT ON security_audit.audit_event TO gr_auditor;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA security_audit TO gr_dba_admin;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA security_audit TO gr_dba_admin;

-- Expone solamente la confirmacion minima necesaria para la traza operativa.
CREATE OR REPLACE FUNCTION integration.fn_trace_audit_event(p_event_id uuid)
RETURNS TABLE (
    audited boolean,
    event_time timestamptz,
    database_user text
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, security_audit
AS $$
    SELECT count(*) > 0,
           max(ae.event_time),
           (array_agg(ae.database_user ORDER BY ae.event_time DESC))[1]
    FROM security_audit.audit_event ae
    WHERE ae.schema_name = 'integration'
      AND ae.table_name = 'outbox_event'
      AND ae.operation = 'INSERT'
      AND ae.row_pk = p_event_id::text;
$$;

REVOKE ALL ON FUNCTION integration.fn_trace_audit_event(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION integration.fn_trace_audit_event(uuid)
TO gr_app_writer, gr_auditor, gr_dba_admin;

COMMIT;


