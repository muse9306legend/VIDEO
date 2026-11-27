-- teruha-gift-mvp 프로젝트용 커밍스톤 SNS 시작 데이터 (growth_schema.sql 실행 후)
insert into growth.playbooks (task_type, version, name, instructions, is_champion) values
('sns_post', 1, '커밍스톤 SNS 글 v1', '브랜드: @comingstone.kr (자연석 말씀돌·교회 기념품·십자가 돌시계)
1. 첫 줄은 질문 또는 짧은 장면 묘사로 시작한다.
2. 본문에 "말씀돌/커밍스톤/자연석" 중 하나 이상, "신년 말씀/교회 기념품/성경 말씀" 같은 검색 키워드 하나 이상을 자연스럽게 넣는다.
3. 마지막 줄은 댓글을 부르는 질문이나 참여 요청으로 끝낸다.
4. 지킬 수 없는 약속(샘플 증정 등)은 쓰지 않는다. 연락처·링크·마감일은 실제 값만 쓴다.
5. 실물 사진 첨부를 전제로 쓴다.
변수: product, platform(threads|instagram), format(질문|썰|정보|공감|참여), deadline, link', true);

insert into growth.learnings (task_type, insight, tags, source) values
('sns_post', '모든 글에 브랜드어(말씀돌/커밍스톤/자연석)와 검색 키워드(신년 말씀/교회 기념품/성경 말씀)를 함께 넣는다.', '{keyword,brand}', 'manual'),
('sns_post', '첫 줄을 질문형으로 시작하고 마지막 줄에서 댓글로 답하게 하면 답글이 늘어난다는 가설을 검증한다.', '{hook,engagement,hypothesis}', 'manual'),
('sns_post', '다른 사람 게시물에 자동 댓글을 달지 않는다. 내 게시물 댓글 응대만 자동화한다(계정 제한 위험).', '{policy,safety}', 'manual');

select task_type, count(*) from growth.learnings group by 1;
