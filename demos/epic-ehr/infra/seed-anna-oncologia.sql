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

-- Clinical context mirroring Anna's synthetic EMR/PACS chart (synthetic_emr.py). Each table is
-- seeded only when Anna has no rows yet; identity keys are generated by SQL Server.
DECLARE @episode int;
IF OBJECT_ID(N'oncologia_demo.episodio') IS NOT NULL
BEGIN
    SELECT @episode = MIN(episodio_id) FROM oncologia_demo.episodio WHERE paziente_id = @annaId;
    IF @episode IS NULL
    BEGIN
        INSERT oncologia_demo.episodio (paziente_id, struttura_id, uo_id, numero_nosologico,
            tipo_episodio, regime, data_inizio, data_fine, motivo, stato)
        SELECT TOP (1) @annaId, struttura_id, uo_id, N'2026/004417', N'RICOVERO', N'ORDINARIO',
            '2026-09-18T22:40:00', '2026-09-23T11:00:00',
            N'Sincope in vacanza (Montalcino) con anemia severa; trasferita a UMC Utrecht (NL) il 23/09/2026',
            N'CHIUSO'
        FROM oncologia_demo.episodio
        ORDER BY CASE WHEN paziente_id = @templateId THEN 0 ELSE 1 END, episodio_id;
        SET @episode = SCOPE_IDENTITY();
    END;
    IF COL_LENGTH(N'oncologia_demo.esame_laboratorio', N'episodio_id') IS NOT NULL
        EXEC sp_executesql N'UPDATE oncologia_demo.esame_laboratorio SET episodio_id = @episode
            WHERE paziente_id = @annaId AND episodio_id IS NULL;',
            N'@episode int, @annaId bigint', @episode, @annaId;
END;

IF OBJECT_ID(N'oncologia_demo.diagnosi') IS NOT NULL
   IF NOT EXISTS (SELECT 1 FROM oncologia_demo.diagnosi WHERE paziente_id = @annaId)
    INSERT oncologia_demo.diagnosi (paziente_id, episodio_id, sistema_codifica, versione_codifica,
        codice, descrizione, tipo, data_diagnosi, attiva) VALUES
    (@annaId, @episode, N'ICD-9-CM', N'2007', N'153.3', N'Neoplasia maligna del sigma (adenocarcinoma, biopsia 19/09/2026)', N'PRINCIPALE', '2026-09-21', 1),
    (@annaId, @episode, N'ICD-9-CM', N'2007', N'197.7', N'Lesioni epatiche secondarie sospette (RM 21/09/2026)', N'SECONDARIA', '2026-09-21', 1),
    (@annaId, @episode, N'ICD-9-CM', N'2007', N'280.0', N'Anemia sideropenica da perdita ematica cronica', N'SECONDARIA', '2026-09-19', 1),
    (@annaId, @episode, N'ICD-9-CM', N'2007', N'780.2', N'Sincope e collasso', N'SECONDARIA', '2026-09-18', 0);

DECLARE @tumour int;
IF OBJECT_ID(N'oncologia_demo.neoplasia') IS NOT NULL
BEGIN
    SELECT @tumour = MIN(neoplasia_id) FROM oncologia_demo.neoplasia WHERE paziente_id = @annaId;
    IF @tumour IS NULL
    BEGIN
        INSERT oncologia_demo.neoplasia (paziente_id, sede_primaria, istologia, grado, data_diagnosi,
            t_clinico, n_clinico, m_clinico, stadio_clinico, resecabilita, stato_malattia) VALUES
        (@annaId, N'Colon sigmoideo', N'Adenocarcinoma moderatamente differenziato', N'G2', '2026-09-21',
            N'cT3', N'cN1', N'cM1 (fegato)', N'IV - stadiazione clinica provvisoria',
            N'Da definire in discussione multidisciplinare', N'Nuova diagnosi, nessuna terapia oncologica avviata');
        SET @tumour = SCOPE_IDENTITY();
    END;
    IF OBJECT_ID(N'oncologia_demo.biomarcatore') IS NOT NULL
       IF NOT EXISTS (SELECT 1 FROM oncologia_demo.biomarcatore WHERE neoplasia_id = @tumour)
        INSERT oncologia_demo.biomarcatore (neoplasia_id, nome, risultato, metodo, data_risultato) VALUES
        (@tumour, N'KRAS', N'Richiesto 22/09/2026 - in corso', N'NGS', NULL),
        (@tumour, N'NRAS', N'Richiesto 22/09/2026 - in corso', N'NGS', NULL),
        (@tumour, N'BRAF', N'Richiesto 22/09/2026 - in corso', N'NGS', NULL),
        (@tumour, N'MSI / MMR', N'Richiesto 22/09/2026 - in corso', N'Immunoistochimica', NULL);
END;

