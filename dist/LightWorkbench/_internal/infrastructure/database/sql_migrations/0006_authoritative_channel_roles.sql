SET XACT_ABORT ON;

ALTER TABLE dbo.SWITCHES
    DROP CONSTRAINT CK_SWITCHES_physical_channel_count;

EXEC sp_rename
    N'dbo.SWITCHES.physical_channel_count',
    N'last_reported_scpi_channel_count',
    N'COLUMN';

GO

ALTER TABLE dbo.SWITCHES ADD CONSTRAINT
    CK_SWITCHES_last_reported_scpi_channel_count
    CHECK (last_reported_scpi_channel_count > 0);

ALTER TABLE dbo.IL_MEASUREMENTS
    DROP CONSTRAINT UQ_IL_MEASUREMENTS_attempt;

ALTER TABLE dbo.IL_MEASUREMENTS
    DROP CONSTRAINT CK_IL_MEASUREMENTS_logical_channel;

ALTER TABLE dbo.IL_MEASUREMENTS ADD
    measurement_role VARCHAR(20) NOT NULL
        CONSTRAINT DF_IL_MEASUREMENTS_measurement_role
        DEFAULT 'logical_channel';

GO

UPDATE dbo.IL_MEASUREMENTS
SET physical_port = logical_channel
WHERE physical_port IS NULL;

ALTER TABLE dbo.IL_MEASUREMENTS
    ALTER COLUMN physical_port INT NOT NULL;

ALTER TABLE dbo.IL_MEASUREMENTS
    ALTER COLUMN logical_channel INT NULL;

UPDATE measurement
SET
    measurement_role = 'extra_candidate',
    logical_channel = NULL
FROM dbo.IL_MEASUREMENTS AS measurement
INNER JOIN dbo.IL_RUNS AS run
    ON run.run_id = measurement.run_id
WHERE
    run.front_panel_channel_count IS NOT NULL
    AND measurement.physical_port > run.front_panel_channel_count
    AND measurement.logical_channel > run.front_panel_channel_count;

ALTER TABLE dbo.IL_MEASUREMENTS ADD CONSTRAINT
    CK_IL_MEASUREMENTS_measurement_identity CHECK (
        (
            measurement_role = 'logical_channel'
            AND logical_channel IS NOT NULL
            AND logical_channel > 0
        )
        OR (
            measurement_role = 'extra_candidate'
            AND logical_channel IS NULL
        )
    );

ALTER TABLE dbo.IL_MEASUREMENTS ADD CONSTRAINT
    CK_IL_MEASUREMENTS_measurement_role CHECK (
        measurement_role IN ('logical_channel', 'extra_candidate')
    );

ALTER TABLE dbo.IL_MEASUREMENTS
    DROP CONSTRAINT CK_IL_MEASUREMENTS_physical_port;

ALTER TABLE dbo.IL_MEASUREMENTS ADD CONSTRAINT
    CK_IL_MEASUREMENTS_physical_port CHECK (physical_port > 0);

CREATE UNIQUE INDEX UX_IL_MEASUREMENTS_logical_attempt
    ON dbo.IL_MEASUREMENTS(run_id, logical_channel, attempt_number)
    WHERE measurement_role = 'logical_channel';

CREATE UNIQUE INDEX UX_IL_MEASUREMENTS_extra_attempt
    ON dbo.IL_MEASUREMENTS(run_id, physical_port, attempt_number)
    WHERE measurement_role = 'extra_candidate';

CREATE INDEX IX_IL_MEASUREMENTS_run_role_port
    ON dbo.IL_MEASUREMENTS(
        run_id,
        measurement_role,
        physical_port,
        attempt_number DESC,
        measurement_id DESC
    );

ALTER TABLE dbo.REPLACEMENT_ANALYSIS_RECOMMENDATIONS ADD
    current_measurement_id BIGINT NULL,
    candidate_measurement_id BIGINT NULL;

GO

