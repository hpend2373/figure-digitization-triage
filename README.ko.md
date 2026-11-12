# figure-digitization-triage (fdt)

[English](README.md) · **한국어**

논문 그림에만 보고된 수치를 읽어 CSV로 내보내는 도구입니다. 자동 판독,
직접 점 입력, 오버레이 검토를 지원합니다. 읽은 값마다 사용한 이미지, 눈금
보정, 판독기, 실행 환경과 검토자를 추적할 수 있습니다.

![곰이 인쇄된 그래프의 눈금과 점을 비교해 읽은 값을 기록하는 모습](assets/figure-digitization-triage-banner.webp)

우주비행과 머리 낮춤 침상 안정 연구에서 심혈관 반응을 검토하려고 만들었습니다.
검사는 선언된 데이터 유형과 조건을 기준으로 적용하므로 다른 분야의 논문 그림에도
같은 절차를 쓸 수 있습니다.

```text
PDF → 그림 목록 초안 → 검토자가 그린 패널 → 확인한 축·계열
    → 논문별 추출 계획 → 실행 명세 → 기계 품질 검사를 통과한 값
    → 검토자가 오버레이 확인 → figure_values_accepted.csv
```

## 예시 그래프로 시작하기

Git과 Python 3.11을 설치한 뒤 터미널에서 실행합니다.

```sh
git clone https://github.com/hpend2373/figure-digitization-triage
cd figure-digitization-triage
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python examples/quickstart/quickstart.py --workbench /tmp/fdt-workbench-demo
```

1. 브라우저에서 `/tmp/fdt-workbench-demo/workbench.html`을 엽니다.
2. 판독 표에서 셀 하나를 고르고 그래프에서 해당 막대의 꼭대기를 클릭합니다.
   오차 막대의 끝점이 보이면 끝점 입력 도구로 표시합니다.
3. 판독자 ID에 `DEMO`를 입력하고 오늘 날짜를 지정합니다. **CSV 내보내기**를 누르면
   이미지 픽셀 좌표와 합성 원본의 지문이 담긴 `manual_readings.csv`가 저장됩니다.