IF OBJECT_ID(N'oncologia_demo.terapia_farmacologica') IS NOT NULL
   IF NOT EXISTS (SELECT 1 FROM oncologia_demo.terapia_farmacologica WHERE paziente_id = @annaId)
    INSERT oncologia_demo.terapia_farmacologica (paziente_id, episodio_id, farmaco, dose, via,
        frequenza, data_inizio, data_fine, stato, indicazione) VALUES
    (@annaId, @episode, N'Ferro carbossimaltosio', N'1000 mg', N'e.v.', N'dose unica', '2026-09-20T10:00:00', '2026-09-20T10:30:00', N'COMPLETATA', N'Anemia sideropenica'),
    (@annaId, @episode, N'Pantoprazolo', N'40 mg', N'e.v.', N'1 volta/die', '2026-09-18T23:30:00', NULL, N'ATTIVA', N'Gastroprotezione'),
    (@annaId, @episode, N'Enoxaparina', N'4000 UI', N's.c.', N'1 volta/die', '2026-09-19T20:00:00', NULL, N'ATTIVA', N'Profilassi tromboembolismo venoso');

IF OBJECT_ID(N'oncologia_demo.osservazione_vitale') IS NOT NULL
   IF NOT EXISTS (SELECT 1 FROM oncologia_demo.osservazione_vitale WHERE paziente_id = @annaId)
    INSERT oncologia_demo.osservazione_vitale (paziente_id, episodio_id, data_ora, frequenza_cardiaca,
        pressione_sistolica, pressione_diastolica, frequenza_respiratoria, spo2, temperatura, news2) VALUES
    (@annaId, @episode, '2026-09-18T22:40:00', 104, 98, 60, 18, 97, 36.4, 3),
    (@annaId, @episode, '2026-09-19T08:00:00', 84, 120, 80, 16, 98, 36.6, 0),
    (@annaId, @episode, '2026-09-22T08:00:00', 78, 118, 76, 16, 98, 36.5, 0);

IF OBJECT_ID(N'oncologia_demo.imaging') IS NOT NULL
   IF NOT EXISTS (SELECT 1 FROM oncologia_demo.imaging WHERE paziente_id = @annaId)
    INSERT oncologia_demo.imaging (paziente_id, episodio_id, data_esame, modalita, distretto,
        indicazione, referto, conclusione) VALUES
    (@annaId, @episode, '2026-09-20T11:05:00', N'CT', N'Torace-addome con mdc',
        N'Stadiazione, anemia sideropenica',
        N'Ispessimento parietale stenosante del sigma per circa 5 cm con linfonodi pericolici fino a 9 mm. Due aree ipodense epatiche (segmenti VII e IVa), da caratterizzare con RM. Polmoni senza noduli. Non versamento.',
        N'Neoformazione del sigma con linfoadenopatia locoregionale; lesioni epatiche da caratterizzare con RM.'),
    (@annaId, @episode, '2026-09-21T15:20:00', N'MR', N'Fegato senza e con mdc',
        N'Stadiazione in paziente con neoformazione del sigma (biopsia: adenocarcinoma)',
        N'Segmento VII: lesione nodulare di 22 x 19 mm, ipointensa in T1, moderatamente iperintensa in T2, con restrizione della diffusione ed enhancement periferico ad anello. Segmento IVa: seconda lesione di 14 mm con analoghe caratteristiche. Vie biliari non dilatate, vena porta pervia.',
        N'Due lesioni epatiche (segmento VII 22 mm, segmento IVa 14 mm) compatibili con localizzazioni secondarie. Si consiglia discussione multidisciplinare.');

IF OBJECT_ID(N'oncologia_demo.anatomia_patologica') IS NOT NULL
   IF NOT EXISTS (SELECT 1 FROM oncologia_demo.anatomia_patologica WHERE paziente_id = @annaId)
    INSERT oncologia_demo.anatomia_patologica (paziente_id, episodio_id, data_prelievo, data_referto,
        tipo_campione, sede, diagnosi, grado, note) VALUES
    (@annaId, @episode, '2026-09-19T10:30:00', '2026-09-21T14:00:00', N'Biopsie endoscopiche multiple',
        N'Colon sigmoideo (25 cm dal margine anale)', N'Adenocarcinoma moderatamente differenziato', N'G2',
        N'Biomarcatori molecolari (KRAS, NRAS, BRAF, MSI) richiesti il 22/09/2026.');

IF OBJECT_ID(N'oncologia_demo.procedura') IS NOT NULL
   IF NOT EXISTS (SELECT 1 FROM oncologia_demo.procedura WHERE paziente_id = @annaId)
    INSERT oncologia_demo.procedura (paziente_id, episodio_id, data_eseguita, sistema_codifica, codice,
        descrizione, approccio, priorita, stato, note) VALUES
    (@annaId, @episode, '2026-09-19T10:30:00', N'ICD-9-CM', N'45.25', N'Colonscopia con biopsie multiple',
        N'Endoscopico', N'URGENTE', N'ESEGUITA', N'Neoformazione stenosante del sigma a 25 cm.'),
    (@annaId, @episode, '2026-09-19T14:00:00', N'ICD-9-CM', N'99.04', N'Trasfusione di emazie concentrate (2 unita)',
        N'Endovenoso', N'URGENTE', N'ESEGUITA', NULL);

