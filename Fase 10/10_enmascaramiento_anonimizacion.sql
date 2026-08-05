-- ============================================================
-- GlobalRemit - Etapa 4
-- Vistas de enmascaramiento y anonimizacion
-- Ejecutar como usuario administrador: postgres
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS security_masked;

CREATE OR REPLACE VIEW security_masked.customer_profile_masked AS
SELECT
    cp.customer_id,
    cp.customer_code,
    CONCAT(LEFT(p.legal_name, 1), '*** ', cp.customer_id) AS legal_name_masked,
    p.party_type,
    p.party_status,
    cp.customer_status,
    cp.created_at
FROM customer.customer_profile cp
JOIN customer.party p
  ON p.party_id = cp.party_id;

CREATE OR REPLACE VIEW security_masked.party_contact_masked AS
SELECT
    pc.party_contact_id,
    pc.party_id,
    pc.contact_type,
    CASE
        WHEN pc.contact_type = 'EMAIL' AND position('@' in pc.contact_value) > 1
            THEN CONCAT('***@', split_part(pc.contact_value, '@', 2))
        WHEN pc.contact_type IN ('PHONE', 'MOBILE') AND length(pc.contact_value) >= 4
            THEN CONCAT('***', right(pc.contact_value, 4))
        ELSE '***'
    END AS contact_value_masked,
    pc.is_verified,
    pc.is_primary,
    pc.created_at
FROM customer.party_contact pc;

CREATE OR REPLACE VIEW security_masked.remittance_order_masked AS
SELECT
    ro.remittance_id,
    ro.remittance_code,
    ro.customer_id,
    ro.beneficiary_id,
    rc.corridor_code,
    rs.status_code AS current_status,
    sendcur.iso_currency_code AS send_currency,
    ROUND(fd.send_amount, 2) AS send_amount,
    payoutcur.iso_currency_code AS payout_currency,
    ROUND(fd.payout_amount, 2) AS payout_amount,
    ROUND(fd.total_charged_amount, 2) AS total_charged_amount,
    ro.created_at,
    ro.authorized_at,
    ro.paid_at,
    ro.completed_at
FROM remittance.remittance_order ro
JOIN fx.remittance_corridor rc
  ON rc.corridor_id = ro.corridor_id
JOIN reference.remittance_status rs
  ON rs.remittance_status_id = ro.current_status_id
JOIN remittance.remittance_financial_detail fd
  ON fd.remittance_id = ro.remittance_id
JOIN reference.currency sendcur
  ON sendcur.currency_id = fd.send_currency_id
JOIN reference.currency payoutcur
  ON payoutcur.currency_id = fd.payout_currency_id;

CREATE OR REPLACE VIEW security_masked.compliance_case_masked AS
SELECT
    aa.aml_alert_id,
    aa.alert_type,
    aa.severity,
    aa.alert_status,
    aa.decision,
    aa.assigned_to,
    aa.created_at,
    aa.resolved_at,
    ar.remittance_id,
    ras.risk_level,
    ras.decision AS risk_decision
FROM compliance.aml_alert aa
JOIN compliance.aml_screening_remittance ar
  ON ar.aml_screening_id = aa.aml_screening_id
LEFT JOIN compliance.risk_assessment ras
  ON ras.remittance_id = ar.remittance_id;

GRANT USAGE ON SCHEMA security_masked TO gr_ops_readonly, gr_risk_analyst, gr_data_analyst, gr_auditor;
GRANT SELECT ON ALL TABLES IN SCHEMA security_masked TO gr_ops_readonly, gr_risk_analyst, gr_data_analyst, gr_auditor;

COMMIT;

