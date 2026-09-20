-- PEP router - unified schema (boston_ma + mexico)
--
-- Design notes:
--   * One `sites` table holds what every region needs. Anything that exists in
--     only one country lives in `region_attrs` as JSON, so adding a third region
--     never means an ALTER TABLE.
--   * Cost is a separate table because each region has a different set of
--     coverage schemes. Boston has 2, Mexico has 4, a third region will have
--     its own. A column per scheme does not generalise.
--   * is_demo_data / operational_data_origin drive the "unverified" badge.
--     Contact details can be official while availability is an estimate, which
--     is exactly the case for the Mexican rows.

DROP TABLE IF EXISTS neighborhoods;
DROP TABLE IF EXISTS site_costs;
DROP TABLE IF EXISTS sites;

CREATE TABLE sites (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    region                        TEXT    NOT NULL,   -- boston_ma | mexico
    source_id                     INTEGER,            -- id within its own CSV
    name                          TEXT    NOT NULL,
    site_type                     TEXT    NOT NULL,   -- er | sexual_health_clinic |
                                                      -- community_health_center | pharmacy |
                                                      -- university_health | capasits | saih |
                                                      -- imss_bienestar_hospital |
                                                      -- imss_bienestar_clinic |
                                                      -- imss_bienestar_mobile
    priority_tier                 INTEGER,            -- 1 = always-available fallback
    is_fallback                   INTEGER NOT NULL DEFAULT 0,  -- the region's guaranteed option

    -- location
    area                          TEXT,               -- Boston neighborhood or Mexican locality
    admin_region                  TEXT,               -- Mexican state; NULL for Boston
    address                       TEXT,
    lat                           REAL,
    lon                           REAL,
    geocode_precision             TEXT,               -- full_address | name_and_place | locality | none
    is_mobile                     INTEGER NOT NULL DEFAULT 0,  -- no fixed address; router skips

    -- contact
    phone                         TEXT,
    alt_phone                     TEXT,
    email                         TEXT,

    -- hours: "HH:MM-HH:MM" | "24h" | "closed" | NULL (unknown)
    open_24h                      INTEGER NOT NULL DEFAULT 0,
    mon TEXT, tue TEXT, wed TEXT, thu TEXT, fri TEXT, sat TEXT, sun TEXT,
    hours_raw                     TEXT,
    hours_needs_review            INTEGER NOT NULL DEFAULT 0,

    -- access
    walk_in                       TEXT,   -- walk_in_ok | appointment_only | same_day_appointment
    walk_in_cutoff                TEXT,
    must_be_existing_patient      TEXT,
    community                     TEXT,    -- closed community: mit | harvard
    serves_minors_without_parent  TEXT,
    min_age                       INTEGER,
    max_age                       INTEGER,   -- upper age limit, e.g. a paediatric ER
    languages                     TEXT,   -- semicolon separated

    -- what actually happens on arrival
    meds_in_hand                  TEXT,   -- full_28_day_course | starter_pack |
                                          -- prescription_only | varies_unknown | no_pep
    starter_pack_days             INTEGER,
    certainty                     REAL,   -- 0..1 probability of leaving with medication
    typical_wait_min              INTEGER,
    priority_triage               TEXT,

    -- provenance
    data_origin                   TEXT NOT NULL,  -- synthetic_demo | government_directory |
                                                  -- teammate_asserted | phone_verified | site_claimed
    operational_data_origin       TEXT,           -- provenance of the availability fields alone
    is_demo_data                  INTEGER NOT NULL DEFAULT 1,
    last_verified                 TEXT,           -- ISO date; drives the staleness layer
    source                        TEXT,

    app_notes                     TEXT,
    region_attrs                  TEXT            -- JSON: region-only fields
                                                  -- boston_ma: accepts_hsn, financial_navigator_onsite,
                                                  --            pharmacy_onsite
                                                  -- mexico:    facility_level, contact_person
);

CREATE TABLE site_costs (
    site_id   INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    scheme    TEXT    NOT NULL,   -- boston_ma: uninsured | masshealth
                                  -- mexico:    none | imss | issste | imss_bienestar
    cost      INTEGER NOT NULL,   -- expected value in local currency, not a quote
    currency  TEXT    NOT NULL DEFAULT 'USD',
    PRIMARY KEY (site_id, scheme)
);

CREATE INDEX idx_sites_region       ON sites(region);
CREATE INDEX idx_sites_type         ON sites(site_type);
CREATE INDEX idx_sites_fallback     ON sites(region, is_fallback);
CREATE INDEX idx_sites_coords       ON sites(lat, lon);

-- Options for the location picker. Coordinates are local, so choosing one of
-- these sends nothing to any external service.
CREATE TABLE neighborhoods (
    id        TEXT PRIMARY KEY,
    region    TEXT NOT NULL,
    name      TEXT NOT NULL,
    kind      TEXT,            -- boston | adjacent
    lat       REAL NOT NULL,
    lon       REAL NOT NULL,
    precision TEXT
);

CREATE INDEX idx_neighborhoods_region ON neighborhoods(region);
