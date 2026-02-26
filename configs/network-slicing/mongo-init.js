// =============================================================================
// Open5GS Subscriber Auto-Provisioning
// =============================================================================
// Registers the 3 UERANSIM UE subscribers required for network slicing:
//   UE1 (IoT)      → imsi-001010000000004  → Slice 1 (sst:1, sd:000001)
//   UE2 (Vehicle)   → imsi-001010000000002  → Slice 2 (sst:1, sd:000002)
//   UE3 (Restricted) → imsi-001010000000001  → Slice 3 (sst:1, sd:000003)
//
// Uses upsert — safe to run multiple times (won't duplicate).
// =============================================================================

db = db.getSiblingDB("open5gs");

var subscribers = [
  {
    imsi: "001010000000004",
    label: "UE1 - IoT (Slice 1)",
    sst: 1,
    sd: "000001",
    dnn: "internet"
  },
  {
    imsi: "001010000000002",
    label: "UE2 - Vehicle (Slice 2)",
    sst: 1,
    sd: "000002",
    dnn: "internet"
  },
  {
    imsi: "001010000000001",
    label: "UE3 - Restricted (Slice 3)",
    sst: 1,
    sd: "000003",
    dnn: "internet"
  }
];

var key = "00000000000000000000000000000000";
var opc = "00000000000000000000000000000000";

subscribers.forEach(function(sub) {
  var doc = {
    imsi: sub.imsi,
    msisdn: [],
    schema_version: 1,
    security: {
      k: key,
      amf: "8000",
      op: null,
      opc: opc
    },
    ambr: {
      downlink: { value: 1, unit: 3 },
      uplink: { value: 1, unit: 3 }
    },
    slice: [
      {
        sst: sub.sst,
        sd: sub.sd,
        default_indicator: true,
        session: [
          {
            name: sub.dnn,
            type: 3,
            qos: {
              index: 9,
              arp: {
                priority_level: 8,
                pre_emption_capability: 1,
                pre_emption_vulnerability: 1
              }
            },
            ambr: {
              downlink: { value: 1, unit: 3 },
              uplink: { value: 1, unit: 3 }
            }
          }
        ]
      }
    ]
  };

  var result = db.subscribers.updateOne(
    { imsi: sub.imsi },
    { $set: doc },
    { upsert: true }
  );

  if (result.upsertedCount > 0) {
    print("CREATED: " + sub.label + " (IMSI: " + sub.imsi + ")");
  } else {
    print("EXISTS:  " + sub.label + " (IMSI: " + sub.imsi + ")");
  }
});

print("");
print("Total subscribers: " + db.subscribers.countDocuments({}));
print("Auto-provisioning complete.");