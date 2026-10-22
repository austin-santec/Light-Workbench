SET XACT_ABORT ON;

ALTER TABLE dbo.IL_RUNS ADD station_number INT NULL;

GO

ALTER TABLE dbo.IL_RUNS ADD CONSTRAINT
    CK_IL_RUNS_station_number_positive CHECK (
        station_number IS NULL OR station_number > 0
    );
