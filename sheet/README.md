# 계수 시트 — 빌더와 시험

이 묶음만으로 시트를 다시 만들고 모든 시험을 다시 돌릴 수 있어야 합니다.
3차 감사가 "이 전달물만으로 재실행 불가"라고 지적한 것을 고친 판입니다.

## 경로

이전 판은 `/tmp/intake*`, `/home/claude`, `/mnt/user-data/uploads`가 코드에
박혀 있었습니다. 이제 `paths.py` 한 곳이며 환경변수로 덮습니다.

    export FDT_DRAFT=/path/to/draft        # figure_intake_draft.csv 가 있는 곳
    export FDT_WORKLIST=/path/to/worklist.csv
    export FDT_AUDIT=/path/to/2026-08-28-contact-sheet-audit
    export FDT_SHEET=/path/to/panel_count_contact_sheet.html
    export FDT_REPO=/path/to/figure-digitization-triage
    export FDT_PAGES=$FDT_DRAFT/pages
    export FDT_STAGED=/path/to/staged_paths.txt   # 원문 절대경로 한 줄에 하나
    export FDT_CENSUS=$FDT_RUN/crop_visual_census.csv   # 육안 조사표
    export FDT_CENSUS_OPTIONAL=1   # 아직 아무도 보지 않은 코퍼스일 때만

## 인테이크 본체는 저장소에 있습니다

`corpus_intake.py`와 `test_corpus_intake.py`는 `kernel`·`batch_manifests` 등
저장소 모듈에 의존하므로 여기 복사본을 두면 갈라집니다. 이 시트를 만든 판은

    hpend2373/figure-digitization-triage  v9.28

**공개 커밋 해시는 여기 적지 않습니다.** 지난 판은 컨테이너의 커밋 SHA를
적었는데 그것은 Mac 클론에서 `git apply` 후 다른 SHA로 다시 만들어졌고, 게다가
아직 푸시되지 않아 공개 저장소에 존재하지 않았습니다. 재현 지점은 **버전 태그와
파일 해시**로 잡습니다:

    corpus_intake.py  sha256 = fc04d880905751fb17c4511d8cf45c491a8a09a66b60d130f8d435420fefc7b8

`git log --oneline` 에서 `v9.28`로 시작하는 커밋을 받은 뒤 그 파일 해시가 위와
같은지 확인하십시오. 아래 크롭 도구들은 `FDT_REPO`로 그 클론을 가리킵니다.

## 다시 돌리기

    python3 -m pip install pillow numpy pdfminer.six playwright
    python3 -m playwright install chromium
    sudo apt-get install poppler-utils

    $FDT_REPO/corpus_intake.py <PDF...> --out draft --render 200  # 1. 인테이크
    python3 build_sheet2.py                                       # 2. 시트
    node    test_sheet_logic.mjs      #  35
    python3 test_sheet_html.py        #  57
    python3 test_sheet_browser.py     #  29 (파트마다; FDT_BROWSER_PART로 고름)
    python3 test_sheet_build.py       # 164
    python3 test_merge_counts.py      #  22
    python3 verify_intake_images.py $FDT_RUN   # 있는가 · 끝까지 읽히는가 · 상자에서 다시 만들어지는가
    python3 roundtrip.py $FDT_RUN     # 상자대로 다시 잘라 크롭과 픽셀 비교 (run2: 642 MATCH)
    python3 mutate_sheet.py           # 변이  7, 전부 사살되어야 함
    python3 test_figure_regions.py    #  32
    python3 test_raster_regions.py    #  16
    python3 validate_regions.py $FDT_RUN   # 세 제안자 + 합의 → validated_regions.csv
    python3 apply_validated.py $FDT_RUN    # AGREE_2 행과 Human_Choice 행을 검증 상자로 다시 자름
    python3 review_packet.py make $FDT_RUN $FDT_RUN/review   # 사람이 볼 13장 + review_queue.csv
    python3 mutate_census.py          # 변이 11, 전부 사살되어야 함
    python3 mutate_regions.py         # 변이 12, 전부 사살되어야 함
    python3 mutate_roundtrip.py       # 변이  9, 전부 사살되어야 함
    python3 mutate_agreement.py       # 변이 14, 전부 사살되어야 함
    (저장소 루트) python3 test_sheet_blocks.py  #  42
    (저장소 루트) python3 test_crop_truth.py    #  60
    python3 regress_crop.py           # 크롭 회귀 (사람 판정 20건 재현 후 점수)

