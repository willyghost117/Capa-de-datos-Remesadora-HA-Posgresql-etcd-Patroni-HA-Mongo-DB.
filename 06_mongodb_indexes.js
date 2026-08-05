// ============================================================
// GlobalRemit - Fase 6
// MongoDB indexes
// Run after 06_mongodb_setup.js
// ============================================================

const targetDb = db.getSiblingDB("globalremit_analytics");

targetDb.remittance_events.createIndex(
  { event_id: 1 },
  { name: "ux_event_id", unique: true }
);
targetDb.remittance_events.createIndex(
  { remittance_id: 1, occurred_at: 1 },
  { name: "ix_event_remittance_date" }
);
targetDb.remittance_events.createIndex(
  { aggregate_type: 1, aggregate_id: 1, occurred_at: 1 },
  { name: "ix_event_aggregate_date" }
);
targetDb.remittance_events.createIndex(
  { event_type: 1, occurred_at: 1 },
  { name: "ix_event_type_date" }
);
targetDb.remittance_events.createIndex(
  { correlation_id: 1 },
  { name: "ix_event_correlation", sparse: true }
);

targetDb.remittance_lifecycle.createIndex(
  { remittance_id: 1 },
  { name: "ux_lifecycle_remittance", unique: true }
);
targetDb.remittance_lifecycle.createIndex(
  { remittance_code: 1 },
  { name: "ux_lifecycle_code", unique: true }
);
targetDb.remittance_lifecycle.createIndex(
  { current_status: 1, "timestamps.created_at": -1 },
  { name: "ix_lifecycle_status_date" }
);
targetDb.remittance_lifecycle.createIndex(
  { "corridor.corridor_code": 1, "timestamps.created_at": -1 },
  { name: "ix_lifecycle_corridor_date" }
);
targetDb.remittance_lifecycle.createIndex(
  { "parties.customer_id": 1, "timestamps.created_at": -1 },
  { name: "ix_lifecycle_customer_date" }
);
targetDb.remittance_lifecycle.createIndex(
  { "parties.beneficiary_id": 1, "timestamps.created_at": -1 },
  { name: "ix_lifecycle_beneficiary_date" }
);
targetDb.remittance_lifecycle.createIndex(
  { "compliance.risk_level": 1, current_status: 1 },
  { name: "ix_lifecycle_risk_status" }
);

// Time-series collections do not support unique indexes.
targetDb.fx_rate_timeseries.createIndex(
  { "metadata.currency_pair": 1, observed_at: -1 },
  { name: "ix_fx_pair_date" }
);
targetDb.fx_rate_timeseries.createIndex(
  { "metadata.provider_code": 1, observed_at: -1 },
  { name: "ix_fx_provider_date" }
);
targetDb.fx_rate_timeseries.createIndex(
  { exchange_rate_id: 1 },
  { name: "ix_fx_exchange_rate_id" }
);

targetDb.customer_behavior_profiles.createIndex(
  { customer_id: 1 },
  { name: "ux_behavior_customer", unique: true }
);
targetDb.customer_behavior_profiles.createIndex(
  { "risk_features.velocity_score": -1 },
  { name: "ix_behavior_velocity" }
);
targetDb.customer_behavior_profiles.createIndex(
  { "risk_features.amount_deviation_score": -1 },
  { name: "ix_behavior_amount_deviation" }
);
targetDb.customer_behavior_profiles.createIndex(
  { computed_at: -1 },
  { name: "ix_behavior_computed" }
);

targetDb.fraud_signals.createIndex(
  { signal_id: 1 },
  { name: "ux_fraud_signal", unique: true }
);
targetDb.fraud_signals.createIndex(
  { remittance_id: 1, detected_at: -1 },
  { name: "ix_fraud_remittance_date" }
);
targetDb.fraud_signals.createIndex(
  { customer_id: 1, detected_at: -1 },
  { name: "ix_fraud_customer_date" }
);
targetDb.fraud_signals.createIndex(
  { status: 1, severity: 1, detected_at: -1 },
  { name: "ix_fraud_status_severity_date" }
);
targetDb.fraud_signals.createIndex(
  { signal_type: 1, detected_at: -1 },
  { name: "ix_fraud_type_date" }
);

targetDb.compliance_case_snapshots.createIndex(
  { case_id: 1 },
  { name: "ux_compliance_case", unique: true }
);
targetDb.compliance_case_snapshots.createIndex(
  { status: 1, severity: 1, opened_at: -1 },
  { name: "ix_case_status_severity_date" }
);
targetDb.compliance_case_snapshots.createIndex(
  { remittance_id: 1 },
  { name: "ix_case_remittance", sparse: true }
);
targetDb.compliance_case_snapshots.createIndex(
  { "party_refs.party_id": 1, status: 1 },
  { name: "ix_case_party_status" }
);

targetDb.corridor_daily_metrics.createIndex(
  { corridor_code: 1, metric_date: 1 },
  { name: "ux_metric_corridor_date", unique: true }
);
targetDb.corridor_daily_metrics.createIndex(
  { metric_date: -1 },
  { name: "ix_metric_date" }
);
targetDb.corridor_daily_metrics.createIndex(
  { "amounts.fx_spread_amount": -1 },
  { name: "ix_metric_fx_spread" }
);
targetDb.corridor_daily_metrics.createIndex(
  { "risk.high_risk_count": -1 },
  { name: "ix_metric_high_risk" }
);

targetDb.settlement_status.createIndex(
  { settlement_batch_id: 1 },
  { name: "ux_settlement_batch", unique: true }
);
targetDb.settlement_status.createIndex(
  { batch_code: 1 },
  { name: "ux_settlement_code", unique: true }
);
targetDb.settlement_status.createIndex(
  { status: 1, updated_at: -1 },
  { name: "ix_settlement_status_date" }
);
targetDb.settlement_status.createIndex(
  { "correspondent.correspondent_id": 1, "period.end_at": -1 },
  { name: "ix_settlement_correspondent_date" }
);
targetDb.settlement_status.createIndex(
  { currency: 1, "period.end_at": -1 },
  { name: "ix_settlement_currency_date" }
);

print("MongoDB indexes created.");
