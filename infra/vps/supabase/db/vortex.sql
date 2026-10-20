-- Vortex (ADR-020): corre una sola vez, al crear la base, después de roles.sql.
--
-- `postgres` es el dueño del esquema: con él corren las migraciones, el hr-engine,
-- postgres-meta y Studio. El roles.sql oficial no le pone contraseña y el CLI de
-- Supabase sí (`supabase start`); aquí, la misma que el resto de los roles.
\set pgpass `echo "$POSTGRES_PASSWORD"`

ALTER USER postgres WITH PASSWORD :'pgpass';
