// ============================================================
// GlobalRemit - Fase 8
// Consultas MongoDB para productos analiticos
// Base objetivo: globalremit_analytics
// ============================================================
// Ejecutar con:
// mongosh "mongodb://127.0.0.1:27017/globalremit_analytics" .\08_consultas_mongodb.js
// ============================================================

const targetDb = db.getSiblingDB("globalremit_analytics");

const collectionAliases = {
  remittance_events: "eventos_remesa",
  remittance_lifecycle: "ciclo_vida_remesa",
  customer_behavior_profiles: "perfiles_comportamiento_cliente",
  fraud_signals: "senales_fraude",
  compliance_case_snapshots: "casos_cumplimiento",
  fx_rate_timeseries: "serie_tasas_fx",
  corridor_daily_metrics: "metricas_diarias_corredor",
  settlement_status: "estado_liquidaciones"
};

function section(title) {
  print("\n============================================================");
  print(title);
  print("============================================================");
}

section("1. Conteo de documentos por coleccion");
[
  "remittance_events",
  "remittance_lifecycle",
  "customer_behavior_profiles",
  "fraud_signals",
  "compliance_case_snapshots",
  "fx_rate_timeseries",
  "corridor_daily_metrics",
  "settlement_status"
].forEach((collectionName) => {
  printjson({
    tabla_o_coleccion: collectionAliases[collectionName],
    nombre_tecnico: collectionName,
    cantidad_documentos: targetDb.getCollection(collectionName).countDocuments()
  });
});

section("2. Remesas por estado actual en lifecycle");
targetDb.remittance_lifecycle.aggregate([
  {
    $group: {
      _id: "$current_status",
      total: { $sum: 1 },
      total_send_amount: { $sum: "$financial.send_amount" },
      total_fee_amount: { $sum: "$financial.fee_amount" },
      total_fx_spread_amount: { $sum: "$financial.fx_spread_amount" }
    }
  },
  {
    $project: {
      _id: 0,
      estado_remesa: "$_id",
      cantidad_remesas: "$total",
      total_monto_enviado: "$total_send_amount",
      total_comisiones: "$total_fee_amount",
      total_spread_fx: "$total_fx_spread_amount"
    }
  },
  { $sort: { cantidad_remesas: -1 } }
]).forEach(printjson);

section("3. Remesas por corredor y estado");
targetDb.remittance_lifecycle.aggregate([
  {
    $group: {
      _id: {
        corridor: "$corridor.corridor_code",
        status: "$current_status"
      },
      total: { $sum: 1 },
      send_amount: { $sum: "$financial.send_amount" },
      payout_amount: { $sum: "$financial.payout_amount" }
    }
  },
  {
    $project: {
      _id: 0,
      codigo_corredor: "$_id.corridor",
      estado_remesa: "$_id.status",
      cantidad_remesas: "$total",
      total_monto_enviado: "$send_amount",
      total_monto_pagado: "$payout_amount"
    }
  },
  { $sort: { codigo_corredor: 1, cantidad_remesas: -1 } }
]).forEach(printjson);

section("4. Remesas de alto riesgo o en revision");
targetDb.remittance_lifecycle.aggregate([
  {
    $match: {
      $or: [
        { "compliance.risk_level": { $in: ["HIGH", "CRITICAL"] } },
        { "compliance.aml_status": "MATCH" },
        { current_status: "UNDER_REVIEW" }
      ]
    }
  },
  {
    $project: {
      _id: 0,
      codigo_remesa: "$remittance_code",
      estado_remesa: "$current_status",
      codigo_corredor: "$corridor.corridor_code",
      monto_enviado: "$financial.send_amount",
      nivel_riesgo: "$compliance.risk_level",
      estado_aml: "$compliance.aml_status",
      actualizado_en: "$updated_at"
    }
  },
  { $sort: { monto_enviado: -1 } },
  { $limit: 25 }
]).forEach(printjson);

section("5. Senales de fraude por severidad y regla");
targetDb.fraud_signals.aggregate([
  {
    $group: {
      _id: {
        severity: "$severity",
        signal_type: "$signal_type",
        rule_code: "$rule.rule_code"
      },
      total: { $sum: 1 },
      average_score: { $avg: "$score" },
      max_score: { $max: "$score" }
    }
  },
  {
    $project: {
      _id: 0,
      severidad: "$_id.severity",
      tipo_senal: "$_id.signal_type",
      codigo_regla: "$_id.rule_code",
      cantidad_senales: "$total",
      puntaje_promedio: "$average_score",
      puntaje_maximo: "$max_score"
    }
  },
  { $sort: { severidad: 1, cantidad_senales: -1 } }
]).forEach(printjson);

