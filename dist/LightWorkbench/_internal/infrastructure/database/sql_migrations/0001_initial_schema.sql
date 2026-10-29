SET XACT_ABORT ON;

CREATE TABLE dbo.SCHEMA_MIGRATIONS (
    migration_id INT NOT NULL,
    migration_name NVARCHAR(200) NOT NULL,
    script_checksum CHAR(64) NOT NULL,
    applied_at_utc DATETIME2(3) NOT NULL
        CONSTRAINT DF_SCHEMA_MIGRATIONS_applied_at_utc DEFAULT SYSUTCDATETIME(),
    application_version NVARCHAR(30) NOT NULL,
    CONSTRAINT PK_SCHEMA_MIGRATIONS PRIMARY KEY (migration_id),
    CONSTRAINT CK_SCHEMA_MIGRATIONS_positive_id CHECK (migration_id > 0),
    CONSTRAINT CK_SCHEMA_MIGRATIONS_checksum_length
        CHECK (LEN(script_checksum) = 64)
);

CREATE TABLE dbo.UNITS (
    unit_id BIGINT IDENTITY(1,1) NOT NULL,
    main_board_serial NVARCHAR(100) NOT NULL,
    part_number NVARCHAR(100) NULL,
    front_panel_channel_count INT NULL,
    unit_model NVARCHAR(50) NULL,
    notes NVARCHAR(MAX) NULL,
    created_at_utc DATETIME2(3) NOT NULL
        CONSTRAINT DF_UNITS_created_at_utc DEFAULT SYSUTCDATETIME(),
    updated_at_utc DATETIME2(3) NOT NULL
        CONSTRAINT DF_UNITS_updated_at_utc DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_UNITS PRIMARY KEY (unit_id),
    CONSTRAINT UQ_UNITS_main_board_serial UNIQUE (main_board_serial),
    CONSTRAINT CK_UNITS_front_panel_channel_count
        CHECK (front_panel_channel_count IS NULL OR front_panel_channel_count > 0)
);

CREATE TABLE dbo.SWITCHES (
    switch_id BIGINT IDENTITY(1,1) NOT NULL,
    switch_serial NVARCHAR(100) NOT NULL,
    switch_model NVARCHAR(30) NOT NULL,
    firmware_version NVARCHAR(50) NULL,
    physical_channel_count INT NOT NULL,
    notes NVARCHAR(MAX) NULL,
    created_at_utc DATETIME2(3) NOT NULL
        CONSTRAINT DF_SWITCHES_created_at_utc DEFAULT SYSUTCDATETIME(),
    updated_at_utc DATETIME2(3) NOT NULL
        CONSTRAINT DF_SWITCHES_updated_at_utc DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_SWITCHES PRIMARY KEY (switch_id),
    CONSTRAINT UQ_SWITCHES_switch_serial UNIQUE (switch_serial),
    CONSTRAINT CK_SWITCHES_physical_channel_count
        CHECK (physical_channel_count > 0)
);

CREATE TABLE dbo.UNIT_SWITCH_ASSIGNMENTS (
    assignment_id BIGINT IDENTITY(1,1) NOT NULL,
    unit_id BIGINT NOT NULL,
    switch_id BIGINT NOT NULL,
    installed_at_utc DATETIME2(3) NOT NULL,
    removed_at_utc DATETIME2(3) NULL,
    installed_by NVARCHAR(100) NOT NULL,
    removed_by NVARCHAR(100) NULL,
    removal_reason NVARCHAR(500) NULL,
    initial_channel_map_json NVARCHAR(MAX) NOT NULL,
    notes NVARCHAR(MAX) NULL,
    created_at_utc DATETIME2(3) NOT NULL
        CONSTRAINT DF_UNIT_SWITCH_ASSIGNMENTS_created_at_utc
        DEFAULT SYSUTCDATETIME(),
    updated_at_utc DATETIME2(3) NOT NULL
        CONSTRAINT DF_UNIT_SWITCH_ASSIGNMENTS_updated_at_utc
        DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_UNIT_SWITCH_ASSIGNMENTS PRIMARY KEY (assignment_id),
    CONSTRAINT FK_UNIT_SWITCH_ASSIGNMENTS_unit
        FOREIGN KEY (unit_id) REFERENCES dbo.UNITS(unit_id),
    CONSTRAINT FK_UNIT_SWITCH_ASSIGNMENTS_switch
        FOREIGN KEY (switch_id) REFERENCES dbo.SWITCHES(switch_id),
    CONSTRAINT CK_UNIT_SWITCH_ASSIGNMENTS_dates
        CHECK (removed_at_utc IS NULL OR removed_at_utc >= installed_at_utc),
    CONSTRAINT CK_UNIT_SWITCH_ASSIGNMENTS_initial_map_json
        CHECK (ISJSON(initial_channel_map_json) = 1)
);

