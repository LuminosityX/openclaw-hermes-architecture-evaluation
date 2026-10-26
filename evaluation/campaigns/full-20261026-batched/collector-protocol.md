# OBS-02: native event publication under collector failure

The exact official `@openclaw/diagnostics-otel@2026.10.7` addon is installed once on the disposable GitHub worker. Its registry integrity, package hash, complete lock, core build identity and provider plugin identity are retained. The core runtime is not patched or copied per case. All local fixtures and publication remain inside the evaluator namespace.

The native plugin logger emits unique `EVAL_OBS_EVENT_...` IDs into both the native local JSONL log and the official OTLP log pipeline. A positive control requires an independently decoded actual OTLP delivery for the native task, not merely a successful task or an open port. Synthetic content capture is explicitly enabled so exact event identities can be joined. No real model, credential or personal data is present.

An independent bounded protobuf parser extracts event IDs only from actual OTLP LogRecord body strings. HTTP 503 attempts are recorded separately from successfully accepted deliveries. File-log IDs define offered native records; successful collector counts define missing and duplicate delivery. The evaluator does not invent unexported spans or treat retry attempts as successfully delivered duplicates.

| Scenario | Matched intervention |
| --- | --- |
| S01 | Collector returns 503 for actual target IDs, remains unavailable for two additional seconds, then recovers. |
| S02 | Same matched boundary, held for twelve additional seconds. |
| S03 | After the target IDs reach a failing collector attempt, the actual Gateway/exporter process is killed. It restarts with the same native state and local log; a new independent task/export control verifies recovery. |
| S04 | 256 synchronous native log records are offered against the SDK's configured 64-entry queue while the collector fails. The installed SDK source must expose the exact queue environment control; its hash/version are retained. |

The explicit SDK profile uses eight-record batches, one-second schedule/export timeouts, and a 64-entry queue. Native local log IDs must prove all offered records existed. Every outage must match target IDs in actual failed collector requests. Post-outage task and OTLP controls must succeed before scoring.

The acceptance criterion is complete, nonduplicating eventual event delivery. A failure is a measured outcome under that criterion, not an assertion that OpenClaw promises durable spooling or exactly-once telemetry. The record retains task outcomes, missing IDs, duplicate counts, batch attempts, publisher restart and locally visible overflow warnings. An absent file-log warning does not establish absence of a signal on every diagnostic interface. Architectural causes and tradeoffs remain deferred.

Contracts: [official setup](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/docs/gateway/opentelemetry/setup.md), [content capture and privacy](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/docs/gateway/opentelemetry/privacy-and-trace-context.md), and [native log exporter integration](https://github.com/openclaw/openclaw/blob/157d8c2bc3ea2fa183afdc11088e69690bf8e64e/extensions/diagnostics-otel/src/service-logs.ts).
