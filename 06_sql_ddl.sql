-- ============================================================
-- GlobalRemit - Fase 6
-- PostgreSQL DDL
-- Base objetivo: globalremit
-- ============================================================
-- ADVERTENCIA:
-- Este script elimina y reconstruye los siete esquemas de
-- GlobalRemit. Ejecutarlo unicamente sobre la base academica
-- globalremit y despues de confirmar que no contiene datos
-- que deban conservarse.
-- ============================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP SCHEMA IF EXISTS integration CASCADE;
DROP SCHEMA IF EXISTS settlement CASCADE;
DROP SCHEMA IF EXISTS compliance CASCADE;
DROP SCHEMA IF EXISTS remittance CASCADE;
DROP SCHEMA IF EXISTS fx CASCADE;
DROP SCHEMA IF EXISTS customer CASCADE;
DROP SCHEMA IF EXISTS reference CASCADE;

CREATE SCHEMA reference;
CREATE SCHEMA customer;
CREATE SCHEMA fx;
CREATE SCHEMA remittance;
CREATE SCHEMA compliance;
CREATE SCHEMA settlement;
CREATE SCHEMA integration;

-- ============================================================
-- Reference
-- ============================================================

CREATE TABLE reference.country (
    country_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    iso_alpha2_code char(2) NOT NULL UNIQUE,
    country_name varchar(120) NOT NULL,
    default_timezone varchar(80) NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    CONSTRAINT ck_country_iso CHECK (iso_alpha2_code ~ '^[A-Z]{2}$')
);

CREATE TABLE reference.currency (
    currency_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    iso_currency_code char(3) NOT NULL UNIQUE,
    currency_name varchar(100) NOT NULL,
    numeric_code char(3) UNIQUE,
    minor_unit smallint NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    CONSTRAINT ck_currency_iso CHECK (iso_currency_code ~ '^[A-Z]{3}$'),
    CONSTRAINT ck_currency_numeric CHECK (numeric_code IS NULL OR numeric_code ~ '^[0-9]{3}$'),
    CONSTRAINT ck_currency_minor_unit CHECK (minor_unit BETWEEN 0 AND 6)
);

