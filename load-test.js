import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  stages: [
    { duration: "10s", target: 20 },
    { duration: "20s", target: 100 },
    { duration: "10s", target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500"],
  },
};

export default function () {
  const health = http.get("http://127.0.0.1:8082/health");
  check(health, { "health ok": (r) => r.status === 200 && r.body.includes("ok") });

  const metrics = http.get("http://127.0.0.1:8082/metrics");
  check(metrics, { "metrics ok": (r) => r.status === 200 && r.body.includes("botkit_") });

  const version = http.get("http://127.0.0.1:8082/version");
  check(version, { "version ok": (r) => r.status === 200 && r.body.includes("0.6.0") });

  sleep(0.1);
}
