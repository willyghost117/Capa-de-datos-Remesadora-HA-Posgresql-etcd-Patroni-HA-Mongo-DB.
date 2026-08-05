import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

import psycopg
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods
from pymongo import MongoClient
from pymongo.errors import PyMongoError


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public.ha_api_events (
    id BIGSERIAL PRIMARY KEY,
    source VARCHAR(80) NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

GENERATOR_SCRIPT = "/workspace/07_generador_datos/run_generator.py"
SINGLE_REMITTANCE_SCRIPT = "/workspace/07_generador_datos/insert_random_remittance.py"
GENERATOR_CONFIG = "/workspace/Migración/07_configuracion_gateway_patroni_docker.json"
PATRONI_REST_PORT = 8008
ETCD_HEALTH_URL = "http://patroni-etcd:2379/health"


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_connection(connect_timeout=5):
    return psycopg.connect(
        host=settings.GLOBALREMIT_DB["host"],
        port=settings.GLOBALREMIT_DB["port"],
        dbname=settings.GLOBALREMIT_DB["dbname"],
        user=settings.GLOBALREMIT_DB["user"],
        password=settings.GLOBALREMIT_DB["password"],
        connect_timeout=connect_timeout,
        autocommit=True,
    )


def ensure_table(conn):
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)


def fetch_recent(conn, limit=8):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, source, message, created_at
            FROM public.ha_api_events
            ORDER BY id DESC
            LIMIT %s;
            """,
            (limit,),
        )
        return [
            {
                "id": row[0],
                "source": row[1],
                "message": row[2],
                "created_at": row[3].isoformat(),
            }
            for row in cur.fetchall()
        ]


def fetch_recent_remittances(conn, limit=10):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ro.remittance_id,
                   ro.remittance_code,
                   rc.corridor_code,
                   sendcur.iso_currency_code AS send_currency,
                   fd.send_amount,
                   payoutcur.iso_currency_code AS payout_currency,
                   fd.payout_amount,
                   rs.status_code,
                   ro.created_at,
                   ro.paid_at
            FROM remittance.remittance_order ro
            JOIN fx.remittance_corridor rc
              ON rc.corridor_id = ro.corridor_id
            JOIN remittance.remittance_financial_detail fd
              ON fd.remittance_id = ro.remittance_id
            JOIN reference.currency sendcur
              ON sendcur.currency_id = fd.send_currency_id
            JOIN reference.currency payoutcur
              ON payoutcur.currency_id = fd.payout_currency_id
            JOIN reference.remittance_status rs
              ON rs.remittance_status_id = ro.current_status_id
            ORDER BY ro.remittance_id DESC
            LIMIT %s;
            """,
            (limit,),
        )
        return [
            {
                "remittance_id": row[0],
                "remittance_code": row[1],
                "corridor": row[2],
                "send_currency": row[3],
                "send_amount": str(row[4]),
                "payout_currency": row[5],
                "payout_amount": str(row[6]),
                "status": row[7],
                "created_at": row[8].isoformat(),
                "paid_at": row[9].isoformat() if row[9] else None,
            }
            for row in cur.fetchall()
        ]


def fetch_json(url, timeout=1.2):
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "GlobalRemit-Lab/1.0"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def short_node_name(name):
    return name.removeprefix("globalremit-patroni-").removeprefix("globalremit-")


def patroni_node_status(name):
    base = {
        "id": short_node_name(name),
        "name": name,
        "healthy": False,
        "role": "unknown",
        "state": "offline",
        "timeline": None,
        "xlog": {},
        "version": None,
        "error": None,
    }
    try:
        payload = fetch_json(f"http://{name}:{PATRONI_REST_PORT}/patroni")
        role = str(payload.get("role", "unknown")).lower()
        if role in {"master", "primary", "leader"}:
            role = "leader"
        elif role in {"replica", "standby_leader"}:
            role = "replica"
        state = str(payload.get("state", "unknown")).lower()
        base.update(
            {
                "healthy": state == "running",
                "role": role,
                "state": state,
                "timeline": payload.get("timeline"),
                "xlog": payload.get("xlog", {}),
                "version": payload.get("server_version"),
            }
        )
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        base["error"] = type(exc).__name__
    return base


