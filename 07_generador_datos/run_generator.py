from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any

from generator.config import GeneratorConfig, load_config
from generator.data_factory import DataFactory, money, rate, sha256, utc_now
from generator.db import fetch_map, pg_connection
from generator.mongo_products import load_mongo, write_json
from generator.report import write_report
from psycopg.types.json import Jsonb


STATUS_PATHS = {
    "AUTHORIZED": ["DRAFT", "QUOTED", "PENDING_COMPLIANCE", "AUTHORIZED"],
    "FUNDED": ["DRAFT", "QUOTED", "PENDING_COMPLIANCE", "AUTHORIZED", "FUNDED"],
    "SENT_TO_PARTNER": ["DRAFT", "QUOTED", "PENDING_COMPLIANCE", "AUTHORIZED", "FUNDED", "SENT_TO_PARTNER"],
    "AVAILABLE_FOR_PAYOUT": ["DRAFT", "QUOTED", "PENDING_COMPLIANCE", "AUTHORIZED", "FUNDED", "SENT_TO_PARTNER", "AVAILABLE_FOR_PAYOUT"],
    "PAID": ["DRAFT", "QUOTED", "PENDING_COMPLIANCE", "AUTHORIZED", "FUNDED", "SENT_TO_PARTNER", "PAID"],
    "SETTLED": ["DRAFT", "QUOTED", "PENDING_COMPLIANCE", "AUTHORIZED", "FUNDED", "SENT_TO_PARTNER", "PAID", "SETTLED"],
    "UNDER_REVIEW": ["DRAFT", "QUOTED", "PENDING_COMPLIANCE", "UNDER_REVIEW"],
    "REJECTED": ["DRAFT", "QUOTED", "PENDING_COMPLIANCE", "REJECTED"],
    "CANCELLED": ["DRAFT", "QUOTED", "CANCELLED"],
    "EXPIRED": ["DRAFT", "QUOTED", "EXPIRED"],
    "REVERSED": ["DRAFT", "QUOTED", "PENDING_COMPLIANCE", "AUTHORIZED", "FUNDED", "REVERSED"],
}


# Ejecuta una consulta que debe devolver un solo valor.
def one(cur, sql: str, params: tuple[Any, ...] = ()) -> Any:
    cur.execute(sql, params)
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"No row returned for SQL: {sql}")
    return next(iter(row.values()))


# Limpia los datos generados para permitir ejecuciones repetibles.
def cleanup(conn) -> None:
    sql = """
    TRUNCATE TABLE
        integration.outbox_publication_attempt,
        integration.outbox_event,
        integration.external_reference_settlement,
        integration.external_reference_movement,
        integration.external_reference_remittance,
        integration.external_operation_reference,
        integration.idempotency_request,
        settlement.settlement_item,
        settlement.settlement_batch,
        settlement.correspondent_corridor,
        settlement.correspondent,
        compliance.risk_assessment_reason,
        compliance.risk_assessment,
        compliance.aml_alert,
        compliance.aml_screening_remittance,
        compliance.aml_screening_party,
        compliance.aml_screening,
        compliance.travel_rule_record,
        compliance.kyc_profile,
        remittance.remittance_payout_instruction,
        remittance.remittance_financial_movement,
        remittance.remittance_status_history,
        remittance.remittance_financial_detail,
        remittance.remittance_order,
        fx.fx_quote,
        fx.corridor_pricing_rule,
        fx.corridor_limit_rule,
        fx.exchange_rate,
        fx.currency_pair,
        fx.remittance_corridor,
        customer.beneficiary_payout_method,
        customer.customer_beneficiary,
        customer.beneficiary_profile,
        customer.customer_profile,
        customer.party_contact,
        customer.party_address,
        customer.party_document,
        customer.organization_detail,
        customer.person_detail,
        customer.party
    RESTART IDENTITY CASCADE;
    """
    with conn.cursor() as cur:
        cur.execute(sql)


# Carga catalogos SQL en diccionarios para resolver FK por codigo.
def load_reference_maps(conn) -> dict[str, dict[str, Any]]:
    return {
        "countries": fetch_map(conn, "SELECT iso_alpha2_code AS code, country_id AS id FROM reference.country", "code"),
        "currencies": fetch_map(conn, "SELECT iso_currency_code AS code, currency_id AS id FROM reference.currency", "code"),
        "channels": fetch_map(conn, "SELECT channel_code AS code, channel_id AS id FROM reference.transaction_channel", "code"),
        "statuses": fetch_map(conn, "SELECT status_code AS code, remittance_status_id AS id FROM reference.remittance_status", "code"),
        "movement_types": fetch_map(conn, "SELECT movement_type_code AS code, movement_type_id AS id FROM reference.financial_movement_type", "code"),
        "document_types": fetch_map(conn, "SELECT document_type_code AS code, document_type_id AS id FROM customer.document_type_catalog", "code"),
        "sources": fetch_map(conn, "SELECT source_code AS code, source_of_funds_id AS id FROM compliance.source_of_funds_catalog", "code"),
        "purposes": fetch_map(conn, "SELECT purpose_code AS code, purpose_id AS id FROM remittance.purpose_catalog", "code"),
        "reasons": fetch_map(conn, "SELECT reason_code AS code, status_reason_id AS id FROM remittance.status_reason_catalog", "code"),
        "risk_reasons": fetch_map(conn, "SELECT reason_code AS code, risk_reason_id AS id FROM compliance.risk_reason_catalog", "code"),
        "screening_providers": fetch_map(conn, "SELECT provider_code AS code, screening_provider_id AS id FROM compliance.screening_provider", "code"),
        "fx_providers": fetch_map(conn, "SELECT provider_code AS code, provider_id AS id FROM fx.exchange_rate_provider", "code"),
        "api_consumers": fetch_map(conn, "SELECT consumer_code AS code, api_consumer_id AS id FROM integration.api_consumer", "code"),
        "destinations": fetch_map(conn, "SELECT destination_code AS code, destination_id AS id FROM integration.publication_destination", "code"),
    }