CREATE TABLE reference.country_currency (
    country_id bigint NOT NULL REFERENCES reference.country,
    currency_id bigint NOT NULL REFERENCES reference.currency,
    valid_from date NOT NULL,
    valid_to date,
    is_primary boolean NOT NULL DEFAULT false,
    PRIMARY KEY (country_id, currency_id, valid_from),
    CONSTRAINT ck_country_currency_dates CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE UNIQUE INDEX ux_country_currency_primary_active
    ON reference.country_currency (country_id)
    WHERE is_primary AND valid_to IS NULL;

CREATE TABLE reference.transaction_channel (
    channel_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_code varchar(20) NOT NULL UNIQUE,
    channel_name varchar(100) NOT NULL,
    requires_ip_address boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE reference.remittance_status (
    remittance_status_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status_code varchar(30) NOT NULL UNIQUE,
    status_name varchar(100) NOT NULL,
    is_final boolean NOT NULL DEFAULT false,
    allows_financial_movement boolean NOT NULL DEFAULT true,
    is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE reference.financial_movement_type (
    movement_type_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    movement_type_code varchar(40) NOT NULL UNIQUE,
    movement_type_name varchar(120) NOT NULL,
    movement_direction varchar(15) NOT NULL,
    is_reversible boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    CONSTRAINT ck_movement_direction
        CHECK (movement_direction IN ('INFLOW', 'OUTFLOW', 'INFORMATIONAL'))
);

-- ============================================================
-- Customer & Identity
-- ============================================================

CREATE TABLE customer.party (
    party_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_code varchar(30) NOT NULL UNIQUE,
    party_type varchar(20) NOT NULL,
    legal_name varchar(200) NOT NULL,
    party_status varchar(20) NOT NULL DEFAULT 'ACTIVE',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_party_type CHECK (party_type IN ('INDIVIDUAL', 'ORGANIZATION')),
    CONSTRAINT ck_party_status CHECK (party_status IN ('ACTIVE', 'INACTIVE', 'BLOCKED'))
);

CREATE TABLE customer.person_detail (
    party_id bigint PRIMARY KEY REFERENCES customer.party,
    given_names varchar(120) NOT NULL,
    family_names varchar(120) NOT NULL,
    birth_date date NOT NULL,
    nationality_country_id bigint REFERENCES reference.country,
    gender_code varchar(20),
    CONSTRAINT ck_person_birth_date CHECK (birth_date < current_date)
);

CREATE TABLE customer.organization_detail (
    party_id bigint PRIMARY KEY REFERENCES customer.party,
    trade_name varchar(200),
    incorporation_date date NOT NULL,
    incorporation_country_id bigint NOT NULL REFERENCES reference.country,
    tax_identifier varchar(60) NOT NULL,
    CONSTRAINT uq_organization_tax UNIQUE (incorporation_country_id, tax_identifier),
    CONSTRAINT ck_organization_date CHECK (incorporation_date <= current_date)
);

CREATE TABLE customer.document_type_catalog (
    document_type_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_type_code varchar(30) NOT NULL UNIQUE,
    document_type_name varchar(100) NOT NULL,
    applies_to_party_type varchar(20),
    is_active boolean NOT NULL DEFAULT true,
    CONSTRAINT ck_document_party_type
        CHECK (applies_to_party_type IS NULL OR applies_to_party_type IN ('INDIVIDUAL', 'ORGANIZATION'))
);

CREATE TABLE customer.party_document (
    party_document_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_id bigint NOT NULL REFERENCES customer.party,
    document_type_id bigint NOT NULL REFERENCES customer.document_type_catalog,
    document_number varchar(80) NOT NULL,
    issuing_country_id bigint NOT NULL REFERENCES reference.country,
    issued_on date,
    expires_on date,
    verification_status varchar(20) NOT NULL DEFAULT 'PENDING',
    verified_at timestamptz,
    is_primary boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_party_document UNIQUE (document_type_id, issuing_country_id, document_number),
    CONSTRAINT ck_party_document_status
        CHECK (verification_status IN ('PENDING', 'VERIFIED', 'REJECTED', 'EXPIRED')),
    CONSTRAINT ck_party_document_dates
        CHECK (expires_on IS NULL OR issued_on IS NULL OR expires_on >= issued_on)
);

CREATE UNIQUE INDEX ux_party_document_primary
    ON customer.party_document (party_id, document_type_id)
    WHERE is_primary AND verification_status <> 'EXPIRED';

CREATE TABLE customer.party_address (
    party_address_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_id bigint NOT NULL REFERENCES customer.party,
    address_type varchar(20) NOT NULL,
    address_line_1 varchar(200) NOT NULL,
    address_line_2 varchar(200),
    city varchar(100) NOT NULL,
    state_region varchar(100),
    postal_code varchar(20),
    country_id bigint NOT NULL REFERENCES reference.country,
    valid_from date NOT NULL DEFAULT current_date,
    valid_to date,
    is_primary boolean NOT NULL DEFAULT false,
    CONSTRAINT ck_party_address_type
        CHECK (address_type IN ('RESIDENTIAL', 'BUSINESS', 'MAILING')),
    CONSTRAINT ck_party_address_dates CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE UNIQUE INDEX ux_party_address_primary
    ON customer.party_address (party_id, address_type)
    WHERE is_primary AND valid_to IS NULL;

CREATE TABLE customer.party_contact (
    party_contact_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_id bigint NOT NULL REFERENCES customer.party,
    contact_type varchar(20) NOT NULL,
    contact_value varchar(200) NOT NULL,
    is_verified boolean NOT NULL DEFAULT false,
    is_primary boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_party_contact UNIQUE (party_id, contact_type, contact_value),
    CONSTRAINT ck_party_contact_type CHECK (contact_type IN ('EMAIL', 'PHONE', 'MOBILE'))
);

CREATE UNIQUE INDEX ux_party_contact_primary
    ON customer.party_contact (party_id, contact_type)
    WHERE is_primary;

CREATE TABLE customer.customer_profile (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_id bigint NOT NULL UNIQUE REFERENCES customer.party,
    customer_code varchar(30) NOT NULL UNIQUE,
    occupation_or_activity varchar(150),
    customer_status varchar(20) NOT NULL DEFAULT 'ACTIVE',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_customer_status CHECK (customer_status IN ('ACTIVE', 'INACTIVE', 'BLOCKED'))
);

CREATE TABLE customer.beneficiary_profile (
    beneficiary_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_id bigint NOT NULL UNIQUE REFERENCES customer.party,
    beneficiary_code varchar(30) NOT NULL UNIQUE,
    beneficiary_status varchar(20) NOT NULL DEFAULT 'ACTIVE',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_beneficiary_status CHECK (beneficiary_status IN ('ACTIVE', 'INACTIVE', 'BLOCKED'))
);

CREATE TABLE customer.customer_beneficiary (
    customer_id bigint NOT NULL REFERENCES customer.customer_profile,
    beneficiary_id bigint NOT NULL REFERENCES customer.beneficiary_profile,
    relationship_type varchar(20) NOT NULL,
    alias varchar(100),
    is_favorite boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (customer_id, beneficiary_id),
    CONSTRAINT ck_customer_beneficiary_relationship
        CHECK (relationship_type IN ('FAMILY', 'FRIEND', 'BUSINESS', 'SELF', 'OTHER'))
);

CREATE TABLE customer.beneficiary_payout_method (
    payout_method_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    beneficiary_id bigint NOT NULL REFERENCES customer.beneficiary_profile,
    payout_method_type varchar(30) NOT NULL,
    institution_name varchar(160) NOT NULL,
    institution_code varchar(50),
    account_identifier_encrypted text,
    account_identifier_masked varchar(100) NOT NULL,
    currency_id bigint NOT NULL REFERENCES reference.currency,
    country_id bigint NOT NULL REFERENCES reference.country,
    is_primary boolean NOT NULL DEFAULT false,
    is_verified boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_payout_method_type
        CHECK (payout_method_type IN ('BANK_ACCOUNT', 'MOBILE_WALLET', 'CASH_PICKUP'))
);

CREATE UNIQUE INDEX ux_beneficiary_payout_primary
    ON customer.beneficiary_payout_method (beneficiary_id)
    WHERE is_primary AND is_active;

-- ============================================================
-- FX & Treasury
-- ============================================================

CREATE TABLE fx.exchange_rate_provider (
    provider_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_code varchar(30) NOT NULL UNIQUE,
    provider_name varchar(120) NOT NULL,
    provider_timezone varchar(80) NOT NULL,
    is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE fx.currency_pair (
    currency_pair_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    base_currency_id bigint NOT NULL REFERENCES reference.currency,
    quote_currency_id bigint NOT NULL REFERENCES reference.currency,
    CONSTRAINT uq_currency_pair UNIQUE (base_currency_id, quote_currency_id),
    CONSTRAINT ck_currency_pair_different CHECK (base_currency_id <> quote_currency_id)
);

CREATE TABLE fx.exchange_rate (
    exchange_rate_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_id bigint NOT NULL REFERENCES fx.exchange_rate_provider,
    currency_pair_id bigint NOT NULL REFERENCES fx.currency_pair,
    market_rate numeric(20,10) NOT NULL,
    bid_rate numeric(20,10),
    ask_rate numeric(20,10),
    valid_from_utc timestamptz NOT NULL,
    valid_to_utc timestamptz,
    provider_timestamp timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    source_reference varchar(120),
    CONSTRAINT uq_exchange_rate_source UNIQUE (provider_id, currency_pair_id, provider_timestamp),
    CONSTRAINT ck_exchange_rate_market CHECK (market_rate > 0),
    CONSTRAINT ck_exchange_rate_bid CHECK (bid_rate IS NULL OR bid_rate > 0),
    CONSTRAINT ck_exchange_rate_ask CHECK (ask_rate IS NULL OR ask_rate > 0),
    CONSTRAINT ck_exchange_rate_spread CHECK (bid_rate IS NULL OR ask_rate IS NULL OR bid_rate <= ask_rate),
    CONSTRAINT ck_exchange_rate_dates CHECK (valid_to_utc IS NULL OR valid_to_utc >= valid_from_utc)
);

CREATE TABLE fx.remittance_corridor (
    corridor_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    corridor_code varchar(40) NOT NULL UNIQUE,
    origin_country_id bigint NOT NULL REFERENCES reference.country,
    destination_country_id bigint NOT NULL REFERENCES reference.country,
    send_currency_id bigint NOT NULL REFERENCES reference.currency,
    payout_currency_id bigint NOT NULL REFERENCES reference.currency,
    is_active boolean NOT NULL DEFAULT true,
    CONSTRAINT uq_corridor UNIQUE (
        origin_country_id, destination_country_id, send_currency_id, payout_currency_id
    ),
    CONSTRAINT ck_corridor_countries CHECK (origin_country_id <> destination_country_id)
);

CREATE TABLE fx.corridor_limit_rule (
    limit_rule_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    corridor_id bigint NOT NULL REFERENCES fx.remittance_corridor,
    channel_id bigint REFERENCES reference.transaction_channel,
    minimum_amount numeric(20,4) NOT NULL,
    maximum_amount numeric(20,4) NOT NULL,
    period_limit_amount numeric(20,4),
    valid_from timestamptz NOT NULL,
    valid_to timestamptz,
    is_active boolean NOT NULL DEFAULT true,
    CONSTRAINT ck_limit_amounts CHECK (
        minimum_amount >= 0
        AND maximum_amount > minimum_amount
        AND (period_limit_amount IS NULL OR period_limit_amount >= maximum_amount)
    ),
    CONSTRAINT ck_limit_dates CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE fx.corridor_pricing_rule (
    pricing_rule_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    corridor_id bigint NOT NULL REFERENCES fx.remittance_corridor,
    channel_id bigint REFERENCES reference.transaction_channel,
    fee_type varchar(20) NOT NULL,
    fixed_fee_amount numeric(20,4),
    percentage_fee_rate numeric(9,6),
    tax_rate numeric(9,6) NOT NULL DEFAULT 0,
    spread_rate numeric(9,6) NOT NULL DEFAULT 0,
    valid_from timestamptz NOT NULL,
    valid_to timestamptz,
    is_active boolean NOT NULL DEFAULT true,
    CONSTRAINT ck_pricing_fee_type CHECK (fee_type IN ('FIXED', 'PERCENTAGE', 'MIXED')),
    CONSTRAINT ck_pricing_values CHECK (
        COALESCE(fixed_fee_amount, 0) >= 0
        AND COALESCE(percentage_fee_rate, 0) >= 0
        AND tax_rate >= 0
        AND spread_rate >= 0
    ),
    CONSTRAINT ck_pricing_required_values CHECK (
        (fee_type = 'FIXED' AND fixed_fee_amount IS NOT NULL)
        OR (fee_type = 'PERCENTAGE' AND percentage_fee_rate IS NOT NULL)
        OR (fee_type = 'MIXED' AND fixed_fee_amount IS NOT NULL AND percentage_fee_rate IS NOT NULL)
    ),
    CONSTRAINT ck_pricing_dates CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE fx.fx_quote (
    fx_quote_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quote_code varchar(40) NOT NULL UNIQUE,
    corridor_id bigint NOT NULL REFERENCES fx.remittance_corridor,
    customer_id bigint NOT NULL REFERENCES customer.customer_profile,
    exchange_rate_id bigint NOT NULL REFERENCES fx.exchange_rate,
    pricing_rule_id bigint NOT NULL REFERENCES fx.corridor_pricing_rule,
    send_amount numeric(20,4) NOT NULL,
    market_exchange_rate numeric(20,10) NOT NULL,
    offered_exchange_rate numeric(20,10) NOT NULL,
    fee_amount numeric(20,4) NOT NULL,
    tax_amount numeric(20,4) NOT NULL,
    payout_amount numeric(20,4) NOT NULL,
    total_charged_amount numeric(20,4) NOT NULL,
    quoted_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    accepted_at timestamptz,
    quote_status varchar(20) NOT NULL DEFAULT 'GENERATED',
    CONSTRAINT ck_quote_status CHECK (quote_status IN ('GENERATED', 'ACCEPTED', 'EXPIRED', 'CANCELLED')),
    CONSTRAINT ck_quote_amounts CHECK (
        send_amount > 0
        AND market_exchange_rate > 0
        AND offered_exchange_rate > 0
        AND fee_amount >= 0
        AND tax_amount >= 0
        AND payout_amount > 0
        AND total_charged_amount >= send_amount
    ),
    CONSTRAINT ck_quote_dates CHECK (
        expires_at > quoted_at
        AND (accepted_at IS NULL OR accepted_at BETWEEN quoted_at AND expires_at)
    ),
    CONSTRAINT ck_quote_acceptance CHECK (
        (quote_status = 'ACCEPTED' AND accepted_at IS NOT NULL)
        OR quote_status <> 'ACCEPTED'
    )
);

-- ============================================================
-- Compliance catalogs required by remittance
-- ============================================================

CREATE TABLE compliance.source_of_funds_catalog (
    source_of_funds_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_code varchar(30) NOT NULL UNIQUE,
    source_name varchar(120) NOT NULL,
    is_active boolean NOT NULL DEFAULT true
);

-- ============================================================
-- Remittance Operations
-- ============================================================

CREATE TABLE remittance.purpose_catalog (
    purpose_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    purpose_code varchar(30) NOT NULL UNIQUE,
    purpose_name varchar(120) NOT NULL,
    is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE remittance.status_reason_catalog (
    status_reason_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reason_code varchar(40) NOT NULL UNIQUE,
    reason_name varchar(150) NOT NULL,
    is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE remittance.remittance_status_transition (
    from_status_id bigint NOT NULL REFERENCES reference.remittance_status,
    to_status_id bigint NOT NULL REFERENCES reference.remittance_status,
    requires_reason boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    PRIMARY KEY (from_status_id, to_status_id),
    CONSTRAINT ck_status_transition_different CHECK (from_status_id <> to_status_id)
);

CREATE TABLE remittance.remittance_order (
    remittance_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    remittance_code varchar(40) NOT NULL UNIQUE,
    customer_id bigint NOT NULL REFERENCES customer.customer_profile,
    beneficiary_id bigint NOT NULL REFERENCES customer.beneficiary_profile,
    corridor_id bigint NOT NULL REFERENCES fx.remittance_corridor,
    fx_quote_id bigint NOT NULL UNIQUE REFERENCES fx.fx_quote,
    channel_id bigint NOT NULL REFERENCES reference.transaction_channel,
    current_status_id bigint NOT NULL REFERENCES reference.remittance_status,
    purpose_id bigint NOT NULL REFERENCES remittance.purpose_catalog,
    source_of_funds_id bigint NOT NULL REFERENCES compliance.source_of_funds_catalog,
    customer_reference varchar(120),
    origin_timezone varchar(80) NOT NULL,
    destination_timezone varchar(80) NOT NULL,
    captured_local_at timestamp NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    authorized_at timestamptz,
    paid_at timestamptz,
    completed_at timestamptz,
    CONSTRAINT ck_remittance_dates CHECK (
        (authorized_at IS NULL OR authorized_at >= created_at)
        AND (paid_at IS NULL OR paid_at >= created_at)
        AND (completed_at IS NULL OR completed_at >= created_at)
    )
);

CREATE TABLE remittance.remittance_financial_detail (
    remittance_id bigint PRIMARY KEY REFERENCES remittance.remittance_order,
    send_currency_id bigint NOT NULL REFERENCES reference.currency,
    send_amount numeric(20,4) NOT NULL,
    market_exchange_rate numeric(20,10) NOT NULL,
    applied_exchange_rate numeric(20,10) NOT NULL,
    exchange_rate_timestamp_utc timestamptz NOT NULL,
    payout_currency_id bigint NOT NULL REFERENCES reference.currency,
    payout_amount numeric(20,4) NOT NULL,
    fee_amount numeric(20,4) NOT NULL,
    tax_amount numeric(20,4) NOT NULL,
    other_charge_amount numeric(20,4) NOT NULL DEFAULT 0,
    fx_spread_amount numeric(20,4) NOT NULL DEFAULT 0,
    fx_gain_amount numeric(20,4) NOT NULL DEFAULT 0,
    total_charged_amount numeric(20,4) NOT NULL,
    settlement_currency_id bigint NOT NULL REFERENCES reference.currency,
    settlement_amount numeric(20,4) NOT NULL,
    calculation_version varchar(30) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_financial_detail_values CHECK (
        send_amount > 0
        AND market_exchange_rate > 0
        AND applied_exchange_rate > 0
        AND payout_amount > 0
        AND fee_amount >= 0
        AND tax_amount >= 0
        AND other_charge_amount >= 0
        AND fx_spread_amount >= 0
        AND fx_gain_amount >= 0
        AND total_charged_amount >= send_amount
        AND settlement_amount >= 0
    )
);

CREATE TABLE remittance.remittance_status_history (
    status_history_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    remittance_id bigint NOT NULL REFERENCES remittance.remittance_order,
    previous_status_id bigint REFERENCES reference.remittance_status,
    new_status_id bigint NOT NULL REFERENCES reference.remittance_status,
    status_reason_id bigint REFERENCES remittance.status_reason_catalog,
    reason_description varchar(500),
    actor_type varchar(30) NOT NULL,
    actor_reference varchar(120) NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT now(),
    local_changed_at timestamp,
    timezone_name varchar(80),
    CONSTRAINT uq_status_history UNIQUE (remittance_id, changed_at, new_status_id),
    CONSTRAINT ck_status_actor CHECK (actor_type IN ('USER', 'SYSTEM', 'CORRESPONDENT', 'API_CONSUMER')),
    CONSTRAINT ck_status_change CHECK (previous_status_id IS NULL OR previous_status_id <> new_status_id),
    CONSTRAINT ck_status_local_timezone CHECK (
        local_changed_at IS NULL OR timezone_name IS NOT NULL
    )
);

CREATE TABLE remittance.remittance_financial_movement (
    financial_movement_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    remittance_id bigint NOT NULL REFERENCES remittance.remittance_order,
    movement_type_id bigint NOT NULL REFERENCES reference.financial_movement_type,
    currency_id bigint NOT NULL REFERENCES reference.currency,
    amount numeric(20,4) NOT NULL,
    movement_status varchar(20) NOT NULL,
    related_movement_id bigint REFERENCES remittance.remittance_financial_movement,
    external_reference varchar(120),
    occurred_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    description varchar(500),
    CONSTRAINT ck_financial_movement_amount CHECK (amount > 0),
    CONSTRAINT ck_financial_movement_status
        CHECK (movement_status IN ('PENDING', 'CONFIRMED', 'FAILED', 'REVERSED')),
    CONSTRAINT ck_financial_movement_relation
        CHECK (related_movement_id IS NULL OR related_movement_id <> financial_movement_id)
);

CREATE TABLE remittance.remittance_payout_instruction (
    payout_instruction_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    remittance_id bigint NOT NULL UNIQUE REFERENCES remittance.remittance_order,
    payout_method_id bigint REFERENCES customer.beneficiary_payout_method,
    payout_method_type varchar(30) NOT NULL,
    institution_name varchar(160) NOT NULL,
    institution_code varchar(50),
    account_identifier_masked varchar(100) NOT NULL,
    destination_reference varchar(120),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_instruction_type
        CHECK (payout_method_type IN ('BANK_ACCOUNT', 'MOBILE_WALLET', 'CASH_PICKUP'))
);

-- ============================================================
-- Compliance AML/KYC and Risk
-- ============================================================

CREATE TABLE compliance.kyc_profile (
    kyc_profile_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_id bigint NOT NULL UNIQUE REFERENCES customer.party,
    kyc_level varchar(20) NOT NULL,
    verification_status varchar(20) NOT NULL,
    risk_level varchar(20) NOT NULL,
    verified_at timestamptz,
    expires_at timestamptz,
    reviewed_by varchar(120),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_kyc_level CHECK (kyc_level IN ('BASIC', 'STANDARD', 'ENHANCED')),
    CONSTRAINT ck_kyc_status CHECK (verification_status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')),
    CONSTRAINT ck_kyc_risk CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    CONSTRAINT ck_kyc_dates CHECK (expires_at IS NULL OR verified_at IS NULL OR expires_at >= verified_at)
);

CREATE TABLE compliance.screening_provider (
    screening_provider_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_code varchar(30) NOT NULL UNIQUE,
    provider_name varchar(120) NOT NULL,
    is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE compliance.aml_screening (
    aml_screening_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    screening_provider_id bigint NOT NULL REFERENCES compliance.screening_provider,
    screening_type varchar(30) NOT NULL,
    screening_status varchar(20) NOT NULL,
    match_score numeric(7,4),
    request_reference varchar(120),
    screened_at timestamptz NOT NULL DEFAULT now(),
    raw_result_reference varchar(250),
    CONSTRAINT ck_screening_type
        CHECK (screening_type IN ('SANCTIONS', 'PEP', 'ADVERSE_MEDIA', 'TRANSACTION', 'VELOCITY')),
    CONSTRAINT ck_screening_status CHECK (screening_status IN ('PENDING', 'CLEAR', 'MATCH', 'ERROR')),
    CONSTRAINT ck_screening_score CHECK (match_score IS NULL OR match_score BETWEEN 0 AND 1)
);

CREATE TABLE compliance.aml_screening_party (
    aml_screening_id bigint NOT NULL REFERENCES compliance.aml_screening,
    party_id bigint NOT NULL REFERENCES customer.party,
    subject_role varchar(30) NOT NULL,
    PRIMARY KEY (aml_screening_id, party_id),
    CONSTRAINT ck_screening_subject_role
        CHECK (subject_role IN ('ORIGINATOR', 'BENEFICIARY', 'RELATED_PARTY'))
);

CREATE TABLE compliance.aml_screening_remittance (
    aml_screening_id bigint NOT NULL REFERENCES compliance.aml_screening,
    remittance_id bigint NOT NULL REFERENCES remittance.remittance_order,
    PRIMARY KEY (aml_screening_id, remittance_id)
);

CREATE TABLE compliance.aml_alert (
    aml_alert_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    aml_screening_id bigint NOT NULL REFERENCES compliance.aml_screening,
    alert_type varchar(40) NOT NULL,
    severity varchar(20) NOT NULL,
    alert_status varchar(30) NOT NULL,
    decision varchar(20),
    decision_reason varchar(500),
    assigned_to varchar(120),
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    CONSTRAINT ck_alert_severity CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    CONSTRAINT ck_alert_status
        CHECK (alert_status IN ('OPEN', 'UNDER_REVIEW', 'DISMISSED', 'CONFIRMED', 'CLOSED')),
    CONSTRAINT ck_alert_decision CHECK (decision IS NULL OR decision IN ('APPROVE', 'REJECT', 'ESCALATE')),
    CONSTRAINT ck_alert_resolution CHECK (resolved_at IS NULL OR resolved_at >= created_at),
    CONSTRAINT ck_alert_closed_decision CHECK (
        alert_status NOT IN ('DISMISSED', 'CONFIRMED', 'CLOSED')
        OR (decision IS NOT NULL AND resolved_at IS NOT NULL)
    )
);

CREATE TABLE compliance.risk_reason_catalog (
    risk_reason_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reason_code varchar(40) NOT NULL UNIQUE,
    reason_name varchar(150) NOT NULL,
    is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE compliance.risk_assessment (
    risk_assessment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    remittance_id bigint NOT NULL REFERENCES remittance.remittance_order,
    assessment_version varchar(40) NOT NULL,
    risk_score numeric(7,4) NOT NULL,
    risk_level varchar(20) NOT NULL,
    decision varchar(20) NOT NULL,
    evaluated_at timestamptz NOT NULL DEFAULT now(),
    model_reference varchar(120),
    CONSTRAINT ck_risk_score CHECK (risk_score BETWEEN 0 AND 1),
    CONSTRAINT ck_risk_level CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    CONSTRAINT ck_risk_decision CHECK (decision IN ('APPROVE', 'REVIEW', 'REJECT'))
);

CREATE TABLE compliance.risk_assessment_reason (
    risk_assessment_id bigint NOT NULL REFERENCES compliance.risk_assessment,
    risk_reason_id bigint NOT NULL REFERENCES compliance.risk_reason_catalog,
    PRIMARY KEY (risk_assessment_id, risk_reason_id)
);

CREATE TABLE compliance.travel_rule_record (
    travel_rule_record_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    remittance_id bigint NOT NULL UNIQUE REFERENCES remittance.remittance_order,
    originator_party_id bigint NOT NULL REFERENCES customer.party,
    originator_name varchar(200) NOT NULL,
    originator_account_or_reference varchar(120),
    originator_document_type varchar(50) NOT NULL,
    originator_document_number_encrypted text NOT NULL,
    originator_address varchar(500) NOT NULL,
    originator_country_id bigint NOT NULL REFERENCES reference.country,
    beneficiary_party_id bigint NOT NULL REFERENCES customer.party,
    beneficiary_name varchar(200) NOT NULL,
    beneficiary_account_or_reference varchar(120),
    beneficiary_document_type varchar(50),
    beneficiary_document_number_encrypted text,
    beneficiary_address varchar(500),
    beneficiary_country_id bigint NOT NULL REFERENCES reference.country,
    completeness_status varchar(20) NOT NULL,
    validated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_travel_rule_status
        CHECK (completeness_status IN ('COMPLETE', 'INCOMPLETE', 'NOT_APPLICABLE')),
    CONSTRAINT ck_travel_rule_validation CHECK (
        completeness_status <> 'COMPLETE' OR validated_at IS NOT NULL
    )
);

-- ============================================================
-- Settlement
-- ============================================================

CREATE TABLE settlement.correspondent (
    correspondent_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    correspondent_code varchar(30) NOT NULL UNIQUE,
    correspondent_name varchar(160) NOT NULL,
    country_id bigint NOT NULL REFERENCES reference.country,
    correspondent_type varchar(20) NOT NULL,
    timezone_name varchar(80) NOT NULL,
    settlement_frequency varchar(30) NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    CONSTRAINT ck_correspondent_type CHECK (correspondent_type IN ('BANK', 'NETWORK', 'AGENT', 'WALLET'))
);

CREATE TABLE settlement.correspondent_corridor (
    correspondent_corridor_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    correspondent_id bigint NOT NULL REFERENCES settlement.correspondent,
    corridor_id bigint NOT NULL REFERENCES fx.remittance_corridor,
    payout_method_type varchar(30) NOT NULL,
    priority_order smallint NOT NULL,
    valid_from date NOT NULL,
    valid_to date,
    is_active boolean NOT NULL DEFAULT true,
    CONSTRAINT uq_correspondent_corridor
        UNIQUE (correspondent_id, corridor_id, payout_method_type, valid_from),
    CONSTRAINT ck_correspondent_payout_type
        CHECK (payout_method_type IN ('BANK_ACCOUNT', 'MOBILE_WALLET', 'CASH_PICKUP')),
    CONSTRAINT ck_correspondent_priority CHECK (priority_order > 0),
    CONSTRAINT ck_correspondent_dates CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE settlement.settlement_batch (
    settlement_batch_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_code varchar(40) NOT NULL UNIQUE,
    correspondent_id bigint NOT NULL REFERENCES settlement.correspondent,
    settlement_currency_id bigint NOT NULL REFERENCES reference.currency,
    period_start_at timestamptz NOT NULL,
    period_end_at timestamptz NOT NULL,
    expected_amount numeric(20,4) NOT NULL,
    reported_amount numeric(20,4),
    difference_amount numeric(20,4),
    batch_status varchar(20) NOT NULL DEFAULT 'OPEN',
    created_at timestamptz NOT NULL DEFAULT now(),
    settled_at timestamptz,
    CONSTRAINT ck_settlement_batch_status
        CHECK (batch_status IN ('OPEN', 'SENT', 'RECONCILING', 'RECONCILED', 'SETTLED', 'DIFFERENCE')),
    CONSTRAINT ck_settlement_batch_period CHECK (period_end_at >= period_start_at),
    CONSTRAINT ck_settlement_batch_amounts CHECK (
        expected_amount >= 0 AND (reported_amount IS NULL OR reported_amount >= 0)
    ),
    CONSTRAINT ck_settlement_batch_settled CHECK (
        batch_status <> 'SETTLED' OR settled_at IS NOT NULL
    )
);

CREATE TABLE settlement.settlement_item (
    settlement_item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    settlement_batch_id bigint NOT NULL REFERENCES settlement.settlement_batch,
    financial_movement_id bigint NOT NULL REFERENCES remittance.remittance_financial_movement,
    expected_amount numeric(20,4) NOT NULL,
    reported_amount numeric(20,4),
    difference_amount numeric(20,4),
    item_status varchar(20) NOT NULL DEFAULT 'PENDING',
    external_reference varchar(120),
    reconciled_at timestamptz,
    CONSTRAINT ck_settlement_item_status
        CHECK (item_status IN ('PENDING', 'MATCHED', 'DIFFERENCE', 'EXCLUDED')),
    CONSTRAINT ck_settlement_item_amounts CHECK (
        expected_amount >= 0 AND (reported_amount IS NULL OR reported_amount >= 0)
    ),
    CONSTRAINT ck_settlement_item_reconciled CHECK (
        item_status NOT IN ('MATCHED', 'DIFFERENCE') OR reconciled_at IS NOT NULL
    )
);

CREATE UNIQUE INDEX ux_settlement_item_active_movement
    ON settlement.settlement_item (financial_movement_id)
    WHERE item_status <> 'EXCLUDED';

-- ============================================================
-- Integration
-- ============================================================

CREATE TABLE integration.api_consumer (
    api_consumer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    consumer_code varchar(40) NOT NULL UNIQUE,
    consumer_name varchar(120) NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE integration.idempotency_request (
    idempotency_request_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    api_consumer_id bigint NOT NULL REFERENCES integration.api_consumer,
    idempotency_key varchar(120) NOT NULL,
    operation_type varchar(40) NOT NULL,
    request_hash char(64) NOT NULL,
    resource_type varchar(40),
    resource_id bigint,
    request_status varchar(20) NOT NULL DEFAULT 'RECEIVED',
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    CONSTRAINT uq_idempotency_consumer_key UNIQUE (api_consumer_id, idempotency_key),
    CONSTRAINT ck_idempotency_hash CHECK (request_hash ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT ck_idempotency_status
        CHECK (request_status IN ('RECEIVED', 'PROCESSING', 'COMPLETED', 'FAILED')),
    CONSTRAINT ck_idempotency_dates CHECK (expires_at > created_at)
);

CREATE TABLE integration.external_system (
    external_system_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    system_code varchar(40) NOT NULL UNIQUE,
    system_name varchar(120) NOT NULL,
    is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE integration.external_operation_reference (
    external_reference_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_system_id bigint NOT NULL REFERENCES integration.external_system,
    operation_type varchar(30) NOT NULL,
    external_reference varchar(120) NOT NULL,
    reference_status varchar(20) NOT NULL DEFAULT 'ACTIVE',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_external_reference UNIQUE (external_system_id, operation_type, external_reference),
    CONSTRAINT ck_external_operation_type
        CHECK (operation_type IN ('REMITTANCE', 'PAYOUT', 'REFUND', 'SETTLEMENT')),
    CONSTRAINT ck_external_reference_status
        CHECK (reference_status IN ('ACTIVE', 'CONFIRMED', 'REJECTED', 'CANCELLED'))
);

CREATE TABLE integration.external_reference_remittance (
    external_reference_id bigint NOT NULL REFERENCES integration.external_operation_reference,
    remittance_id bigint NOT NULL REFERENCES remittance.remittance_order,
    PRIMARY KEY (external_reference_id, remittance_id)
);

CREATE TABLE integration.external_reference_movement (
    external_reference_id bigint NOT NULL REFERENCES integration.external_operation_reference,
    financial_movement_id bigint NOT NULL REFERENCES remittance.remittance_financial_movement,
    PRIMARY KEY (external_reference_id, financial_movement_id)
);

CREATE TABLE integration.external_reference_settlement (
    external_reference_id bigint NOT NULL REFERENCES integration.external_operation_reference,
    settlement_batch_id bigint NOT NULL REFERENCES settlement.settlement_batch,
    PRIMARY KEY (external_reference_id, settlement_batch_id)
);

CREATE TABLE integration.outbox_event (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type varchar(40) NOT NULL,
    aggregate_id bigint NOT NULL,
    event_type varchar(80) NOT NULL,
    event_version smallint NOT NULL DEFAULT 1,
    payload jsonb NOT NULL,
    occurred_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    publication_status varchar(20) NOT NULL DEFAULT 'PENDING',
    published_at timestamptz,
    CONSTRAINT ck_outbox_version CHECK (event_version > 0),
    CONSTRAINT ck_outbox_status
        CHECK (publication_status IN ('PENDING', 'PROCESSING', 'PUBLISHED', 'FAILED')),
    CONSTRAINT ck_outbox_published CHECK (
        publication_status <> 'PUBLISHED' OR published_at IS NOT NULL
    )
);

CREATE TABLE integration.publication_destination (
    destination_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    destination_code varchar(40) NOT NULL UNIQUE,
    destination_name varchar(120) NOT NULL,
    is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE integration.outbox_publication_attempt (
    publication_attempt_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id uuid NOT NULL REFERENCES integration.outbox_event,
    destination_id bigint NOT NULL REFERENCES integration.publication_destination,
    attempted_at timestamptz NOT NULL DEFAULT now(),
    attempt_status varchar(20) NOT NULL,
    error_code varchar(50),
    error_message varchar(1000),
    CONSTRAINT uq_outbox_attempt UNIQUE (event_id, destination_id, attempted_at),
    CONSTRAINT ck_outbox_attempt_status CHECK (attempt_status IN ('SUCCESS', 'FAILED')),
    CONSTRAINT ck_outbox_attempt_error CHECK (
        attempt_status <> 'FAILED' OR error_message IS NOT NULL
    )
);

-- ============================================================
-- Advanced integrity functions and triggers
-- ============================================================

CREATE OR REPLACE FUNCTION customer.fn_validate_party_subtype()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_party_type varchar(20);
BEGIN
    SELECT party_type INTO v_party_type
    FROM customer.party
    WHERE party_id = NEW.party_id;

    IF TG_TABLE_NAME = 'person_detail' AND v_party_type <> 'INDIVIDUAL' THEN
        RAISE EXCEPTION 'party % must be INDIVIDUAL for person_detail', NEW.party_id;
    END IF;

    IF TG_TABLE_NAME = 'organization_detail' AND v_party_type <> 'ORGANIZATION' THEN
        RAISE EXCEPTION 'party % must be ORGANIZATION for organization_detail', NEW.party_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_person_party_type
BEFORE INSERT OR UPDATE ON customer.person_detail
FOR EACH ROW EXECUTE FUNCTION customer.fn_validate_party_subtype();

CREATE TRIGGER trg_organization_party_type
BEFORE INSERT OR UPDATE ON customer.organization_detail
FOR EACH ROW EXECUTE FUNCTION customer.fn_validate_party_subtype();

CREATE OR REPLACE FUNCTION fx.fn_protect_accepted_quote()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.quote_status = 'ACCEPTED' AND NEW IS DISTINCT FROM OLD THEN
        RAISE EXCEPTION 'Accepted quote % is immutable', OLD.fx_quote_id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_fx_quote_immutable
BEFORE UPDATE ON fx.fx_quote
FOR EACH ROW EXECUTE FUNCTION fx.fn_protect_accepted_quote();

CREATE OR REPLACE FUNCTION remittance.fn_protect_financial_detail()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Financial detail for remittance % is immutable', OLD.remittance_id;
END;
$$;

CREATE TRIGGER trg_financial_detail_immutable
BEFORE UPDATE OR DELETE ON remittance.remittance_financial_detail
FOR EACH ROW EXECUTE FUNCTION remittance.fn_protect_financial_detail();

CREATE OR REPLACE FUNCTION remittance.fn_validate_status_history()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_current_status_id bigint;
    v_requires_reason boolean;
BEGIN
    SELECT current_status_id INTO v_current_status_id
    FROM remittance.remittance_order
    WHERE remittance_id = NEW.remittance_id
    FOR UPDATE;

    IF NEW.previous_status_id IS NOT NULL AND NEW.previous_status_id <> v_current_status_id THEN
        RAISE EXCEPTION 'Previous status does not match current status for remittance %', NEW.remittance_id;
    END IF;

    IF NEW.previous_status_id IS NOT NULL THEN
        SELECT requires_reason INTO v_requires_reason
        FROM remittance.remittance_status_transition
        WHERE from_status_id = NEW.previous_status_id
          AND to_status_id = NEW.new_status_id
          AND is_active;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Invalid status transition for remittance %', NEW.remittance_id;
        END IF;

        IF v_requires_reason
           AND NEW.status_reason_id IS NULL
           AND NULLIF(btrim(NEW.reason_description), '') IS NULL THEN
            RAISE EXCEPTION 'Status transition requires a reason';
        END IF;
    END IF;

    UPDATE remittance.remittance_order
    SET current_status_id = NEW.new_status_id,
        authorized_at = CASE
            WHEN NEW.new_status_id = (
                SELECT remittance_status_id FROM reference.remittance_status WHERE status_code = 'AUTHORIZED'
            ) THEN COALESCE(authorized_at, NEW.changed_at)
            ELSE authorized_at
        END,
        paid_at = CASE
            WHEN NEW.new_status_id = (
                SELECT remittance_status_id FROM reference.remittance_status WHERE status_code = 'PAID'
            ) THEN COALESCE(paid_at, NEW.changed_at)
            ELSE paid_at
        END,
        completed_at = CASE
            WHEN EXISTS (
                SELECT 1 FROM reference.remittance_status
                WHERE remittance_status_id = NEW.new_status_id AND is_final
            ) THEN COALESCE(completed_at, NEW.changed_at)
            ELSE completed_at
        END
    WHERE remittance_id = NEW.remittance_id;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_status_history_validate_sync
BEFORE INSERT ON remittance.remittance_status_history
FOR EACH ROW EXECUTE FUNCTION remittance.fn_validate_status_history();

CREATE OR REPLACE FUNCTION remittance.fn_validate_reversal()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_type_code varchar(40);
    v_original_status varchar(20);
    v_original_remittance bigint;
BEGIN
    SELECT movement_type_code INTO v_type_code
    FROM reference.financial_movement_type
    WHERE movement_type_id = NEW.movement_type_id;

    IF v_type_code = 'REVERSAL' THEN
        IF NEW.related_movement_id IS NULL THEN
            RAISE EXCEPTION 'REVERSAL requires related_movement_id';
        END IF;

        SELECT movement_status, remittance_id
        INTO v_original_status, v_original_remittance
        FROM remittance.remittance_financial_movement
        WHERE financial_movement_id = NEW.related_movement_id;

        IF v_original_status <> 'CONFIRMED' OR v_original_remittance <> NEW.remittance_id THEN
            RAISE EXCEPTION 'Invalid movement selected for reversal';
        END IF;

        IF EXISTS (
            SELECT 1
            FROM remittance.remittance_financial_movement fm
            JOIN reference.financial_movement_type mt ON mt.movement_type_id = fm.movement_type_id
            WHERE fm.related_movement_id = NEW.related_movement_id
              AND mt.movement_type_code = 'REVERSAL'
              AND fm.movement_status = 'CONFIRMED'
        ) THEN
            RAISE EXCEPTION 'Movement % has already been reversed', NEW.related_movement_id;
        END IF;
    ELSIF NEW.related_movement_id IS NOT NULL THEN
        RAISE EXCEPTION 'Only REVERSAL may reference another movement';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_financial_movement_reversal
BEFORE INSERT OR UPDATE ON remittance.remittance_financial_movement
FOR EACH ROW EXECUTE FUNCTION remittance.fn_validate_reversal();

-- ============================================================
-- Query indexes
-- ============================================================

CREATE INDEX ix_exchange_rate_pair_provider_date
    ON fx.exchange_rate (currency_pair_id, provider_id, valid_from_utc DESC);
CREATE INDEX ix_fx_quote_customer_status_expiry
    ON fx.fx_quote (customer_id, quote_status, expires_at);
CREATE INDEX ix_remittance_customer_date
    ON remittance.remittance_order (customer_id, created_at DESC);
CREATE INDEX ix_remittance_beneficiary_date
    ON remittance.remittance_order (beneficiary_id, created_at DESC);
CREATE INDEX ix_remittance_status_corridor_date
    ON remittance.remittance_order (current_status_id, corridor_id, created_at DESC);
CREATE INDEX ix_status_history_remittance_date
    ON remittance.remittance_status_history (remittance_id, changed_at DESC);
CREATE INDEX ix_movement_remittance_type_date
    ON remittance.remittance_financial_movement (remittance_id, movement_type_id, occurred_at DESC);
CREATE UNIQUE INDEX ux_movement_external_reference
    ON remittance.remittance_financial_movement (external_reference)
    WHERE external_reference IS NOT NULL;
CREATE INDEX ix_aml_screening_party
    ON compliance.aml_screening_party (party_id, aml_screening_id);
CREATE INDEX ix_aml_alert_open_severity
    ON compliance.aml_alert (severity, created_at DESC)
    WHERE alert_status IN ('OPEN', 'UNDER_REVIEW');
CREATE INDEX ix_risk_assessment_remittance_date
    ON compliance.risk_assessment (remittance_id, evaluated_at DESC);
CREATE INDEX ix_settlement_batch_correspondent_status
    ON settlement.settlement_batch (correspondent_id, batch_status, period_end_at DESC);
CREATE INDEX ix_settlement_item_batch_status
    ON settlement.settlement_item (settlement_batch_id, item_status);
CREATE INDEX ix_idempotency_status_expiry
    ON integration.idempotency_request (request_status, expires_at);
CREATE INDEX ix_outbox_pending
    ON integration.outbox_event (created_at)
    WHERE publication_status IN ('PENDING', 'FAILED');
CREATE INDEX ix_outbox_attempt_event_destination
    ON integration.outbox_publication_attempt (event_id, destination_id, attempted_at DESC);

COMMIT;
