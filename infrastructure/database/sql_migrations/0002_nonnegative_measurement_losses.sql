SET XACT_ABORT ON;

ALTER TABLE dbo.IL_MEASUREMENTS ADD CONSTRAINT
    CK_IL_MEASUREMENTS_nonnegative_losses CHECK (
        wavelength_1_il_db >= 0 AND wavelength_2_il_db >= 0
    );
