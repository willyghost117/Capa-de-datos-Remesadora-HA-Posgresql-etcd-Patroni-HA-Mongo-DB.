-- ============================================================
-- GlobalRemit - Fase 8
-- Validacion de integridad del modelo SQL
-- Base objetivo: globalremit
-- ============================================================
-- Cada consulta debe retornar 0 filas invalidas o diferencias 0
-- cuando la carga fue consistente.
-- ============================================================

-- 1. Remesas sin detalle financiero.
SELECT
    ro.remittance_id,
    ro.remittance_code
FROM remittance.remittance_order ro
LEFT JOIN remittance.remittance_financial_detail rfd
    ON rfd.remittance_id = ro.remittance_id
WHERE rfd.remittance_id IS NULL;

-- 2. Detalles financieros huerfanos.
SELECT
    rfd.remittance_id
FROM remittance.remittance_financial_detail rfd
LEFT JOIN remittance.remittance_order ro
    ON ro.remittance_id = rfd.remittance_id
WHERE ro.remittance_id IS NULL;

-- 3. Estado actual diferente al ultimo evento historico.
WITH latest_status AS (
    SELECT DISTINCT ON (rsh.remittance_id)
        rsh.remittance_id,
        rsh.new_status_id,
        rsh.changed_at
    FROM remittance.remittance_status_history rsh
    ORDER BY
        rsh.remittance_id,
        rsh.changed_at DESC,
        rsh.status_history_id DESC
)
SELECT
    ro.remittance_id,
    ro.remittance_code,
    current_status.status_code AS current_status,
    latest_status_code.status_code AS latest_history_status,
    ls.changed_at AS latest_history_at
FROM remittance.remittance_order ro
JOIN latest_status ls
    ON ls.remittance_id = ro.remittance_id
JOIN reference.remittance_status current_status
    ON current_status.remittance_status_id = ro.current_status_id
JOIN reference.remittance_status latest_status_code
    ON latest_status_code.remittance_status_id = ls.new_status_id
WHERE ro.current_status_id <> ls.new_status_id;

-- 4. Remesas sin historial de estados.
SELECT
    ro.remittance_id,
    ro.remittance_code
FROM remittance.remittance_order ro
LEFT JOIN remittance.remittance_status_history rsh
    ON rsh.remittance_id = ro.remittance_id
WHERE rsh.remittance_id IS NULL;

-- 5. Montos financieros incoherentes.
SELECT
    rfd.remittance_id,
    rfd.send_amount,
    rfd.payout_amount,
    rfd.fee_amount,
    rfd.tax_amount,
    rfd.fx_spread_amount,
    rfd.fx_gain_amount,
    rfd.total_charged_amount
FROM remittance.remittance_financial_detail rfd
WHERE
    rfd.send_amount <= 0
    OR rfd.payout_amount <= 0
    OR rfd.fee_amount < 0
    OR rfd.tax_amount < 0
    OR rfd.fx_spread_amount < 0
    OR rfd.fx_gain_amount < 0
    OR rfd.total_charged_amount < rfd.send_amount;

-- 6. Alertas AML cerradas sin decision o sin fecha de resolucion.
SELECT
    aa.aml_alert_id,
    aa.alert_status,
    aa.decision,
    aa.created_at,
    aa.resolved_at
FROM compliance.aml_alert aa
WHERE
    aa.alert_status IN ('DISMISSED', 'CONFIRMED', 'CLOSED')
    AND (aa.decision IS NULL OR aa.resolved_at IS NULL);

-- 7. Alertas AML resueltas antes de su creacion.
SELECT
    aa.aml_alert_id,
    aa.alert_status,
    aa.created_at,
    aa.resolved_at
FROM compliance.aml_alert aa
WHERE
    aa.resolved_at IS NOT NULL
    AND aa.resolved_at < aa.created_at;

-- 8. Registros Travel Rule completos sin validacion.
SELECT
    trr.travel_rule_record_id,
    trr.remittance_id,
    trr.completeness_status,
    trr.validated_at
FROM compliance.travel_rule_record trr
WHERE
    trr.completeness_status = 'COMPLETE'
    AND trr.validated_at IS NULL;

-- 9. Diferencias entre lote de liquidacion y suma de items.
SELECT
    sb.settlement_batch_id,
    sb.batch_code,
    sb.expected_amount AS batch_expected_amount,
    COALESCE(SUM(si.expected_amount), 0) AS item_expected_amount,
    sb.expected_amount - COALESCE(SUM(si.expected_amount), 0) AS expected_difference,
    sb.reported_amount AS batch_reported_amount,
    COALESCE(SUM(si.reported_amount), 0) AS item_reported_amount,
    sb.reported_amount - COALESCE(SUM(si.reported_amount), 0) AS reported_difference
FROM settlement.settlement_batch sb
LEFT JOIN settlement.settlement_item si
    ON si.settlement_batch_id = sb.settlement_batch_id
GROUP BY
    sb.settlement_batch_id,
    sb.batch_code,
    sb.expected_amount,
    sb.reported_amount
HAVING
    ABS(sb.expected_amount - COALESCE(SUM(si.expected_amount), 0)) > 0.01
    OR ABS(COALESCE(sb.reported_amount, 0) - COALESCE(SUM(si.reported_amount), 0)) > 0.01;

-- 10. Eventos publicados sin fecha de publicacion.
SELECT
    oe.event_id,
    oe.aggregate_type,
    oe.aggregate_id,
    oe.event_type,
    oe.publication_status,
    oe.published_at
FROM integration.outbox_event oe
WHERE
    oe.publication_status = 'PUBLISHED'
    AND oe.published_at IS NULL;

-- 11. Resumen de conteos principales para evidencia.
SELECT 'customer.customer_profile' AS object_name, COUNT(*) AS total_rows FROM customer.customer_profile
UNION ALL
SELECT 'customer.beneficiary_profile', COUNT(*) FROM customer.beneficiary_profile
UNION ALL
SELECT 'remittance.remittance_order', COUNT(*) FROM remittance.remittance_order
UNION ALL
SELECT 'remittance.remittance_financial_detail', COUNT(*) FROM remittance.remittance_financial_detail
UNION ALL
SELECT 'remittance.remittance_status_history', COUNT(*) FROM remittance.remittance_status_history
UNION ALL
SELECT 'remittance.remittance_financial_movement', COUNT(*) FROM remittance.remittance_financial_movement
UNION ALL
SELECT 'compliance.risk_assessment', COUNT(*) FROM compliance.risk_assessment
UNION ALL
SELECT 'compliance.aml_alert', COUNT(*) FROM compliance.aml_alert
UNION ALL
SELECT 'settlement.settlement_batch', COUNT(*) FROM settlement.settlement_batch
UNION ALL
SELECT 'integration.outbox_event', COUNT(*) FROM integration.outbox_event
ORDER BY object_name;
