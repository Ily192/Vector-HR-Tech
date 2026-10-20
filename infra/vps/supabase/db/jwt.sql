-- Vendorizado de supabase/supabase@bc27d2661edd, docker/volumes/db/jwt.sql,
-- con infra/vps/scripts/vendorizar_supabase.py. Sin cambios.
-- No editar a mano: se regenera al actualizar Supabase.
\set jwt_exp `echo "$JWT_EXP"`

ALTER DATABASE postgres SET "app.settings.jwt_exp" TO :'jwt_exp';
