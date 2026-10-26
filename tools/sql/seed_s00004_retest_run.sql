SET NOCOUNT ON;
SET XACT_ABORT ON;
SET ANSI_NULLS ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET QUOTED_IDENTIFIER ON;
SET NUMERIC_ROUNDABORT OFF;

BEGIN TRANSACTION;

DECLARE @UnitId BIGINT;
DECLARE @AssignmentId BIGINT;
DECLARE @SourceRunId BIGINT;
DECLARE @RetestRunId BIGINT;
DECLARE @ExistingRunId BIGINT;
DECLARE @RunUuid UNIQUEIDENTIFIER = '7D0F8E6C-8D1D-4A5C-9B6E-2F5A8C1D0E74';

SELECT TOP (1)
    @UnitId = unit.unit_id,
    @AssignmentId = assignment.assignment_id
FROM dbo.UNITS AS unit
INNER JOIN dbo.UNIT_SWITCH_ASSIGNMENTS AS assignment
    ON assignment.unit_id = unit.unit_id
    AND assignment.removed_at_utc IS NULL
WHERE unit.main_board_serial = N'S-00004';

IF @UnitId IS NULL OR @AssignmentId IS NULL
    THROW 51000, N'Expected active S-00004 unit assignment was not found.', 1;

SELECT @SourceRunId = run_id
FROM dbo.IL_RUNS
WHERE assignment_id = @AssignmentId
  AND run_number = 1;

IF @SourceRunId IS NULL
    THROW 51001, N'Expected S-00004 source run 1 was not found.', 1;

SELECT @ExistingRunId = run_id
FROM dbo.IL_RUNS
WHERE client_run_uuid = @RunUuid;

IF @ExistingRunId IS NOT NULL
BEGIN
    COMMIT TRANSACTION;
    SELECT
        @ExistingRunId AS retest_run_id,
        N'The S-00004 retest fixture already exists; no rows were added.' AS result;
    RETURN;
END;

IF EXISTS (
    SELECT 1
    FROM dbo.IL_RUNS
    WHERE assignment_id = @AssignmentId
      AND run_number = 2
)
    THROW 51002, N'S-00004 run 2 already exists with a different identity.', 1;

INSERT INTO dbo.IL_RUNS (
    assignment_id,
    run_number,
    client_run_uuid,
    run_started_at_utc,
    run_ended_at_utc,
    tested_by,
    wavelength_mode,
    operating_band,
    application_version,
    completion_status,
    run_purpose,
    analysis_status,
    part_number_snapshot,
    front_panel_channel_count,
    measurement_hardware_json,
    limit_snapshot_json,
    notes,
    station_number
)
SELECT
    source_run.assignment_id,
    2,
    @RunUuid,
    DATEADD(MINUTE, 30, source_run.run_ended_at_utc),
    DATEADD(MINUTE, 40, source_run.run_ended_at_utc),
    source_run.tested_by,
    source_run.wavelength_mode,
    source_run.operating_band,
    source_run.application_version,
    'complete',
    'engineering',
    'pending',
    source_run.part_number_snapshot,
    source_run.front_panel_channel_count,
    source_run.measurement_hardware_json,
    source_run.limit_snapshot_json,
    N'Sample retest fixture: channels 20-22 use current replacement ports 51, 50, and 49 and pass; channel 23 remains on port 23 and fails.',
    source_run.station_number
FROM dbo.IL_RUNS AS source_run
WHERE source_run.run_id = @SourceRunId;

SET @RetestRunId = CONVERT(BIGINT, SCOPE_IDENTITY());

DECLARE @Retests TABLE (
    logical_channel INT NOT NULL,
    physical_port INT NOT NULL,
    wavelength_1_il_db DECIMAL(9,4) NOT NULL,
    wavelength_2_il_db DECIMAL(9,4) NOT NULL
);