예시에는 눈금 보정과 계열 이름이 설정되어 있습니다. 다시 실행할 때는 새 출력
폴더를 지정하세요. 같은 그림을 자동으로 읽는 방법은
[자동 판독 예제](examples/quickstart/)에 있습니다. 개발 테스트는 Node.js를
사용하며, PDF 가져오기와 눈금 OCR에는 [별도 설정](docs/PROCEDURE.md#0-set-up)이
필요합니다.

## 판독과 검토 원칙

1. **같은 검증 규칙을 적용합니다.** 선언된 조건의 조합으로 검증합니다. 예외도
   데이터 유형을 기준으로 정해 모든 논문에 일관되게 적용합니다.
2. **계열은 계획에서 명시합니다.** 어떤 표식이 어떤 계열인지 계획에서 정합니다.
   표식을 구분할 근거가 부족하면 셀을 비워 두고 확인이 필요한 이유를 기록합니다.
3. **검토가 필요한 패널을 표시합니다.** 각 패널에 상태를 부여하고, 통과하지 못한
   패널을 사유와 함께 대기열에 넣습니다. 등록된 검토자의 확인을 받은 뒤
   `finalize_batch.py`가 승인된 판독값을 기록합니다. 메타분석에 포함할 수
   있는지는 별도로 판단합니다.

## 실제 논문에서 사용하기

[전체 절차](docs/PROCEDURE.md)는 PDF에서 승인된 수치를 얻기까지 9단계를 설명하고,
각 단계의 담당을 스크립트, AI 에이전트, 검토자로 표시합니다. 사람이 확인하는
단계는 [검토 안내서](docs/REVIEW_RUNBOOK.md)를 참고하세요.

```sh
python3 fdt/compile_plan.py PLAN.json MANIFESTS --file-root RUN
python3 fdt/run_batch.py MANIFESTS OUT --file-root RUN --doc-root PDFS
python3 fdt/finalize_batch.py OUT --template
# 검토자가 OUT/review_queue.csv의 각 항목을 열고 OUT/value_review.csv를 작성합니다.
python3 fdt/review_preflight.py OUT --review OUT/value_review.csv
python3 fdt/finalize_batch.py OUT --review OUT/value_review.csv
```

`OUT/figure_values_accepted.csv`가 생성되고 같은 폴더의
`finalize_stamp.json`에 `Status=FINALIZED`가 기록되면 판독 절차가 끝납니다.

**논문 PDF, 그림 원본, 실행 결과와 검토 답안은 공개 저장소 밖에 보관하세요.**
저장소 검사는 추적 중인 PDF를 차단하고, 이미지는 `tests/`와 README 표지
경로에서만 허용합니다. 표지에는 SHA-256 검사도 적용합니다.

## 그래프 판독 화면 열기

그림 가져오기, 패널 지정, 축과 계열 확인을 먼저 마칩니다. 이 단계에서 만든
실행 폴더(`RUN`)의 `seg/identity600/identity_decisions.csv`에서
`Read_Route=MANUAL`인 확인된 행의 `Proposal_ID`를 찾습니다. ID를 하나 이상
지정하면 해당 그래프가 열립니다.

```sh
python3 fdt/workbench.py --run RUN --panel PROPOSAL_A PROPOSAL_B --out RUN/workbench.html
```

여러 패널을 여는 작업 화면과 단일 패널 페이지의 조작 방식은 같습니다. 내보낸
좌표는 기존 보정과 검토 절차를 거칩니다. 자세한 내용은
[직접 판독 절차](docs/PROCEDURE.md#7-manual-digitization)에 있습니다.

확정된 파일에는 `Value_Status=HUMAN_APPROVED`와 `Pooling_Eligible=FALSE`가
기록됩니다. 예전 파일의 `TRUE`는 추출 승인을 뜻할 수 있습니다. 특정 분석에
포함할 수 있는지는 [근거 종합 단계로 넘기는 절차](docs/SYNTHESIS_HANDOFF.md)에
따라 판단합니다.

## AI 에이전트에서 사용하기

[SKILL.md](SKILL.md)를 스킬로 설치할 수 있습니다. 실행 규칙, 검토 모드와 실패
상태, 사람이 개입해야 할 단계가 정리되어 있습니다. 에이전트는 명령을 실행하고
판독을 제안하며, 사전에 승인된 범위에서 일치하는 독립 점검 결과를 기록할 수
있습니다. 검토 답안, 서명, 날짜, 확인 항목은 검토자가 직접 작성합니다.

## 저장소 구성

| 경로 | 용도 |
| --- | --- |
| `fdt/` | 판독 파이프라인. `python3 fdt/<script>.py --help`로 옵션을 확인합니다. |
| `fdt/sheet/` | 가져온 그림의 패널 수를 확인하는 썸네일 시트 |
| `templates/` | 코드에서 열 정의를 읽어 생성한 CSV 스키마 |
| `docs/` | 전체 절차, 검토 안내서와 세부 가이드 |
| `examples/` | 합성 그림의 계획 작성부터 판독·검토까지 보여 주는 예시 |
| `tests/` | 독립 실행 테스트와 합성 테스트 데이터 |
| `SKILL.md` | 에이전트가 따르는 실행 절차 |

## 테스트

```sh
bash .github/run_suites.sh
for t in tests/test_*.mjs tests/sheet/test_*.mjs; do node "$t"; done
```

테스트 파일은 독립적으로 실행됩니다. 실패하면 0이 아닌 종료 코드를 반환하고,
완료하면 `FDT_SCENARIOS_RUN=N`을 출력합니다. CI는 PDF 백엔드를 뺀 고정
환경과 PDF 가져오기 기능을 포함한 환경에서 각각 테스트합니다.

## 검토자 기록과 승인

`reviewer_registry.csv`에 그림을 검토한 사람, 연락처로 쓰는 ORCID, 검토자
유형(`HUMAN` 또는 `DEMO_IDENTITY`)을 기록합니다. 데모 신원으로 실행하면
`DEMO_ONLY` 상태로 끝나며 승인된 판독값을 생성하지 않습니다.

승인은 판독값, 실행 명세, 원시 표식과 실행 환경에서 계산한
`Review_Subject_SHA256`에 연결됩니다. 검토 이후 그중 하나라도 바뀌면
`APPROVAL_STALE`로 표시됩니다. `Human_Attestation`은 검토자가 확인했다고
명시한 기록입니다. 이 항목으로 어떤 값을 누가 확인했는지 추적할 수 있습니다.