section("6. Clientes con mayor velocidad operativa o desviacion de monto");
targetDb.customer_behavior_profiles.aggregate([
  {
    $match: {
      $or: [
        { "risk_features.velocity_score": { $gte: 0.60 } },
        { "risk_features.amount_deviation_score": { $gte: 0.60 } },
        { "windows.last_30d.remittance_count": { $gte: 10 } }
      ]
    }
  },
  {
    $project: {
      _id: 0,
      cliente_id: "$customer_id",
      ventana_24h: "$windows.last_24h",
      ventana_30d: "$windows.last_30d",
      factores_riesgo: "$risk_features",
      patrones_usuales: "$usual_patterns",
      calculado_en: "$computed_at"
    }
  },
  {
    $sort: {
      "factores_riesgo.velocity_score": -1,
      "factores_riesgo.amount_deviation_score": -1
    }
  },
  { $limit: 25 }
]).forEach(printjson);

section("7. Metricas diarias por corredor");
targetDb.corridor_daily_metrics.aggregate([
  {
    $project: {
      _id: 0,
      codigo_corredor: "$corridor_code",
      fecha_metrica: "$metric_date",
      moneda_envio: "$send_currency",
      moneda_pago: "$payout_currency",
      cantidad_total: {
        $sum: {
          $map: {
            input: { $objectToArray: "$counts" },
            as: "status_count",
            in: "$$status_count.v"
          }
        }
      },
      monto_enviado: "$amounts.send_amount",
      monto_comisiones: "$amounts.fee_amount",
      monto_spread_fx: "$amounts.fx_spread_amount",
      cantidad_alertas: "$risk.alert_count",
      cantidad_alto_riesgo: "$risk.high_risk_count"
    }
  },
  { $sort: { fecha_metrica: -1, monto_enviado: -1 } },
  { $limit: 30 }
]).forEach(printjson);

section("8. Serie temporal de tipo de cambio por par");
targetDb.fx_rate_timeseries.aggregate([
  {
    $group: {
      _id: "$metadata.currency_pair",
      observations: { $sum: 1 },
      min_rate: { $min: "$market_rate" },
      max_rate: { $max: "$market_rate" },
      avg_rate: { $avg: "$market_rate" },
      first_observed_at: { $min: "$observed_at" },
      last_observed_at: { $max: "$observed_at" }
    }
  },
  {
    $project: {
      _id: 0,
      par_monedas: "$_id",
      cantidad_observaciones: "$observations",
      tasa_minima: "$min_rate",
      tasa_maxima: "$max_rate",
      tasa_promedio: "$avg_rate",
      primera_observacion_en: "$first_observed_at",
      ultima_observacion_en: "$last_observed_at"
    }
  },
  { $sort: { par_monedas: 1 } }
]).forEach(printjson);

section("9. Estado de liquidaciones analiticas");
targetDb.settlement_status.aggregate([
  {
    $group: {
      _id: "$status",
      batch_count: { $sum: 1 },
      item_count: { $sum: "$totals.item_count" },
      expected_amount: { $sum: "$totals.expected_amount" },
      reported_amount: { $sum: "$totals.reported_amount" },
      difference_amount: { $sum: "$totals.difference_amount" }
    }
  },
  {
    $project: {
      _id: 0,
      estado_liquidacion: "$_id",
      cantidad_lotes: "$batch_count",
      cantidad_items: "$item_count",
      monto_esperado: "$expected_amount",
      monto_reportado: "$reported_amount",
      monto_diferencia: "$difference_amount"
    }
  },
  { $sort: { cantidad_lotes: -1 } }
]).forEach(printjson);

section("10. Conciliacion documental lifecycle vs eventos");
targetDb.remittance_lifecycle.aggregate([
  {
    $lookup: {
      from: "remittance_events",
      localField: "last_event_id",
      foreignField: "event_id",
      as: "last_event"
    }
  },
  {
    $project: {
      codigo_remesa: "$remittance_code",
      estado_actual: "$current_status",
      ultimo_evento_id: "$last_event_id",
      evento_encontrado: { $gt: [{ $size: "$last_event" }, 0] }
    }
  },
  {
    $group: {
      _id: "$evento_encontrado",
      remittances: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 0,
      evento_encontrado: "$_id",
      cantidad_remesas: "$remittances"
    }
  }
]).forEach(printjson);