# Inserta una identidad base con datos personales, documento, direccion y contacto.
def insert_party(cur, maps, factory: DataFactory, index: int, country_code: str, code_prefix: str) -> dict[str, Any]:
    first, last, legal_name = factory.name()
    party_code = f"{code_prefix}-P-{index:06d}"
    cur.execute(
        """
        INSERT INTO customer.party (party_code, party_type, legal_name)
        VALUES (%s, 'INDIVIDUAL', %s)
        RETURNING party_id
        """,
        (party_code, legal_name),
    )
    party_id = cur.fetchone()["party_id"]
    cur.execute(
        """
        INSERT INTO customer.person_detail
            (party_id, given_names, family_names, birth_date, nationality_country_id, gender_code)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            party_id,
            first,
            last,
            factory.birth_date(),
            maps["countries"][country_code],
            factory.random.choice(["F", "M", None]),
        ),
    )
    document_type = factory.random.choice(["NATIONAL_ID", "PASSPORT"])
    cur.execute(
        """
        INSERT INTO customer.party_document
            (party_id, document_type_id, document_number, issuing_country_id,
             issued_on, expires_on, verification_status, verified_at, is_primary)
        VALUES (%s, %s, %s, %s, %s, %s, 'VERIFIED', %s, true)
        """,
        (
            party_id,
            maps["document_types"][document_type],
            factory.document_number(country_code, index),
            maps["countries"][country_code],
            date.today() - timedelta(days=900),
            date.today() + timedelta(days=1200),
            utc_now(),
        ),
    )
    line, city, region = factory.address(country_code)
    cur.execute(
        """
        INSERT INTO customer.party_address
            (party_id, address_type, address_line_1, city, state_region, country_id, is_primary)
        VALUES (%s, 'RESIDENTIAL', %s, %s, %s, %s, true)
        """,
        (party_id, line, city, region, maps["countries"][country_code]),
    )
    cur.execute(
        """
        INSERT INTO customer.party_contact
            (party_id, contact_type, contact_value, is_verified, is_primary)
        VALUES (%s, 'EMAIL', %s, true, true)
        """,
        (party_id, factory.email(party_code)),
    )
    return {
        "party_id": party_id,
        "party_code": party_code,
        "legal_name": legal_name,
        "country_code": country_code,
        "country_id": maps["countries"][country_code],
    }


# Genera remitentes, beneficiarios y sus relaciones operativas.
def generate_customers(conn, cfg: GeneratorConfig, maps, factory: DataFactory) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    customers = []
    beneficiaries = []
    volume = cfg.raw["volume"]
    with conn.cursor() as cur:
        for idx in range(1, volume["customers"] + 1):
            party = insert_party(cur, maps, factory, idx, "GT", "CUS")
            cur.execute(
                """
                INSERT INTO customer.customer_profile
                    (party_id, customer_code, occupation_or_activity, customer_status)
                VALUES (%s, %s, %s, 'ACTIVE')
                RETURNING customer_id
                """,
                (
                    party["party_id"],
                    f"CUST-{idx:06d}",
                    factory.random.choice(["Empleado", "Comerciante", "Profesional", "Empresario"]),
                ),
            )
            customer_id = cur.fetchone()["customer_id"]
            cur.execute(
                """
                INSERT INTO compliance.kyc_profile
                    (party_id, kyc_level, verification_status, risk_level, verified_at, expires_at, reviewed_by)
                VALUES (%s, %s, 'APPROVED', %s, %s, %s, 'SYSTEM_GENERATOR')
                """,
                (
                    party["party_id"],
                    factory.random.choice(["BASIC", "STANDARD", "ENHANCED"]),
                    factory.random.choice(["LOW", "LOW", "MEDIUM", "HIGH"]),
                    utc_now() - timedelta(days=factory.random.randint(1, 60)),
                    utc_now() + timedelta(days=365),
                ),
            )
            party["customer_id"] = customer_id
            party["customer_code"] = f"CUST-{idx:06d}"
            customers.append(party)

        destination_pool = ["US", "MX", "SV", "HN"]
        for idx in range(1, volume["beneficiaries"] + 1):
            country_code = factory.random.choice(destination_pool)
            party = insert_party(cur, maps, factory, idx, country_code, "BEN")
            cur.execute(
                """
                INSERT INTO customer.beneficiary_profile
                    (party_id, beneficiary_code, beneficiary_status)
                VALUES (%s, %s, 'ACTIVE')
                RETURNING beneficiary_id
                """,
                (party["party_id"], f"BEN-{idx:06d}"),
            )
            beneficiary_id = cur.fetchone()["beneficiary_id"]
            currency_code = {"US": "USD", "MX": "MXN", "SV": "USD", "HN": "HNL"}[country_code]
            cur.execute(
                """
                INSERT INTO customer.beneficiary_payout_method
                    (beneficiary_id, payout_method_type, institution_name, institution_code,
                     account_identifier_encrypted, account_identifier_masked, currency_id,
                     country_id, is_primary, is_verified)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true, true)
                RETURNING payout_method_id
                """,
                (
                    beneficiary_id,
                    factory.random.choice(["BANK_ACCOUNT", "MOBILE_WALLET", "CASH_PICKUP"]),
                    factory.random.choice(["Global Bank", "Union Network", "Payout Wallet"]),
                    f"INST-{country_code}",
                    sha256(f"BEN-{idx:06d}-ACCOUNT"),
                    f"****{factory.random.randint(1000, 9999)}",
                    maps["currencies"][currency_code],
                    maps["countries"][country_code],
                ),
            )
            payout_method_id = cur.fetchone()["payout_method_id"]
            party.update(
                {
                    "beneficiary_id": beneficiary_id,
                    "beneficiary_code": f"BEN-{idx:06d}",
                    "payout_method_id": payout_method_id,
                    "currency_code": currency_code,
                }
            )
            beneficiaries.append(party)

        for customer in customers:
            linked = factory.random.sample(beneficiaries, k=factory.random.randint(1, min(4, len(beneficiaries))))
            for beneficiary in linked:
                cur.execute(
                    """
                    INSERT INTO customer.customer_beneficiary
                        (customer_id, beneficiary_id, relationship_type, alias, is_favorite)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        customer["customer_id"],
                        beneficiary["beneficiary_id"],
                        factory.random.choice(["FAMILY", "FRIEND", "BUSINESS", "OTHER"]),
                        beneficiary["legal_name"].split()[0],
                        factory.random.random() < 0.25,
                    ),
                )
    return customers, beneficiaries


