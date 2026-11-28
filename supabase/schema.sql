
create table if not exists public.voice_invites (
  id            uuid primary key default gen_random_uuid(),
  token_hash    text unique not null,
  speaker_id    text not null,
  speaker_name  text,
  consent_text  text,
  consent_at    timestamptz,
  active        boolean not null default true,
  created_at    timestamptz not null default now()
);

create table if not exists public.voice_uploads (
  id          bigserial primary key,
  invite_id   uuid not null references public.voice_invites(id),
  speaker_id  text not null,
  item_id     text not null,
  path        text not null,
  marks       jsonb,
  duration    real,
  client_qc   jsonb,
  synced      boolean not null default false,
  created_at  timestamptz not null default now()
);

create index if not exists voice_uploads_unsynced on public.voice_uploads (synced) where not synced;
create index if not exists voice_uploads_invite on public.voice_uploads (invite_id);

alter table public.voice_invites enable row level security;
alter table public.voice_uploads enable row level security;

grant select, insert, update, delete on public.voice_invites, public.voice_uploads to service_role;
grant usage, select on sequence public.voice_uploads_id_seq to service_role;
revoke all on public.voice_invites, public.voice_uploads from anon, authenticated;