IF OBJECT_ID(N'oncologia_demo.anamnesi') IS NOT NULL
   IF NOT EXISTS (SELECT 1 FROM oncologia_demo.anamnesi WHERE paziente_id = @annaId)
    INSERT oncologia_demo.anamnesi (paziente_id, categoria, descrizione, data_inizio, data_fine, attiva) VALUES
    (@annaId, N'Anamnesi patologica prossima', N'Astenia e pallore da alcune settimane; sincope durante passeggiata', '2026-08-15', NULL, 1),
    (@annaId, N'Anamnesi patologica remota', N'Nessuna patologia cronica nota', NULL, NULL, 1),
    (@annaId, N'Anamnesi sociale', N'Turista olandese, residente a Utrecht (NL)', NULL, NULL, 1);

IF OBJECT_ID(N'oncologia_demo.valutazione_funzione') IS NOT NULL
   IF NOT EXISTS (SELECT 1 FROM oncologia_demo.valutazione_funzione WHERE paziente_id = @annaId)
    INSERT oncologia_demo.valutazione_funzione (paziente_id, episodio_id, data_ora, ecog, asa, note) VALUES
    (@annaId, @episode, '2026-09-19T12:10:00', 1, 2, N'Consulenza chirurgica: addome trattabile, non segni di occlusione o perforazione.');

IF OBJECT_ID(N'oncologia_demo.alert_clinico') IS NOT NULL
   IF NOT EXISTS (SELECT 1 FROM oncologia_demo.alert_clinico WHERE paziente_id = @annaId)
    INSERT oncologia_demo.alert_clinico (paziente_id, episodio_id, data_ora, sorgente, severita, titolo,
        messaggio, stato) VALUES
    (@annaId, @episode, '2026-09-18T23:10:00', N'Laboratorio', N'ALTA', N'Emoglobina critica',
        N'Hb 8.1 g/dL (rif. 12.0-16.0) con MCV 71 fL: anemia microcitica severa.', N'RISOLTO'),
    (@annaId, @episode, '2026-09-22T10:30:00', N'Oncologia', N'MEDIA', N'Discussione MDT richiesta',
        N'Adenocarcinoma del sigma con sospette metastasi epatiche: discussione multidisciplinare presso centro di riferimento.', N'ATTIVO');

IF OBJECT_ID(N'oncologia_demo.evento_clinico') IS NOT NULL
   IF NOT EXISTS (SELECT 1 FROM oncologia_demo.evento_clinico WHERE paziente_id = @annaId)
    INSERT oncologia_demo.evento_clinico (paziente_id, episodio_id, data_ora, tipo_evento, titolo, descrizione, fonte) VALUES
    (@annaId, @episode, '2026-09-18T22:40:00', N'Accesso PS', N'Sincope in vacanza', N'Pallore, astenia, PA 98/60, FC 104, Hb 8.1 g/dL. Ricovero in Chirurgia Generale.', N'Pronto Soccorso'),
    (@annaId, @episode, '2026-09-19T10:30:00', N'Procedura', N'Colonscopia', N'Neoformazione stenosante del sigma, biopsie multiple.', N'Endoscopia'),
    (@annaId, @episode, '2026-09-21T14:00:00', N'Referto', N'Istologico', N'Adenocarcinoma G2 del sigma.', N'Anatomia patologica'),
    (@annaId, @episode, '2026-09-22T10:30:00', N'Consulenza', N'Consulenza oncologica', N'Due lesioni epatiche sospette. Richiesti biomarcatori. Indicata discussione MDT.', N'Oncologia'),
    (@annaId, @episode, '2026-09-23T09:00:00', N'Trasferimento', N'Trasferimento a UMC Utrecht (NL)', N'Paziente stabile, trasferita su richiesta della famiglia.', N'Chirurgia Generale');

COMMIT TRANSACTION;

SELECT p.mrn, p.nome, p.cognome, p.data_nascita,
       (SELECT COUNT(*) FROM oncologia_demo.esame_laboratorio e WHERE e.paziente_id = p.paziente_id) AS esami
FROM oncologia_demo.paziente p WHERE p.mrn = @mrn;
IF OBJECT_ID(N'oncologia_demo.diagnosi') IS NOT NULL
    EXEC sp_executesql N'SELECT COUNT(*) AS diagnosi_anna FROM oncologia_demo.diagnosi WHERE paziente_id = @annaId;',
        N'@annaId bigint', @annaId;
