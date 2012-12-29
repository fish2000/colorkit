

DROP INDEX "colordb_rgb__r";
DROP INDEX "colordb_rgb__g";
DROP INDEX "colordb_rgb__b";
DROP TABLE "colordb_rgb";

BEGIN;
CREATE TABLE "colordb_rgb" (
    "id" integer CHECK ("id" >= 0) NOT NULL,
    "_r" smallint CHECK ("_r" >= 0) NOT NULL,
    "_g" smallint CHECK ("_g" >= 0) NOT NULL,
    "_b" smallint CHECK ("_b" >= 0) NOT NULL
)
;

COMMIT;

drop function populate_rgb_values();
create function populate_rgb_values() returns integer as $$
begin
    for r in 0..255 loop
        for g in 0..255 loop
            for b in 0..255 loop
                insert into colordb_rgb (
                    "id",
                    "_r", "_g", "_b")
                values (
                    compand(r, g, b),
                    r, g, b);
            end loop;
        end loop;
    end loop;
    return (select count(*) from colordb_rgb);
end;
$$ language plpgsql;

select populate_rgb_values();

BEGIN;
CREATE INDEX "colordb_rgb__r" ON "colordb_rgb" ("_r");
CREATE INDEX "colordb_rgb__g" ON "colordb_rgb" ("_g");
CREATE INDEX "colordb_rgb__b" ON "colordb_rgb" ("_b");
ALTER TABLE "colordb_rgb" ADD PRIMARY KEY (id);

COMMIT;
reindex database colorkit;