`build_sheet2.py`는 자기 옆의 `sheet_logic.js`·`sheet_page.js`를 읽습니다
(4차 감사가 지적한 `/tmp/intake` 하드코딩을 없앴습니다). 그리고 시트를 쓸 때 자기가 읽은 두 CSV를 시트 옆에 복사합니다.
3차 감사가 지적한 "639행 HTML 대 604행 CSV" 불일치가 다시 생길 수 없습니다.

## 육안 조사표 — ACCEPTABLE이 무엇을 뜻하지 않는가

`ACCEPTABLE`은 인테이크가 크롭을 **재어** 보고 이상을 찾지 못했다는 뜻입니다.
크롭이 그림을 담고 있다는 뜻이 아닙니다. 상자는 `corpus_intake.figure_bbox`가
잡은 "캡션 위의 빈칸"이고, 그 함수의 주석이 스스로 밝히듯 *"a LOOK HERE for a
contact sheet, not a crop anybody measures from"* — 글자 블록만 보고 잡으며
PDF가 들고 있는 그림 객체는 한 번도 보지 않습니다.

run2에서 열려 있던 440행을 한 장씩 눈으로 본 결과는 이렇습니다.

    그림이 아예 없음 (본문·참고문헌·빈 영역)   171
    잘렸거나 두 그림이 섞임                   136
    표를 그림으로 잡음                        29
    그림이 온전                              104

그래서 `crop_visual_census.csv`가 실행 폴더에 함께 있고, `sheet/census.py`가
그것을 읽어 차단합니다. 규칙은 세 가지입니다.

- 판정은 **크롭의 sha256에 묶입니다.** 크롭을 다시 자르면 그 판정은 이 크롭에
  대한 판정이 아니므로, 결함으로 봤던 그림이 다시 잘린 경우 자동으로 열리지
  않고 `REVIEW_REQUIRED`로 남습니다.
- 에이전트 판정(`Agent_Visual_Code`)은 **행을 빼기만 합니다.** 다시 여는 것은
  사람이 `Human_Verdict`에 `COUNTABLE`이라고 적었을 때뿐입니다.
- 조사표가 **없으면 빌드가 멈춥니다.** 파일 하나가 사라졌다고 336행이 조용히
  다시 열리면 그것은 안전 규칙이 아닙니다. 아직 아무도 보지 않은 코퍼스라면
  `FDT_CENSUS_OPTIONAL=1`로 그렇다고 밝히십시오.

## 왕복 검사 — 크롭은 자기 상자에서 다시 만들어져야 합니다

`roundtrip.py`가 인테이크의 자르기(`pad=8` → 바깥 여백 제거)를 그대로 반복해
크롭 파일과 픽셀 단위로 비교합니다. run2는 644행 중 **642 MATCH, 불일치 0,
NO_CUT 2**입니다. NO_CUT 둘은 두 번째 판독기 행(`_S001`)으로, 크롭은 있는데
쪽 크기가 비어 상자를 페이지에 놓을 수 없었습니다 — `corpus_intake.py`가 그
행들에 기하를 찍지 않던 결함이고, 이번에 고쳤습니다(`test_corpus_intake.py`
264 시나리오).

세 곳에서 씁니다.

- `build_sheet2.py`: 모든 행을 검사해 MISMATCH·NO_CUT이면 막습니다
  (`block_rules.ROUNDTRIP_UNVERIFIABLE`). 크롭이 어느 상자에서 나왔는지 알 수
  없으면 셀 수 없습니다.
- `verify_intake_images.py`: 1단계(파일 무결성)의 세 번째 질문입니다. 디코드는
  파일이 온전함을, 기대 목록은 초안이 부르는 파일임을, 왕복은 그 그림이 상자가
  가리키는 영역임을 증명합니다. 뒤집힌 크롭도 완벽하게 디코드됩니다.
