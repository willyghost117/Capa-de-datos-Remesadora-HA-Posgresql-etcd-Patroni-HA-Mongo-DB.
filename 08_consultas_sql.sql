-- ============================================================
-- GlobalRemit - Fase 8
-- Consultas SQL complejas para validacion funcional
-- Base objetivo: globalremit
-- ============================================================
-- Ejecutar despues de:
--   06_sql_ddl.sql
--   06_sql_seed.sql
--   07_generador_datos/run_generator.py --mode load
-- ============================================================

-- 1. Remesas por corredor, moneda y estado.
-- Demuestra volumen operativo, monto enviado, monto pagado y margen financiero.
SELECT
    rc.corridor_code AS codigo_corredor,
    send_cur.iso_currency_code AS moneda_envio,
    payout_cur.iso_currency_code AS moneda_pago,
    rs.status_code AS estado_remesa,
    COUNT(*) AS cantidad_remesas,
    ROUND(SUM(rfd.send_amount), 2) AS total_monto_enviado,
    ROUND(SUM(rfd.payout_amount), 2) AS total_monto_pagado,
    ROUND(SUM(rfd.fee_amount), 2) AS total_comisiones,
    ROUND(SUM(rfd.tax_amount), 2) AS total_impuestos,
    ROUND(SUM(rfd.fx_spread_amount), 2) AS total_spread_fx,
    ROUND(SUM(rfd.fx_gain_amount), 2) AS total_ganancia_fx
FROM remittance.remittance_order ro
JOIN remittance.remittance_financial_detail rfd
    ON rfd.remittance_id = ro.remittance_id
JOIN reference.remittance_status rs
    ON rs.remittance_status_id = ro.current_status_id
JOIN fx.remittance_corridor rc
    ON rc.corridor_id = ro.corridor_id
JOIN reference.currency send_cur
    ON send_cur.currency_id = rfd.send_currency_id
JOIN reference.currency payout_cur
    ON payout_cur.currency_id = rfd.payout_currency_id
GROUP BY
    rc.corridor_code,
    send_cur.iso_currency_code,
    payout_cur.iso_currency_code,
    rs.status_code
ORDER BY
    rc.corridor_code,
    COUNT(*) DESC;

-- 2. Rentabilidad diaria por corredor.
-- Demuestra comisiones, spread, ganancia FX e impuestos sin entrar a contabilidad formal.
SELECT
    DATE(ro.created_at) AS fecha_operacion,
    rc.corridor_code AS codigo_corredor,
    COUNT(*) AS cantidad_remesas,
    ROUND(SUM(rfd.send_amount), 2) AS total_monto_enviado,
    ROUND(SUM(rfd.fee_amount), 2) AS ingresos_por_comision,
    ROUND(SUM(rfd.fx_spread_amount + rfd.fx_gain_amount), 2) AS ingresos_fx,
    ROUND(SUM(rfd.tax_amount), 2) AS impuestos_cobrados,
    ROUND(SUM(rfd.fee_amount + rfd.fx_spread_amount + rfd.fx_gain_amount), 2) AS ingreso_bruto_estimado
FROM remittance.remittance_order ro
JOIN remittance.remittance_financial_detail rfd
    ON rfd.remittance_id = ro.remittance_id
JOIN fx.remittance_corridor rc
    ON rc.corridor_id = ro.corridor_id
GROUP BY
    DATE(ro.created_at),
    rc.corridor_code
ORDER BY
    DATE(ro.created_at) DESC,
    ROUND(SUM(rfd.fee_amount + rfd.fx_spread_amount + rfd.fx_gain_amount), 2) DESC;

-- 3. Clientes con mayor volumen y riesgo.
-- Demuestra cruce entre clientes, remesas, riesgo y alertas AML.
SELECT
    cp.customer_code AS codigo_cliente,
    p.legal_name AS nombre_cliente,
    COUNT(DISTINCT ro.remittance_id) AS cantidad_remesas,
    ROUND(SUM(rfd.send_amount), 2) AS total_monto_enviado,
    ROUND(AVG(ra.risk_score), 4) AS puntaje_riesgo_promedio,
    MAX(ra.risk_level) AS mayor_nivel_riesgo,
    COUNT(DISTINCT aa.aml_alert_id) AS cantidad_alertas_aml
