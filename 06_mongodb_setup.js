// ============================================================
// GlobalRemit - Fase 6
// MongoDB collections and validators
// Run with: mongosh "mongodb://localhost:27017" 06_mongodb_setup.js
// ============================================================

const databaseName = "globalremit_analytics";
const targetDb = db.getSiblingDB(databaseName);

const regularCollections = [
  "remittance_events",
  "remittance_lifecycle",
  "customer_behavior_profiles",
  "fraud_signals",
  "compliance_case_snapshots",
  "corridor_daily_metrics",
  "settlement_status"
];

const allCollections = [...regularCollections, "fx_rate_timeseries"];

for (const collectionName of allCollections) {
  if (targetDb.getCollectionNames().includes(collectionName)) {
    targetDb.getCollection(collectionName).drop();
  }
}

const validators = {
  remittance_events: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "event_id", "event_type", "event_version",
        "aggregate_type", "aggregate_id", "occurred_at",
        "ingested_at", "source", "payload"
      ],
      properties: {
        _id: { bsonType: "string" },
        event_id: { bsonType: "string" },
        event_type: { bsonType: "string" },
        event_version: { bsonType: "int", minimum: 1 },
        aggregate_type: { bsonType: "string" },
        aggregate_id: { bsonType: ["long", "int"] },
        remittance_id: { bsonType: ["long", "int", "null"] },
        occurred_at: { bsonType: "date" },
        ingested_at: { bsonType: "date" },
        correlation_id: { bsonType: ["string", "null"] },
        source: {
          bsonType: "object",
          required: ["database", "schema", "table"],
          properties: {
            database: { bsonType: "string" },
            schema: { bsonType: "string" },
            table: { bsonType: "string" }
          }
        },
        payload: { bsonType: "object" },
        data_classification: {
          enum: ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "SENSITIVE"]
        }
      }
    }
  },
  remittance_lifecycle: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "remittance_id", "remittance_code", "version",
        "current_status", "corridor", "parties", "financial",
        "compliance", "timestamps", "last_event_id", "updated_at"
      ],
      properties: {
        _id: { bsonType: ["long", "int"] },
        remittance_id: { bsonType: ["long", "int"] },
        remittance_code: { bsonType: "string" },
        version: { bsonType: "int", minimum: 1 },
        current_status: { bsonType: "string" },
        corridor: { bsonType: "object" },
        parties: { bsonType: "object" },
        financial: { bsonType: "object" },
        compliance: { bsonType: "object" },
        timestamps: { bsonType: "object" },
        status_timeline: { bsonType: "array" },
        last_event_id: { bsonType: "string" },
        updated_at: { bsonType: "date" }
      }
    }
  },
  customer_behavior_profiles: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "customer_id", "profile_version", "windows",
        "usual_patterns", "risk_features", "last_event_id", "computed_at"
      ],
      properties: {
        _id: { bsonType: ["long", "int"] },
        customer_id: { bsonType: ["long", "int"] },
        profile_version: { bsonType: "int", minimum: 1 },
        windows: { bsonType: "object" },
        usual_patterns: { bsonType: "object" },
        risk_features: { bsonType: "object" },
        last_event_id: { bsonType: "string" },
        computed_at: { bsonType: "date" },
        expires_at: { bsonType: ["date", "null"] }
      }
    }
  },
  fraud_signals: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "signal_id", "remittance_id", "customer_id",
        "signal_type", "severity", "score", "rule",
        "detected_at", "source_event_id", "status"
      ],
      properties: {
        _id: { bsonType: "string" },
        signal_id: { bsonType: "string" },
        remittance_id: { bsonType: ["long", "int"] },
        customer_id: { bsonType: ["long", "int"] },
        signal_type: { bsonType: "string" },
        severity: { enum: ["LOW", "MEDIUM", "HIGH", "CRITICAL"] },
        score: { bsonType: ["double", "decimal"], minimum: 0, maximum: 1 },
        rule: { bsonType: "object" },
        features: { bsonType: "object" },
        decision_context: { bsonType: "object" },
        detected_at: { bsonType: "date" },
        source_event_id: { bsonType: "string" },
        status: { enum: ["OPEN", "REVIEWED", "DISMISSED", "CONFIRMED"] }
      }
    }
  },
  compliance_case_snapshots: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "case_id", "case_type", "status", "severity",
        "party_refs", "opened_at", "updated_at", "source_event_id"
      ],
      properties: {
        _id: { bsonType: ["long", "int"] },
        case_id: { bsonType: ["long", "int"] },
        case_type: { enum: ["AML_ALERT", "KYC_REVIEW"] },
        status: { bsonType: "string" },
        severity: { enum: ["LOW", "MEDIUM", "HIGH", "CRITICAL"] },
        remittance_id: { bsonType: ["long", "int", "null"] },
        party_refs: { bsonType: "array", minItems: 1 },
        screening: { bsonType: ["object", "null"] },
        decision: { bsonType: ["string", "null"] },
        assigned_team: { bsonType: ["string", "null"] },
        opened_at: { bsonType: "date" },
        updated_at: { bsonType: "date" },
        source_event_id: { bsonType: "string" }
      }
    }
  },
  corridor_daily_metrics: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "corridor_code", "metric_date", "send_currency",
        "payout_currency", "counts", "amounts", "service", "risk",
        "calculation_version", "computed_at", "source_watermark"
      ],
      properties: {
        _id: { bsonType: "string" },
        corridor_code: { bsonType: "string" },
        metric_date: { bsonType: "date" },
        send_currency: { bsonType: "string", minLength: 3, maxLength: 3 },
        payout_currency: { bsonType: "string", minLength: 3, maxLength: 3 },
        counts: { bsonType: "object" },
        amounts: { bsonType: "object" },
        service: { bsonType: "object" },
        risk: { bsonType: "object" },
        calculation_version: { bsonType: "int", minimum: 1 },
        computed_at: { bsonType: "date" },
        source_watermark: { bsonType: "date" }
      }
    }
  },
  settlement_status: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "settlement_batch_id", "batch_code", "correspondent",
        "currency", "period", "totals", "status", "last_event_id", "updated_at"
      ],
      properties: {
        _id: { bsonType: ["long", "int"] },
        settlement_batch_id: { bsonType: ["long", "int"] },
        batch_code: { bsonType: "string" },
        correspondent: { bsonType: "object" },
        currency: { bsonType: "string", minLength: 3, maxLength: 3 },
        period: { bsonType: "object" },
        totals: { bsonType: "object" },
        status: { bsonType: "string" },
        exceptions: { bsonType: "array" },
        last_event_id: { bsonType: "string" },
        updated_at: { bsonType: "date" }
      }
    }
  }
};

for (const collectionName of regularCollections) {
  targetDb.createCollection(collectionName, {
    validator: validators[collectionName],
    validationLevel: "strict",
    validationAction: "error"
  });
}

targetDb.createCollection("fx_rate_timeseries", {
  timeseries: {
    timeField: "observed_at",
    metaField: "metadata",
    granularity: "seconds"
  }
});

print(`Created ${allCollections.length} collections in ${databaseName}.`);

