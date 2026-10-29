SET XACT_ABORT ON;

CREATE TABLE dbo.REPLACEMENT_ANALYSES (
    analysis_id BIGINT IDENTITY(1,1) NOT NULL,
    analysis_uuid UNIQUEIDENTIFIER NOT NULL,
    run_id BIGINT NOT NULL,
    analyzed_at_utc DATETIME2(3) NOT NULL,
    analyzed_by NVARCHAR(100) NOT NULL,
    application_version VARCHAR(30) NOT NULL,
    source_measurement_high_watermark_id BIGINT NOT NULL,
    front_panel_channel_count INT NOT NULL,
    wavelengths_json NVARCHAR(MAX) NOT NULL,
    criteria_json NVARCHAR(MAX) NOT NULL,
    result_status VARCHAR(40) NOT NULL,
    result_details_json NVARCHAR(MAX) NOT NULL,
    CONSTRAINT PK_REPLACEMENT_ANALYSES PRIMARY KEY (analysis_id),
    CONSTRAINT UQ_REPLACEMENT_ANALYSES_uuid UNIQUE (analysis_uuid),
    CONSTRAINT FK_REPLACEMENT_ANALYSES_run
        FOREIGN KEY (run_id) REFERENCES dbo.IL_RUNS(run_id),
    CONSTRAINT FK_REPLACEMENT_ANALYSES_measurement
        FOREIGN KEY (source_measurement_high_watermark_id)
        REFERENCES dbo.IL_MEASUREMENTS(measurement_id),
    CONSTRAINT CK_REPLACEMENT_ANALYSES_front_panel_count
        CHECK (front_panel_channel_count > 0),
    CONSTRAINT CK_REPLACEMENT_ANALYSES_wavelengths_json
        CHECK (ISJSON(wavelengths_json) = 1),
    CONSTRAINT CK_REPLACEMENT_ANALYSES_criteria_json
        CHECK (ISJSON(criteria_json) = 1),
    CONSTRAINT CK_REPLACEMENT_ANALYSES_result_details_json
        CHECK (ISJSON(result_details_json) = 1),
    CONSTRAINT CK_REPLACEMENT_ANALYSES_result_status
        CHECK (result_status IN (
            'recommendations_available',
            'no_viable_recommendations',
            'not_applicable_no_extra_ports',
            'incomplete_input'
        ))
);

CREATE TABLE dbo.REPLACEMENT_ANALYSIS_RECOMMENDATIONS (
    recommendation_id BIGINT IDENTITY(1,1) NOT NULL,
    analysis_id BIGINT NOT NULL,
    recommendation_rank INT NOT NULL,
    category VARCHAR(20) NOT NULL,
    logical_channel INT NOT NULL,
    current_physical_port INT NOT NULL,
    candidate_physical_port INT NOT NULL,
    current_wavelength_1_il_db DECIMAL(9,4) NOT NULL,
    current_wavelength_2_il_db DECIMAL(9,4) NOT NULL,
    candidate_wavelength_1_il_db DECIMAL(9,4) NOT NULL,
    candidate_wavelength_2_il_db DECIMAL(9,4) NOT NULL,
    current_worst_loss_db DECIMAL(9,4) NOT NULL,
    candidate_worst_loss_db DECIMAL(9,4) NOT NULL,
    improvement_db DECIMAL(9,4) NOT NULL,
    CONSTRAINT PK_REPLACEMENT_ANALYSIS_RECOMMENDATIONS
        PRIMARY KEY (recommendation_id),
    CONSTRAINT FK_REPLACEMENT_ANALYSIS_RECOMMENDATIONS_analysis
        FOREIGN KEY (analysis_id)
        REFERENCES dbo.REPLACEMENT_ANALYSES(analysis_id),
    CONSTRAINT CK_REPLACEMENT_ANALYSIS_RECOMMENDATIONS_rank
        CHECK (recommendation_rank > 0),
    CONSTRAINT CK_REPLACEMENT_ANALYSIS_RECOMMENDATIONS_category
        CHECK (category IN ('required', 'optional')),
    CONSTRAINT CK_REPLACEMENT_ANALYSIS_RECOMMENDATIONS_channels
        CHECK (
            logical_channel > 0
            AND current_physical_port > 0
            AND candidate_physical_port > 0
            AND current_physical_port <> candidate_physical_port
        ),
    CONSTRAINT CK_REPLACEMENT_ANALYSIS_RECOMMENDATIONS_losses
        CHECK (
            current_wavelength_1_il_db >= 0
            AND current_wavelength_2_il_db >= 0
            AND candidate_wavelength_1_il_db >= 0
            AND candidate_wavelength_2_il_db >= 0
            AND current_worst_loss_db >= 0
            AND candidate_worst_loss_db >= 0
            AND improvement_db >= 0
        ),
    CONSTRAINT UQ_REPLACEMENT_ANALYSIS_RECOMMENDATIONS_rank
        UNIQUE (analysis_id, recommendation_rank),
    CONSTRAINT UQ_REPLACEMENT_ANALYSIS_RECOMMENDATIONS_channel
        UNIQUE (analysis_id, logical_channel),
    CONSTRAINT UQ_REPLACEMENT_ANALYSIS_RECOMMENDATIONS_candidate
        UNIQUE (analysis_id, candidate_physical_port)
);

