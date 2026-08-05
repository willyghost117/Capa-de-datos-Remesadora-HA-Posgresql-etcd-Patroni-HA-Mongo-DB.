-- ============================================================
-- GlobalRemit - Fase 6
-- PostgreSQL base catalog data
-- Execute after 06_sql_ddl.sql
-- ============================================================

BEGIN;

INSERT INTO reference.country (iso_alpha2_code, country_name, default_timezone)
VALUES
    ('GT', 'Guatemala', 'America/Guatemala'),
    ('US', 'United States', 'America/New_York'),
    ('MX', 'Mexico', 'America/Mexico_City'),
    ('SV', 'El Salvador', 'America/El_Salvador'),
    ('HN', 'Honduras', 'America/Tegucigalpa');

INSERT INTO reference.currency (iso_currency_code, currency_name, numeric_code, minor_unit)
VALUES
    ('GTQ', 'Guatemalan Quetzal', '320', 2),
    ('USD', 'US Dollar', '840', 2),
    ('MXN', 'Mexican Peso', '484', 2),
    ('HNL', 'Honduran Lempira', '340', 2);

INSERT INTO reference.country_currency (country_id, currency_id, valid_from, is_primary)
SELECT c.country_id, cu.currency_id, DATE '2000-01-01', true
FROM (VALUES
    ('GT', 'GTQ'), ('US', 'USD'), ('MX', 'MXN'), ('SV', 'USD'), ('HN', 'HNL')
) AS x(country_code, currency_code)
JOIN reference.country c ON c.iso_alpha2_code = x.country_code
JOIN reference.currency cu ON cu.iso_currency_code = x.currency_code;

INSERT INTO reference.transaction_channel
    (channel_code, channel_name, requires_ip_address)
VALUES
    ('WEB', 'Web', true),
    ('MOBILE', 'Mobile', true),
    ('AGENT', 'Agent or branch', false),
    ('API', 'Partner API', true);

INSERT INTO reference.remittance_status
    (status_code, status_name, is_final, allows_financial_movement)
VALUES
    ('DRAFT', 'Draft', false, false),
    ('QUOTED', 'Quoted', false, false),
    ('PENDING_COMPLIANCE', 'Pending compliance', false, false),
    ('UNDER_REVIEW', 'Under review', false, false),
    ('AUTHORIZED', 'Authorized', false, true),
    ('FUNDED', 'Funded', false, true),
    ('SENT_TO_PARTNER', 'Sent to partner', false, true),
    ('AVAILABLE_FOR_PAYOUT', 'Available for payout', false, true),
    ('PAID', 'Paid', false, true),
    ('SETTLED', 'Settled', true, true),
    ('REJECTED', 'Rejected', true, false),
    ('CANCELLED', 'Cancelled', true, false),
    ('EXPIRED', 'Expired', true, false),
    ('REVERSED', 'Reversed', true, true);

INSERT INTO reference.financial_movement_type
    (movement_type_code, movement_type_name, movement_direction, is_reversible)
VALUES
    ('CUSTOMER_CHARGE', 'Customer charge', 'INFLOW', true),
    ('FEE_REVENUE', 'Fee revenue', 'INFORMATIONAL', true),
    ('TAX_WITHHELD', 'Tax withheld', 'INFORMATIONAL', true),
    ('FX_SPREAD_REVENUE', 'FX spread revenue', 'INFORMATIONAL', true),
    ('PAYOUT_OBLIGATION', 'Payout obligation', 'INFORMATIONAL', true),
    ('PARTNER_PAYOUT', 'Partner payout', 'OUTFLOW', true),
    ('SETTLEMENT_TO_PARTNER', 'Settlement to partner', 'OUTFLOW', true),
    ('CUSTOMER_REFUND', 'Customer refund', 'OUTFLOW', false),
    ('REVERSAL', 'Movement reversal', 'INFORMATIONAL', false);

INSERT INTO customer.document_type_catalog
    (document_type_code, document_type_name, applies_to_party_type)
VALUES
    ('NATIONAL_ID', 'National identification', 'INDIVIDUAL'),
    ('PASSPORT', 'Passport', 'INDIVIDUAL'),
    ('TAX_ID', 'Tax identification', 'ORGANIZATION'),
    ('BUSINESS_REGISTRATION', 'Business registration', 'ORGANIZATION');

INSERT INTO compliance.source_of_funds_catalog (source_code, source_name)
VALUES
    ('SALARY', 'Salary'),
    ('BUSINESS_INCOME', 'Business income'),
    ('SAVINGS', 'Savings'),
    ('FAMILY_SUPPORT', 'Family support'),
    ('OTHER', 'Other documented source');

INSERT INTO remittance.purpose_catalog (purpose_code, purpose_name)
VALUES
    ('FAMILY_SUPPORT', 'Family support'),
    ('EDUCATION', 'Education'),
    ('MEDICAL', 'Medical expenses'),
    ('SERVICES', 'Payment for services'),
    ('SAVINGS', 'Personal savings'),
    ('OTHER', 'Other declared purpose');