CREATE TABLE dbo.IL_RUNS (
    run_id BIGINT IDENTITY(1,1) NOT NULL,
    assignment_id BIGINT NOT NULL,
    run_number INT NOT NULL,
    client_run_uuid UNIQUEIDENTIFIER NOT NULL,
    run_started_at_utc DATETIME2(3) NOT NULL,
    run_ended_at_utc DATETIME2(3) NULL,
    tested_by NVARCHAR(100) NOT NULL,
    wavelength_mode VARCHAR(2) NOT NULL,
    operating_band VARCHAR(20) NOT NULL,
    application_version NVARCHAR(30) NOT NULL,
    completion_status VARCHAR(20) NOT NULL
        CONSTRAINT DF_IL_RUNS_completion_status DEFAULT 'in_progress',
    run_purpose VARCHAR(30) NOT NULL
        CONSTRAINT DF_IL_RUNS_run_purpose DEFAULT 'production',
    analysis_status VARCHAR(20) NOT NULL
        CONSTRAINT DF_IL_RUNS_analysis_status DEFAULT 'pending',
    analysis_exclusion_reason NVARCHAR(1000) NULL,
    superseded_by_run_id BIGINT NULL,
    part_number_snapshot NVARCHAR(100) NULL,
    front_panel_channel_count INT NULL,
    measurement_hardware_json NVARCHAR(MAX) NOT NULL,
    limit_snapshot_json NVARCHAR(MAX) NOT NULL,
    notes NVARCHAR(MAX) NULL,
    created_at_utc DATETIME2(3) NOT NULL
        CONSTRAINT DF_IL_RUNS_created_at_utc DEFAULT SYSUTCDATETIME(),
    updated_at_utc DATETIME2(3) NOT NULL
        CONSTRAINT DF_IL_RUNS_updated_at_utc DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_IL_RUNS PRIMARY KEY (run_id),
    CONSTRAINT UQ_IL_RUNS_client_run_uuid UNIQUE (client_run_uuid),
    CONSTRAINT FK_IL_RUNS_assignment
        FOREIGN KEY (assignment_id)
        REFERENCES dbo.UNIT_SWITCH_ASSIGNMENTS(assignment_id),
    CONSTRAINT FK_IL_RUNS_superseded_by
        FOREIGN KEY (superseded_by_run_id) REFERENCES dbo.IL_RUNS(run_id),
    CONSTRAINT CK_IL_RUNS_positive_run_number CHECK (run_number > 0),
    CONSTRAINT CK_IL_RUNS_dates
        CHECK (run_ended_at_utc IS NULL OR run_ended_at_utc >= run_started_at_utc),
    CONSTRAINT CK_IL_RUNS_wavelength_mode
        CHECK (wavelength_mode IN ('SM', 'MM')),
    CONSTRAINT CK_IL_RUNS_completion_status
        CHECK (completion_status IN ('in_progress', 'complete', 'stopped', 'failed')),
    CONSTRAINT CK_IL_RUNS_run_purpose
        CHECK (run_purpose IN ('production', 'engineering', 'training', 'calibration')),
    CONSTRAINT CK_IL_RUNS_analysis_status
        CHECK (analysis_status IN ('pending', 'included', 'excluded', 'superseded')),
    CONSTRAINT CK_IL_RUNS_exclusion_reason
        CHECK (
            analysis_status <> 'excluded'
            OR NULLIF(LTRIM(RTRIM(analysis_exclusion_reason)), N'') IS NOT NULL
        ),
    CONSTRAINT CK_IL_RUNS_not_self_superseded
        CHECK (superseded_by_run_id IS NULL OR superseded_by_run_id <> run_id),
    CONSTRAINT CK_IL_RUNS_front_panel_channel_count
        CHECK (front_panel_channel_count IS NULL OR front_panel_channel_count > 0),
    CONSTRAINT CK_IL_RUNS_measurement_hardware_json
        CHECK (ISJSON(measurement_hardware_json) = 1),
    CONSTRAINT CK_IL_RUNS_limit_snapshot_json
        CHECK (ISJSON(limit_snapshot_json) = 1)
);

