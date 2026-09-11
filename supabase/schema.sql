-- Cole isto no Supabase: SQL Editor → Run
-- Deixa o banco pronto para o sistema e para o Render.

alter table if exists vagas
  alter column origem_linha type bigint;

alter table if exists vagas
  alter column data drop not null;

alter table if exists vagas add column if not exists turma text;
alter table if exists vagas add column if not exists n_alunos integer;
alter table if exists vagas add column if not exists n_presentes integer;
alter table if exists vagas add column if not exists alocacao text;
alter table if exists vagas add column if not exists finalizado_em text;
alter table if exists vagas add column if not exists prova_recebida_em text;

alter table if exists viagens add column if not exists dias_aplicacao text;

alter table if exists aplicadores add column if not exists cpf text;
alter table if exists aplicadores add column if not exists numero integer;
alter table if exists aplicadores add column if not exists acesso_token text;