ALTER TABLE dbo.REPLACEMENT_ANALYSIS_RECOMMENDATIONS ADD CONSTRAINT
    FK_REPLACEMENT_ANALYSIS_RECOMMENDATIONS_current_measurement
    FOREIGN KEY (current_measurement_id)
    REFERENCES dbo.IL_MEASUREMENTS(measurement_id);

ALTER TABLE dbo.REPLACEMENT_ANALYSIS_RECOMMENDATIONS ADD CONSTRAINT
    FK_REPLACEMENT_ANALYSIS_RECOMMENDATIONS_candidate_measurement
    FOREIGN KEY (candidate_measurement_id)
    REFERENCES dbo.IL_MEASUREMENTS(measurement_id);

GO

CREATE OR ALTER VIEW dbo.vw_CurrentILMeasurements
AS
    WITH RankedMeasurements AS (
        SELECT
            measurement_id,
            measurement_uuid,
            run_id,
            logical_channel,
            physical_port,
            measurement_role,
            attempt_number,
            wavelength_1_nm,
            wavelength_1_il_db,
            wavelength_2_nm,
            wavelength_2_il_db,
            reference_snapshot_json,
            written_at_utc,
            written_by,
            ROW_NUMBER() OVER (
                PARTITION BY
                    run_id,
                    measurement_role,
                    CASE
                        WHEN measurement_role = 'logical_channel'
                            THEN logical_channel
                        ELSE physical_port
                    END
                ORDER BY attempt_number DESC, measurement_id DESC
            ) AS current_rank
        FROM dbo.IL_MEASUREMENTS
    )
    SELECT
        measurement_id,
        measurement_uuid,
        run_id,
        logical_channel,
        physical_port,
        measurement_role,
        attempt_number,
        wavelength_1_nm,
        wavelength_1_il_db,
        wavelength_2_nm,
        wavelength_2_il_db,
        reference_snapshot_json,
        written_at_utc,
        written_by
    FROM RankedMeasurements
    WHERE current_rank = 1;
GO

CREATE VIEW dbo.vw_ConfirmedExtraPorts
AS
    WITH RankedExtras AS (
        SELECT
            run.assignment_id,
            measurement.run_id,
            measurement.measurement_id,
            measurement.measurement_uuid,
            measurement.physical_port,
            measurement.attempt_number,
            measurement.wavelength_1_nm,
            measurement.wavelength_1_il_db,
            measurement.wavelength_2_nm,
            measurement.wavelength_2_il_db,
            measurement.reference_snapshot_json,
            measurement.written_at_utc,
            measurement.written_by,
            run.analysis_status,
            run.front_panel_channel_count,
            ROW_NUMBER() OVER (
                PARTITION BY run.assignment_id, measurement.physical_port
                ORDER BY
                    measurement.written_at_utc DESC,
                    measurement.attempt_number DESC,
                    measurement.measurement_id DESC
            ) AS current_rank
        FROM dbo.IL_MEASUREMENTS AS measurement
        INNER JOIN dbo.IL_RUNS AS run
            ON run.run_id = measurement.run_id
        WHERE
            measurement.measurement_role = 'extra_candidate'
            AND run.analysis_status NOT IN ('excluded', 'superseded')
            AND run.front_panel_channel_count IS NOT NULL
            AND measurement.physical_port > run.front_panel_channel_count
    )
    SELECT
        assignment_id,
        run_id,
        measurement_id,
        measurement_uuid,
        physical_port,
        attempt_number,
        wavelength_1_nm,
        wavelength_1_il_db,
        wavelength_2_nm,
        wavelength_2_il_db,
        reference_snapshot_json,
        written_at_utc,
        written_by,
        analysis_status,
        front_panel_channel_count
    FROM RankedExtras
    WHERE current_rank = 1;
GO

GRANT SELECT ON dbo.vw_CurrentILMeasurements TO lwb_app_writer;
GRANT SELECT ON dbo.vw_ConfirmedExtraPorts TO lwb_app_writer;
GRANT SELECT ON dbo.vw_ConfirmedExtraPorts TO lwb_report_reader;

