-- 성과가 향상되는 자율 개선형 시스템 — growth 스키마 전체 (구조·뷰·함수·트리거)
-- Supabase 대시보드 → SQL Editor 에 통째로 붙여 넣고 Run.  여러 번 실행해도 안전하지 않으니 처음 한 번만 실행하세요.
-- 실행 후 같은 프로젝트에 seed 파일(growth_seed_*.sql)을 이어서 실행합니다.

create schema if not exists growth;
revoke all on schema growth from public, anon, authenticated;

create table growth.goals (
  id bigint generated always as identity primary key,
  title text not null,
  task_type text not null,
  objective text,
  variables jsonb not null default '{}'::jsonb,
  metric text,
  target numeric,
  status text not null default 'active' check (status in ('active','achieved','paused')),
  created_at timestamptz not null default now()
);

create table growth.playbooks (
  id bigint generated always as identity primary key,
  task_type text not null,
  version int not null,
  name text not null,
  instructions text not null,
  parent_id bigint references growth.playbooks(id),
  is_champion boolean not null default false,
  created_at timestamptz not null default now(),
  unique (task_type, version)
);
create unique index playbooks_one_champion on growth.playbooks(task_type) where is_champion;
create index playbooks_parent_idx on growth.playbooks(parent_id);

create table growth.learnings (
  id bigint generated always as identity primary key,
  task_type text not null,
  insight text not null,
  tags text[] not null default '{}',
  source text not null default 'manual' check (source in ('feedback','metric','manual','research')),
  evidence jsonb not null default '[]'::jsonb,
  status text not null default 'active' check (status in ('active','retired')),
  applied_count int not null default 0 check (applied_count >= 0),
  success_count int not null default 0 check (success_count >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index learnings_task_status_idx on growth.learnings(task_type, status);

create table growth.runs (
  id bigint generated always as identity primary key,
  goal_id bigint references growth.goals(id) on delete set null,
  task_type text not null,
  playbook_id bigint references growth.playbooks(id) on delete set null,
  variables jsonb not null default '{}'::jsonb,
  input text,
  output text,
  metrics jsonb not null default '{}'::jsonb,
  score numeric check (score between 0 and 100),
  status text not null default 'started' check (status in ('started','done','failed')),
  created_at timestamptz not null default now(),
  finished_at timestamptz
);
create index runs_goal_idx on growth.runs(goal_id);
create index runs_playbook_idx on growth.runs(playbook_id);
create index runs_task_created_idx on growth.runs(task_type, created_at desc);

create table growth.run_learnings (
  run_id bigint not null references growth.runs(id) on delete cascade,
  learning_id bigint not null references growth.learnings(id) on delete cascade,
  primary key (run_id, learning_id)
);
create index run_learnings_learning_idx on growth.run_learnings(learning_id);

create table growth.feedback (
  id bigint generated always as identity primary key,
  run_id bigint not null references growth.runs(id) on delete cascade,
  source text not null default 'user' check (source in ('user','audience','platform','self')),
  rating smallint check (rating between 1 and 5),
  comment text,
  tags text[] not null default '{}',
  created_at timestamptz not null default now()
);
create index feedback_run_idx on growth.feedback(run_id);

alter table growth.goals enable row level security;
alter table growth.playbooks enable row level security;
alter table growth.learnings enable row level security;
alter table growth.runs enable row level security;
alter table growth.run_learnings enable row level security;
alter table growth.feedback enable row level security;

create view growth.v_learning_rank with (security_invoker = true) as
select l.*, round((l.success_count + 1)::numeric / (l.applied_count + 2), 3) as confidence
from growth.learnings l;

create view growth.v_playbook_perf with (security_invoker = true) as
select p.id, p.task_type, p.version, p.name, p.is_champion,
       count(r.id) filter (where r.score is not null) as scored_runs,
       round(avg(r.score), 1) as avg_score,
       max(r.score) as best_score
from growth.playbooks p
left join growth.runs r on r.playbook_id = p.id
group by p.id;

create view growth.v_goal_progress with (security_invoker = true) as
select g.id, g.title, g.task_type, g.metric, g.target, g.status,
       count(r.id) filter (where r.score is not null) as scored_runs,
       round(avg(r.score), 1) as avg_score,
       max(r.score) as best_score,
       (select (r2.metrics ->> g.metric)::numeric from growth.runs r2
         where r2.goal_id = g.id and r2.metrics ? g.metric order by r2.finished_at desc nulls last limit 1) as latest_metric,
       (select round(avg(s.score), 1) from (select score from growth.runs where goal_id = g.id and score is not null order by created_at desc limit 3) s) as last3_avg
from growth.goals g
left join growth.runs r on r.goal_id = g.id
group by g.id;

CREATE OR REPLACE FUNCTION growth.start_run(p_task_type text, p_goal_id bigint DEFAULT NULL::bigint, p_variables jsonb DEFAULT '{}'::jsonb, p_input text DEFAULT NULL::text, p_k integer DEFAULT 7, p_trial_runs integer DEFAULT 3)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  v_pb growth.playbooks; v_challenger growth.playbooks; v_run_id bigint; v_ids bigint[]; v_explore bigint; v_trial boolean := false;
begin
  select * into v_pb from growth.playbooks
   where task_type = p_task_type order by is_champion desc, version desc limit 1;

  -- A/B: 아직 검증 실행이 p_trial_runs 미만인 새 버전이 있으면 50% 확률로 그 버전을 시험
  select p.* into v_challenger from growth.playbooks p
   where p.task_type = p_task_type and not p.is_champion and p.id is distinct from v_pb.id
     and (select count(*) from growth.runs r where r.playbook_id = p.id and r.score is not null) < p_trial_runs
   order by p.version desc limit 1;
  if v_challenger.id is not null and random() < 0.5 then
    v_pb := v_challenger; v_trial := true;
  end if;

  select coalesce(array_agg(id), '{}') into v_ids from (
    select id from growth.v_learning_rank
     where status = 'active' and task_type in (p_task_type, 'all')
     order by confidence desc, applied_count desc, created_at desc
     limit greatest(p_k - 1, 0)) t;

  select id into v_explore from growth.learnings
   where status = 'active' and task_type in (p_task_type, 'all') and applied_count < 3 and not (id = any(v_ids))
   order by created_at desc limit 1;
  if v_explore is not null then v_ids := v_ids || v_explore; end if;

  insert into growth.runs (goal_id, task_type, playbook_id, variables, input)
  values (p_goal_id, p_task_type, v_pb.id, coalesce(p_variables, '{}'::jsonb), p_input)
  returning id into v_run_id;

  insert into growth.run_learnings (run_id, learning_id) select v_run_id, unnest(v_ids);

  return jsonb_build_object(
    'run_id', v_run_id,
    'goal', (select to_jsonb(g) from growth.goals g where g.id = p_goal_id),
    'playbook', case when v_pb.id is null then null else jsonb_build_object('id', v_pb.id, 'version', v_pb.version, 'name', v_pb.name, 'instructions', v_pb.instructions, 'trial', v_trial) end,
    'learnings', coalesce((select jsonb_agg(jsonb_build_object('id', id, 'insight', insight, 'confidence', confidence, 'applied', applied_count, 'explore', coalesce(id = v_explore, false)) order by confidence desc)
                           from growth.v_learning_rank where id = any(v_ids)), '[]'::jsonb),
    'best_examples', coalesce((select jsonb_agg(jsonb_build_object('run_id', id, 'score', score, 'output', left(output, 1500)))
                               from (select id, score, output from growth.runs
                                      where task_type = p_task_type and score is not null and output is not null
                                      order by score desc limit 3) b), '[]'::jsonb));
end $function$;

CREATE OR REPLACE FUNCTION growth.record_result(p_run_id bigint, p_output text, p_score numeric, p_metrics jsonb DEFAULT '{}'::jsonb, p_success_threshold numeric DEFAULT 70)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_run growth.runs; v_goal growth.goals; v_hit boolean := false; v_val numeric;
begin
  update growth.runs
     set output = p_output, score = p_score, metrics = metrics || coalesce(p_metrics, '{}'::jsonb),
         status = 'done', finished_at = now()
   where id = p_run_id and status = 'started'
  returning * into v_run;
  if v_run.id is null then raise exception 'run % not found or already recorded', p_run_id; end if;

  update growth.learnings l
     set applied_count = applied_count + 1,
         success_count = success_count + (p_score >= p_success_threshold)::int,
         updated_at = now()
    from growth.run_learnings rl
   where rl.run_id = p_run_id and rl.learning_id = l.id;

  if v_run.goal_id is not null then
    select * into v_goal from growth.goals where id = v_run.goal_id;
    v_val := coalesce((v_run.metrics ->> v_goal.metric)::numeric, case when v_goal.metric = 'score' then p_score end);
    if v_goal.target is not null and v_val is not null and v_val >= v_goal.target then
      update growth.goals set status = 'achieved' where id = v_goal.id;
      v_hit := true;
    end if;
  end if;

  return jsonb_build_object('run_id', p_run_id, 'score', p_score, 'goal_achieved', v_hit,
    'goal_progress', (select to_jsonb(p) from growth.v_goal_progress p where p.id = v_run.goal_id));
end $function$;

CREATE OR REPLACE FUNCTION growth.add_feedback(p_run_id bigint, p_rating smallint DEFAULT NULL::smallint, p_comment text DEFAULT NULL::text, p_tags text[] DEFAULT '{}'::text[], p_source text DEFAULT 'user'::text)
 RETURNS bigint
 LANGUAGE sql
 SET search_path TO ''
AS $function$
  insert into growth.feedback (run_id, rating, comment, tags, source)
  values (p_run_id, p_rating, p_comment, coalesce(p_tags, '{}'), p_source)
  returning id;
$function$;

CREATE OR REPLACE FUNCTION growth.add_learning(p_task_type text, p_insight text, p_tags text[] DEFAULT '{}'::text[], p_source text DEFAULT 'feedback'::text, p_evidence jsonb DEFAULT '[]'::jsonb)
 RETURNS bigint
 LANGUAGE sql
 SET search_path TO ''
AS $function$
  insert into growth.learnings (task_type, insight, tags, source, evidence)
  values (p_task_type, p_insight, coalesce(p_tags, '{}'), p_source, coalesce(p_evidence, '[]'::jsonb))
  returning id;
$function$;

CREATE OR REPLACE FUNCTION growth.add_playbook(p_task_type text, p_name text, p_instructions text, p_parent_id bigint DEFAULT NULL::bigint)
 RETURNS bigint
 LANGUAGE sql
 SET search_path TO ''
AS $function$
  insert into growth.playbooks (task_type, version, name, instructions, parent_id)
  values (p_task_type,
          coalesce((select max(version) from growth.playbooks where task_type = p_task_type), 0) + 1,
          p_name, p_instructions, p_parent_id)
  returning id;
$function$;

CREATE OR REPLACE FUNCTION growth.promote_champion(p_task_type text, p_min_runs integer DEFAULT 3)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_best bigint;
begin
  select id into v_best from growth.v_playbook_perf
   where task_type = p_task_type and scored_runs >= p_min_runs
   order by avg_score desc, scored_runs desc limit 1;
  if v_best is not null then
    update growth.playbooks set is_champion = false where task_type = p_task_type and is_champion and id <> v_best;
    update growth.playbooks set is_champion = true where id = v_best;
  end if;
  return coalesce((select jsonb_agg(to_jsonb(v) order by v.avg_score desc nulls last)
                   from growth.v_playbook_perf v where v.task_type = p_task_type), '[]'::jsonb);
end $function$;

CREATE OR REPLACE FUNCTION growth.retire_weak_learnings(p_min_applied integer DEFAULT 5, p_max_conf numeric DEFAULT 0.3)
 RETURNS integer
 LANGUAGE sql
 SET search_path TO ''
AS $function$
  with u as (
    update growth.learnings set status = 'retired', updated_at = now()
     where status = 'active' and applied_count >= p_min_applied
       and (success_count + 1)::numeric / (applied_count + 2) < p_max_conf
    returning 1)
  select count(*)::int from u;
$function$;

CREATE OR REPLACE FUNCTION growth.improve_all(p_min_runs integer DEFAULT 3)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_t text; v_result jsonb := '{}'::jsonb; v_retired int;
begin
  for v_t in select distinct task_type from growth.playbooks loop
    perform growth.promote_champion(v_t, p_min_runs);
    v_result := v_result || jsonb_build_object(v_t,
      (select jsonb_build_object('champion_id', id, 'version', version, 'name', name)
         from growth.playbooks where task_type = v_t and is_champion limit 1));
  end loop;
  v_retired := growth.retire_weak_learnings();
  return jsonb_build_object('ran_at', now(), 'champions', v_result, 'retired_learnings', v_retired);
end $function$;

-- 피드백이 들어오면: 평점을 실행 지표에 반영, 평점 4~5/1~2로 적용 학습의 성공·실패 집계, 'lesson' 태그 댓글은 새 학습으로 저장
CREATE OR REPLACE FUNCTION growth.on_feedback_insert()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_task text;
begin
  select task_type into v_task from growth.runs where id = new.run_id;

  if new.rating is not null then
    update growth.runs r
       set metrics = r.metrics || jsonb_build_object(
             'user_rating', (select round(avg(f.rating)::numeric, 2) from growth.feedback f where f.run_id = new.run_id),
             'feedback_count', (select count(*) from growth.feedback f where f.run_id = new.run_id))
     where r.id = new.run_id;

    if new.rating <> 3 then
      update growth.learnings l
         set applied_count = l.applied_count + 1,
             success_count = l.success_count + (new.rating >= 4)::int,
             updated_at = now()
        from growth.run_learnings rl
       where rl.run_id = new.run_id and rl.learning_id = l.id;
    end if;
  end if;

  if new.comment is not null and 'lesson' = any(new.tags) and v_task is not null then
    insert into growth.learnings (task_type, insight, tags, source, evidence)
    values (v_task, new.comment, array_remove(new.tags, 'lesson'), 'feedback',
            jsonb_build_object('run_id', new.run_id, 'feedback_id', new.id, 'rating', new.rating));
  end if;

  return new;
end $function$;

CREATE TRIGGER trg_feedback_learn AFTER INSERT ON growth.feedback FOR EACH ROW EXECUTE FUNCTION growth.on_feedback_insert();

revoke all on all tables in schema growth from public, anon, authenticated;
revoke all on all functions in schema growth from public, anon, authenticated;

-- (선택) 매일 자동 개선: Database → Extensions 에서 pg_cron 을 켠 뒤 아래 한 줄 실행
-- select cron.schedule('growth-daily-improve', '17 18 * * *', 'select growth.improve_all()');
