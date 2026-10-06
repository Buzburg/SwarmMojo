# Chat trajectory recording

The gateway does not automatically create trajectory records from chat requests by default. It omits the `X-ROMS-Session` header when no trajectory was created. Successful, failed, streaming and cancelled requests follow the same setting.

An operator can explicitly enable automatic recording by setting `ROMS_RECORD_CHAT_TRAJECTORIES=1` in the gateway's environment. Only the exact value `1` enables it. Changing a managed service's environment requires a service restart. This change does not edit the installed environment or restart any service.

When enabled, a request with nonempty user text records the latest user prompt as the trajectory goal, a generated session ID and completion outcome. The gateway does not record completion text as trajectory steps. Error summaries may include backend diagnostic text. Successful completion means the request completed; it does not verify the answer or prove that tools ran. Empty user text creates no trajectory or session header.

This is a control for **automatic gateway trajectory capture**, not a complete private browsing mode. Prompts still reach the configured model and may be used by local retrieval; clients, retrieval caches, model backends and explicitly invoked tools have their own data handling. Existing records, databases and backups are not erased. Automatic retention, a data-deletion interface and diagnostic redaction remain separate work.

Manually invoked trajectory tools retain their existing behavior: an explicit `start_trajectory_session`, `record_trajectory_step` or `finish_trajectory_session` call can store supplied content even when automatic chat recording is off. Recorded trajectories remain local application data and can be read by existing analysis/export tools. Review their contents before sharing or using them in datasets.

Offline regression coverage lives in `tests/test_gateway_privacy.py`: isolated SQLite recording, synthetic private prompt/completion, opt-in values, session-header accuracy, streaming, backend rejection/error, cancellation, disconnect and manual-tool behavior. The real TCP disconnect regression explicitly enables recording when checking trajectory outcomes.
