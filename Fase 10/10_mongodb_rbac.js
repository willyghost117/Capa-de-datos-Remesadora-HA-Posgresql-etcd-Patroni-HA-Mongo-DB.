// ============================================================
// GlobalRemit - Etapa 4
// RBAC MongoDB para ambiente academico
// Ejecutar en mongosh con privilegios administrativos.
// ============================================================

const adminDb = db.getSiblingDB("admin");
const analyticsDbName = "globalremit_analytics";

adminDb.createRole({
  role: "gr_mongo_analytics_read",
  privileges: [
    {
      resource: { db: analyticsDbName, collection: "" },
      actions: ["find"]
    }
  ],
  roles: []
});

adminDb.createRole({
  role: "gr_mongo_pipeline_rw",
  privileges: [
    {
      resource: { db: analyticsDbName, collection: "" },
      actions: ["find", "insert", "update", "remove", "createIndex"]
    }
  ],
  roles: []
});

adminDb.createRole({
  role: "gr_mongo_compliance_read",
  privileges: [
    {
      resource: { db: analyticsDbName, collection: "fraud_signals" },
      actions: ["find"]
    },
    {
      resource: { db: analyticsDbName, collection: "compliance_case_snapshots" },
      actions: ["find"]
    }
  ],
  roles: []
});

adminDb.createUser({
  user: "gr_mongo_analyst",
  pwd: "ChangeMe_MongoAnalyst_2026!",
  roles: [{ role: "gr_mongo_analytics_read", db: "admin" }]
});

adminDb.createUser({
  user: "gr_mongo_pipeline",
  pwd: "ChangeMe_MongoPipeline_2026!",
  roles: [{ role: "gr_mongo_pipeline_rw", db: "admin" }]
});

adminDb.createUser({
  user: "gr_mongo_compliance",
  pwd: "ChangeMe_MongoCompliance_2026!",
  roles: [{ role: "gr_mongo_compliance_read", db: "admin" }]
});

print("MongoDB RBAC academico creado. Cambiar claves antes de usar en ambientes reales.");

