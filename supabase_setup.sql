-- Run this once in the Supabase SQL Editor for the Ask Mahesh project.
-- The owner email below must match OWNER_EMAIL in the app's private settings.

create table if not exists public.questions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    user_email text not null,
    question_type text not null check (question_type in ('ai', 'mahesh')),
    question text not null check (char_length(question) between 1 and 4000),
    answer text,
    created_at timestamptz not null default now(),
    answered_at timestamptz,
    read_at timestamptz
);

alter table public.questions enable row level security;

revoke all on public.questions from anon, authenticated;
grant select, insert on public.questions to authenticated;

drop policy if exists "Users read own questions and owner reads Mahesh inbox"
    on public.questions;
create policy "Users read own questions and owner reads Mahesh inbox"
    on public.questions
    for select
    to authenticated
    using (
        auth.uid() = user_id
        or (
            lower(coalesce(auth.jwt() ->> 'email', '')) = 'mahi.eduu@gmail.com'
            and question_type = 'mahesh'
        )
    );

drop policy if exists "Users insert their own questions" on public.questions;
create policy "Users insert their own questions"
    on public.questions
    for insert
    to authenticated
    with check (
        auth.uid() = user_id
        and lower(user_email) = lower(coalesce(auth.jwt() ->> 'email', ''))
        and (
            question_type = 'ai'
            or (
                question_type = 'mahesh'
                and answer is null
                and answered_at is null
                and read_at is null
            )
        )
    );

create or replace function public.owner_reply_to_question(
    p_question_id uuid,
    p_answer text
)
returns void
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    if lower(coalesce(auth.jwt() ->> 'email', '')) <> 'mahi.eduu@gmail.com' then
        raise exception 'Only the configured owner can answer questions'
            using errcode = '42501';
    end if;

    if p_answer is null or btrim(p_answer) = '' then
        raise exception 'An answer is required' using errcode = '22023';
    end if;

    update public.questions
    set answer = btrim(p_answer),
        answered_at = now(),
        read_at = null
    where id = p_question_id
      and question_type = 'mahesh';

    if not found then
        raise exception 'Question not found' using errcode = 'P0002';
    end if;
end;
$$;

create or replace function public.mark_question_read(p_question_id uuid)
returns void
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    update public.questions
    set read_at = now()
    where id = p_question_id
      and user_id = auth.uid()
      and answered_at is not null;

    if not found then
        raise exception 'Answered question not found for this user'
            using errcode = 'P0002';
    end if;
end;
$$;

revoke all on function public.owner_reply_to_question(uuid, text) from public, anon;
revoke all on function public.mark_question_read(uuid) from public, anon;
grant execute on function public.owner_reply_to_question(uuid, text) to authenticated;
grant execute on function public.mark_question_read(uuid) to authenticated;
