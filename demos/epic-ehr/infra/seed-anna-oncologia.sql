-- Seed synthetic patient Anna Ricci (TUS-2026-0417) into the VM's OncologiaDemo database.
-- Idempotent and schema-adaptive: unknown columns are copied from the synthetic template
-- patient SYN-2026-0001, so the script survives schema details not kept in this repository.
-- All values are invented. Run on the VM as the SQL administrator:
--   sqlcmd -S localhost -E -d OncologiaDemo -b -i seed-anna-oncologia.sql
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @mrn nvarchar(64) = N'TUS-2026-0417';
DECLARE @template nvarchar(64) = N'SYN-2026-0001';
DECLARE @patients int = OBJECT_ID(N'oncologia_demo.paziente');
DECLARE @labs int = OBJECT_ID(N'oncologia_demo.esame_laboratorio');
DECLARE @templateId bigint, @annaId bigint, @sql nvarchar(max), @cols nvarchar(max), @vals nvarchar(max);

IF @patients IS NULL OR @labs IS NULL
    THROW 50001, 'oncologia_demo.paziente or esame_laboratorio is missing.', 1;

SELECT @templateId = paziente_id FROM oncologia_demo.paziente WHERE mrn = @template;
IF @templateId IS NULL
    THROW 50002, 'Template patient SYN-2026-0001 is missing.', 1;

BEGIN TRANSACTION;

IF NOT EXISTS (SELECT 1 FROM oncologia_demo.paziente WHERE mrn = @mrn)
BEGIN
    DECLARE @nextPatient bigint = (SELECT ISNULL(MAX(paziente_id), 0) + 1 FROM oncologia_demo.paziente);
    SELECT
        @cols = STRING_AGG(CAST(QUOTENAME(c.name) AS nvarchar(max)), N', ') WITHIN GROUP (ORDER BY c.column_id),
        @vals = STRING_AGG(CAST(CASE c.name
            WHEN N'paziente_id' THEN N'@nextPatient'
            WHEN N'mrn' THEN N'@mrn'
            WHEN N'nome' THEN N'N''Anna'''
            WHEN N'cognome' THEN N'N''Ricci'''
            WHEN N'sesso' THEN N'N''F'''
            WHEN N'data_nascita' THEN N'''1971-03-14'''
            WHEN N'comune_residenza' THEN N'N''Utrecht (NL)'''
            ELSE N't.' + QUOTENAME(c.name) END AS nvarchar(max)), N', ') WITHIN GROUP (ORDER BY c.column_id)
    FROM sys.columns c
    WHERE c.object_id = @patients AND c.is_identity = 0 AND c.is_computed = 0
      AND TYPE_NAME(c.user_type_id) NOT IN (N'timestamp', N'rowversion');
    SET @sql = N'INSERT oncologia_demo.paziente (' + @cols + N') SELECT ' + @vals
        + N' FROM oncologia_demo.paziente t WHERE t.mrn = @template;';
    EXEC sp_executesql @sql, N'@mrn nvarchar(64), @template nvarchar(64), @nextPatient bigint',
        @mrn, @template, @nextPatient;
END;

SELECT @annaId = paziente_id FROM oncologia_demo.paziente WHERE mrn = @mrn;