# Genera corredores, reglas comerciales y tasas historicas FX.
def generate_fx(conn, cfg: GeneratorConfig, maps, factory: DataFactory) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    corridor_specs = [
        ("GT-US-GTQ-USD", "GT", "US", "GTQ", "USD", Decimal("0.1285")),
        ("GT-MX-GTQ-MXN", "GT", "MX", "GTQ", "MXN", Decimal("2.3200")),
        ("GT-SV-GTQ-USD", "GT", "SV", "GTQ", "USD", Decimal("0.1282")),
        ("US-GT-USD-GTQ", "US", "GT", "USD", "GTQ", Decimal("7.7600")),
        ("MX-GT-MXN-GTQ", "MX", "GT", "MXN", "GTQ", Decimal("0.4300")),
        ("HN-US-HNL-USD", "HN", "US", "HNL", "USD", Decimal("0.0405")),
    ]
    corridors = []
    rates_by_pair: dict[int, list[dict[str, Any]]] = defaultdict(list)
    provider_id = maps["fx_providers"]["ACADEMIC_FX"]
    with conn.cursor() as cur:
        for code, origin, destination, send_currency, payout_currency, base_rate in corridor_specs:
            cur.execute(
                """
                INSERT INTO fx.currency_pair (base_currency_id, quote_currency_id)
                VALUES (%s, %s)
                ON CONFLICT (base_currency_id, quote_currency_id)
                DO UPDATE SET base_currency_id = EXCLUDED.base_currency_id
                RETURNING currency_pair_id
                """,
                (maps["currencies"][send_currency], maps["currencies"][payout_currency]),
            )
            currency_pair_id = cur.fetchone()["currency_pair_id"]
            cur.execute(
                """
                INSERT INTO fx.remittance_corridor
                    (corridor_code, origin_country_id, destination_country_id, send_currency_id, payout_currency_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING corridor_id
                """,
                (
                    code,
                    maps["countries"][origin],
                    maps["countries"][destination],
                    maps["currencies"][send_currency],
                    maps["currencies"][payout_currency],
                ),
            )
            corridor_id = cur.fetchone()["corridor_id"]
            channel_id = maps["channels"][factory.random.choice(["WEB", "MOBILE", "AGENT"])]
            cur.execute(
                """
                INSERT INTO fx.corridor_limit_rule
                    (corridor_id, channel_id, minimum_amount, maximum_amount, period_limit_amount, valid_from)
                VALUES (%s, %s, 50, 25000, 50000, %s)
                """,
                (corridor_id, channel_id, utc_now() - timedelta(days=90)),
            )
            cur.execute(
                """
                INSERT INTO fx.corridor_pricing_rule
                    (corridor_id, channel_id, fee_type, fixed_fee_amount,
                     percentage_fee_rate, tax_rate, spread_rate, valid_from)
                VALUES (%s, %s, 'MIXED', %s, %s, %s, %s, %s)
                RETURNING pricing_rule_id
                """,
                (
                    corridor_id,
                    channel_id,
                    money(factory.random.uniform(8, 25)),
                    Decimal("0.008000"),
                    Decimal("0.001200"),
                    Decimal("0.004000"),
                    utc_now() - timedelta(days=90),
                ),
            )
            pricing_rule_id = cur.fetchone()["pricing_rule_id"]
            if currency_pair_id not in rates_by_pair:
                for days_ago in range(cfg.raw["volume"]["fx_history_days"], -1, -1):
                    observed = (utc_now() - timedelta(days=days_ago)).replace(hour=12, minute=0, second=0)
                    drift = Decimal(str(factory.random.uniform(-0.015, 0.015)))
                    market = rate(base_rate * (Decimal("1") + drift))
                    cur.execute(
                        """
                        INSERT INTO fx.exchange_rate
                            (provider_id, currency_pair_id, market_rate, bid_rate, ask_rate,
                             valid_from_utc, valid_to_utc, provider_timestamp, source_reference)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING exchange_rate_id
                        """,
                        (
                            provider_id,
                            currency_pair_id,
                            market,
                            rate(market * Decimal("0.9990")),
                            rate(market * Decimal("1.0010")),
                            observed,
                            observed + timedelta(hours=24),
                            observed,
                            f"FX-{send_currency}-{payout_currency}-{observed.date()}",
                        ),
                    )
                    exchange_rate_id = cur.fetchone()["exchange_rate_id"]
                    rates_by_pair[currency_pair_id].append(
                        {
                            "exchange_rate_id": exchange_rate_id,
                            "currency_pair_id": currency_pair_id,
                            "market_rate": market,
                            "observed_at": observed,
                            "provider_code": "ACADEMIC_FX",
                            "currency_pair": f"{send_currency}-{payout_currency}",
                            "base_currency": send_currency,
                            "quote_currency": payout_currency,
                        }
                    )
            corridors.append(
                {
                    "corridor_id": corridor_id,
                    "corridor_code": code,
                    "origin": origin,
                    "destination": destination,
                    "send_currency": send_currency,
                    "payout_currency": payout_currency,
                    "currency_pair_id": currency_pair_id,
                    "pricing_rule_id": pricing_rule_id,
                }
            )
    return corridors, rates_by_pair


# Selecciona un estado final simulado usando una distribucion academica.
def choose_target_status(factory: DataFactory) -> str:
    roll = factory.random.random()
    if roll < 0.45:
        return "PAID"
    if roll < 0.70:
        return "SETTLED"
    if roll < 0.85:
        return factory.random.choice(["AUTHORIZED", "FUNDED", "SENT_TO_PARTNER", "AVAILABLE_FOR_PAYOUT"])
    if roll < 0.93:
        return "UNDER_REVIEW"
    return factory.random.choice(["REJECTED", "CANCELLED", "REVERSED", "EXPIRED"])


# Construye eventos basicos para representar el ciclo de vida de una remesa.
def build_events(factory: DataFactory, remittance_id: int, status_path: list[str], created_at: datetime) -> list[dict[str, Any]]:
    events = [
        {
            "event_id": factory.event_id(),
            "aggregate_type": "REMITTANCE",
            "aggregate_id": remittance_id,
            "event_type": "REMITTANCE_CREATED",
            "event_version": 1,
            "payload": {"remittance_id": remittance_id},
            "occurred_at": created_at,
        }
    ]
    for offset, status in enumerate(status_path[1:], start=1):
        events.append(
            {
                "event_id": factory.event_id(),
                "aggregate_type": "REMITTANCE",
                "aggregate_id": remittance_id,
                "event_type": "REMITTANCE_STATUS_CHANGED",
                "event_version": 1,
                "payload": {"remittance_id": remittance_id, "new_status": status},
                "occurred_at": created_at + timedelta(minutes=offset * 7),
            }
        )
    return events


