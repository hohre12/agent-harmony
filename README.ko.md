# Agent Harmony

**한 줄이면 프로덕션까지.** 만들고 싶은 것을 설명하세요. Agent Harmony가 팀을 구성하고, 지식을 정리하고, 프로덕션 품질로 빌드합니다.

[English README](README.md)

## 작동 방식

```
You: /agent-harmony:harmony 코드 품질을 분석하는 SaaS를 만들고 싶어

Agent Harmony:
  1. 심층 인터뷰 — 구체적인 질문 → 완전한 PRD 생성
  2. 자동 셋업 — 에이전트 팀, 참조 문서, 태스크 생성
  3. 멀티패스 빌드 — 각 태스크마다:
     구현 → 자기 리뷰 → 품질 게이트 → 프로덕션 감사 → 수정
  4. 프로덕션 레디 코드베이스 완성
```

## 품질 격차 문제

AI가 생성한 코드에는 품질 격차가 있습니다:

| 방식 | 품질 | 이유 |
|------|------|------|
| AI 자율 실행 | 낮음 | "동작하면 끝", 한 번 패스, 판단 없음 |
| AI + 사람 리뷰 | 높음 | 사람이 문제를 잡고 개선을 요구 |

Agent Harmony는 **사람 개입 없이** 멀티패스 품질로 이 격차를 해소합니다:

```
각 태스크마다:
  1. 팀이 설계 → 에이전트가 격리된 worktree에서 구현
  2. 각 에이전트가 완료 보고 전 자기 리뷰
  3. 리뷰 에이전트가 품질 기준으로 검증
  4. 품질 게이트: build + test + lint (결정적)
  5. 프로덕션 감사: 새 에이전트가 시니어 엔지니어처럼 리뷰
  6. 이슈 발견 시 → 수정 → 재감사 (최대 2라운드)
```

## 빠른 시작

```bash
# 마켓플레이스 추가 & 플러그인 설치
/plugin marketplace add hohre12/jwbae-plugins
/plugin install agent-harmony@jwbae-plugins

# 빌드 시작
/agent-harmony:harmony 인증과 팀 협업이 있는 투두 앱
```

이게 전부입니다. 명령어 하나.

## 파이프라인

```
Phase 1: 대화 → PRD
  아이디어 설명 → 심층 인터뷰 (객관식 + AI 추천)
  → PRD 생성

Phase 2: 환경 셋업 (자동)
  /project-init → /generate-agents → /build-refs �� 태스크 생성
  → 에이전트 팀, 참조 문서, 태스크 준비 완료

Phase 3: 멀티패스 품질 빌드 (자동)
  각 태스크마다:
    /team-executor → 품질 게이트 → 프로덕션 감사 → 필요시 수정
  → 모든 태스크 품질 검증 통과

Phase 4: 완료
  → 테스트 통과하는 프로덕션 레디 프로젝트
```

## 생성되는 구조

```
{project}/
├── docs/
│   ├── prd.md                        # 대화에서 생성된 PRD
│   ├── refs/                         # 에이전트별 도메인 참조 문서
│   └── tasks/                        # 태스크별 설계 문서
├── .claude/
│   ├── agents/                       # 프로젝트 전용 에이전트 팀
│   ├── skills/
│   │   └── team-executor/SKILL.md    # 태스크 실행 스킬
│   └── settings.local.json           # 팀 기능 활성화
├── .harmony/
│   └── state.json                    # 파이프라인 상태 + 태스크 (자동 관리)
├── CLAUDE.md                         # 프로젝트 규칙과 컨벤션
└── README.md                         # 프로젝트 문서
```

## 멀티패스 품질 시스템

각 태스크는 5단계 품질 레이어를 거칩니다:

