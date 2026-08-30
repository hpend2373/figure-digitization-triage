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

    hpend2373/figure-digitization-triage  v9.23

**공개 커밋 해시는 여기 적지 않습니다.** 지난 판은 컨테이너의 커밋 SHA를
적었는데 그것은 Mac 클론에서 `git apply` 후 다른 SHA로 다시 만들어졌고, 게다가
아직 푸시되지 않아 공개 저장소에 존재하지 않았습니다. 재현 지점은 **버전 태그와
파일 해시**로 잡습니다:

    corpus_intake.py  sha256 = 803d00c21e6c2e325f2737b82a0282b0f193a98cb915b7863ec94176e18fe61c

`git log --oneline` 에서 `v9.23`로 시작하는 커밋을 받은 뒤 그 파일 해시가 위와
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
    python3 regress_crop.py           # 크롭 회귀 19건

`build_sheet2.py`는 자기 옆의 `sheet_logic.js`·`sheet_page.js`를 읽습니다
(4차 감사가 지적한 `/tmp/intake` 하드코딩을 없앴습니다). 그리고 시트를 쓸 때 자기가 읽은 두 CSV를 시트 옆에 복사합니다.
3차 감사가 지적한 "639행 HTML 대 604행 CSV" 불일치가 다시 생길 수 없습니다.

## 배포되지 않는 것

**원문 PDF 102편과 페이지 래스터·크롭.** 출판사 저작물이라 재배포할 수
없습니다. 시트 안의 그림은 폭 300px 확인용 재압축본이며, `corpus_intake.py`를
원문에 돌리면 같은 초안이 나옵니다.

## 크롭 회귀가 보장하지 않는 것

`regress_crop.py`는 잉크로 재는 **대리 지표**입니다. 3차 감사는 이 지표가
통과시킨 것 중 5건이 여전히 틀렸음을 눈으로 확인했습니다. 그 5건과 새로 찾은
3건은 `build_sheet2.py`의 `STILL_WRONG`에 **문서·라벨·쪽 기준**으로 박혀
있어, 지표가 뭐라 하든 입력이 막힙니다. `Draft_ID`는 재생성 순번이므로
영구 키로 쓰지 않습니다.
