import http from "k6/http";
import exec from "k6/execution";
import { check, fail } from "k6";

const baseUrl = requiredEnvironment("COMMON_AGENT_PERFORMANCE_BASE_URL").replace(/\/$/, "");
const email = requiredEnvironment("COMMON_AGENT_PERFORMANCE_EMAIL");
const password = requiredEnvironment("COMMON_AGENT_PERFORMANCE_PASSWORD");
const origin = baseUrl;

const readRoutes = [
  "/api/v1/employees?limit=20",
  "/api/v1/conversations?limit=20",
  "/api/v1/workflows?limit=20",
  "/api/v1/model-configurations?limit=20",
];

export const options = {
  scenarios: {
    api_capacity: {
      executor: "constant-arrival-rate",
      rate: 25,
      timeUnit: "1s",
      duration: "60s",
      preAllocatedVUs: 32,
      maxVUs: 64,
      gracefulStop: "10s",
    },
  },
  thresholds: {
    "checks{scenario:api_capacity}": ["rate>0.999"],
    "http_req_failed{scenario:api_capacity}": ["rate<0.001"],
    "http_req_duration{scenario:api_capacity}": ["p(95)<500", "p(99)<1000"],
    "dropped_iterations{scenario:api_capacity}": ["count==0"],
  },
  noConnectionReuse: false,
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
  hosts: { "common-agent.test": "127.0.0.1" },
  userAgent: "common-agent-production-capacity/1",
};

export function setup() {
  const login = http.post(
    `${baseUrl}/api/v1/auth/login`,
    JSON.stringify({ email, password }),
    {
      headers: {
        "Content-Type": "application/json",
        Origin: origin,
      },
      tags: { route: "auth-login" },
    },
  );
  if (login.status !== 200) {
    fail(`capacity setup login failed: ${login.status}`);
  }
  const cookieName = Object.keys(login.cookies).find((name) =>
    name.endsWith("common-agent-session"),
  );
  const cookie = cookieName ? login.cookies[cookieName]?.[0]?.value : undefined;
  if (!cookieName || !cookie) {
    fail("capacity setup did not receive the production session cookie");
  }
  const sessionCookie = `${cookieName}=${cookie}`;
  const tenants = http.get(`${baseUrl}/api/v1/tenants`, {
    headers: { Cookie: sessionCookie },
    tags: { route: "tenant-list" },
  });
  if (tenants.status !== 200) {
    fail(`capacity setup tenant list failed: ${tenants.status}`);
  }
  const accesses = tenants.json();
  if (!Array.isArray(accesses) || typeof accesses[0]?.id !== "string") {
    fail("capacity setup did not resolve an accessible tenant");
  }
  return { sessionCookie, tenantId: accesses[0].id };
}

export default function (authentication) {
  const route = readRoutes[exec.scenario.iterationInTest % readRoutes.length];
  const response = http.get(`${baseUrl}${route}`, {
    headers: {
      Cookie: authentication.sessionCookie,
      "X-Tenant-ID": authentication.tenantId,
    },
    responseType: "none",
    tags: { route: route.split("?", 1)[0] },
  });
  check(response, { "authenticated read returns 200": (result) => result.status === 200 });
}

export function handleSummary(data) {
  const result = {
    schema_version: 1,
    requests_total: metricValue(data, "http_reqs", "count"),
    failure_rate: metricValue(data, "http_req_failed", "rate"),
    dropped_iterations: metricValue(data, "dropped_iterations", "count"),
    p95_ms: metricValue(data, "http_req_duration", "p(95)"),
    p99_ms: metricValue(data, "http_req_duration", "p(99)"),
  };
  const serialized = `${JSON.stringify(result)}\n`;
  const output = { stdout: serialized };
  const resultFile = __ENV.COMMON_AGENT_K6_RESULT_FILE?.trim();
  if (resultFile) {
    output[resultFile] = serialized;
  }
  return output;
}

function metricValue(data, metricName, valueName) {
  const value = data.metrics?.[metricName]?.values?.[valueName];
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error(`k6 summary is missing ${metricName}.${valueName}`);
  }
  return value;
}

function requiredEnvironment(name) {
  const value = __ENV[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}