INSERT INTO remittance.status_reason_catalog (reason_code, reason_name)
VALUES
    ('INITIAL_CREATION', 'Initial remittance creation'),
    ('COMPLIANCE_APPROVED', 'Compliance controls approved'),
    ('COMPLIANCE_REJECTED', 'Compliance controls rejected'),
    ('CUSTOMER_CANCELLED', 'Cancelled by customer'),
    ('QUOTE_EXPIRED', 'Quote expired'),
    ('FUNDS_RECEIVED', 'Customer funds received'),
    ('PARTNER_ACCEPTED', 'Partner accepted operation'),
    ('PAYOUT_CONFIRMED', 'Payout confirmed'),
    ('SETTLEMENT_CONFIRMED', 'Settlement confirmed'),
    ('REVERSAL_APPROVED', 'Exceptional reversal approved');

WITH transitions(from_code, to_code, requires_reason) AS (
    VALUES
        ('DRAFT', 'QUOTED', false),
        ('DRAFT', 'CANCELLED', true),
        ('QUOTED', 'PENDING_COMPLIANCE', false),
        ('QUOTED', 'EXPIRED', true),
        ('QUOTED', 'CANCELLED', true),
        ('PENDING_COMPLIANCE', 'UNDER_REVIEW', false),
        ('PENDING_COMPLIANCE', 'AUTHORIZED', false),
        ('PENDING_COMPLIANCE', 'REJECTED', true),
        ('UNDER_REVIEW', 'AUTHORIZED', true),
        ('UNDER_REVIEW', 'REJECTED', true),
        ('UNDER_REVIEW', 'CANCELLED', true),
        ('AUTHORIZED', 'FUNDED', false),
        ('AUTHORIZED', 'CANCELLED', true),
        ('FUNDED', 'SENT_TO_PARTNER', false),
        ('FUNDED', 'CANCELLED', true),
        ('FUNDED', 'REVERSED', true),
        ('SENT_TO_PARTNER', 'AVAILABLE_FOR_PAYOUT', false),
        ('SENT_TO_PARTNER', 'PAID', false),
        ('SENT_TO_PARTNER', 'REJECTED', true),
        ('SENT_TO_PARTNER', 'REVERSED', true),
        ('AVAILABLE_FOR_PAYOUT', 'PAID', false),
        ('AVAILABLE_FOR_PAYOUT', 'REVERSED', true),
        ('PAID', 'SETTLED', false),
        ('PAID', 'REVERSED', true),
        ('SETTLED', 'REVERSED', true)
)
INSERT INTO remittance.remittance_status_transition
    (from_status_id, to_status_id, requires_reason)
SELECT fs.remittance_status_id, ts.remittance_status_id, t.requires_reason
FROM transitions t
JOIN reference.remittance_status fs ON fs.status_code = t.from_code
JOIN reference.remittance_status ts ON ts.status_code = t.to_code;

INSERT INTO compliance.screening_provider (provider_code, provider_name)
VALUES
    ('INTERNAL_AML', 'GlobalRemit Internal AML'),
    ('SANCTIONS_DEMO', 'Academic Sanctions Provider');

INSERT INTO compliance.risk_reason_catalog (reason_code, reason_name)
VALUES
    ('HIGH_AMOUNT', 'Amount exceeds usual pattern'),
    ('HIGH_VELOCITY', 'High transaction velocity'),
    ('NEW_BENEFICIARY', 'New beneficiary'),
    ('HIGH_RISK_CORRIDOR', 'High risk corridor'),
    ('IDENTITY_MISMATCH', 'Identity information mismatch');

INSERT INTO fx.exchange_rate_provider
    (provider_code, provider_name, provider_timezone)
VALUES
    ('ACADEMIC_FX', 'Academic FX Feed', 'UTC');

INSERT INTO integration.api_consumer (consumer_code, consumer_name)
VALUES
    ('GLOBALREMIT_WEB', 'GlobalRemit Web'),
    ('GLOBALREMIT_MOBILE', 'GlobalRemit Mobile'),
    ('PARTNER_API', 'Correspondent Partner API');

INSERT INTO integration.external_system (system_code, system_name)
VALUES
    ('FX_PROVIDER', 'External FX Provider'),
    ('PAYMENT_NETWORK', 'Payout Network'),
    ('CORPORATE_ACCOUNTING', 'Future Corporate Accounting');

INSERT INTO integration.publication_destination
    (destination_code, destination_name)
VALUES
    ('MONGODB_ANALYTICS', 'GlobalRemit MongoDB Analytics'),
    ('FRAUD_ENGINE', 'Fraud and Behavior Engine'),
    ('ACCOUNTING_EVENTS', 'Future Accounting Events');

COMMIT;
