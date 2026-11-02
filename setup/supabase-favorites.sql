-- Fetch Feed: saved favorites for signed-in visitors.
-- Paste all of this into Supabase > SQL Editor > New query, then click Run.

create table if not exists public.favorites (
  user_id  uuid not null default auth.uid() references auth.users on delete cascade,
  pet_id   text not null,
  pet      jsonb not null,
  saved_at timestamptz not null default now(),
  primary key (user_id, pet_id)
);

-- Each person can only see and change their own favorites.
alter table public.favorites enable row level security;
create policy "read own favorites"   on public.favorites for select using (auth.uid() = user_id);
create policy "add own favorites"    on public.favorites for insert with check (auth.uid() = user_id);
create policy "update own favorites" on public.favorites for update using (auth.uid() = user_id);
create policy "remove own favorites" on public.favorites for delete using (auth.uid() = user_id);
