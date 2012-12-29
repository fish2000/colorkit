
drop function compand(r int, g int, b int);
create function compand(r int, g int, b int) returns integer as $$
begin
    return (r * 65536) + (g * 256) + b;
end;
$$ language plpgsql;


drop function populate_rgb_values();
reindex table colordb_rgb;
create function populate_rgb_values() returns integer as $$
begin
    for r in 0..255 loop
        for g in 0..255 loop
            for b in 0..255 loop
                insert into colordb_rgb (
                    "id",
                    "r", "g", "b")
                values (
                    compand(r, g, b),
                    r, g, b);
            end loop;
        end loop;
    end loop;
    return (select count(*) from colordb_rgb);
end;
$$ language plpgsql;




