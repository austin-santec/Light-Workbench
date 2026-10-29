SET XACT_ABORT ON;

ALTER TABLE dbo.IL_RUNS ADD void_info_json NVARCHAR(MAX) NULL;
GO

UPDATE dbo.IL_RUNS
SET void_info_json = (
    SELECT
        CONVERT(VARCHAR(33), updated_at_utc, 127) + 'Z' AS voided_at_utc,
        COALESCE(NULLIF(LTRIM(RTRIM(tested_by)), N''), N'Unknown') AS voided_by,
        COALESCE(
            NULLIF(LTRIM(RTRIM(analysis_exclusion_reason)), N''),
            N'Migrated excluded run'
        ) AS reason
    FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
)
WHERE analysis_status = 'excluded';

ALTER TABLE dbo.IL_RUNS DROP CONSTRAINT CK_IL_RUNS_exclusion_reason;

ALTER TABLE dbo.IL_RUNS ADD CONSTRAINT CK_IL_RUNS_void_info_json
CHECK (
    (
        analysis_status = 'excluded'
        AND ISJSON(void_info_json) = 1
        AND NULLIF(LTRIM(RTRIM(JSON_VALUE(void_info_json, '$.voided_at_utc'))), N'') IS NOT NULL
        AND TRY_CONVERT(DATETIME2(3), JSON_VALUE(void_info_json, '$.voided_at_utc'), 127) IS NOT NULL
        AND NULLIF(LTRIM(RTRIM(JSON_VALUE(void_info_json, '$.voided_by'))), N'') IS NOT NULL
        AND NULLIF(LTRIM(RTRIM(JSON_VALUE(void_info_json, '$.reason'))), N'') IS NOT NULL
    )
    OR (analysis_status <> 'excluded' AND void_info_json IS NULL)
);

ALTER TABLE dbo.IL_RUNS DROP COLUMN analysis_exclusion_reason;

ALTER TABLE dbo.REPLACEMENT_ANALYSES
    DROP CONSTRAINT CK_REPLACEMENT_ANALYSES_result_status;

ALTER TABLE dbo.REPLACEMENT_ANALYSES ADD CONSTRAINT
    CK_REPLACEMENT_ANALYSES_result_status CHECK (result_status IN (
        'optimized',
        'recommendations_available',
        'verification_required',
        'pass_no_viable_optimization',
        'fail_no_viable_recovery',
        'incomplete_input',
        'review_required',
        'no_viable_recommendations',
        'not_applicable_no_extra_ports'
    ));

GRANT SELECT, INSERT, UPDATE ON dbo.IL_RUNS TO lwb_app_writer;