# Genera remesas completas con cotizacion, detalle financiero, estados, riesgo y eventos.
def generate_remittances(conn, cfg, maps, factory, customers, beneficiaries, corridors, rates_by_pair):
    remittances = []
    movements = []
    risk_rows = []
    fraud_docs = []
    aml_alert_count = 0
    status_counter: Counter[str] = Counter()
    linked_by_customer: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for beneficiary in beneficiaries:
        linked_by_customer[factory.random.choice(customers)["customer_id"]].append(beneficiary)

    with conn.cursor() as cur:
        for idx in range(1, cfg.raw["volume"]["remittances"] + 1):
            customer = factory.random.choice(customers)
            possible_beneficiaries = linked_by_customer.get(customer["customer_id"]) or beneficiaries
            beneficiary = factory.random.choice(possible_beneficiaries)
            corridor_options = [c for c in corridors if c["destination"] == beneficiary["country_code"]]
            corridor = factory.random.choice(corridor_options or corridors)
            exchange_rate = factory.random.choice(rates_by_pair[corridor["currency_pair_id"]][-10:])
            send_amount = money(factory.random.uniform(150, 5000))
            is_suspicious = factory.random.random() < cfg.raw["risk"]["fraud_rate"]
            if is_suspicious:
                send_amount = money(factory.random.uniform(7000, 18000))
            fee_amount = money(Decimal("12.00") + send_amount * Decimal("0.0080"))
            tax_amount = money(fee_amount * Decimal("0.12"))
            market_rate = exchange_rate["market_rate"]
            applied_rate = rate(market_rate * Decimal("0.9960"))
            payout_amount = money(send_amount * applied_rate)
            spread_amount = money(send_amount * (market_rate - applied_rate))
            fx_gain = money(spread_amount * Decimal("0.65"))
            total_charged = money(send_amount + fee_amount + tax_amount)
            created_at = utc_now() - timedelta(days=factory.random.randint(0, 29), minutes=factory.random.randint(0, 1440))
            quoted_at = created_at - timedelta(minutes=3)
            expires_at = quoted_at + timedelta(minutes=20)
            channel_code = factory.random.choice(["WEB", "MOBILE", "AGENT"])
            target_status = choose_target_status(factory)
            if is_suspicious:
                target_status = factory.random.choice(["UNDER_REVIEW", "REJECTED", "PAID", "SETTLED"])
            status_path = STATUS_PATHS[target_status]
            status_counter[target_status] += 1

            cur.execute(
                """
                INSERT INTO fx.fx_quote
                    (quote_code, corridor_id, customer_id, exchange_rate_id, pricing_rule_id,
                     send_amount, market_exchange_rate, offered_exchange_rate, fee_amount,
                     tax_amount, payout_amount, total_charged_amount, quoted_at, expires_at,
                     accepted_at, quote_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACCEPTED')
                RETURNING fx_quote_id
                """,
                (
                    f"QTE-{idx:08d}",
                    corridor["corridor_id"],
                    customer["customer_id"],
                    exchange_rate["exchange_rate_id"],
                    corridor["pricing_rule_id"],
                    send_amount,
                    market_rate,
                    applied_rate,
                    fee_amount,
                    tax_amount,
                    payout_amount,
                    total_charged,
                    quoted_at,
                    expires_at,
                    quoted_at + timedelta(minutes=2),
                ),
            )
            fx_quote_id = cur.fetchone()["fx_quote_id"]
            cur.execute(
                """
                INSERT INTO remittance.remittance_order
                    (remittance_code, customer_id, beneficiary_id, corridor_id, fx_quote_id,
                     channel_id, current_status_id, purpose_id, source_of_funds_id,
                     customer_reference, origin_timezone, destination_timezone,
                     captured_local_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING remittance_id
                """,
                (
                    f"REM-{idx:08d}",
                    customer["customer_id"],
                    beneficiary["beneficiary_id"],
                    corridor["corridor_id"],
                    fx_quote_id,
                    maps["channels"][channel_code],
                    maps["statuses"]["DRAFT"],
                    factory.random.choice(list(maps["purposes"].values())),
                    factory.random.choice(list(maps["sources"].values())),
                    f"REF-{idx:08d}",
                    "America/Guatemala",
                    {"US": "America/New_York", "MX": "America/Mexico_City", "SV": "America/El_Salvador", "HN": "America/Tegucigalpa"}.get(corridor["destination"], "UTC"),
                    created_at.replace(tzinfo=None),
                    created_at,
                ),
            )
            remittance_id = cur.fetchone()["remittance_id"]
            cur.execute(
                """
                INSERT INTO remittance.remittance_financial_detail
                    (remittance_id, send_currency_id, send_amount, market_exchange_rate,
                     applied_exchange_rate, exchange_rate_timestamp_utc, payout_currency_id,
                     payout_amount, fee_amount, tax_amount, other_charge_amount,
                     fx_spread_amount, fx_gain_amount, total_charged_amount,
                     settlement_currency_id, settlement_amount, calculation_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s, %s, 'GEN-1')
                """,
                (
                    remittance_id,
                    maps["currencies"][corridor["send_currency"]],
                    send_amount,
                    market_rate,
                    applied_rate,
                    exchange_rate["observed_at"],
                    maps["currencies"][corridor["payout_currency"]],
                    payout_amount,
                    fee_amount,
                    tax_amount,
                    spread_amount,
                    fx_gain,
                    total_charged,
                    maps["currencies"][corridor["payout_currency"]],
                    payout_amount,
                ),
            )
            cur.execute(
                """
                INSERT INTO remittance.remittance_payout_instruction
                    (remittance_id, payout_method_id, payout_method_type, institution_name,
                     institution_code, account_identifier_masked, destination_reference)
                VALUES (%s, %s, 'BANK_ACCOUNT', 'Global Bank', %s, %s, %s)
                """,
                (
                    remittance_id,
                    beneficiary["payout_method_id"],
                    f"INST-{corridor['destination']}",
                    f"****{factory.random.randint(1000, 9999)}",
                    f"DEST-{idx:08d}",
                ),
            )

            previous = None
            for step, status in enumerate(status_path):
                cur.execute(
                    """
                    INSERT INTO remittance.remittance_status_history
                        (remittance_id, previous_status_id, new_status_id, status_reason_id,
                         reason_description, actor_type, actor_reference, changed_at,
                         local_changed_at, timezone_name)
                    VALUES (%s, %s, %s, %s, %s, 'SYSTEM', 'GENERATOR', %s, %s, %s)
                    """,
                    (
                        remittance_id,
                        maps["statuses"].get(previous) if previous else None,
                        maps["statuses"][status],
                        maps["reasons"].get("INITIAL_CREATION" if step == 0 else "COMPLIANCE_APPROVED"),
                        f"Synthetic transition to {status}",
                        created_at + timedelta(minutes=step * 7),
                        (created_at + timedelta(minutes=step * 7)).replace(tzinfo=None),
                        "America/Guatemala",
                    ),
                )
                previous = status

            cur.execute(
                """
                INSERT INTO compliance.travel_rule_record
                    (remittance_id, originator_party_id, originator_name,
                     originator_account_or_reference, originator_document_type,
                     originator_document_number_encrypted, originator_address,
                     originator_country_id, beneficiary_party_id, beneficiary_name,
                     beneficiary_account_or_reference, beneficiary_document_type,
                     beneficiary_document_number_encrypted, beneficiary_address,
                     beneficiary_country_id, completeness_status, validated_at)
                VALUES (%s, %s, %s, %s, 'NATIONAL_ID', %s, %s, %s, %s, %s, %s,
                        'NATIONAL_ID', %s, %s, %s, 'COMPLETE', %s)
                """,
                (
                    remittance_id,
                    customer["party_id"],
                    customer["legal_name"],
                    f"CUST-{customer['customer_id']}",
                    sha256(f"DOC-{customer['party_id']}"),
                    "Direccion registrada originador",
                    customer["country_id"],
                    beneficiary["party_id"],
                    beneficiary["legal_name"],
                    f"BEN-{beneficiary['beneficiary_id']}",
                    sha256(f"DOC-{beneficiary['party_id']}"),
                    "Direccion registrada beneficiario",
                    beneficiary["country_id"],
                    created_at + timedelta(minutes=5),
                ),
            )

            if target_status not in {"REJECTED", "CANCELLED", "EXPIRED", "UNDER_REVIEW"}:
                for movement_code, amount, currency in [
                    ("CUSTOMER_CHARGE", total_charged, corridor["send_currency"]),
                    ("FEE_REVENUE", fee_amount, corridor["send_currency"]),
                    ("TAX_WITHHELD", tax_amount, corridor["send_currency"]),
                    ("FX_SPREAD_REVENUE", spread_amount, corridor["send_currency"]),
                    ("PAYOUT_OBLIGATION", payout_amount, corridor["payout_currency"]),
                ]:
                    cur.execute(
                        """
                        INSERT INTO remittance.remittance_financial_movement
                            (remittance_id, movement_type_id, currency_id, amount,
                             movement_status, external_reference, occurred_at, description)
                        VALUES (%s, %s, %s, %s, 'CONFIRMED', %s, %s, %s)
                        RETURNING financial_movement_id
                        """,
                        (
                            remittance_id,
                            maps["movement_types"][movement_code],
                            maps["currencies"][currency],
                            amount,
                            f"{movement_code}-{idx:08d}",
                            created_at + timedelta(minutes=20),
                            f"Synthetic {movement_code}",
                        ),
                    )
                    movement_id = cur.fetchone()["financial_movement_id"]
                    movements.append(
                        {
                            "financial_movement_id": movement_id,
                            "remittance_id": remittance_id,
                            "movement_code": movement_code,
                            "amount": amount,
                            "currency": currency,
                            "status": target_status,
                        }
                    )
                if target_status in {"PAID", "SETTLED"}:
                    cur.execute(
                        """
                        INSERT INTO remittance.remittance_financial_movement
                            (remittance_id, movement_type_id, currency_id, amount,
                             movement_status, external_reference, occurred_at, description)
                        VALUES (%s, %s, %s, %s, 'CONFIRMED', %s, %s, 'Synthetic partner payout')
                        RETURNING financial_movement_id
                        """,
                        (
                            remittance_id,
                            maps["movement_types"]["PARTNER_PAYOUT"],
                            maps["currencies"][corridor["payout_currency"]],
                            payout_amount,
                            f"PARTNER_PAYOUT-{idx:08d}",
                            created_at + timedelta(minutes=45),
                        ),
                    )
                    movement_id = cur.fetchone()["financial_movement_id"]
                    movements.append(
                        {
                            "financial_movement_id": movement_id,
                            "remittance_id": remittance_id,
                            "movement_code": "PARTNER_PAYOUT",
                            "amount": payout_amount,
                            "currency": corridor["payout_currency"],
                            "status": target_status,
                        }
                    )

            risk_score = Decimal("0.25")
            risk_level = "LOW"
            decision = "APPROVE"
            if target_status == "UNDER_REVIEW" or is_suspicious:
                risk_score = Decimal(str(round(factory.random.uniform(0.65, 0.92), 4)))
                risk_level = "HIGH" if risk_score < Decimal("0.85") else "CRITICAL"
                decision = "REVIEW" if target_status != "REJECTED" else "REJECT"
            cur.execute(
                """
                INSERT INTO compliance.risk_assessment
                    (remittance_id, assessment_version, risk_score, risk_level,
                     decision, evaluated_at, model_reference)
                VALUES (%s, 'RULES-1', %s, %s, %s, %s, 'SYNTHETIC_RULES')
                RETURNING risk_assessment_id
                """,
                (remittance_id, risk_score, risk_level, decision, created_at + timedelta(minutes=4)),
            )
            risk_assessment_id = cur.fetchone()["risk_assessment_id"]
            if risk_level in {"HIGH", "CRITICAL"}:
                reason_code = factory.random.choice(["HIGH_AMOUNT", "HIGH_VELOCITY", "NEW_BENEFICIARY", "HIGH_RISK_CORRIDOR"])
                cur.execute(
                    """
                    INSERT INTO compliance.risk_assessment_reason
                        (risk_assessment_id, risk_reason_id)
                    VALUES (%s, %s)
                    """,
                    (risk_assessment_id, maps["risk_reasons"][reason_code]),
                )
                fraud_docs.append(
                    {
                        "_id": factory.event_id(),
                        "signal_id": factory.event_id(),
                        "remittance_id": remittance_id,
                        "customer_id": customer["customer_id"],
                        "signal_type": reason_code,
                        "severity": "CRITICAL" if risk_level == "CRITICAL" else "HIGH",
                        "score": float(risk_score),
                        "rule": {"rule_code": f"FRD-{reason_code}", "rule_version": "1.0"},
                        "features": {"send_amount": float(send_amount), "corridor": corridor["corridor_code"]},
                        "decision_context": {
                            "recommended_action": decision,
                            "postgres_risk_assessment_id": risk_assessment_id,
                        },
                        "detected_at": created_at + timedelta(minutes=4),
                        "source_event_id": factory.event_id(),
                        "status": "OPEN" if decision == "REVIEW" else "CONFIRMED",
                    }
                )

            if risk_level in {"HIGH", "CRITICAL"} and factory.random.random() < 0.55:
                cur.execute(
                    """
                    INSERT INTO compliance.aml_screening
                        (screening_provider_id, screening_type, screening_status,
                         match_score, request_reference, screened_at)
                    VALUES (%s, %s, 'MATCH', %s, %s, %s)
                    RETURNING aml_screening_id
                    """,
                    (
                        maps["screening_providers"]["INTERNAL_AML"],
                        factory.random.choice(["VELOCITY", "TRANSACTION", "SANCTIONS"]),
                        Decimal(str(round(factory.random.uniform(0.70, 0.98), 4))),
                        f"AML-{idx:08d}",
                        created_at + timedelta(minutes=3),
                    ),
                )
                screening_id = cur.fetchone()["aml_screening_id"]
                cur.execute(
                    "INSERT INTO compliance.aml_screening_party (aml_screening_id, party_id, subject_role) VALUES (%s, %s, 'ORIGINATOR')",
                    (screening_id, customer["party_id"]),
                )
                cur.execute(
                    "INSERT INTO compliance.aml_screening_remittance (aml_screening_id, remittance_id) VALUES (%s, %s)",
                    (screening_id, remittance_id),
                )
                cur.execute(
                    """
                    INSERT INTO compliance.aml_alert
                        (aml_screening_id, alert_type, severity, alert_status,
                         decision, decision_reason, assigned_to, created_at, resolved_at)
                    VALUES (%s, %s, %s, %s, %s, %s, 'COMPLIANCE_TEAM', %s, %s)
                    """,
                    (
                        screening_id,
                        "SYNTHETIC_RISK",
                        risk_level,
                        "UNDER_REVIEW" if decision == "REVIEW" else "CONFIRMED",
                        None if decision == "REVIEW" else decision,
                        None if decision == "REVIEW" else "Synthetic decision",
                        created_at + timedelta(minutes=6),
                        None if decision == "REVIEW" else created_at + timedelta(minutes=12),
                    ),
                )
                aml_alert_count += 1

            for event in build_events(factory, remittance_id, status_path, created_at):
                cur.execute(
                    """
                    INSERT INTO integration.outbox_event
                        (event_id, aggregate_type, aggregate_id, event_type, event_version,
                         payload, occurred_at, publication_status, published_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'PUBLISHED', %s)
                    """,
                    (
                        event["event_id"],
                        event["aggregate_type"],
                        event["aggregate_id"],
                        event["event_type"],
                        event["event_version"],
                        Jsonb(event["payload"]),
                        event["occurred_at"],
                        event["occurred_at"] + timedelta(seconds=2),
                    ),
                )

            remittances.append(
                {
                    "remittance_id": remittance_id,
                    "remittance_code": f"REM-{idx:08d}",
                    "customer_id": customer["customer_id"],
                    "beneficiary_id": beneficiary["beneficiary_id"],
                    "customer_country": customer["country_code"],
                    "beneficiary_country": beneficiary["country_code"],
                    "corridor_code": corridor["corridor_code"],
                    "send_currency": corridor["send_currency"],
                    "payout_currency": corridor["payout_currency"],
                    "send_amount": send_amount,
                    "payout_amount": payout_amount,
                    "fee_amount": fee_amount,
                    "tax_amount": tax_amount,
                    "fx_spread_amount": spread_amount,
                    "total_charged_amount": total_charged,
                    "applied_exchange_rate": applied_rate,
                    "current_status": target_status,
                    "risk_level": risk_level,
                    "decision": decision,
                    "created_at": created_at,
                    "paid_at": created_at + timedelta(minutes=45) if target_status in {"PAID", "SETTLED"} else None,
                    "is_suspicious": is_suspicious or risk_level in {"HIGH", "CRITICAL"},
                }
            )
    return remittances, movements, fraud_docs, aml_alert_count, status_counter


