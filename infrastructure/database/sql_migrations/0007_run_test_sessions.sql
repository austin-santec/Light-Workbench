CREATE TABLE dbo.IL_RUN_SESSIONS (
    session_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES dbo.IL_RUNS(run_id),
    client_session_uuid UNIQUEIDENTIFIER NOT NULL UNIQUE,
    started_at_utc DATETIME2(3) NOT NULL,
    ended_at_utc DATETIME2(3) NULL,
    active_duration_ms BIGINT NOT NULL DEFAULT 0,
    last_checkpoint_at_utc DATETIME2(3) NOT NULL,
    end_reason VARCHAR(20) NULL,
    timing_quality VARCHAR(30) NOT NULL,
    CONSTRAINT CK_IL_RUN_SESSIONS_duration CHECK (active_duration_ms >= 0),
    CONSTRAINT CK_IL_RUN_SESSIONS_dates CHECK (
        last_checkpoint_at_utc >= started_at_utc AND
        (ended_at_utc IS NULL OR ended_at_utc = last_checkpoint_at_utc)),
    CONSTRAINT CK_IL_RUN_SESSIONS_reason CHECK (
        (ended_at_utc IS NULL AND end_reason IS NULL) OR
        (ended_at_utc IS NOT NULL AND end_reason IS NOT NULL AND
         end_reason IN ('completed', 'stopped', 'failed', 'interrupted'))),
    CONSTRAINT CK_IL_RUN_SESSIONS_quality CHECK (
        timing_quality IN ('confirmed', 'checkpoint_estimate', 'partial'))
);
CREATE UNIQUE INDEX UX_IL_RUN_SESSIONS_open ON dbo.IL_RUN_SESSIONS(run_id)
    WHERE ended_at_utc IS NULL;
CREATE INDEX IX_IL_RUN_SESSIONS_history ON dbo.IL_RUN_SESSIONS(run_id, started_at_utc, session_id);
GO
CREATE VIEW dbo.vw_RunTimingSummary AS
SELECT r.run_id, r.assignment_id,
    COALESCE(s.session_count, 0) AS timing_session_count,
    s.active_test_ms,
    DATEDIFF_BIG(millisecond, r.run_started_at_utc,
        COALESCE(r.run_ended_at_utc, SYSUTCDATETIME())) AS elapsed_ms,
    CASE WHEN s.partial_count = 0 AND s.estimated_count = 0 AND s.open_count = 0
        THEN CASE WHEN DATEDIFF_BIG(millisecond, r.run_started_at_utc,
             COALESCE(r.run_ended_at_utc, SYSUTCDATETIME())) >= s.active_test_ms
             THEN DATEDIFF_BIG(millisecond, r.run_started_at_utc,
                  COALESCE(r.run_ended_at_utc, SYSUTCDATETIME())) - s.active_test_ms
             ELSE CONVERT(BIGINT, 0) END
        ELSE NULL END AS stopped_ms,
    CASE WHEN s.session_count IS NULL THEN 'unavailable'
         WHEN s.partial_count > 0 THEN 'partial'
         WHEN s.estimated_count > 0 THEN 'checkpoint_estimate'
         WHEN s.open_count > 0 THEN 'provisional'
         ELSE 'confirmed' END AS timing_quality
FROM dbo.IL_RUNS r
LEFT JOIN (
    SELECT run_id, COUNT_BIG(*) AS session_count,
        SUM(active_duration_ms) AS active_test_ms,
        SUM(CASE WHEN timing_quality = 'partial' THEN 1 ELSE 0 END) AS partial_count,
        SUM(CASE WHEN timing_quality = 'checkpoint_estimate' THEN 1 ELSE 0 END) AS estimated_count,
        SUM(CASE WHEN ended_at_utc IS NULL THEN 1 ELSE 0 END) AS open_count
    FROM dbo.IL_RUN_SESSIONS GROUP BY run_id
) s ON s.run_id = r.run_id;
GO
GRANT SELECT, INSERT, UPDATE ON dbo.IL_RUN_SESSIONS TO lwb_app_writer;
GRANT SELECT ON dbo.vw_RunTimingSummary TO lwb_app_writer;
GRANT SELECT ON dbo.vw_RunTimingSummary TO lwb_report_reader;