INSERT INTO @Retests (
    logical_channel,
    physical_port,
    wavelength_1_il_db,
    wavelength_2_il_db
)
VALUES
    (20, 51, 1.6200, 1.5800),
    (21, 50, 1.7400, 1.6900),
    (22, 49, 1.9100, 1.8600),
    (23, 23, 2.7500, 2.6800);

INSERT INTO dbo.IL_MEASUREMENTS (
    measurement_uuid,
    run_id,
    logical_channel,
    physical_port,
    attempt_number,
    wavelength_1_nm,
    wavelength_1_il_db,
    wavelength_2_nm,
    wavelength_2_il_db,
    reference_snapshot_json,
    written_at_utc,
    written_by
)
SELECT
    NEWID(),
    @RetestRunId,
    retest.logical_channel,
    retest.physical_port,
    1,
    source_measurement.wavelength_1_nm,
    retest.wavelength_1_il_db,
    source_measurement.wavelength_2_nm,
    retest.wavelength_2_il_db,
    source_measurement.reference_snapshot_json,
    DATEADD(SECOND, retest.logical_channel, retest_run.run_started_at_utc),
    retest_run.tested_by
FROM @Retests AS retest
INNER JOIN dbo.IL_MEASUREMENTS AS source_measurement
    ON source_measurement.run_id = @SourceRunId
    AND source_measurement.logical_channel = retest.logical_channel
    AND source_measurement.attempt_number = 1
INNER JOIN dbo.IL_RUNS AS retest_run
    ON retest_run.run_id = @RetestRunId;

IF (SELECT COUNT(*) FROM dbo.IL_MEASUREMENTS WHERE run_id = @RetestRunId) <> 4
    THROW 51003, N'The retest fixture did not create exactly four measurements.', 1;

INSERT INTO dbo.CHANNEL_REPLACEMENTS (
    assignment_id,
    logical_channel,
    previous_physical_port,
    replacement_physical_port,
    reason,
    replaced_by,
    replaced_at_utc,
    related_run_id,
    notes,
    source_recommendation_id
)
SELECT
    @AssignmentId,
    retest.logical_channel,
    retest.logical_channel,
    retest.physical_port,
    N'Unknown cause of high loss',
    retest_run.tested_by,
    DATEADD(SECOND, retest.logical_channel, retest_run.run_started_at_utc),
    @RetestRunId,
    N'Sample replacement record created for the S-00004 retest fixture.',
    NULL
FROM @Retests AS retest
INNER JOIN dbo.IL_RUNS AS retest_run
    ON retest_run.run_id = @RetestRunId
WHERE retest.logical_channel IN (20, 21, 22);

COMMIT TRANSACTION;

SELECT
    retest_run.run_id AS retest_run_id,
    unit.main_board_serial,
    retest_run.run_number,
    retest_run.completion_status,
    retest_run.run_purpose,
    retest_run.station_number,
    (
        SELECT COUNT(*)
        FROM dbo.IL_MEASUREMENTS AS measurement
        WHERE measurement.run_id = retest_run.run_id
    ) AS retest_measurement_count,
    (
        SELECT COUNT(*)
        FROM dbo.CHANNEL_REPLACEMENTS AS replacement
        WHERE replacement.related_run_id = retest_run.run_id
    ) AS replacement_record_count
FROM dbo.IL_RUNS AS retest_run
INNER JOIN dbo.UNIT_SWITCH_ASSIGNMENTS AS assignment
    ON assignment.assignment_id = retest_run.assignment_id
INNER JOIN dbo.UNITS AS unit
    ON unit.unit_id = assignment.unit_id
WHERE retest_run.run_id = @RetestRunId
;

SELECT
    measurement.logical_channel,
    measurement.physical_port,
    measurement.wavelength_1_il_db,
    measurement.wavelength_2_il_db,
    CASE
        WHEN measurement.logical_channel = 23 THEN N'Fail'
        ELSE N'Pass'
    END AS expected_result
FROM dbo.IL_MEASUREMENTS AS measurement
WHERE measurement.run_id = @RetestRunId
ORDER BY measurement.logical_channel;