CREATE TABLE dbo.IL_MEASUREMENTS (
    measurement_id BIGINT IDENTITY(1,1) NOT NULL,
    measurement_uuid UNIQUEIDENTIFIER NOT NULL,
    run_id BIGINT NOT NULL,
    logical_channel INT NOT NULL,
    physical_port INT NULL,
    attempt_number INT NOT NULL,
    wavelength_1_nm SMALLINT NOT NULL,
    wavelength_1_il_db DECIMAL(9,4) NOT NULL,
    wavelength_2_nm SMALLINT NOT NULL,
    wavelength_2_il_db DECIMAL(9,4) NOT NULL,
    reference_snapshot_json NVARCHAR(MAX) NOT NULL,
    written_at_utc DATETIME2(3) NOT NULL,
    written_by NVARCHAR(100) NOT NULL,
    CONSTRAINT PK_IL_MEASUREMENTS PRIMARY KEY (measurement_id),
    CONSTRAINT UQ_IL_MEASUREMENTS_measurement_uuid UNIQUE (measurement_uuid),
    CONSTRAINT UQ_IL_MEASUREMENTS_attempt
        UNIQUE (run_id, logical_channel, attempt_number),
    CONSTRAINT FK_IL_MEASUREMENTS_run
        FOREIGN KEY (run_id) REFERENCES dbo.IL_RUNS(run_id),
    CONSTRAINT CK_IL_MEASUREMENTS_logical_channel CHECK (logical_channel > 0),
    CONSTRAINT CK_IL_MEASUREMENTS_physical_port
        CHECK (physical_port IS NULL OR physical_port > 0),
    CONSTRAINT CK_IL_MEASUREMENTS_attempt_number CHECK (attempt_number > 0),
    CONSTRAINT CK_IL_MEASUREMENTS_wavelengths
        CHECK (
            wavelength_1_nm > 0
            AND wavelength_2_nm > 0
            AND wavelength_1_nm <> wavelength_2_nm
        ),
    CONSTRAINT CK_IL_MEASUREMENTS_reference_snapshot_json
        CHECK (ISJSON(reference_snapshot_json) = 1)
);

CREATE TABLE dbo.CHANNEL_REPLACEMENTS (
    replacement_id BIGINT IDENTITY(1,1) NOT NULL,
    assignment_id BIGINT NOT NULL,
    logical_channel INT NOT NULL,
    previous_physical_port INT NOT NULL,
    replacement_physical_port INT NOT NULL,
    reason NVARCHAR(500) NOT NULL,
    replaced_by NVARCHAR(100) NOT NULL,
    replaced_at_utc DATETIME2(3) NOT NULL,
    related_run_id BIGINT NULL,
    notes NVARCHAR(MAX) NULL,
    CONSTRAINT PK_CHANNEL_REPLACEMENTS PRIMARY KEY (replacement_id),
    CONSTRAINT FK_CHANNEL_REPLACEMENTS_assignment
        FOREIGN KEY (assignment_id)
        REFERENCES dbo.UNIT_SWITCH_ASSIGNMENTS(assignment_id),
    CONSTRAINT FK_CHANNEL_REPLACEMENTS_run
        FOREIGN KEY (related_run_id) REFERENCES dbo.IL_RUNS(run_id),
    CONSTRAINT CK_CHANNEL_REPLACEMENTS_logical_channel
        CHECK (logical_channel > 0),
    CONSTRAINT CK_CHANNEL_REPLACEMENTS_ports
        CHECK (
            previous_physical_port > 0
            AND replacement_physical_port > 0
            AND previous_physical_port <> replacement_physical_port
        )
);

CREATE TABLE dbo.DESIGNATED_SPARES (
    spare_event_id BIGINT IDENTITY(1,1) NOT NULL,
    assignment_id BIGINT NOT NULL,
    physical_port INT NOT NULL,
    action VARCHAR(20) NOT NULL,
    recorded_by NVARCHAR(100) NOT NULL,
    recorded_at_utc DATETIME2(3) NOT NULL,
    notes NVARCHAR(MAX) NULL,
    CONSTRAINT PK_DESIGNATED_SPARES PRIMARY KEY (spare_event_id),
    CONSTRAINT FK_DESIGNATED_SPARES_assignment
        FOREIGN KEY (assignment_id)
        REFERENCES dbo.UNIT_SWITCH_ASSIGNMENTS(assignment_id),
    CONSTRAINT CK_DESIGNATED_SPARES_physical_port CHECK (physical_port > 0),
    CONSTRAINT CK_DESIGNATED_SPARES_action
        CHECK (action IN ('designated', 'undesignated'))
);

CREATE UNIQUE INDEX UX_UNIT_SWITCH_ASSIGNMENTS_active_unit
    ON dbo.UNIT_SWITCH_ASSIGNMENTS(unit_id)
    WHERE removed_at_utc IS NULL;

CREATE UNIQUE INDEX UX_UNIT_SWITCH_ASSIGNMENTS_active_switch
    ON dbo.UNIT_SWITCH_ASSIGNMENTS(switch_id)
    WHERE removed_at_utc IS NULL;

CREATE INDEX IX_UNIT_SWITCH_ASSIGNMENTS_unit_history
    ON dbo.UNIT_SWITCH_ASSIGNMENTS(unit_id, installed_at_utc DESC);

CREATE INDEX IX_UNIT_SWITCH_ASSIGNMENTS_switch_history
    ON dbo.UNIT_SWITCH_ASSIGNMENTS(switch_id, installed_at_utc DESC);

