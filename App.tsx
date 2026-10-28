
import { useEffect, useMemo, useState } from "react";

import {
  Alert,
  AppBar,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  CssBaseline,
  Drawer,
  Grid,
  List,
  ListItemButton,
  ListItemText,
  Toolbar,
  Typography,
} from "@mui/material";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import AlertCenter from "./components/AlertCenter";
import MetricsDashboard from "./components/MetricsDashboard";
import LogExplorer from "./components/LogExplorer";
import TraceExplorer from "./components/TraceExplorer";
import DependencyMap from "./components/DependencyMap";
import RootCauseAnalysis from "./components/RootCauseAnalysis";

import { getAlerts } from "./api/metrics";

const drawerWidth = 240;

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080";
const METRICS_API = API_BASE;
const TRACES_API = API_BASE;

const menuItems = [
  "Overview Dashboard",
  "Trace Explorer",
  "Dependency Map",
  "Log Explorer",
  "Metrics Dashboard",
  "Root-Cause Analysis",
  "Alert Center",
] as const;

type Page = (typeof menuItems)[number];

type MetricAggregate = {
  service_name: string;
  metric_name: string;
  average?: number | string | null;
  avg_value?: number | string | null;
  sample_count?: number | null;
  count?: number | null;
};

type MetricSample = {
  service_name: string;
  metric_name: string;
  value: number;
};

type TraceSummary = {
  trace_id: string;
  service_name: string | null;
  status: string;
};

type TraceSpan = {
  service_name: string;
  duration_ms: number | null;
  status: string;
};

type ChartPoint = {
  service: string;
  latency: number;
};

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(
      `API request failed: ${response.status} (${url})`
    );
  }

  return (await response.json()) as T;
}