ALTER TABLE dbo.CHANNEL_REPLACEMENTS ADD source_recommendation_id BIGINT NULL;

GO

ALTER TABLE dbo.CHANNEL_REPLACEMENTS ADD CONSTRAINT
    FK_CHANNEL_REPLACEMENTS_source_recommendation
    FOREIGN KEY (source_recommendation_id)
    REFERENCES dbo.REPLACEMENT_ANALYSIS_RECOMMENDATIONS(recommendation_id);

CREATE UNIQUE INDEX UX_CHANNEL_REPLACEMENTS_source_recommendation
    ON dbo.CHANNEL_REPLACEMENTS(source_recommendation_id)
    WHERE source_recommendation_id IS NOT NULL;

CREATE INDEX IX_REPLACEMENT_ANALYSES_run_time
    ON dbo.REPLACEMENT_ANALYSES(run_id, analyzed_at_utc DESC, analysis_id DESC);

CREATE INDEX IX_REPLACEMENT_ANALYSIS_RECOMMENDATIONS_analysis
    ON dbo.REPLACEMENT_ANALYSIS_RECOMMENDATIONS(analysis_id, recommendation_rank);

GO

CREATE VIEW dbo.vw_ReplacementRecommendationUsage
AS
    SELECT
        analysis.analysis_id,
        analysis.analysis_uuid,
        analysis.run_id,
        analysis.analyzed_at_utc,
        analysis.analyzed_by,
        analysis.application_version,
        analysis.result_status,
        recommendation.recommendation_id,
        recommendation.recommendation_rank,
        recommendation.category,
        recommendation.logical_channel,
        recommendation.current_physical_port,
        recommendation.candidate_physical_port,
        recommendation.improvement_db,
        replacement.replacement_id,
        replacement.replaced_by,
        replacement.replaced_at_utc,
        CASE WHEN replacement.replacement_id IS NULL
             THEN CAST(0 AS BIT) ELSE CAST(1 AS BIT) END AS recommendation_used
    FROM dbo.REPLACEMENT_ANALYSIS_RECOMMENDATIONS AS recommendation
    INNER JOIN dbo.REPLACEMENT_ANALYSES AS analysis
        ON analysis.analysis_id = recommendation.analysis_id
    LEFT JOIN dbo.CHANNEL_REPLACEMENTS AS replacement
        ON replacement.source_recommendation_id = recommendation.recommendation_id;
GO

GRANT SELECT, INSERT ON dbo.REPLACEMENT_ANALYSES TO lwb_app_writer;
GRANT SELECT, INSERT ON dbo.REPLACEMENT_ANALYSIS_RECOMMENDATIONS TO lwb_app_writer;
GRANT SELECT, INSERT ON dbo.CHANNEL_REPLACEMENTS TO lwb_app_writer;
GRANT SELECT ON dbo.vw_ReplacementRecommendationUsage TO lwb_app_writer;
GRANT SELECT ON dbo.vw_ReplacementRecommendationUsage TO lwb_report_reader;
