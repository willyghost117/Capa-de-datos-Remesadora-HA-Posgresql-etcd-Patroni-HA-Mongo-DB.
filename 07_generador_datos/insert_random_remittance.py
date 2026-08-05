from __future__ import annotations

import argparse
import json
import random
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from generator.config import load_config
from generator.data_factory import money, rate, sha256, utc_now
from generator.db import fetch_map, pg_connection
from psycopg.types.json import Jsonb


STATUS_PATH = [
    "DRAFT",
    "QUOTED",
    "PENDING_COMPLIANCE",
    "AUTHORIZED",
    "FUNDED",
    "SENT_TO_PARTNER",
    "PAID",
]

STATUS_REASON_BY_STEP = {
    "DRAFT": "INITIAL_CREATION",
    "AUTHORIZED": "COMPLIANCE_APPROVED",
    "FUNDED": "FUNDS_RECEIVED",
    "SENT_TO_PARTNER": "PARTNER_ACCEPTED",
    "PAID": "PAYOUT_CONFIRMED",
}


def decimal_to_str(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return value


def load_maps(conn) -> dict[str, dict[str, Any]]:
    return {
        "currencies": fetch_map(conn, "SELECT iso_currency_code AS code, currency_id AS id FROM reference.currency", "code"),
        "channels": fetch_map(conn, "SELECT channel_code AS code, channel_id AS id FROM reference.transaction_channel", "code"),
        "statuses": fetch_map(conn, "SELECT status_code AS code, remittance_status_id AS id FROM reference.remittance_status", "code"),
        "movement_types": fetch_map(conn, "SELECT movement_type_code AS code, movement_type_id AS id FROM reference.financial_movement_type", "code"),
        "sources": fetch_map(conn, "SELECT source_code AS code, source_of_funds_id AS id FROM compliance.source_of_funds_catalog", "code"),
        "purposes": fetch_map(conn, "SELECT purpose_code AS code, purpose_id AS id FROM remittance.purpose_catalog", "code"),
        "reasons": fetch_map(conn, "SELECT reason_code AS code, status_reason_id AS id FROM remittance.status_reason_catalog", "code"),
        "screening_providers": fetch_map(conn, "SELECT provider_code AS code, screening_provider_id AS id FROM compliance.screening_provider", "code"),
    }


def fetch_random_relationship(cur) -> dict[str, Any]:
    cur.execute(
        """
        SELECT cp.customer_id,
               cp.party_id AS customer_party_id,
               pc.legal_name AS customer_name,
               customer_address.country_id AS customer_country_id,
               bp.beneficiary_id,
               bp.party_id AS beneficiary_party_id,
               pb.legal_name AS beneficiary_name,
               beneficiary_address.country_id AS beneficiary_country_id,
               bpm.payout_method_id
        FROM customer.customer_beneficiary cb
        JOIN customer.customer_profile cp
          ON cp.customer_id = cb.customer_id
         AND cp.customer_status = 'ACTIVE'
        JOIN customer.party pc
          ON pc.party_id = cp.party_id
        JOIN customer.beneficiary_profile bp
          ON bp.beneficiary_id = cb.beneficiary_id
         AND bp.beneficiary_status = 'ACTIVE'
        JOIN customer.party pb
          ON pb.party_id = bp.party_id
        JOIN LATERAL (
            SELECT country_id
            FROM customer.party_address
            WHERE party_id = pc.party_id
              AND valid_to IS NULL
            ORDER BY is_primary DESC, party_address_id
            LIMIT 1
        ) customer_address ON true
        JOIN LATERAL (
            SELECT country_id
            FROM customer.party_address
            WHERE party_id = pb.party_id
              AND valid_to IS NULL
            ORDER BY is_primary DESC, party_address_id
            LIMIT 1
        ) beneficiary_address ON true
        JOIN LATERAL (
            SELECT payout_method_id
            FROM customer.beneficiary_payout_method
            WHERE beneficiary_id = bp.beneficiary_id
              AND is_active
            ORDER BY is_primary DESC, payout_method_id
            LIMIT 1
        ) bpm ON true
        ORDER BY random()
        LIMIT 1;
        """
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("No hay clientes/beneficiarios activos para generar una remesa.")
    return row


def fetch_random_corridor(cur) -> dict[str, Any]:
    cur.execute(
        """
        SELECT rc.corridor_id,
               rc.corridor_code,
               origin.iso_alpha2_code AS origin_country,
               destination.iso_alpha2_code AS destination_country,
               sendcur.currency_id AS send_currency_id,
               sendcur.iso_currency_code AS send_currency,
               payoutcur.currency_id AS payout_currency_id,
               payoutcur.iso_currency_code AS payout_currency,
               er.exchange_rate_id,
               er.market_rate,
               er.provider_timestamp AS observed_at,
               pr.pricing_rule_id,
               COALESCE(pr.fixed_fee_amount, 0) AS fixed_fee_amount,
               COALESCE(pr.percentage_fee_rate, 0) AS percentage_fee_rate,
               COALESCE(pr.tax_rate, 0) AS tax_rate,
               COALESCE(pr.spread_rate, 0) AS spread_rate
        FROM fx.remittance_corridor rc
        JOIN reference.country origin
          ON origin.country_id = rc.origin_country_id
        JOIN reference.country destination
          ON destination.country_id = rc.destination_country_id
        JOIN reference.currency sendcur
          ON sendcur.currency_id = rc.send_currency_id
        JOIN reference.currency payoutcur
          ON payoutcur.currency_id = rc.payout_currency_id
        JOIN fx.currency_pair pair
          ON pair.base_currency_id = rc.send_currency_id
         AND pair.quote_currency_id = rc.payout_currency_id
        JOIN LATERAL (
            SELECT exchange_rate_id, market_rate, provider_timestamp
            FROM fx.exchange_rate er
            WHERE er.currency_pair_id = pair.currency_pair_id
            ORDER BY er.provider_timestamp DESC
            LIMIT 1
        ) er ON true
        JOIN LATERAL (
            SELECT pricing_rule_id, fixed_fee_amount, percentage_fee_rate, tax_rate, spread_rate
            FROM fx.corridor_pricing_rule pr
            WHERE pr.corridor_id = rc.corridor_id
              AND pr.is_active
            ORDER BY pr.valid_from DESC
            LIMIT 1
        ) pr ON true
        WHERE rc.is_active
        ORDER BY random()
        LIMIT 1;
        """
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("No hay corredores, tasas FX o reglas de precio activas.")
    return row


def insert_random_remittance(conn) -> dict[str, Any]:
    maps = load_maps(conn)
    now = utc_now()
    suffix = now.strftime("%Y%m%d%H%M%S") + f"{random.randint(1000, 9999)}"
    remittance_code = f"REM-HA-{suffix}"
    quote_code = f"QTE-HA-{suffix}"
    rng = random.Random()

    with conn.cursor() as cur:
        relationship = fetch_random_relationship(cur)
        corridor = fetch_random_corridor(cur)

        send_amount = money(rng.uniform(75, 1200))
        fixed_fee = money(corridor["fixed_fee_amount"])
        percentage_fee = Decimal(str(corridor["percentage_fee_rate"]))
        tax_rate = Decimal(str(corridor["tax_rate"]))
        spread_rate = Decimal(str(corridor["spread_rate"]))
        market_rate = rate(corridor["market_rate"])
        applied_rate = rate(market_rate * (Decimal("1") - spread_rate))
        if applied_rate <= 0:
            applied_rate = market_rate
        fee_amount = money(fixed_fee + (send_amount * percentage_fee))
        tax_amount = money(fee_amount * tax_rate)
        payout_amount = money(send_amount * applied_rate)
        spread_amount = money(send_amount * max(market_rate - applied_rate, Decimal("0")))
        fx_gain = money(spread_amount * Decimal("0.65"))
        total_charged = money(send_amount + fee_amount + tax_amount)
        quoted_at = now - timedelta(minutes=3)
        accepted_at = now - timedelta(minutes=1)
        purpose_id = rng.choice(list(maps["purposes"].values()))
        source_id = rng.choice(list(maps["sources"].values()))
        channel_code = rng.choice(["WEB", "MOBILE", "AGENT"])

        cur.execute(
            """
            INSERT INTO fx.fx_quote
                (quote_code, corridor_id, customer_id, exchange_rate_id, pricing_rule_id,
                 send_amount, market_exchange_rate, offered_exchange_rate, fee_amount,
                 tax_amount, payout_amount, total_charged_amount, quoted_at, expires_at,
                 accepted_at, quote_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACCEPTED')
            RETURNING fx_quote_id;
            """,
            (
                quote_code,
                corridor["corridor_id"],
                relationship["customer_id"],
                corridor["exchange_rate_id"],
                corridor["pricing_rule_id"],
                send_amount,
                market_rate,
                applied_rate,
                fee_amount,
                tax_amount,
                payout_amount,
                total_charged,
                quoted_at,
                quoted_at + timedelta(minutes=20),
                accepted_at,
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'America/Guatemala',
                    %s, %s, %s)
            RETURNING remittance_id;
            """,
            (
                remittance_code,
                relationship["customer_id"],
                relationship["beneficiary_id"],
                corridor["corridor_id"],
                fx_quote_id,
                maps["channels"][channel_code],
                maps["statuses"]["DRAFT"],
                purpose_id,
                source_id,
                f"FAILOVER-{suffix}",
                {
                    "US": "America/New_York",
                    "MX": "America/Mexico_City",
                    "SV": "America/El_Salvador",
                    "HN": "America/Tegucigalpa",
                }.get(corridor["destination_country"], "UTC"),
                now.replace(tzinfo=None),
                now,
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s, %s, 'HA-DEMO-1');
            """,
            (
                remittance_id,
                corridor["send_currency_id"],
                send_amount,
                market_rate,
                applied_rate,
                corridor["observed_at"],
                corridor["payout_currency_id"],
                payout_amount,
                fee_amount,
                tax_amount,
                spread_amount,
                fx_gain,
                total_charged,
                corridor["payout_currency_id"],
                payout_amount,
            ),
        )

        cur.execute(
            """
            INSERT INTO remittance.remittance_payout_instruction
                (remittance_id, payout_method_id, payout_method_type, institution_name,
                 institution_code, account_identifier_masked, destination_reference)
            VALUES (%s, %s, 'BANK_ACCOUNT', 'GlobalRemit Failover Bank', %s, %s, %s);
            """,
            (
                remittance_id,
                relationship["payout_method_id"],
                f"INST-{corridor['destination_country']}",
                f"****{rng.randint(1000, 9999)}",
                f"DEST-HA-{suffix}",
            ),
        )

        previous_status = None
        for step, status in enumerate(STATUS_PATH):
            changed_at = now + timedelta(minutes=step * 2)
            reason_code = STATUS_REASON_BY_STEP.get(status)
            cur.execute(
                """
                INSERT INTO remittance.remittance_status_history
                    (remittance_id, previous_status_id, new_status_id, status_reason_id,
                     reason_description, actor_type, actor_reference, changed_at,
                     local_changed_at, timezone_name)
                VALUES (%s, %s, %s, %s, %s, 'SYSTEM', 'DJANGO_FAILOVER_DEMO',
                        %s, %s, 'America/Guatemala');
                """,
                (
                    remittance_id,
                    maps["statuses"].get(previous_status) if previous_status else None,
                    maps["statuses"][status],
                    maps["reasons"].get(reason_code) if reason_code else None,
                    f"Transicion automatica de demostracion hacia {status}",
                    changed_at,
                    changed_at.replace(tzinfo=None),
                ),
            )
            previous_status = status

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
            VALUES (%s, %s, %s, %s, 'NATIONAL_ID', %s, 'Direccion registrada originador',
                    %s, %s, %s, %s, 'NATIONAL_ID', %s, 'Direccion registrada beneficiario',
                    %s, 'COMPLETE', %s);
            """,
            (
                remittance_id,
                relationship["customer_party_id"],
                relationship["customer_name"],
                f"CUST-{relationship['customer_id']}",
                sha256(f"DOC-{relationship['customer_party_id']}"),
                relationship["customer_country_id"],
                relationship["beneficiary_party_id"],
                relationship["beneficiary_name"],
                f"BEN-{relationship['beneficiary_id']}",
                sha256(f"DOC-{relationship['beneficiary_party_id']}"),
                relationship["beneficiary_country_id"],
                now + timedelta(minutes=1),
            ),
        )

        for movement_code, amount, currency_id in [
            ("CUSTOMER_CHARGE", total_charged, corridor["send_currency_id"]),
            ("FEE_REVENUE", fee_amount, corridor["send_currency_id"]),
            ("TAX_WITHHELD", tax_amount, corridor["send_currency_id"]),
            ("FX_SPREAD_REVENUE", spread_amount, corridor["send_currency_id"]),
            ("PAYOUT_OBLIGATION", payout_amount, corridor["payout_currency_id"]),
            ("PARTNER_PAYOUT", payout_amount, corridor["payout_currency_id"]),
        ]:
            cur.execute(
                """
                INSERT INTO remittance.remittance_financial_movement
                    (remittance_id, movement_type_id, currency_id, amount, movement_status,
                     external_reference, occurred_at, description)
                VALUES (%s, %s, %s, %s, 'CONFIRMED', %s, %s, %s);
                """,
                (
                    remittance_id,
                    maps["movement_types"][movement_code],
                    currency_id,
                    amount,
                    f"{movement_code}-{suffix}",
                    now + timedelta(minutes=15),
                    f"Movimiento generado por prueba HA: {movement_code}",
                ),
            )

        cur.execute(
            """
            INSERT INTO compliance.risk_assessment
                (remittance_id, assessment_version, risk_score, risk_level,
                 decision, evaluated_at, model_reference)
            VALUES (%s, 'HA-DEMO-1', 0.2500, 'LOW', 'APPROVE', %s, 'DJANGO_FAILOVER_DEMO');
            """,
            (remittance_id, now + timedelta(minutes=1)),
        )

        cur.execute(
            """
            INSERT INTO compliance.aml_screening
                (screening_provider_id, screening_type, screening_status,
                 match_score, request_reference, screened_at)
            VALUES (%s, 'TRANSACTION', 'CLEAR', 0.0500, %s, %s)
            RETURNING aml_screening_id;
            """,
            (
                maps["screening_providers"]["INTERNAL_AML"],
                f"AML-HA-{suffix}",
                now + timedelta(minutes=1),
            ),
        )
        screening_id = cur.fetchone()["aml_screening_id"]
        for party_id, role in [
            (relationship["customer_party_id"], "ORIGINATOR"),
            (relationship["beneficiary_party_id"], "BENEFICIARY"),
        ]:
            cur.execute(
                """
                INSERT INTO compliance.aml_screening_party
                    (aml_screening_id, party_id, subject_role)
                VALUES (%s, %s, %s)
                ON CONFLICT (aml_screening_id, party_id) DO NOTHING;
                """,
                (screening_id, party_id, role),
            )
        cur.execute(
            "INSERT INTO compliance.aml_screening_remittance (aml_screening_id, remittance_id) VALUES (%s, %s);",
            (screening_id, remittance_id),
        )

        event_payload = {
            "source": "django-api-gateway",
            "purpose": "failover_insert_demo",
            "remittance_id": remittance_id,
            "remittance_code": remittance_code,
            "corridor": corridor["corridor_code"],
            "status": "PAID",
            "send_amount": str(send_amount),
            "payout_amount": str(payout_amount),
        }
        event_id = uuid4()
        cur.execute(
            """
            INSERT INTO integration.outbox_event
                (event_id, aggregate_type, aggregate_id, event_type, event_version,
                 payload, occurred_at, publication_status)
            VALUES (%s, 'REMITTANCE', %s, 'REMITTANCE_CREATED_BY_FAILOVER_DEMO',
                    1, %s, %s, 'PENDING');
            """,
            (event_id, remittance_id, Jsonb(event_payload), now),
        )

        cur.execute(
            "SELECT current_database() AS database, inet_server_addr()::text AS server_addr, pg_is_in_recovery() AS is_replica;"
        )
        server = cur.fetchone()

    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT pg_current_wal_lsn()::text AS commit_lsn;")
        commit_lsn = cur.fetchone()["commit_lsn"]

    return {
        "status": "inserted",
        "source": "07_generador_datos/insert_random_remittance.py",
        "remittance_id": remittance_id,
        "remittance_code": remittance_code,
        "event_id": str(event_id),
        "commit_lsn": commit_lsn,
        "customer": relationship["customer_name"],
        "beneficiary": relationship["beneficiary_name"],
        "corridor": corridor["corridor_code"],
        "target_status": "PAID",
        "send_amount": str(send_amount),
        "send_currency": corridor["send_currency"],
        "payout_amount": str(payout_amount),
        "payout_currency": corridor["payout_currency"],
        "total_charged_amount": str(total_charged),
        "database": server["database"],
        "server_addr": server["server_addr"],
        "is_replica": server["is_replica"],
        "created_at": now.isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inserta una remesa completa aleatoria para pruebas de HA.")
    parser.add_argument(
        "--config",
        default=Path(__file__).resolve().parents[1] / "Migración" / "07_configuracion_generador_patroni_docker.json",
        help="Ruta al archivo de configuracion del generador.",
    )
    args = parser.parse_args()
    cfg = load_config(args.config)

    try:
        with pg_connection(cfg.postgres_dsn) as conn:
            result = insert_random_remittance(conn)
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2, default=decimal_to_str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