def mongo_node_status(name):
    mongo = settings.GLOBALREMIT_MONGO
    base = {
        "id": short_node_name(name),
        "name": name,
        "healthy": False,
        "role": "unknown",
        "state": "offline",
        "primary": None,
        "replica_set": mongo["replica_set"],
        "error": None,
    }
    user = quote_plus(mongo["user"])
    password = quote_plus(mongo["password"])
    auth_db = quote_plus(mongo["auth_db"])
    uri = (
        f"mongodb://{user}:{password}@{name}:{mongo['port']}/"
        f"?authSource={auth_db}&directConnection=true"
    )
    client = None
    try:
        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=1200,
            connectTimeoutMS=1200,
            socketTimeoutMS=1200,
        )
        hello = client.admin.command("hello")
        if hello.get("isWritablePrimary"):
            role = "primary"
        elif hello.get("secondary"):
            role = "secondary"
        elif hello.get("arbiterOnly"):
            role = "arbiter"
        else:
            role = "unknown"
        base.update(
            {
                "healthy": True,
                "role": role,
                "state": "running",
                "primary": hello.get("primary"),
                "replica_set": hello.get("setName", mongo["replica_set"]),
            }
        )
    except (PyMongoError, OSError, ValueError) as exc:
        base["error"] = type(exc).__name__
    finally:
        if client is not None:
            client.close()
    return base


def endpoint_status():
    result = {
        "name": f"{settings.GLOBALREMIT_DB['host']}:{settings.GLOBALREMIT_DB['port']}",
        "healthy": False,
        "database": settings.GLOBALREMIT_DB["dbname"],
        "server_addr": None,
        "is_replica": None,
        "total_remittances": None,
        "error": None,
    }
    try:
        with get_connection(connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT current_database(), inet_server_addr()::text, pg_is_in_recovery();"
                )
                database, server_addr, is_replica = cur.fetchone()
                try:
                    cur.execute("SELECT COUNT(*) FROM remittance.remittance_order;")
                    total_remittances = cur.fetchone()[0]
                except psycopg.Error:
                    total_remittances = None
        result.update(
            {
                "healthy": True,
                "database": database,
                "server_addr": server_addr,
                "is_replica": is_replica,
                "total_remittances": total_remittances,
            }
        )
    except Exception as exc:
        result["error"] = type(exc).__name__
    return result


def etcd_status():
    result = {"name": "patroni-etcd:2379", "healthy": False, "error": None}
    try:
        payload = fetch_json(ETCD_HEALTH_URL, timeout=1.0)
        health = payload.get("health", False)
        result["healthy"] = health is True or str(health).lower() == "true"
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        result["error"] = type(exc).__name__
    return result


def topology_snapshot():
    patroni_nodes = settings.GLOBALREMIT_PATRONI_NODES
    mongo_nodes = settings.GLOBALREMIT_MONGO["nodes"]
    tasks = {}
    postgres = []
    mongodb = []

    with ThreadPoolExecutor(max_workers=9) as executor:
        for node in patroni_nodes:
            tasks[executor.submit(patroni_node_status, node)] = ("postgres", node)
        for node in mongo_nodes:
            tasks[executor.submit(mongo_node_status, node)] = ("mongodb", node)
        tasks[executor.submit(endpoint_status)] = ("endpoint", "haproxy")
        tasks[executor.submit(etcd_status)] = ("etcd", "etcd")

        endpoint = None
        etcd = None
        for future in as_completed(tasks):
            category, _ = tasks[future]
            result = future.result()
            if category == "postgres":
                postgres.append(result)
            elif category == "mongodb":
                mongodb.append(result)
            elif category == "endpoint":
                endpoint = result
            else:
                etcd = result

    postgres.sort(key=lambda node: node["id"])
    mongodb.sort(key=lambda node: node["id"])
    endpoint = endpoint or endpoint_status()
    etcd = etcd or {"name": "patroni-etcd:2379", "healthy": False, "error": "unknown"}

    leaders = [node for node in postgres if node["healthy"] and node["role"] == "leader"]
    primaries = [node for node in mongodb if node["healthy"] and node["role"] == "primary"]
    healthy_pg = sum(1 for node in postgres if node["healthy"])
    healthy_mongo = sum(1 for node in mongodb if node["healthy"])

    if leaders and endpoint["healthy"]:
        postgres_state = "operational"
    elif healthy_pg:
        postgres_state = "electing"
    else:
        postgres_state = "offline"

    if primaries:
        mongo_state = "operational"
    elif healthy_mongo >= 2:
        mongo_state = "electing"
    elif healthy_mongo:
        mongo_state = "degraded"
    else:
        mongo_state = "offline"

    if postgres_state == "operational" and mongo_state == "operational" and etcd["healthy"]:
        overall = "operational"
    elif endpoint["healthy"] or primaries or healthy_pg or healthy_mongo:
        overall = "degraded"
    else:
        overall = "critical"

    return {
        "status": "ok",
        "generated_at": utc_now_iso(),
        "overall": overall,
        "postgres": {
            "state": postgres_state,
            "leader": leaders[0]["name"] if leaders else None,
            "healthy_nodes": healthy_pg,
            "total_nodes": len(postgres),
            "nodes": postgres,
            "endpoint": endpoint,
            "coordinator": etcd,
        },
        "mongodb": {
            "state": mongo_state,
            "primary": primaries[0]["name"] if primaries else None,
            "healthy_nodes": healthy_mongo,
            "total_nodes": len(mongodb),
            "nodes": mongodb,
        },
    }


