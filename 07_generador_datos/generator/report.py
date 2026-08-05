from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def write_report(path: Path, metrics: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Fase 7 - Reporte de Carga GlobalRemit",
        "",
        f"Generado: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Resultado",
        "",
        f"- PostgreSQL: {metrics.get('postgres_status', 'unknown')}",
        f"- MongoDB: {metrics.get('mongo_status', 'unknown')}",
        f"- Duracion segundos: {metrics.get('duration_seconds')}",
        "",
        "## Cantidades",
        "",
        "| Entidad | Cantidad |",
        "|---|---:|",
    ]
    for key, value in metrics.get("counts", {}).items():
        lines.append(f"| {key} | {value} |")
    lines.extend([
        "",
        "## Distribucion de remesas",
        "",
        "| Estado | Cantidad |",
        "|---|---:|",
    ])
    for key, value in metrics.get("status_distribution", {}).items():
        lines.append(f"| {key} | {value} |")
    lines.extend([
        "",
        "## Fraude y riesgo",
        "",
        f"- Remesas sospechosas: {metrics.get('suspect_remittances', 0)}",
        f"- Senales de fraude: {metrics.get('fraud_signals', 0)}",
        f"- Casos AML: {metrics.get('aml_alerts', 0)}",
        "",
        "## Observaciones",
        "",
    ])
    lines.extend(f"- {item}" for item in metrics.get("notes", []))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