- `validate_regions.py`·`compare_regions.py`: 시작할 때 `roundtrip.selfcheck`로
  세 행을 확인하고, 안 맞으면 돌지 않습니다.

픽스처(`make_fixture.py`)의 크롭도 이제 같은 공식으로 페이지에서 잘라 냅니다.
따로 그린 크롭은 이 검사를 절대 통과하지 못하고, 통과하지 못하는 검사는 작동을
보일 수 없기 때문입니다.

## 세 제안자와 합의 — 언제 셀 수 있는가

그림 영역을 세 방법이 따로 답합니다.

    TEXT    `Figure_BBox`        글자 블록 걸음 (인테이크) — 지금 크롭이 잘린 상자
    PDF     `figure_regions.py`  PDF가 선언한 이미지·곡선·선의 뭉치
    RASTER  `raster_regions.py`  페이지 래스터의 잉크 연결 성분 (본문 글줄은 지운 뒤)

`validate_regions.py`가 셋을 한 표에 놓고 합의를 매깁니다.

    AGREE_3                PDF·RASTER가 같은 곳(IoU ≥ 0.6)을 가리키고, TEXT도 그곳
                           → 지금 크롭으로 셀 수 있음
    AGREE_2_TEXT_DIFFERS   PDF·RASTER는 일치하는데 TEXT가 다름
                           → `apply_validated.py`가 검증 상자로 다시 자름 (ACCEPTABLE 행만)
    DISAGREE · RASTER_ONLY · PDF_ONLY · NONE
                           → REVIEW_REQUIRED. 사람이 `Human_Choice`로 정함

한 방법의 답은 언제나 제안입니다. run2 (2026-09-02): 입력 가능 428행 중
AGREE_3 239 · AGREE_2 55(→ 다시 잘라 열림) · 검토 134. 사람이 먼저 본 12행과
합의 판정을 대조하니 12/12 일치했습니다 — "두 상자 모두 틀림" 9건은 전부
DISAGREE/RASTER_ONLY, "새 상자가 맞음" 3건은 전부 AGREE_2였습니다.

**사람이 푸는 길.** `review_packet.py make`가 검토 대기 행을 12칸씩 그려
(빨강 TEXT · 파랑 PDF · 초록 RASTER) `review_queue.csv`와 함께 냅니다.
`Human_Choice`에 RASTER / PDF / TEXT / BLOCKED 를 적고 `review_packet.py merge`
→ `apply_validated.py` 하면 그 상자로 다시 잘려 열립니다(HUMAN_VALIDATED).
`Agent_Choice`는 에이전트가 제안을 적는 칸이며 **아무것도 열지 못합니다** —
시나리오가 그것을 지킵니다. 판정은 크롭 digest에 묶여, 다시 잘린 뒤의 옛
판정은 merge가 거부합니다.

## 좌표는 위 기준입니다 — 한 번 뒤집으면 조용히 틀립니다

`Figure_BBox`와 `Caption_BBox`는 **래스터와 같은 위 기준**입니다. y는 페이지
위에서 아래로 자랍니다. PDF 자체는 아래 기준(y가 아래에서 위로)이고
`pdfminer`도 그 좌표로 답하므로, 둘을 섞으면 상자가 페이지 한가운데를 축으로
**거울처럼 뒤집힙니다.**

이것이 위험한 이유는 실패하지 않기 때문입니다. 뒤집힌 상자도 페이지 안의
멀쩡한 직사각형이라 그림처럼 보이고, 그 자리에 본문이 있으면 "이 행에는
그림이 없다"는 그럴듯한 결론이 나옵니다. 2026-09-02에 실제로 그렇게 461행을
잘못 판정했고, 그 판정으로 336행을 막았다가 되돌렸습니다.

- `validate_regions.py`의 `to_raster()`가 pdfminer의 답을 한 번만 바꿉니다.
- 그 아래로는(초안·시트·`compare_regions.py`) 전부 위 기준 하나뿐입니다.
- 새 도구를 붙일 때 확인하는 방법: 상자대로 페이지를 잘라 실제 크롭 파일과
  겹쳐 보십시오. 방향이 맞으면 거의 같은 그림이 나옵니다.

