// ============================================================
// GlobalRemit - Fase 7
// Load generated JSON products into MongoDB using mongosh.
// Run from Tarea2:
// mongosh "mongodb://127.0.0.1:27017" .\07_generador_datos\load_mongo_from_json.js
// ============================================================

const fs = require("fs");
const path = require("path");

const databaseName = "globalremit_analytics";
const outputDir = path.join(process.cwd(), "07_generador_datos", "output");
const targetDb = db.getSiblingDB(databaseName);

const collections = [
  "remittance_events",
  "remittance_lifecycle",
  "fx_rate_timeseries",
  "customer_behavior_profiles",
  "fraud_signals",
  "compliance_case_snapshots",
  "corridor_daily_metrics",
  "settlement_status"
];

const isoDatePattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/;

function reviveDates(value) {
  if (Array.isArray(value)) {
    return value.map(reviveDates);
  }
  if (value && typeof value === "object") {
    for (const key of Object.keys(value)) {
      value[key] = reviveDates(value[key]);
    }
    return value;
  }
  if (typeof value === "string" && isoDatePattern.test(value)) {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed;
    }
  }
  return value;
}

for (const collectionName of collections) {
  const filePath = path.join(outputDir, `${collectionName}.json`);
  if (!fs.existsSync(filePath)) {
    print(`Skipping ${collectionName}; file not found.`);
    continue;
  }

  const docs = reviveDates(JSON.parse(fs.readFileSync(filePath, "utf8")));
  targetDb.getCollection(collectionName).deleteMany({});

  if (docs.length > 0) {
    targetDb.getCollection(collectionName).insertMany(docs, { ordered: false });
  }
  print(`${collectionName}: ${docs.length} documents loaded.`);
}

print("MongoDB JSON load completed.");