# Agrupa movimientos pagados en lotes de liquidacion simulados.
def generate_settlement(conn, cfg, maps, factory, corridors, movements):
    settlement_movements = [m for m in movements if m["movement_code"] == "PARTNER_PAYOUT"]
    batches = []
    with conn.cursor() as cur:
        country_id = maps["countries"]["US"]
        cur.execute(
            """
            INSERT INTO settlement.correspondent
                (correspondent_code, correspondent_name, country_id, correspondent_type,
                 timezone_name, settlement_frequency)
            VALUES ('BANK-US-01', 'Global Bank US', %s, 'BANK', 'America/New_York', 'DAILY')
            RETURNING correspondent_id
            """,
            (country_id,),
        )
        correspondent_id = cur.fetchone()["correspondent_id"]
        for corridor in corridors:
            cur.execute(
                """
                INSERT INTO settlement.correspondent_corridor
                    (correspondent_id, corridor_id, payout_method_type, priority_order, valid_from)
                VALUES (%s, %s, 'BANK_ACCOUNT', 1, %s)
                """,
                (correspondent_id, corridor["corridor_id"], date.today() - timedelta(days=90)),
            )
        if not settlement_movements:
            return []
        chunks = max(1, min(cfg.raw["volume"]["settlement_batches"], len(settlement_movements)))
        size = max(1, len(settlement_movements) // chunks)
        for idx in range(0, len(settlement_movements), size):
            subset = settlement_movements[idx: idx + size]
            if not subset:
                continue
            expected = sum((m["amount"] for m in subset), Decimal("0.0000"))
            reported = expected
            batch_number = len(batches) + 1
            cur.execute(
                """
                INSERT INTO settlement.settlement_batch
                    (batch_code, correspondent_id, settlement_currency_id, period_start_at,
                     period_end_at, expected_amount, reported_amount, difference_amount,
                     batch_status, settled_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 0, 'SETTLED', %s)
                RETURNING settlement_batch_id
                """,
                (
                    f"SET-{batch_number:06d}",
                    correspondent_id,
                    maps["currencies"][subset[0]["currency"]],
                    utc_now() - timedelta(days=1),
                    utc_now(),
                    money(expected),
                    money(reported),
                    utc_now(),
                ),
            )
            batch_id = cur.fetchone()["settlement_batch_id"]
            for movement in subset:
                cur.execute(
                    """
                    INSERT INTO settlement.settlement_item
                        (settlement_batch_id, financial_movement_id, expected_amount,
                         reported_amount, difference_amount, item_status,
                         external_reference, reconciled_at)
                    VALUES (%s, %s, %s, %s, 0, 'MATCHED', %s, %s)
                    """,
                    (
                        batch_id,
                        movement["financial_movement_id"],
                        movement["amount"],
                        movement["amount"],
                        f"SET-ITEM-{movement['financial_movement_id']}",
                        utc_now(),
                    ),
                )
            batches.append(
                {
                    "settlement_batch_id": batch_id,
                    "batch_code": f"SET-{batch_number:06d}",
                    "correspondent_id": correspondent_id,
                    "currency": subset[0]["currency"],
                    "item_count": len(subset),
                    "expected_amount": money(expected),
                    "reported_amount": money(reported),
                    "difference_amount": money(0),
                    "status": "SETTLED",
                }
            )
    return batches


# Construye documentos derivados para las colecciones analiticas de MongoDB.
def build_mongo_products(factory, remittances, corridors, rates_by_pair, fraud_docs, batches):
    products: dict[str, list[dict[str, Any]]] = {
        "remittance_events": [],
        "remittance_lifecycle": [],
        "fx_rate_timeseries": [],
        "customer_behavior_profiles": [],
        "fraud_signals": fraud_docs,
        "compliance_case_snapshots": [],
        "corridor_daily_metrics": [],
        "settlement_status": [],
    }
    for remittance in remittances:
        event_id = factory.event_id()
        products["remittance_events"].append(
            {
                "_id": event_id,
                "event_id": event_id,
                "event_type": "REMITTANCE_SNAPSHOT_BUILT",
                "event_version": 1,
                "aggregate_type": "REMITTANCE",
                "aggregate_id": remittance["remittance_id"],
                "remittance_id": remittance["remittance_id"],
                "occurred_at": remittance["created_at"],
                "ingested_at": utc_now(),
                "correlation_id": factory.event_id(),
                "source": {"database": "globalremit", "schema": "integration", "table": "outbox_event"},
                "payload": {"status": remittance["current_status"]},
                "data_classification": "INTERNAL",
            }
        )
        products["remittance_lifecycle"].append(
            {
                "_id": remittance["remittance_id"],
                "remittance_id": remittance["remittance_id"],
                "remittance_code": remittance["remittance_code"],
                "version": 1,
                "current_status": remittance["current_status"],
                "corridor": {
                    "corridor_code": remittance["corridor_code"],
                    "send_currency": remittance["send_currency"],
                    "payout_currency": remittance["payout_currency"],
                },
                "parties": {
                    "customer_id": remittance["customer_id"],
                    "beneficiary_id": remittance["beneficiary_id"],
                    "customer_country": remittance["customer_country"],
                    "beneficiary_country": remittance["beneficiary_country"],
                },
                "financial": {
                    "send_amount": float(remittance["send_amount"]),
                    "applied_exchange_rate": float(remittance["applied_exchange_rate"]),
                    "payout_amount": float(remittance["payout_amount"]),
                    "fee_amount": float(remittance["fee_amount"]),
                    "tax_amount": float(remittance["tax_amount"]),
                    "fx_spread_amount": float(remittance["fx_spread_amount"]),
                    "total_charged_amount": float(remittance["total_charged_amount"]),
                },
                "compliance": {
                    "kyc_status": "APPROVED",
                    "aml_status": "MATCH" if remittance["is_suspicious"] else "CLEAR",
                    "risk_level": remittance["risk_level"],
                    "travel_rule_status": "COMPLETE",
                },
                "timestamps": {
                    "created_at": remittance["created_at"],
                    "paid_at": remittance["paid_at"],
                },
                "status_timeline": [{"status": remittance["current_status"], "at": remittance["created_at"]}],
                "last_event_id": event_id,
                "updated_at": utc_now(),
            }
        )
    for rates in rates_by_pair.values():
        for row in rates:
            products["fx_rate_timeseries"].append(
                {
                    "observed_at": row["observed_at"],
                    "metadata": {
                        "provider_code": row["provider_code"],
                        "currency_pair": row["currency_pair"],
                        "base_currency": row["base_currency"],
                        "quote_currency": row["quote_currency"],
                    },
                    "exchange_rate_id": row["exchange_rate_id"],
                    "market_rate": float(row["market_rate"]),
                    "received_at": row["observed_at"],
                    "source_event_id": factory.event_id(),
                }
            )
    by_customer = defaultdict(list)
    for remittance in remittances:
        by_customer[remittance["customer_id"]].append(remittance)
    for customer_id, items in by_customer.items():
        last_24h = [r for r in items if r["created_at"] >= utc_now() - timedelta(days=1)]
        products["customer_behavior_profiles"].append(
            {
                "_id": customer_id,
                "customer_id": customer_id,
                "profile_version": 1,
                "windows": {
                    "last_24h": {
                        "remittance_count": len(last_24h),
                        "send_amount_base": float(sum((r["send_amount"] for r in last_24h), Decimal("0"))),
                        "distinct_beneficiaries": len({r["beneficiary_id"] for r in last_24h}),
                        "distinct_countries": len({r["beneficiary_country"] for r in last_24h}),
                    },
                    "last_30d": {
                        "remittance_count": len(items),
                        "send_amount_base": float(sum((r["send_amount"] for r in items), Decimal("0"))),
                        "distinct_beneficiaries": len({r["beneficiary_id"] for r in items}),
                        "distinct_countries": len({r["beneficiary_country"] for r in items}),
                    },
                },
                "usual_patterns": {
                    "corridors": sorted({r["corridor_code"] for r in items})[:5],
                    "channels": ["WEB", "MOBILE"],
                    "active_hours_utc": [14, 15, 16],
                },
                "risk_features": {
                    "velocity_score": min(1.0, len(last_24h) / 5),
                    "amount_deviation_score": min(1.0, float(max(r["send_amount"] for r in items)) / 15000),
                    "new_beneficiary_ratio": min(1.0, len({r["beneficiary_id"] for r in items}) / max(1, len(items))),
                },
                "last_event_id": factory.event_id(),
                "computed_at": utc_now(),
                "expires_at": utc_now() + timedelta(days=90),
            }
        )
    by_corridor_day = defaultdict(list)
    for remittance in remittances:
        by_corridor_day[(remittance["corridor_code"], remittance["created_at"].date())].append(remittance)
    for (corridor_code, metric_date), items in by_corridor_day.items():
        products["corridor_daily_metrics"].append(
            {
                "_id": f"{corridor_code}|{metric_date}",
                "corridor_code": corridor_code,
                "metric_date": datetime.combine(metric_date, datetime.min.time(), tzinfo=UTC),
                "send_currency": items[0]["send_currency"],
                "payout_currency": items[0]["payout_currency"],
                "counts": dict(Counter(r["current_status"] for r in items)),
                "amounts": {
                    "send_amount": float(sum((r["send_amount"] for r in items), Decimal("0"))),
                    "payout_amount": float(sum((r["payout_amount"] for r in items), Decimal("0"))),
                    "fee_amount": float(sum((r["fee_amount"] for r in items), Decimal("0"))),
                    "tax_amount": float(sum((r["tax_amount"] for r in items), Decimal("0"))),
                    "fx_spread_amount": float(sum((r["fx_spread_amount"] for r in items), Decimal("0"))),
                },
                "service": {"average_minutes_to_pay": 35.0, "p95_minutes_to_pay": 70.0},
                "risk": {
                    "alert_count": sum(1 for r in items if r["is_suspicious"]),
                    "high_risk_count": sum(1 for r in items if r["risk_level"] in {"HIGH", "CRITICAL"}),
                },
                "calculation_version": 1,
                "computed_at": utc_now(),
                "source_watermark": utc_now(),
            }
        )
    for batch in batches:
        products["settlement_status"].append(
            {
                "_id": batch["settlement_batch_id"],
                "settlement_batch_id": batch["settlement_batch_id"],
                "batch_code": batch["batch_code"],
                "correspondent": {
                    "correspondent_id": batch["correspondent_id"],
                    "correspondent_code": "BANK-US-01",
                    "country": "US",
                },
                "currency": batch["currency"],
                "period": {"start_at": utc_now() - timedelta(days=1), "end_at": utc_now()},
                "totals": {
                    "item_count": batch["item_count"],
                    "expected_amount": float(batch["expected_amount"]),
                    "reported_amount": float(batch["reported_amount"]),
                    "difference_amount": float(batch["difference_amount"]),
                },
                "status": batch["status"],
                "exceptions": [],
                "last_event_id": factory.event_id(),
                "updated_at": utc_now(),
            }
        )
    for doc in fraud_docs[:100]:
        products["compliance_case_snapshots"].append(
            {
                "_id": abs(hash(doc["signal_id"])) % 1000000000,
                "case_id": abs(hash(doc["signal_id"])) % 1000000000,
                "case_type": "AML_ALERT",
                "status": "UNDER_REVIEW" if doc["status"] == "OPEN" else "CLOSED",
                "severity": doc["severity"],
                "remittance_id": doc["remittance_id"],
                "party_refs": [{"party_id": doc["customer_id"], "role": "ORIGINATOR"}],
                "screening": {"screening_type": doc["signal_type"], "provider_code": "INTERNAL_AML", "match_score": doc["score"]},
                "decision": None if doc["status"] == "OPEN" else doc["decision_context"]["recommended_action"],
                "assigned_team": "COMPLIANCE",
                "opened_at": doc["detected_at"],
                "updated_at": utc_now(),
                "source_event_id": doc["source_event_id"],
            }
        )
    return products


# Orquesta la generacion, carga SQL, salida JSON, carga MongoDB y reporte.
def run_generation(config: GeneratorConfig) -> dict[str, Any]:
    started = perf_counter()
    factory = DataFactory(int(config.raw["seed"]))
    metrics: dict[str, Any] = {"counts": {}, "notes": []}
    with pg_connection(config.postgres_dsn) as conn:
        if config.cleanup_generated_data:
            cleanup(conn)
        maps = load_reference_maps(conn)
        customers, beneficiaries = generate_customers(conn, config, maps, factory)
        corridors, rates_by_pair = generate_fx(conn, config, maps, factory)
        remittances, movements, fraud_docs, aml_alerts, status_counter = generate_remittances(
            conn, config, maps, factory, customers, beneficiaries, corridors, rates_by_pair
        )
        batches = generate_settlement(conn, config, maps, factory, corridors, movements)
        conn.commit()
        metrics["postgres_status"] = "loaded"
    products = build_mongo_products(factory, remittances, corridors, rates_by_pair, fraud_docs, batches)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    for collection_name, documents in products.items():
        write_json(config.output_dir / f"{collection_name}.json", documents)
    mongo_loaded = False
    mongo_message = "MongoDB disabled by configuration."
    if config.mongo_enabled:
        mongo_loaded, mongo_message = load_mongo(config.mongo_uri, config.mongo_database, products)
    metrics.update(
        {
            "mongo_status": "loaded" if mongo_loaded else mongo_message,
            "duration_seconds": round(perf_counter() - started, 2),
            "counts": {
                "customers": len(customers),
                "beneficiaries": len(beneficiaries),
                "corridors": len(corridors),
                "exchange_rates": sum(len(v) for v in rates_by_pair.values()),
                "remittances": len(remittances),
                "financial_movements": len(movements),
                "settlement_batches": len(batches),
                "mongo_documents": sum(len(v) for v in products.values()),
            },
            "status_distribution": dict(status_counter),
            "suspect_remittances": sum(1 for r in remittances if r["is_suspicious"]),
            "fraud_signals": len(fraud_docs),
            "aml_alerts": aml_alerts,
            "notes": [
                "PostgreSQL remains the transactional source of truth.",
                "MongoDB products were generated from synthetic SQL-domain records.",
                mongo_message,
            ],
        }
    )
    write_report(config.report_path, metrics)
    return metrics


# Ejecuta una prueba controlada para demostrar una restriccion de integridad.
def run_integrity_demo(config: GeneratorConfig) -> dict[str, Any]:
    with pg_connection(config.postgres_dsn) as conn:
        maps = load_reference_maps(conn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO compliance.aml_screening
                        (screening_provider_id, screening_type, screening_status,
                         match_score, request_reference, screened_at)
                    VALUES (%s, 'TRANSACTION', 'MATCH', 0.9500, 'DEMO-INVALID-AML', %s)
                    RETURNING aml_screening_id
                    """,
                    (maps["screening_providers"]["INTERNAL_AML"], utc_now()),
                )
                screening_id = cur.fetchone()["aml_screening_id"]
                cur.execute(
                    """
                    INSERT INTO compliance.aml_alert
                        (aml_screening_id, alert_type, severity, alert_status,
                         decision, decision_reason, assigned_to, created_at, resolved_at)
                    VALUES (%s, 'INTEGRITY_DEMO', 'HIGH', 'CONFIRMED',
                            'REJECT', 'Intentional invalid chronology',
                            'COMPLIANCE_TEAM', %s, %s)
                    """,
                    (
                        screening_id,
                        utc_now(),
                        utc_now() - timedelta(days=1),
                    ),
                )
        except Exception as exc:
            conn.rollback()
            message = str(exc)
            expected = "ck_alert_resolution" in message
            return {
                "mode": "integrity-demo",
                "expected_rejection": expected,
                "constraint": "ck_alert_resolution",
                "explanation": "PostgreSQL rejected an AML alert resolved before its creation date.",
                "database_message": message,
            }
        conn.rollback()
        return {
            "mode": "integrity-demo",
            "expected_rejection": False,
            "constraint": "ck_alert_resolution",
            "explanation": "The invalid row was not rejected. Review the database constraint.",
        }


# Pregunta o resuelve la modalidad de ejecucion del generador.
def resolve_mode(mode: str | None) -> str:
    if mode:
        return mode
    print("Seleccione modalidad:")
    print("1. load - cargar datos validos")
    print("2. integrity-demo - demostrar rechazo por restriccion SQL")
    try:
        choice = input("Opcion [1]: ").strip()
    except EOFError:
        choice = "1"
    return "integrity-demo" if choice == "2" else "load"


# Punto de entrada CLI para ejecutar el generador desde PowerShell.
def main() -> int:
    parser = argparse.ArgumentParser(description="Generate GlobalRemit synthetic data.")
    parser.add_argument("--config", default="07_configuracion_generador.json")
    parser.add_argument("--mode", choices=["load", "integrity-demo"])
    args = parser.parse_args()
    config = load_config(args.config)
    mode = resolve_mode(args.mode)
    try:
        if mode == "integrity-demo":
            metrics = run_integrity_demo(config)
        else:
            metrics = run_generation(config)
    except Exception as exc:
        print(f"Generation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(metrics, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