IF NOT EXISTS (SELECT 1 FROM oncologia_demo.esame_laboratorio WHERE paziente_id = @annaId)
BEGIN
    CREATE TABLE #anna (n int NOT NULL, data_ora datetime2 NOT NULL, codice nvarchar(20) NOT NULL,
        nome_esame nvarchar(100) NOT NULL, valore decimal(10, 2) NOT NULL, unita nvarchar(20) NOT NULL,
        basso decimal(10, 2) NOT NULL, alto decimal(10, 2) NOT NULL, flag nvarchar(5) NULL);
    INSERT #anna VALUES
        (1, '2026-09-18T23:05:00', N'HB', N'Emoglobina', 8.1, N'g/dL', 12.0, 16.0, N'L'),
        (2, '2026-09-18T23:05:00', N'MCV', N'Volume corpuscolare medio', 71, N'fL', 80, 100, N'L'),
        (3, '2026-09-18T23:05:00', N'WBC', N'Leucociti', 7.2, N'10^3/uL', 4.0, 10.0, NULL),
        (4, '2026-09-18T23:05:00', N'PLT', N'Piastrine', 412, N'10^3/uL', 150, 400, N'H'),
        (5, '2026-09-18T23:05:00', N'CREA', N'Creatinina', 0.8, N'mg/dL', 0.5, 1.1, NULL),
        (6, '2026-09-18T23:05:00', N'PCR', N'Proteina C reattiva', 6.1, N'mg/L', 0, 5.0, N'H'),
        (7, '2026-09-19T07:30:00', N'FERR', N'Ferritina', 6, N'ng/mL', 15, 150, N'L'),
        (8, '2026-09-19T07:30:00', N'CEA', N'Antigene carcinoembrionario', 18.4, N'ng/mL', 0, 5.0, N'H'),
        (9, '2026-09-19T07:30:00', N'CA199', N'CA 19-9', 41, N'U/mL', 0, 37, N'H'),
        (10, '2026-09-21T07:15:00', N'HB', N'Emoglobina', 10.2, N'g/dL', 12.0, 16.0, N'L');

    -- A single-column, non-identity integer primary key gets MAX + n.
    DECLARE @pk sysname = (
        SELECT MIN(c.name) FROM sys.indexes i
        JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
        JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE i.object_id = @labs AND i.is_primary_key = 1 AND c.is_identity = 0
          AND c.name <> N'paziente_id' AND TYPE_NAME(c.user_type_id) IN (N'int', N'bigint')
        GROUP BY i.index_id HAVING COUNT(*) = 1);
    DECLARE @nextLab bigint = 0;
    IF @pk IS NOT NULL
    BEGIN
        SET @sql = N'SELECT @next = ISNULL(MAX(' + QUOTENAME(@pk) + N'), 0) FROM oncologia_demo.esame_laboratorio;';
        EXEC sp_executesql @sql, N'@next bigint OUTPUT', @nextLab OUTPUT;
    END;

    SELECT
        @cols = STRING_AGG(CAST(QUOTENAME(c.name) AS nvarchar(max)), N', ') WITHIN GROUP (ORDER BY c.column_id),
        @vals = STRING_AGG(CAST(CASE
            WHEN c.name = @pk THEN N'@nextLab + a.n'
            WHEN c.name = N'paziente_id' THEN N'@annaId'
            WHEN c.name = N'data_ora' THEN N'a.data_ora'
            WHEN c.name = N'codice' THEN N'a.codice'
            WHEN c.name = N'nome_esame' THEN N'a.nome_esame'
            WHEN c.name = N'valore_numerico' THEN N'a.valore'
            WHEN c.name = N'valore_testo' AND c.is_nullable = 1 THEN N'NULL'
            WHEN c.name = N'valore_testo' THEN N'CONVERT(nvarchar(20), a.valore)'
            WHEN c.name = N'unita' THEN N'a.unita'
            WHEN c.name = N'range_basso' THEN N'a.basso'
            WHEN c.name = N'range_alto' THEN N'a.alto'
            WHEN c.name = N'flag_anomalia' AND TYPE_NAME(c.user_type_id) = N'bit'
                THEN N'CASE WHEN a.flag IS NULL THEN 0 ELSE 1 END'
            WHEN c.name = N'flag_anomalia' AND c.is_nullable = 1 THEN N'a.flag'
            WHEN c.name = N'flag_anomalia' THEN N'ISNULL(a.flag, N'''')'
            ELSE N't.' + QUOTENAME(c.name) END AS nvarchar(max)), N', ') WITHIN GROUP (ORDER BY c.column_id)
    FROM sys.columns c
    WHERE c.object_id = @labs AND c.is_identity = 0 AND c.is_computed = 0
      AND TYPE_NAME(c.user_type_id) NOT IN (N'timestamp', N'rowversion');
    SET @sql = N'INSERT oncologia_demo.esame_laboratorio (' + @cols + N') SELECT ' + @vals
        + N' FROM #anna a CROSS JOIN (SELECT TOP (1) * FROM oncologia_demo.esame_laboratorio '
        + N'ORDER BY CASE WHEN paziente_id = @templateId THEN 0 ELSE 1 END) t;';
    EXEC sp_executesql @sql, N'@annaId bigint, @templateId bigint, @nextLab bigint',
        @annaId, @templateId, @nextLab;
    DROP TABLE #anna;
END;

COMMIT TRANSACTION;

SELECT p.mrn, p.nome, p.cognome, p.data_nascita,
       (SELECT COUNT(*) FROM oncologia_demo.esame_laboratorio e WHERE e.paziente_id = p.paziente_id) AS esami
FROM oncologia_demo.paziente p WHERE p.mrn = @mrn;
