개발 계획 문서를 생성하거나 업데이트합니다.

아래 순서를 따릅니다.

1. 프로젝트 내 관련 `.md` 문서를 먼저 읽습니다.
   - `CLAUDE.md`, `AUTOMATION_MECHANISM.md`, 기존 `dev-plan/implement_*.md` 등
2. `@dev-plan-generator/SKILL.md` 에 정의된 문서 구조와 워크플로우를 따릅니다.
3. 새로운 작업이면 `dev-plan-generator/scripts/new_dev_plan.py` 를 실행해 골격을 생성합니다.
4. 같은 작업의 연속이면 기존 `dev-plan/implement_*.md` 를 찾아 업데이트합니다.

요청 내용: $ARGUMENTS

진행 규칙:
- 목적 / 범위 / 제외 범위를 먼저 고정한 뒤 구현 태스크를 작성합니다.
- 각 Phase에 자체 테스트를 포함합니다.
- 문서에 없는 범위 확장은 하지 않습니다.
- 체크박스 상태를 실제 진행 상태와 맞게 유지합니다.