def lsn_to_int(value):
    if not value or "/" not in value:
        return None
    high, low = value.split("/", 1)
    return (int(high, 16) << 32) + int(low, 16)


def int_to_lsn(value):
    if value is None:
        return None
    return f"{value >> 32:X}/{value & 0xFFFFFFFF:X}"


def fetch_trace_record(event_id):
    with get_connection(connect_timeout=3) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT oe.event_id,
                       oe.aggregate_id,
                       oe.event_type,
                       oe.payload,
                       oe.created_at,
                       oe.publication_status,
                       oe.published_at,
                       ro.remittance_code,
                       audit.audited,
                       audit.event_time,
                       audit.database_user,
                       attempt.attempted_at,
                       attempt.attempt_status
                FROM integration.outbox_event oe
                JOIN remittance.remittance_order ro
                  ON ro.remittance_id = oe.aggregate_id
                LEFT JOIN LATERAL integration.fn_trace_audit_event(oe.event_id) audit
                  ON true
                LEFT JOIN LATERAL (
                    SELECT opa.attempted_at, opa.attempt_status
                    FROM integration.outbox_publication_attempt opa
                    WHERE opa.event_id = oe.event_id
                    ORDER BY opa.attempted_at DESC
                    LIMIT 1
                ) attempt ON true
                WHERE oe.event_id = %s;
                """,
                (event_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return {
        "event_id": str(row[0]),
        "remittance_id": row[1],
        "event_type": row[2],
        "payload": row[3],
        "created_at": row[4].isoformat(),
        "publication_status": row[5],
        "published_at": row[6].isoformat() if row[6] else None,
        "remittance_code": row[7],
        "audited": bool(row[8]),
        "audit_time": row[9].isoformat() if row[9] else None,
        "audit_user": row[10],
        "publication_attempted_at": row[11].isoformat() if row[11] else None,
        "publication_attempt_status": row[12],
    }


def mongo_event_status(name, event_id):
    mongo = settings.GLOBALREMIT_MONGO
    result = {
        "name": name,
        "healthy": False,
        "role": "unknown",
        "document_found": False,
        "ingested_at": None,
        "error": None,
    }
    uri = (
        f"mongodb://{quote_plus(mongo['user'])}:{quote_plus(mongo['password'])}@"
        f"{name}:{mongo['port']}/?authSource={quote_plus(mongo['auth_db'])}"
        "&directConnection=true&readPreference=secondaryPreferred"
    )
    client = None
    try:
        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=1400,
            connectTimeoutMS=1400,
            socketTimeoutMS=1400,
        )
        hello = client.admin.command("hello")
        role = "primary" if hello.get("isWritablePrimary") else "secondary" if hello.get("secondary") else "unknown"
        document = client[mongo["database"]]["remittance_events"].find_one(
            {"_id": str(event_id)},
            {"_id": 1, "ingested_at": 1},
        )
        result.update(
            {
                "healthy": True,
                "role": role,
                "document_found": document is not None,
                "ingested_at": document.get("ingested_at").isoformat()
                if document and document.get("ingested_at")
                else None,
            }
        )
    except (PyMongoError, OSError, ValueError) as exc:
        result["error"] = type(exc).__name__
    finally:
        if client is not None:
            client.close()
    return result


def build_remittance_trace(event_id, commit_lsn):
    event = fetch_trace_record(event_id)
    if event is None:
        return None

    target_location = lsn_to_int(commit_lsn)
    postgres_nodes = []
    mongo_nodes = []
    tasks = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        for node in settings.GLOBALREMIT_PATRONI_NODES:
            tasks[executor.submit(patroni_node_status, node)] = "postgres"
        for node in settings.GLOBALREMIT_MONGO["nodes"]:
            tasks[executor.submit(mongo_event_status, node, event_id)] = "mongodb"
        for future in as_completed(tasks):
            category = tasks[future]
            if category == "postgres":
                node = future.result()
                xlog = node.get("xlog") or {}
                location = xlog.get("location")
                if location is None:
                    location = xlog.get("replayed_location")
                node["replay_lsn"] = int_to_lsn(location)
                node["caught_up"] = (
                    bool(node["healthy"] and target_location is not None and location is not None and location >= target_location)
                )
                postgres_nodes.append(node)
            else:
                mongo_nodes.append(future.result())

    postgres_nodes.sort(key=lambda node: node["id"])
    mongo_nodes.sort(key=lambda node: node["name"])
    replicas = [node for node in postgres_nodes if node["healthy"] and node["role"] == "replica"]
    caught_up_replicas = sum(1 for node in replicas if node["caught_up"])
    mongo_confirmations = sum(1 for node in mongo_nodes if node["document_found"])
    publication_status = event["publication_status"]

    if replicas and caught_up_replicas == len(replicas):
        replication_stage = "done"
    elif caught_up_replicas:
        replication_stage = "partial"
    else:
        replication_stage = "waiting"

    if publication_status == "PUBLISHED":
        outbox_stage = "done"
    elif publication_status == "FAILED":
        outbox_stage = "error"
    elif publication_status == "PROCESSING":
        outbox_stage = "active"
    else:
        outbox_stage = "waiting"

    if mongo_confirmations >= 2:
        mongo_stage = "done"
    elif mongo_confirmations:
        mongo_stage = "partial"
    else:
        mongo_stage = "waiting"

    stages = [
        {"id": "django", "status": "done", "detail": "Solicitud correlacionada por event_id"},
        {"id": "haproxy", "status": "done", "detail": "Escritura enviada al líder disponible"},
        {"id": "postgres", "status": "done", "detail": f"COMMIT confirmado en {commit_lsn or 'LSN no informado'}"},
        {"id": "audit", "status": "done" if event["audited"] else "waiting", "detail": "Cambio registrado por trigger" if event["audited"] else "Esperando evidencia de auditoría"},
        {"id": "replication", "status": replication_stage, "detail": f"{caught_up_replicas}/{len(replicas)} réplicas disponibles alcanzaron el LSN"},
        {"id": "outbox", "status": outbox_stage, "detail": f"Evento {publication_status}"},
        {"id": "mongodb", "status": mongo_stage, "detail": f"Documento confirmado en {mongo_confirmations}/3 nodos"},
        {"id": "analytics", "status": mongo_stage, "detail": "Proyección disponible para consulta" if mongo_confirmations else "Esperando proyección"},
    ]
    complete = (
        event["audited"]
        and replication_stage == "done"
        and publication_status == "PUBLISHED"
        and mongo_confirmations >= 2
    )
    return {
        "status": "ok",
        "generated_at": utc_now_iso(),
        "complete": complete,
        "commit_lsn": commit_lsn,
        "event": event,
        "stages": stages,
        "postgres_nodes": postgres_nodes,
        "mongodb_nodes": mongo_nodes,
    }


def index(request):
    return render(request, "ha_api/index.html")


@require_GET
@never_cache
def topology(request):
    return JsonResponse(topology_snapshot(), headers={"Cache-Control": "no-store"})


@require_GET
@never_cache
def remittance_trace(request, event_id):
    try:
        trace = build_remittance_trace(event_id, request.GET.get("commit_lsn"))
        if trace is None:
            return JsonResponse({"status": "error", "error": "Evento no encontrado"}, status=404)
        return JsonResponse(trace, headers={"Cache-Control": "no-store"})
    except Exception as exc:
        return JsonResponse(
            {"status": "error", "error": f"{type(exc).__name__}: {exc}"},
            status=503,
        )


@require_GET
def health(request):
    try:
        result = endpoint_status()
        if not result["healthy"]:
            raise psycopg.OperationalError("HAProxy no tiene un líder PostgreSQL disponible")
        return JsonResponse({"status": "ok", **result})
    except Exception as exc:
        return JsonResponse({"status": "error", "error": str(exc)}, status=503)


@csrf_exempt
@require_http_methods(["POST"])
def insert_ha_test(request):
    message = "Evento insertado desde API Gateway Django"
    if request.body:
        try:
            payload = json.loads(request.body.decode("utf-8"))
            message = payload.get("message", message)
        except json.JSONDecodeError:
            pass
    elif request.POST.get("message"):
        message = request.POST["message"]

    try:
        with get_connection() as conn:
            ensure_table(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH inserted AS (
                        INSERT INTO public.ha_api_events (source, message)
                        VALUES ('django-api-gateway', %s)
                        RETURNING id, source, message, created_at
                    )
                    SELECT inserted.id,
                           inserted.source,
                           inserted.message,
                           inserted.created_at,
                           current_database(),
                           inet_server_addr()::text,
                           pg_is_in_recovery()
                    FROM inserted;
                    """,
                    (message,),
                )
                row = cur.fetchone()
        return JsonResponse(
            {
                "status": "inserted",
                "id": row[0],
                "source": row[1],
                "message": row[2],
                "created_at": row[3].isoformat(),
                "database": row[4],
                "server_addr": row[5],
                "is_replica": row[6],
            }
        )
    except Exception as exc:
        return JsonResponse({"status": "error", "error": str(exc)}, status=500)