| 레이어 | 유형 | 잡아내는 것 |
|--------|------|------------|
| **자기 리뷰** | 에이전트별 | 누락된 요구사항, 죽은 코드, 미테스트 함수 |
| **코드 리뷰** | 리뷰 에이전트 | 통합 이슈, 보안 취약점, 에러 핸들링 갭 |
| **품질 게이트** | 결정적 | 빌드/테스트/린트 실패, 파일 크기 초과, 보안 이슈 |
| **프로덕션 감사** | 새 에이전트 | PRD 준수, 엣지 케이스, UX 이슈 |
| **수정 루프** | 반복적 | 지속되는 이슈 → 사용자에게 에스컬레이션 (자동 통과 없음) |

### 결정적 품질 임계값

품질 게이트는 실제 도구를 실행하고 수치 기준을 강제합니다. **모든 메트릭이 기준을 충족해야** 태스크가 통과됩니다:

| 메트릭 | 임계값 | 측정 방법 |
|--------|--------|----------|
| 빌드 | 통과 필수 | 프로젝트 빌드 명령어 |
| 테스트 | 통과 필수 | 전체 테스트 스위트 |
| 린트 | 에러 0개 | 프로젝트 린터 |
| 테스트 커버리지 | >= 70% | pytest --cov / jest --coverage |
| 최대 파일 줄 수 | <= 400줄 | wc -l |
| 최대 함수 줄 수 | <= 60줄 | 가장 큰 함수의 줄 수 |
| 보안 (크리티컬) | 0개 | bandit / npm audit + 시크릿 grep |

N라운드 후 자동 통과 없음. 기준 미달 시 사용자에게 에스컬레이션.

## 권장 플러그인

| 플러그인 | 용도 |
|---------|------|
| `frontend-design` | 프로페셔널한 UI 디자인 — AI slop 방지 |

```bash
/plugin install frontend-design@claude-plugins-official
```

## 세션 복원

개발이 중단되어도 이어서 진행:

```bash
# 세션 중단 또는 레이트 리밋
# /agent-harmony:harmony를 다시 실행하면 저장된 상태를 감지
/agent-harmony:harmony
# → "태스크 15/23에서 이어하시겠습니까? (a) 이어하기 (b) 처음부터"
```

## 명령어

### 메인 명령어

| 명령어 | 설명 |
|--------|------|
| `/agent-harmony:harmony [설명]` | **한 줄이면 프로덕션까지.** 대화 → PRD → 셋업 → 빌드 → 완료 |

### 파이프라인 명령어 (개별 사용 가능)

| 명령어 | 설명 |
|--------|------|
| `/project-init` | 새 프로젝트 구조 초기화 |
| `/codebase-init` | 기존 코드베이스에서 초기화 |
| `/generate-agents` | 프로젝트 전용 에이전트 팀 생성 |
| `/build-refs` | 도메인 참조 문서 생성 |


## 아키텍처

```
글로벌 에이전트 (플러그인):
└── expert-agent           PRD 분석 → 프로젝트 전용 에이전트 팀 생성

프로젝트별 팀 (expert-agent가 생성):
├── architect-agent        시스템 설계 & 팀 조율
├── backend-agent          백엔드 구현
├── frontend-agent         프론트엔드 구현
├── review-agent           코드 리뷰 & 품질 검증
└── ...                    (프로젝트마다 다름)

Python 오케스트레이터가 파이프라인을 단계별로 관리.
에이전트는 짧고 구체적인 지시를 받아 실행.
멀티패스 품질이 프로덕션 수준을 보장.
```

## 설치

```bash
# Claude Code 플러그인으로 설치
/plugin install agent-harmony@jwbae-plugins

# 또는 수동
git clone https://github.com/hohre12/agent-harmony ~/.claude/plugins/agent-harmony
```

`pip install` 불필요. Python 런타임은 첫 사용 시 자동 부트스트랩됩니다.

## 요구사항

- Claude Code CLI (Max Plan 또는 API 키)
- Python 3.10+ (런타임 엔진 — venv 자동 부트스트랩)
- git (브랜치 관리, worktree)
- macOS 또는 Linux (Windows는 WSL)
- 선택: tmux (에이전트 분할 화면 — 없어도 동작)

## 라이선스

오픈소스. MIT License.

## 버전

1.0.0
