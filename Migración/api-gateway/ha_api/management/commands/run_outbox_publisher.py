import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

import psycopg
from django.conf import settings
from django.core.management.base import BaseCommand
from pymongo import MongoClient
from pymongo.write_concern import WriteConcern


DESTINATION_CODE = "MONGODB_ANALYTICS"
COLLECTION_NAME = "remittance_events"


def postgres_connection():
    database = settings.GLOBALREMIT_DB
    return psycopg.connect(
        host=database["host"],
        port=database["port"],
        dbname=database["dbname"],
        user=database["user"],
        password=database["password"],
        application_name="globalremit-outbox-publisher",
        connect_timeout=5,
    )


def mongo_client():
    mongo = settings.GLOBALREMIT_MONGO
    hosts = ",".join(f"{node}:{mongo['port']}" for node in mongo["nodes"])
    uri = (
        f"mongodb://{quote_plus(mongo['user'])}:{quote_plus(mongo['password'])}@{hosts}/"
        f"?replicaSet={quote_plus(mongo['replica_set'])}"
        f"&authSource={quote_plus(mongo['auth_db'])}&retryWrites=true&w=majority"
    )
    return MongoClient(uri, serverSelectionTimeoutMS=5000)


def ensure_destination(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO integration.publication_destination
                (destination_code, destination_name, is_active)
            VALUES (%s, 'MongoDB Analytics Replica Set', true)
            ON CONFLICT (destination_code)
            DO UPDATE SET destination_name = EXCLUDED.destination_name,
                          is_active = true;
            """,
            (DESTINATION_CODE,),
        )
    conn.commit()


def next_event(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT event_id,
                   aggregate_type,
                   aggregate_id,
                   event_type,
                   event_version,
                   payload,
                   occurred_at,
                   created_at
            FROM integration.outbox_event
            WHERE publication_status IN ('PENDING', 'FAILED')
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1;
            """
        )
        row = cur.fetchone()
        if row is None:
            return None

        cur.execute(
            """
            UPDATE integration.outbox_event
            SET publication_status = 'PROCESSING'
            WHERE event_id = %s;
            """,
            (row[0],),
        )
        return row


def publish_event(conn, collection, row):
    event_id = str(row[0])
    document = {
        "_id": event_id,
        "event_id": event_id,
        "aggregate_type": row[1],
        "aggregate_id": row[2],
        "event_type": row[3],
        "event_version": row[4],
        "payload": row[5],
        "occurred_at": row[6],
        "created_at": row[7],
        "ingested_at": datetime.now(timezone.utc),
        "source": {
            "database": settings.GLOBALREMIT_DB["dbname"],
            "schema": "integration",
            "table": "outbox_event",
            "publisher": "globalremit-outbox-publisher",
        },
        "data_classification": "INTERNAL",
    }
    collection.replace_one({"_id": event_id}, document, upsert=True)

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE integration.outbox_event
            SET publication_status = 'PUBLISHED',
                published_at = now()
            WHERE event_id = %s;
            """,
            (row[0],),
        )
        cur.execute(
            """
            INSERT INTO integration.outbox_publication_attempt
                (event_id, destination_id, attempt_status)
            SELECT %s, destination_id, 'SUCCESS'
            FROM integration.publication_destination
            WHERE destination_code = %s;
            """,
            (row[0], DESTINATION_CODE),
        )


def mark_failed(event_id, message):
    with postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE integration.outbox_event
                SET publication_status = 'FAILED'
                WHERE event_id = %s;
                """,
                (event_id,),
            )
            cur.execute(
                """
                INSERT INTO integration.outbox_publication_attempt
                    (event_id, destination_id, attempt_status, error_code, error_message)
                SELECT %s, destination_id, 'FAILED', 'PUBLISH_ERROR', %s
                FROM integration.publication_destination
                WHERE destination_code = %s;
                """,
                (event_id, str(message)[:1000], DESTINATION_CODE),
            )


class Command(BaseCommand):
    help = "Publica eventos Outbox de PostgreSQL en MongoDB con entrega idempotente."

    def handle(self, *args, **options):
        self.stdout.write("GlobalRemit Outbox Publisher iniciado")
        client = mongo_client()
        database = settings.GLOBALREMIT_MONGO["database"]
        collection = client[database].get_collection(
            COLLECTION_NAME,
            write_concern=WriteConcern("majority", wtimeout=5000),
        )

        while True:
            event_id = None
            try:
                with postgres_connection() as conn:
                    ensure_destination(conn)
                    row = next_event(conn)
                    if row is None:
                        conn.rollback()
                        time.sleep(0.5)
                        continue
                    event_id = row[0]
                    publish_event(conn, collection, row)
                    conn.commit()
                    self.stdout.write(f"PUBLISHED event_id={event_id}")
            except KeyboardInterrupt:
                break
            except Exception as exc:
                if event_id is not None:
                    try:
                        mark_failed(event_id, exc)
                    except Exception as mark_exc:
                        self.stderr.write(f"No se pudo marcar {event_id}: {mark_exc}")
                self.stderr.write(f"Publicación fallida: {type(exc).__name__}: {exc}")
                time.sleep(2)

        client.close()
