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

## 인테이크 본체는 저장소에 있습니다

`corpus_intake.py`와 `test_corpus_intake.py`는 `kernel`·`batch_manifests` 등
저장소 모듈에 의존하므로 여기 복사본을 두면 갈라집니다. 이 시트를 만든 판은

    hpend2373/figure-digitization-triage  v9.28

**공개 커밋 해시는 여기 적지 않습니다.** 지난 판은 컨테이너의 커밋 SHA를
적었는데 그것은 Mac 클론에서 `git apply` 후 다른 SHA로 다시 만들어졌고, 게다가
아직 푸시되지 않아 공개 저장소에 존재하지 않았습니다. 재현 지점은 **버전 태그와
파일 해시**로 잡습니다:

    corpus_intake.py  sha256 = 292a404e6d3af41d2f526f25e270a35ecc32c7dbcea06d5ca47630b535d10aae

`git log --oneline` 에서 `v9.28`로 시작하는 커밋을 받은 뒤 그 파일 해시가 위와
같은지 확인하십시오. 아래 크롭 도구들은 `FDT_REPO`로 그 클론을 가리킵니다.

## 다시 돌리기

    python3 -m pip install pillow numpy pdfminer.six playwright
    python3 -m playwright install chromium
    sudo apt-get install poppler-utils

    $FDT_REPO/corpus_intake.py <PDF...> --out draft --render 150  # 1. 인테이크
    python3 build_sheet2.py                                       # 2. 시트
    node    test_sheet_logic.mjs      #  19
    python3 test_sheet_html.py        #  44
    python3 test_sheet_browser.py     #  28
    python3 mutate_intake.py          # 변이 28, 전부 사살되어야 함
    python3 mutate_sheet.py           # 변이  7, 전부 사살되어야 함
    python3 regress_crop.py           # 크롭 회귀 (사람 판정 18건 재현 후 점수)

`build_sheet2.py`는 자기 옆의 `sheet_logic.js`·`sheet_page.js`를 읽습니다
(4차 감사가 지적한 `/tmp/intake` 하드코딩을 없앴습니다). 그리고 시트를 쓸 때 자기가 읽은 두 CSV를 시트 옆에 복사합니다.
3차 감사가 지적한 "639행 HTML 대 604행 CSV" 불일치가 다시 생길 수 없습니다.

## 배포되지 않는 것

**원문 PDF 102편과 페이지 래스터·크롭.** 출판사 저작물이라 재배포할 수
없습니다. 시트 안의 그림은 폭 300px 확인용 재압축본이며, `corpus_intake.py`를
원문에 돌리면 같은 초안이 나옵니다.

## 크롭 회귀가 무엇을 재는가 (v9.28 기준)

`regress_crop.py`는 더 이상 잉크로 재지 않고, `crop_truth.py`가 들고 있는
**사람이 페이지를 보고 기록한 그림 영역**에 대고 두 값을 냅니다 — 목표 그림을
얼마나 담았는지(covered), 다른 그림을 얼마나 물었는지(intrusion). 그리고 점수를
내기 전에 **자기부터 검사합니다**: 사람이 남긴 18건의 OK/WRONG 판정을 재현하지
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
