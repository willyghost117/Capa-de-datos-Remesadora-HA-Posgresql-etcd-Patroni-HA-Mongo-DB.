-- ============================================================
-- GlobalRemit - Etapa 4
-- RBAC PostgreSQL para ambiente academico
-- Ejecutar como usuario administrador: postgres
-- ============================================================

BEGIN;

CREATE ROLE gr_app_writer NOLOGIN;
CREATE ROLE gr_ops_readonly NOLOGIN;
CREATE ROLE gr_compliance_officer NOLOGIN;
CREATE ROLE gr_risk_analyst NOLOGIN;
CREATE ROLE gr_finance_settlement NOLOGIN;
CREATE ROLE gr_data_analyst NOLOGIN;
CREATE ROLE gr_auditor NOLOGIN;
CREATE ROLE gr_dba_admin NOLOGIN;

GRANT USAGE ON SCHEMA reference, customer, fx, remittance, compliance, settlement, integration TO gr_dba_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA reference, customer, fx, remittance, compliance, settlement, integration TO gr_dba_admin;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA reference, customer, fx, remittance, compliance, settlement, integration TO gr_dba_admin;

GRANT USAGE ON SCHEMA reference, customer, fx, remittance, compliance, settlement, integration TO gr_app_writer;
GRANT SELECT ON ALL TABLES IN SCHEMA reference TO gr_app_writer;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA fx, remittance, compliance, integration TO gr_app_writer;
GRANT SELECT ON ALL TABLES IN SCHEMA customer, settlement TO gr_app_writer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA fx, remittance, compliance, integration TO gr_app_writer;

GRANT USAGE ON SCHEMA reference, customer, fx, remittance, settlement TO gr_ops_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA reference, fx, remittance, settlement TO gr_ops_readonly;

GRANT USAGE ON SCHEMA reference, customer, remittance, compliance TO gr_compliance_officer;
GRANT SELECT ON ALL TABLES IN SCHEMA reference, customer, remittance TO gr_compliance_officer;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA compliance TO gr_compliance_officer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA compliance TO gr_compliance_officer;

GRANT USAGE ON SCHEMA reference, fx, remittance, compliance TO gr_risk_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA reference, fx, remittance, compliance TO gr_risk_analyst;

GRANT USAGE ON SCHEMA reference, fx, remittance, settlement TO gr_finance_settlement;
GRANT SELECT ON ALL TABLES IN SCHEMA reference, fx, remittance TO gr_finance_settlement;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA settlement TO gr_finance_settlement;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA settlement TO gr_finance_settlement;

GRANT USAGE ON SCHEMA reference, fx, remittance TO gr_data_analyst;
GRANT SELECT ON ALL TABLES IN SCHEMA reference, fx TO gr_data_analyst;

GRANT USAGE ON SCHEMA reference, customer, fx, remittance, compliance, settlement, integration TO gr_auditor;
GRANT SELECT ON ALL TABLES IN SCHEMA reference, customer, fx, remittance, compliance, settlement, integration TO gr_auditor;

-- Usuarios de ejemplo para laboratorio. En produccion las claves deben venir de un vault.
CREATE ROLE gr_api_gateway LOGIN PASSWORD 'ChangeMe_ApiGateway_2026!' IN ROLE gr_app_writer;
CREATE ROLE gr_ops_user LOGIN PASSWORD 'ChangeMe_Ops_2026!' IN ROLE gr_ops_readonly;
CREATE ROLE gr_compliance_user LOGIN PASSWORD 'ChangeMe_Compliance_2026!' IN ROLE gr_compliance_officer;
CREATE ROLE gr_risk_user LOGIN PASSWORD 'ChangeMe_Risk_2026!' IN ROLE gr_risk_analyst;
CREATE ROLE gr_finance_user LOGIN PASSWORD 'ChangeMe_Finance_2026!' IN ROLE gr_finance_settlement;
CREATE ROLE gr_analyst_user LOGIN PASSWORD 'ChangeMe_Analyst_2026!' IN ROLE gr_data_analyst;
CREATE ROLE gr_auditor_user LOGIN PASSWORD 'ChangeMe_Auditor_2026!' IN ROLE gr_auditor;

COMMIT;