@require_GET
def events(request):
    try:
        with get_connection() as conn:
            remittances = fetch_recent_remittances(conn, limit=10)
        return JsonResponse({"status": "ok", "events": [], "remittances": remittances})
    except Exception as exc:
        return JsonResponse({"status": "error", "error": str(exc)}, status=503)


def run_command(command, timeout):
    env = os.environ.copy()
    env.setdefault("GLOBALREMIT_PG_PASSWORD", settings.GLOBALREMIT_DB["password"])
    return subprocess.run(
        command,
        cwd="/workspace/07_generador_datos",
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


@csrf_exempt
@require_http_methods(["POST"])
def run_data_generator(request):
    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        payload = {}

    mode = payload.get("mode", "load")
    if mode not in {"load", "integrity-demo"}:
        return JsonResponse({"status": "error", "error": "Modo no permitido"}, status=400)

    command = [sys.executable, GENERATOR_SCRIPT, "--config", GENERATOR_CONFIG, "--mode", mode]

    try:
        completed = run_command(command, timeout=240)
    except subprocess.TimeoutExpired as exc:
        return JsonResponse(
            {
                "status": "timeout",
                "mode": mode,
                "error": f"El generador excedió el límite de {exc.timeout} segundos.",
            },
            status=504,
        )
    except Exception as exc:
        return JsonResponse({"status": "error", "mode": mode, "error": str(exc)}, status=500)

    parsed = None
    if completed.stdout.strip():
        try:
            parsed = json.loads(completed.stdout)
        except json.JSONDecodeError:
            parsed = None

    return JsonResponse(
        {
            "status": "completed" if completed.returncode == 0 else "failed",
            "mode": mode,
            "returncode": completed.returncode,
            "parsed": parsed,
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
        },
        status=200 if completed.returncode == 0 else 500,
    )


@csrf_exempt
@require_http_methods(["POST"])
def insert_random_remittance(request):
    command = [sys.executable, SINGLE_REMITTANCE_SCRIPT, "--config", GENERATOR_CONFIG]
    started = time.monotonic()
    attempts = []
    completed = None
    parsed = None

    while len(attempts) < 7 and time.monotonic() - started < 78:
        attempt_number = len(attempts) + 1
        try:
            completed = run_command(command, timeout=12)
            stdout = completed.stdout.strip()
            try:
                parsed = json.loads(stdout) if stdout else None
            except json.JSONDecodeError:
                parsed = None
            attempts.append(
                {
                    "attempt": attempt_number,
                    "result": "ok" if completed.returncode == 0 else "retry",
                    "elapsed_seconds": round(time.monotonic() - started, 1),
                }
            )
            if completed.returncode == 0:
                return JsonResponse(
                    {
                        "status": "completed",
                        "returncode": 0,
                        "attempts": attempts,
                        "elapsed_seconds": round(time.monotonic() - started, 1),
                        "parsed": parsed,
                    }
                )
        except subprocess.TimeoutExpired:
            attempts.append(
                {
                    "attempt": attempt_number,
                    "result": "timeout",
                    "elapsed_seconds": round(time.monotonic() - started, 1),
                }
            )
        except Exception as exc:
            attempts.append(
                {
                    "attempt": attempt_number,
                    "result": type(exc).__name__,
                    "elapsed_seconds": round(time.monotonic() - started, 1),
                }
            )
        if time.monotonic() - started < 78:
            time.sleep(3)

    error_text = "No se recuperó un líder PostgreSQL dentro de la ventana de demostración."
    if parsed and parsed.get("error"):
        error_text = parsed["error"]
    elif completed and completed.stderr.strip():
        error_text = completed.stderr.strip()[-600:]

    return JsonResponse(
        {
            "status": "failed",
            "returncode": completed.returncode if completed else 1,
            "attempts": attempts,
            "elapsed_seconds": round(time.monotonic() - started, 1),
            "error": error_text,
        },
        status=503,
    )