export default function App() {
  const [selectedPage, setSelectedPage] =
    useState<Page>("Overview Dashboard");

  const [alertCount, setAlertCount] =
    useState<number | null>(null);

  const [metricSamples, setMetricSamples] =
    useState<MetricSample[]>([]);

  const [aggregates, setAggregates] =
    useState<MetricAggregate[]>([]);

  const [traces, setTraces] =
    useState<TraceSummary[]>([]);

  const [spans, setSpans] =
    useState<TraceSpan[]>([]);

  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadDashboard() {
      try {
        const [
          alertsResult,
          samplesResult,
          aggregatesResult,
          tracesResult,
        ] = await Promise.all([
          getAlerts(),
          fetchJson<{
            count: number;
            samples: MetricSample[];
          }>(`${METRICS_API}/metrics/samples?limit=500`),
          fetchJson<{
            count: number;
            aggregates: MetricAggregate[];
          }>(`${METRICS_API}/metrics/aggregates?limit=500`),
          fetchJson<{
            count: number;
            traces: TraceSummary[];
          }>(`${TRACES_API}/traces?limit=500`),
        ]);

        const detailResults = await Promise.all(
          tracesResult.traces.map((trace) =>
            fetchJson<{
              span_count: number;
              spans: TraceSpan[];
            }>(
              `${TRACES_API}/traces/${encodeURIComponent(
                trace.trace_id
              )}`
            )
          )
        );

        if (!active) return;

        setAlertCount(alertsResult.count);
        setMetricSamples(samplesResult.samples ?? []);
        setAggregates(aggregatesResult.aggregates ?? []);
        setTraces(tracesResult.traces ?? []);
        setSpans(detailResults.flatMap((item) => item.spans));
        setApiError("");
      } catch (error) {
        if (active) {
          setApiError(
            error instanceof Error
              ? error.message
              : "Unable to load dashboard data"
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    void loadDashboard();

    const interval = window.setInterval(() => {
      void loadDashboard();
    }, 10000);

    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  const services = useMemo(() => {
    const names = new Set<string>();

    spans.forEach((span) => {
      if (span.service_name) names.add(span.service_name);
    });

    metricSamples.forEach((sample) => {
      if (sample.service_name) names.add(sample.service_name);
    });

    return Array.from(names).sort();
  }, [spans, metricSamples]);

  const latencyData = useMemo<ChartPoint[]>(() => {
    const grouped = new Map<
      string,
      { total: number; count: number }
    >();

    const latencySamples = metricSamples.filter(
      (sample) =>
        sample.metric_name === "response_time_ms" &&
        Number.isFinite(Number(sample.value))
    );

    latencySamples.forEach((sample) => {
      const previous = grouped.get(sample.service_name) ?? {
        total: 0,
        count: 0,
      };

      grouped.set(sample.service_name, {
        total: previous.total + Number(sample.value),
        count: previous.count + 1,
      });
    });

    return Array.from(grouped.entries()).map(
      ([service, values]) => ({
        service,
        latency: Math.round(
          values.total / values.count
        ),
      })
    );
  }, [metricSamples]);

  const averageLatency = useMemo(() => {
    const values = metricSamples
      .filter(
        (sample) =>
          sample.metric_name === "response_time_ms"
      )
      .map((sample) => Number(sample.value))
      .filter((value) => Number.isFinite(value));

    if (values.length === 0) return null;

    return Math.round(
      values.reduce((sum, value) => sum + value, 0) /
        values.length
    );
  }, [metricSamples]);

  const serviceHealth = useMemo(() => {
    return services.map((service) => {
      const relevantSpans = spans.filter(
        (span) => span.service_name === service
      );

      const failed = relevantSpans.some((span) =>
        ["ERROR", "FAILED", "FAILURE"].includes(
          span.status.toUpperCase()
        )
      );

      const latency = latencyData.find(
        (item) => item.service === service
      )?.latency;

      const slow =
        (latency !== undefined && latency > 1000) ||
        relevantSpans.some(
          (span) =>
            span.duration_ms !== null &&
            span.duration_ms > 1000
        );

      return {
        service,
        status: failed
          ? "Error"
          : slow
            ? "Slow"
            : relevantSpans.length > 0 || latency !== undefined
              ? "No issues detected"
              : "Unknown",
        color: failed
          ? ("error" as const)
          : slow
            ? ("warning" as const)
            : ("default" as const),
      };
    });
  }, [services, spans, latencyData]);

  function renderOverview() {
    return (
      <>
        {apiError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {apiError}
          </Alert>
        )}

        {loading && (
          <Box sx={{ display: "flex", justifyContent: "center", mb: 2 }}>
            <CircularProgress />
          </Box>
        )}

        <Grid container spacing={3}>
          {[
            {
              title: "Detected Services",
              value: services.length,
            },
            {
              title: "Recorded Traces",
              value: traces.length,
            },
            {
              title: "Average Response Time",
              value:
                averageLatency === null
                  ? "N/A"
                  : `${averageLatency} ms`,
            },
            {
              title: "Recorded Alerts",
              value: alertCount ?? "...",
            },
          ].map((item) => (
            <Grid
              size={{ xs: 12, sm: 6, md: 3 }}
              key={item.title}
            >
              <Card sx={{ height: "100%" }}>
                <CardContent>
                  <Typography
                    color="text.secondary"
                    gutterBottom
                  >
                    {item.title}
                  </Typography>
                  <Typography variant="h4">
                    {item.value}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>

        <Card sx={{ mt: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Service Response Times (Live Metrics)
            </Typography>

            {latencyData.length === 0 ? (
              <Typography color="text.secondary">
                No response-time metrics recorded yet.
              </Typography>
            ) : (
              <Box sx={{ width: "100%", height: 320 }}>
                <ResponsiveContainer
                  width="100%"
                  height="100%"
                >
                  <BarChart data={latencyData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="service" />
                    <YAxis />
                    <Tooltip />
                    <Bar
                      dataKey="latency"
                      name="Average latency (ms)"
                      fill="#1976d2"
                    />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            )}
          </CardContent>
        </Card>

        <Card sx={{ mt: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Observed Service Status
            </Typography>

            {serviceHealth.length === 0 ? (
              <Typography color="text.secondary">
                No service telemetry available yet.
              </Typography>
            ) : (
              serviceHealth.map((item) => (
                <Chip
                  key={item.service}
                  label={`${item.service}: ${item.status}`}
                  color={item.color}
                  sx={{ mr: 1, mb: 1 }}
                />
              ))
            )}
          </CardContent>
        </Card>

        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mt: 2 }}
        >
          Values reflect retrieved telemetry records, not
          production-wide request totals or active health checks.
          Metrics and traces are limited to the latest 500 records.
          Loaded aggregate groups: {aggregates.length}.
        </Typography>
      </>
    );
  }

  function renderPage() {
    switch (selectedPage) {
      case "Trace Explorer":
        return <TraceExplorer />;
      case "Dependency Map":
        return <DependencyMap />;
      case "Log Explorer":
        return <LogExplorer />;
      case "Metrics Dashboard":
        return <MetricsDashboard />;
      case "Root-Cause Analysis":
        return <RootCauseAnalysis />;
      case "Alert Center":
        return <AlertCenter />;
      default:
        return renderOverview();
    }
  }

  return (
    <Box sx={{ display: "flex" }}>
      <CssBaseline />

      <AppBar
        position="fixed"
        sx={{
          zIndex: (theme) => theme.zIndex.drawer + 1,
        }}
      >
        <Toolbar>
          <Typography variant="h6">
            Distributed Observability Platform
          </Typography>
        </Toolbar>
      </AppBar>

      <Drawer
        variant="permanent"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          "& .MuiDrawer-paper": {
            width: drawerWidth,
            boxSizing: "border-box",
          },
        }}
      >
        <Toolbar />
        <List>
          {menuItems.map((item) => (
            <ListItemButton
              key={item}
              selected={selectedPage === item}
              onClick={() => setSelectedPage(item)}
            >
              <ListItemText primary={item} />
            </ListItemButton>
          ))}
        </List>
      </Drawer>

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          minHeight: "100vh",
          bgcolor: "#f4f6f8",
          minWidth: 0,
        }}
      >
        <Toolbar />

        <Typography variant="h4" sx={{ mb: 3 }}>
          {selectedPage}
        </Typography>

        {renderPage()}
      </Box>
    </Box>
  );
}
