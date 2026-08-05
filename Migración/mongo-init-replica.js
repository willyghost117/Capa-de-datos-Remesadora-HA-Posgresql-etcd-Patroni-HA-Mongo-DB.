const replicaSetName = "rsGlobalRemit";

const config = {
  _id: replicaSetName,
  members: [
    { _id: 0, host: "globalremit-mongo1:27017", priority: 2 },
    { _id: 1, host: "globalremit-mongo2:27017", priority: 1 },
    { _id: 2, host: "globalremit-mongo3:27017", priority: 1 }
  ]
};

try {
  const status = rs.status();
  print(`Replica set already initialized: ${status.set}`);
} catch (error) {
  print(`Initializing replica set ${replicaSetName}...`);
  rs.initiate(config);
}

printjson(rs.status());