FROM customer.customer_profile cp
JOIN customer.party p
    ON p.party_id = cp.party_id
JOIN remittance.remittance_order ro
    ON ro.customer_id = cp.customer_id
JOIN remittance.remittance_financial_detail rfd
    ON rfd.remittance_id = ro.remittance_id
LEFT JOIN compliance.risk_assessment ra
    ON ra.remittance_id = ro.remittance_id
LEFT JOIN compliance.aml_screening_remittance asr
    ON asr.remittance_id = ro.remittance_id
LEFT JOIN compliance.aml_alert aa
    ON aa.aml_screening_id = asr.aml_screening_id
GROUP BY
    cp.customer_code,
    p.legal_name
HAVING
    COUNT(DISTINCT ro.remittance_id) >= 3
ORDER BY
    COUNT(DISTINCT aa.aml_alert_id) DESC,
    ROUND(AVG(ra.risk_score), 4) DESC,
    ROUND(SUM(rfd.send_amount), 2) DESC
LIMIT 20;

-- 4. Auditoria de tipo de cambio aplicado contra historico FX.
-- Demuestra que la remesa conserva un snapshot financiero y puede compararse contra la tasa fuente.
SELECT
    ro.remittance_code AS codigo_remesa,
    rc.corridor_code AS codigo_corredor,
    rfd.exchange_rate_timestamp_utc AS fecha_tasa_fx,
    er.market_rate AS tasa_historica_mercado,
    rfd.market_exchange_rate AS tasa_mercado_snapshot,
    rfd.applied_exchange_rate AS tasa_aplicada,
    ROUND((rfd.applied_exchange_rate - er.market_rate), 10) AS diferencia_tasa_aplicada_vs_mercado,
    ROUND(rfd.fx_spread_amount, 2) AS monto_spread_fx,
    ROUND(rfd.fx_gain_amount, 2) AS monto_ganancia_fx
FROM remittance.remittance_order ro
JOIN remittance.remittance_financial_detail rfd
    ON rfd.remittance_id = ro.remittance_id
JOIN fx.fx_quote fq
    ON fq.fx_quote_id = ro.fx_quote_id
JOIN fx.exchange_rate er
    ON er.exchange_rate_id = fq.exchange_rate_id
JOIN fx.remittance_corridor rc
    ON rc.corridor_id = ro.corridor_id
ORDER BY
    ABS(rfd.applied_exchange_rate - er.market_rate) DESC,
    ro.remittance_id
LIMIT 30;

-- 5. Tiempo de ciclo por remesa.
-- Demuestra trazabilidad de estados y duracion desde creacion hasta cierre/pago.
WITH timeline AS (
    SELECT
        ro.remittance_id,
        ro.remittance_code,
        MIN(rsh.changed_at) AS first_status_at,
        MAX(rsh.changed_at) AS last_status_at,
        COUNT(*) AS status_events
    FROM remittance.remittance_order ro
    JOIN remittance.remittance_status_history rsh
        ON rsh.remittance_id = ro.remittance_id
    GROUP BY
        ro.remittance_id,
        ro.remittance_code
)
SELECT
    t.remittance_code AS codigo_remesa,
    rs.status_code AS estado_actual,
    t.status_events AS cantidad_eventos_estado,
    t.first_status_at AS primer_estado_en,
    t.last_status_at AS ultimo_estado_en,
    ROUND(EXTRACT(EPOCH FROM (t.last_status_at - t.first_status_at)) / 60, 2) AS minutos_ciclo_vida
FROM timeline t
JOIN remittance.remittance_order ro
    ON ro.remittance_id = t.remittance_id
JOIN reference.remittance_status rs
    ON rs.remittance_status_id = ro.current_status_id
ORDER BY
    ROUND(EXTRACT(EPOCH FROM (t.last_status_at - t.first_status_at)) / 60, 2) DESC,
    t.status_events DESC