## 그림 영역을 PDF에서 직접 찾기 (`figure_regions.py`)

캡션 위 빈칸을 글자 블록으로 잡는 것 말고, PDF가 그리는 것(이미지·곡선·선·
사각형)에서 후보를 만들어 캡션과 짝짓는 두 번째 방법입니다.

    떨어진 패널을 하나로        GAP 안의 조각을 뭉치고, 사이에 글이 없으면
                                REACH_BLANK까지 더 잇습니다.
    거터 너머는 남              두 단 사이 빈 띠를 본문에서 찾아 넘지 않습니다.
    캡션을 함께 배정            페이지의 캡션과 후보를 한 번에 일대일로.
    비슷하면 고르지 않음        1·2위 점수 차가 MARGIN 미만이면 AMBIGUOUS.

`validate_regions.py`가 이것을 코퍼스 전체에 돌려 `validated_regions.csv`에
`Validated_Figure_BBox`와 `Region_Code`를 씁니다. **계수에 바로 쓰지
않습니다.** run2에서 두 방법은 476행에 대해 답을 냈고 겹침 중앙값은 0.59이며,
크게 어긋난 22행을 눈으로 보면 어느 쪽이 맞는지는 반반이었습니다. 지금 이
파일의 쓸모는 "사람이 봐야 할 행"을 99행으로 좁혀 주는 것입니다.

## 배포되지 않는 것

**원문 PDF 102편과 페이지 래스터·크롭.** 출판사 저작물이라 재배포할 수
없습니다. 시트 안의 그림은 폭 300px 확인용 재압축본이며, `corpus_intake.py`를
원문에 돌리면 같은 초안이 나옵니다.

## 크롭 회귀가 무엇을 재는가 (v9.28 기준)

`regress_crop.py`는 더 이상 잉크로 재지 않고, `crop_truth.py`가 들고 있는
**사람이 페이지를 보고 기록한 그림 영역**에 대고 두 값을 냅니다 — 목표 그림을
얼마나 담았는지(covered), 다른 그림을 얼마나 물었는지(intrusion). 그리고 점수를
내기 전에 **자기부터 검사합니다**: 사람이 남긴 20건의 OK/WRONG 판정을 재현하지
못하면 점수를 출력하지 않고 비정상 종료합니다.

**이 하네스는 PDF를 열지 않습니다.** 상자도 페이지 크기도 배포된
`figure_intake_draft.csv`에서 읽습니다. 이전 판들은 두 번 다른 것을 쟀습니다 —
`figure_bbox`를 자기가 다시 계산했고(v9.27에서 수정), 그 뒤에도 페이지 크기를
페이지 위 **텍스트의 범위**로 계산했습니다. 글자는 종이 끝까지 인쇄되지 않으므로
분모가 작아지고 모든 비율이 부풀었습니다(v9.28에서 수정). PDF를 연다는 것은
파일을 찾는다는 뜻이기도 해서 **basename으로** 찾았고, `fulltext.pdf`가 둘이면
한 논문의 상자가 다른 논문의 페이지로 채점될 수 있었습니다. 지금은 열지 않습니다.

같은 `(문서, 라벨, 쪽)`에 **서로 다른 상자**가 두 번 제안되면 파일 순서로 고르지
않고 `AMBIGUOUS_DRAFT_BOX`로 두어 사람에게 후보 둘을 모두 보여줍니다.

## 안전 규칙은 어디에 있나

감사가 눈으로 틀렸다고 판정한 그림들은 `sheet/block_rules.py`의
`STILL_WRONG`에 **문서·라벨·쪽 기준**으로 박혀 있어, 지표가 뭐라 하든 입력이
막힙니다(`build_sheet2.py`가 아니라 여기입니다). `Draft_ID`는 재생성 순번이므로
영구 키로 쓰지 않습니다. 크롭 상태는 `ACCEPTABLE`만 통과하고, 해석할 수 없는
값은 **막습니다** — 읽지 못한 것을 통과시키는 문은 문이 아닙니다.