CREATE INDEX IX_IL_RUNS_assignment_date
    ON dbo.IL_RUNS(assignment_id, run_started_at_utc DESC);

CREATE INDEX IX_IL_RUNS_status_purpose_analysis
    ON dbo.IL_RUNS(completion_status, run_purpose, analysis_status);

CREATE INDEX IX_IL_MEASUREMENTS_run_channel
    ON dbo.IL_MEASUREMENTS(run_id, logical_channel, attempt_number DESC);

CREATE INDEX IX_CHANNEL_REPLACEMENTS_assignment_channel_time
    ON dbo.CHANNEL_REPLACEMENTS(
        assignment_id,
        logical_channel,
        replaced_at_utc DESC,
        replacement_id DESC
    );

CREATE INDEX IX_DESIGNATED_SPARES_assignment_port_time
    ON dbo.DESIGNATED_SPARES(
        assignment_id,
        physical_port,
        recorded_at_utc DESC,
        spare_event_id DESC
    );
GO

CREATE VIEW dbo.vw_CurrentILMeasurements
AS
    WITH RankedMeasurements AS (
        SELECT
            measurement_id,
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
            written_by,
            ROW_NUMBER() OVER (
                PARTITION BY run_id, logical_channel
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

CREATE VIEW dbo.vw_CurrentChannelMap
AS
    WITH InitialMap AS (
        SELECT
            assignment.assignment_id,
            assignment.unit_id,
            assignment.switch_id,
            TRY_CONVERT(INT, channel_entry.[key]) AS logical_channel,
            TRY_CONVERT(INT, channel_entry.[value]) AS initial_physical_port
        FROM dbo.UNIT_SWITCH_ASSIGNMENTS AS assignment
        CROSS APPLY OPENJSON(assignment.initial_channel_map_json) AS channel_entry
    ),
    RankedReplacements AS (
        SELECT
            replacement.replacement_id,
            replacement.assignment_id,
            replacement.logical_channel,
            replacement.replacement_physical_port,
            replacement.replaced_at_utc,
            ROW_NUMBER() OVER (
                PARTITION BY replacement.assignment_id, replacement.logical_channel
                ORDER BY
                    replacement.replaced_at_utc DESC,
                    replacement.replacement_id DESC
            ) AS current_rank
        FROM dbo.CHANNEL_REPLACEMENTS AS replacement
    )
    SELECT
        initial_map.assignment_id,
        initial_map.unit_id,
        initial_map.switch_id,
        initial_map.logical_channel,
        initial_map.initial_physical_port,
        COALESCE(
            replacement.replacement_physical_port,
            initial_map.initial_physical_port
        ) AS effective_physical_port,
        CONVERT(BIT, CASE WHEN replacement.replacement_id IS NULL THEN 0 ELSE 1 END)
            AS is_replaced,
        replacement.replacement_id AS latest_replacement_id,
        replacement.replaced_at_utc AS latest_replaced_at_utc
    FROM InitialMap AS initial_map
    LEFT JOIN RankedReplacements AS replacement
        ON replacement.assignment_id = initial_map.assignment_id
        AND replacement.logical_channel = initial_map.logical_channel
        AND replacement.current_rank = 1
    WHERE
        initial_map.logical_channel IS NOT NULL
        AND initial_map.initial_physical_port IS NOT NULL;
GO

IF DATABASE_PRINCIPAL_ID(N'lwb_app_writer') IS NULL
    CREATE ROLE lwb_app_writer;

IF DATABASE_PRINCIPAL_ID(N'lwb_report_reader') IS NULL
    CREATE ROLE lwb_report_reader;

GRANT SELECT ON dbo.SCHEMA_MIGRATIONS TO lwb_app_writer;
GRANT SELECT, INSERT, UPDATE ON dbo.UNITS TO lwb_app_writer;
GRANT SELECT, INSERT, UPDATE ON dbo.SWITCHES TO lwb_app_writer;
GRANT SELECT, INSERT, UPDATE ON dbo.UNIT_SWITCH_ASSIGNMENTS TO lwb_app_writer;
GRANT SELECT, INSERT, UPDATE ON dbo.IL_RUNS TO lwb_app_writer;
GRANT SELECT, INSERT ON dbo.IL_MEASUREMENTS TO lwb_app_writer;
GRANT SELECT, INSERT ON dbo.CHANNEL_REPLACEMENTS TO lwb_app_writer;
GRANT SELECT, INSERT ON dbo.DESIGNATED_SPARES TO lwb_app_writer;
GRANT SELECT ON dbo.vw_CurrentILMeasurements TO lwb_app_writer;
GRANT SELECT ON dbo.vw_CurrentChannelMap TO lwb_app_writer;

GRANT SELECT ON SCHEMA::dbo TO lwb_report_reader;
GO