LIMIT 30;

-- 6. Remesas con alertas AML o riesgo alto.
-- Demuestra capacidad de investigacion para cumplimiento y fraude.
SELECT
    ro.remittance_code AS codigo_remesa,
    cp.customer_code AS codigo_cliente,
    customer_party.legal_name AS nombre_cliente,
    rs.status_code AS estado_remesa,
    ra.risk_level AS nivel_riesgo,
    ra.risk_score AS puntaje_riesgo,
    aa.alert_type AS tipo_alerta,
    aa.severity AS severidad,
    aa.alert_status AS estado_alerta,
    aa.decision AS decision_aml,
    aa.created_at AS fecha_creacion_alerta
FROM remittance.remittance_order ro
JOIN customer.customer_profile cp
    ON cp.customer_id = ro.customer_id
JOIN customer.party customer_party
    ON customer_party.party_id = cp.party_id
JOIN reference.remittance_status rs
    ON rs.remittance_status_id = ro.current_status_id
LEFT JOIN compliance.risk_assessment ra
    ON ra.remittance_id = ro.remittance_id
LEFT JOIN compliance.aml_screening_remittance asr
    ON asr.remittance_id = ro.remittance_id
LEFT JOIN compliance.aml_alert aa
    ON aa.aml_screening_id = asr.aml_screening_id
WHERE
    ra.risk_level IN ('HIGH', 'CRITICAL')
    OR aa.aml_alert_id IS NOT NULL
ORDER BY
    CASE ra.risk_level
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        ELSE 4
    END,
    aa.severity DESC,
    ro.created_at DESC
LIMIT 50;

-- 7. Validacion de Travel Rule.
-- Demuestra cumplimiento minimo de datos de originador y beneficiario.
SELECT
    trr.completeness_status AS estado_completitud,
    COUNT(*) AS cantidad_registros,
    COUNT(*) FILTER (WHERE trr.validated_at IS NOT NULL) AS cantidad_validados,
    COUNT(*) FILTER (WHERE trr.beneficiary_document_number_encrypted IS NULL) AS cantidad_sin_documento_beneficiario
FROM compliance.travel_rule_record trr
GROUP BY
    trr.completeness_status
ORDER BY
    COUNT(*) DESC;

-- 8. Conciliacion de liquidaciones por corresponsal.
-- Demuestra control operativo entre movimientos financieros y lotes de liquidacion.
SELECT
    c.correspondent_code AS codigo_corresponsal,
    c.correspondent_name AS nombre_corresponsal,
    sb.batch_code AS codigo_lote,
    sb.batch_status AS estado_lote,
    COUNT(si.settlement_item_id) AS cantidad_items,
    ROUND(sb.expected_amount, 2) AS monto_esperado_lote,
    ROUND(COALESCE(SUM(si.expected_amount), 0), 2) AS monto_esperado_items,
    ROUND(sb.reported_amount, 2) AS monto_reportado_lote,
    ROUND(COALESCE(SUM(si.difference_amount), 0), 2) AS diferencia_items
FROM settlement.settlement_batch sb
JOIN settlement.correspondent c
    ON c.correspondent_id = sb.correspondent_id
LEFT JOIN settlement.settlement_item si
    ON si.settlement_batch_id = sb.settlement_batch_id
GROUP BY
    c.correspondent_code,
    c.correspondent_name,
    sb.batch_code,
    sb.batch_status,
    sb.expected_amount,
    sb.reported_amount
ORDER BY
    sb.batch_code;

-- 9. Estado del outbox.
-- Demuestra publicacion confiable hacia productos NoSQL/analiticos.
SELECT
    publication_status AS estado_publicacion,
    event_type AS tipo_evento,
    COUNT(*) AS cantidad_eventos,
    MIN(occurred_at) AS primer_evento_en,
    MAX(occurred_at) AS ultimo_evento_en,
    COUNT(*) FILTER (WHERE published_at IS NOT NULL) AS cantidad_publicados
FROM integration.outbox_event
GROUP BY
    publication_status,
    event_type
ORDER BY
    publication_status,
    COUNT(*) DESC;
